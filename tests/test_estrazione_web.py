"""Estrazione (con API simulata) e applicazione web di revisione."""

from __future__ import annotations

import types
from html.parser import HTMLParser
from pathlib import Path
from typing import get_args, get_origin

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import BaseModel

from saporesta import archivio, estrazione
from saporesta.cli import carica
from saporesta.estrazione import EPersona, Estrazione, ErroreEstrazione
from saporesta.models import Pratica

PDF_PROVA = Path(__file__).resolve().parent / "dati" / "documento_prova.pdf"
CASI = Path(__file__).resolve().parents[1] / "casi"


# ------------------------------------------------------------------- fixture

def vuoto(modello: type[BaseModel]) -> dict:
    """Istanza 'tutto null' di un modello di estrazione (tutti i campi sono obbligatori)."""
    d = {}
    for nome, info in modello.model_fields.items():
        a = info.annotation
        if get_origin(a) is list:
            d[nome] = []
        elif isinstance(a, type) and issubclass(a, BaseModel):
            d[nome] = vuoto(a)
        else:
            d[nome] = None
    return d


def estrazione_esempio() -> Estrazione:
    d = vuoto(Estrazione)
    d.update(
        protocollo="100001", data_protocollo="2026-10-26", data_istanza="2026-09-20",
        riferimento_normativo_modulo="PMPF D.G.R. n. 218 del 20.05.2011",
        richiedente={**vuoto(EPersona), "cognome": "Rossi", "nome": "Mario", "data_nascita": "1970-01-01",
                     "comune_residenza": "Crotone", "provincia": "KR", "indirizzo": "Via Esempio", "civico": "1"},
        titolo_richiedente="proprietario", tipo_intervento="ceduo", sottotipi=["senza_matricine"],
        eta_min=8, eta_max=15, anno_ultimo_taglio=2018, comune="Crotone", provincia="KR", localita="Esempio",
        particelle=[{"foglio": "6", "particelle": ["115", "244", "247"]}],
        superficie_catastale_ha=26.1481, superficie_intervento_ha=21.5, vincolo_art54=True, versamento_importo=57.0,
        documenti_presenti=[{"voce": "istanza", "file": "istanza.pdf", "pagine": "1-4"}],
        dubbi=[{"campo": "specie", "motivo": "La specie prevalente non è indicata nel modulo."}],
    )
    return Estrazione.model_validate(d)


class ClienteFinto:
    def __init__(self, risposta):
        self.chiamate = []
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(parse=self._parse))
        self._risposta = risposta

    def _parse(self, **kwargs):
        self.chiamate.append(kwargs)
        return self._risposta


# --------------------------------------------------------------- estrazione

def test_estrai_invia_pdf_e_schema(tmp_path):
    pdf = tmp_path / "istanza.pdf"
    pdf.write_bytes(b"%PDF-1.4 finto")
    cliente = ClienteFinto(types.SimpleNamespace(stop_reason="end_turn", parsed_output=estrazione_esempio()))
    risultato = estrazione.estrai([pdf], client=cliente)
    assert risultato.protocollo == "100001"
    kw = cliente.chiamate[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_format"] is Estrazione
    blocchi = kw["messages"][0]["content"]
    assert any(b["type"] == "document" and b["source"]["media_type"] == "application/pdf" for b in blocchi)


def test_estrai_rifiuto(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF")
    cliente = ClienteFinto(types.SimpleNamespace(stop_reason="refusal", parsed_output=None))
    with pytest.raises(ErroreEstrazione):
        estrazione.estrai([pdf], client=cliente)


def test_conversione_in_pratica_e_verifiche():
    e = estrazione_esempio()
    dati = estrazione.in_pratica(e)
    p = Pratica.model_validate(dati)
    assert p.vincoli.vincolo_art54 and p.inquadramento.superficie_intervento_ha == 21.5
    assert p.istruttoria.checklist["istanza"].stato.value == "si"
    from saporesta.verifiche import esegui
    assert any(x.codice == "ced.tagliate" for x in esegui(p).esiti)


def test_dati_obbligatori_mancanti_diventano_dubbi():
    d = vuoto(Estrazione)
    e = Estrazione.model_validate(d)
    campi = {x["campo"] for x in estrazione.dubbi_dopo_conversione(e)}
    assert {"protocollo", "comune", "superficie_intervento_ha", "richiedente"} <= campi
    estrazione.in_pratica(e)  # non deve fallire: i mancanti diventano segnaposto


# ----------------------------------------------------------------------- web

class LettoreModulo(HTMLParser):
    """Raccoglie i valori che il browser invierebbe per il form con id dato."""

    def __init__(self, id_modulo: str):
        super().__init__()
        self.id = id_modulo
        self.dentro = False
        self.template = 0
        self.valori: list[tuple[str, str]] = []
        self._select = None
        self._opzione_sel = None
        self._textarea = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.dentro = a.get("id") == self.id
        if not self.dentro:
            return
        if tag == "template":
            self.template += 1
        if self.template:
            return
        if tag == "input" and a.get("name"):
            tipo = a.get("type", "text")
            if tipo in ("checkbox", "radio"):
                if "checked" in a:
                    self.valori.append((a["name"], a.get("value", "on")))
            elif tipo != "file":
                self.valori.append((a["name"], a.get("value", "")))
        elif tag == "select":
            self._select, self._opzione_sel = a.get("name"), ""
        elif tag == "option" and self._select and "selected" in a:
            self._opzione_sel = a.get("value", "")
        elif tag == "textarea":
            self._textarea = [a.get("name"), ""]

    def handle_endtag(self, tag):
        if tag == "template":
            self.template -= 1
        elif tag == "select" and self._select:
            self.valori.append((self._select, self._opzione_sel))
            self._select = None
        elif tag == "textarea" and self._textarea:
            self.valori.append(tuple(self._textarea))
            self._textarea = None
        elif tag == "form":
            self.dentro = False

    def handle_data(self, data):
        if self._textarea:
            self._textarea[1] += data


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPORESTA_DATI", str(tmp_path))
    monkeypatch.setenv("SAPORESTA_CONFIG", str(tmp_path / "config" / "impostazioni.json"))
    for nome in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(nome, raising=False)
    from saporesta.web import app as modulo_app
    monkeypatch.setitem(modulo_app.ESTRATTORE, "funzione", lambda percorsi: estrazione_esempio())
    return TestClient(modulo_app.app)


def test_caricamento_con_estrazione(client):
    r = client.post("/nuova", files=[("documenti_pdf", ("istanza.pdf", PDF_PROVA.read_bytes(), "application/pdf"))],
                    data={"etichetta": "Rossi", "estrai": "1"})
    assert r.status_code == 200
    assert "Dati estratti dai PDF" in r.text
    assert "RICHIESTA INTEGRAZIONI" in r.text
    assert "La specie prevalente non è indicata" in r.text
    assert 'class="gruppo lista dubbio"' in r.text  # la lista delle specie è evidenziata
    id_ = archivio.elenco()[0].id
    assert client.get(f"/pratica/{id_}/pdf/istanza.pdf").headers["content-type"] == "application/pdf"


def test_rifiuta_file_non_pdf(client):
    r = client.post("/nuova", files=[("documenti_pdf", ("nota.txt", b"ciao", "text/plain"))], data={})
    assert "non è un PDF" in r.text


@pytest.mark.parametrize("caso", ["esempio_fustaia", "esempio_ceduo"])
def test_modulo_andata_e_ritorno(client, caso):
    """Il modulo, reinviato senza modifiche, deve riprodurre esattamente la pratica."""
    originale = carica(CASI / f"{caso}.yaml")
    id_ = archivio.crea(caso, [("doc.pdf", b"%PDF-1.4")])
    archivio.salva(id_, originale)
    pagina = client.get(f"/pratica/{id_}").text
    lettore = LettoreModulo("modulo")
    lettore.feed(pagina)
    r = client.post(f"/pratica/{id_}", data=_multi(lettore.valori))
    assert r.status_code == 200 and "Dati da correggere" not in r.text, r.text[:2000]
    ricaricata = archivio.carica(id_)
    assert ricaricata.model_dump() == originale.model_dump()


def _multi(valori):
    """httpx accetta liste per i nomi ripetuti."""
    d: dict[str, list[str]] = {}
    for k, v in valori:
        d.setdefault(k, []).append(v)
    return d


def test_modifica_e_genera(client):
    originale = carica(CASI / "esempio_fustaia.yaml")
    id_ = archivio.crea("b", [("doc.pdf", b"%PDF-1.4")])
    archivio.salva(id_, originale)
    lettore = LettoreModulo("modulo")
    lettore.feed(client.get(f"/pratica/{id_}").text)
    valori = [(k, "0.7" if k == "inquadramento.superficie_intervento_ha" else v) for k, v in lettore.valori]
    client.post(f"/pratica/{id_}", data=_multi(valori))
    assert archivio.carica(id_).inquadramento.superficie_intervento_ha == 0.7
    r = client.post(f"/pratica/{id_}/genera", data={"tutti": "1"})
    assert "Generati" in r.text
    nomi = {p.name for p in archivio.cartella_documenti(id_).iterdir()}
    assert "autorizzazione_100002.docx" in nomi
    assert client.get(f"/pratica/{id_}/documenti/autorizzazione_100002.docx").status_code == 200


def test_errore_di_validazione_non_salva(client):
    originale = carica(CASI / "esempio_ceduo.yaml")
    id_ = archivio.crea("n", [("doc.pdf", b"%PDF-1.4")])
    archivio.salva(id_, originale)
    lettore = LettoreModulo("modulo")
    lettore.feed(client.get(f"/pratica/{id_}").text)
    valori = [(k, "abc" if k == "inquadramento.superficie_intervento_ha" else v) for k, v in lettore.valori]
    r = client.post(f"/pratica/{id_}", data=_multi(valori))
    assert "Dati da correggere" in r.text and "numero non valido" in r.text
    assert yaml.safe_load((archivio.radice() / id_ / "pratica.yaml").read_text())["inquadramento"]["superficie_intervento_ha"] == 21.5


def test_elimina_pratiche_selezionate(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPORESTA_DATI", str(tmp_path / "pratiche"))
    monkeypatch.delenv("SAPORESTA_PASSWORD", raising=False)
    monkeypatch.setenv("SAPORESTA_CONFIG", str(tmp_path / "cfg" / "impostazioni.json"))
    from saporesta.web.app import app
    client = TestClient(app)
    ids = [archivio.crea(f"prova {i}", [("a.pdf", PDF_PROVA.read_bytes())]) for i in range(3)]
    r = client.post("/pratiche/elimina", data={"id": ids[:2]})
    assert "Eliminate 2 pratiche" in r.text
    assert [v.id for v in archivio.elenco()] == [ids[2]]
    r = client.post(f"/pratica/{ids[2]}/elimina")
    assert "Pratica eliminata" in r.text and archivio.elenco() == []
    assert "Nessuna pratica selezionata" in client.post("/pratiche/elimina", data={}).text


def test_ritenta_acquisizione_dalla_pratica(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPORESTA_DATI", str(tmp_path / "pratiche"))
    monkeypatch.setenv("SAPORESTA_CONFIG", str(tmp_path / "cfg" / "impostazioni.json"))
    monkeypatch.delenv("SAPORESTA_PASSWORD", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-finta")
    from saporesta.web import app as modulo_app
    client = TestClient(modulo_app.app)
    id_ = archivio.crea("novello", [("istanza.pdf", PDF_PROVA.read_bytes())])

    def guasto(percorsi):
        raise ErroreEstrazione("Gemini è sovraccarico (503).")
    monkeypatch.setitem(modulo_app.ESTRATTORE, "funzione", guasto)
    r = client.get(f"/pratica/{id_}")
    assert "Dati non ancora acquisiti" in r.text and "Acquisisci con l&#39;AI" in r.text
    r = client.post(f"/pratica/{id_}/estrai")
    assert "Estrazione non riuscita" in r.text and archivio.dati(id_) is None

    monkeypatch.setitem(modulo_app.ESTRATTORE, "funzione", lambda percorsi: estrazione_esempio())
    r = client.post(f"/pratica/{id_}/estrai")
    assert "Dati estratti dai PDF" in r.text and "Ripeti acquisizione" in r.text
    assert archivio.dati(id_)["protocollo"] == "100001"
    assert client.post("/pratica/inesistente/estrai").status_code == 404
