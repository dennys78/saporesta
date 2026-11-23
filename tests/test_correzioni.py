"""Le correzioni dell'istruttore prevalgono sui dati letti dai PDF."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from saporesta import archivio, estrazione
from saporesta.cli import carica
from tests.test_estrazione_web import LettoreModulo, _multi, estrazione_esempio

CASI = Path(__file__).resolve().parents[1] / "casi"
PDF = Path(__file__).resolve().parent / "dati" / "documento_prova.pdf"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPORESTA_DATI", str(tmp_path / "pratiche"))
    monkeypatch.setenv("SAPORESTA_CONFIG", str(tmp_path / "cfg" / "impostazioni.json"))
    monkeypatch.delenv("SAPORESTA_PASSWORD", raising=False)
    from saporesta.web import app as modulo_app
    return TestClient(modulo_app.app)


def _pratica(nome="esempio_fustaia", dubbi=()):
    id_ = archivio.crea("prova", [("d.pdf", PDF.read_bytes())])
    archivio.salva(id_, carica(CASI / f"{nome}.yaml"))
    archivio.salva_estrazione(id_, {}, list(dubbi))
    return id_


def _invia(client, id_, modifiche: dict, extra=()):
    lettore = LettoreModulo("modulo")
    lettore.feed(client.get(f"/pratica/{id_}").text)
    valori = [(k, modifiche.get(k, v)) for k, v in lettore.valori] + list(extra)
    return client.post(f"/pratica/{id_}", data=_multi(valori))


def test_discordanza_risolta_con_valore_accertato(client):
    id_ = _pratica()
    pagina = client.get(f"/pratica/{id_}").text
    assert "Dati discordanti tra i documenti" in pagina
    r = _invia(client, id_, {"istruttoria.dati_accertati.0.valore": "51,97",
                             "istruttoria.dati_accertati.0.nota": "conta del piedilista"})
    assert "Salvato" in r.text
    p = archivio.carica(id_)
    assert p.istruttoria.dati_accertati[0].valore == "51,97"
    from saporesta.verifiche import Livello, esegui
    esiti = {e.codice: e for e in esegui(p).esiti}
    e = esiti["ris.volume prelevato (m³)"]
    assert e.livello is Livello.INFO and "accertato il valore 51,97 – conta del piedilista" in e.messaggio
    assert not any("Allineamento del dato" in i for i in esegui(p).integrazioni)


def test_dubbio_chiuso_quando_il_campo_viene_corretto(client):
    id_ = _pratica(dubbi=[
        {"campo": "scheda.totale_taglio.volume", "motivo": "Volume diverso tra i documenti."},
        {"campo": "superficie_intervento_ha", "motivo": "Superficie poco leggibile."},
        {"campo": "comune", "motivo": "Comune da confermare."},
    ])
    r = _invia(client, id_, {"scheda.totale_taglio.volume": "51.5"}, extra=[("_dubbio", "2")])
    assert "Chiusi 2 dubbi" in r.text
    dubbi = archivio.estrazione(id_)["dubbi"]
    assert dubbi[0]["risolto"] and "corretto" in dubbi[0]["come"]
    assert not dubbi[1].get("risolto")  # superficie non toccata: resta aperto
    assert dubbi[2]["risolto"] and "controllato" in dubbi[2]["come"]
    pagina = client.get(f"/pratica/{id_}").text
    assert "Da controllare sui documenti (1)" in pagina
    assert "Dubbi dell&#39;estrazione chiusi (2)" in pagina or "Dubbi dell'estrazione chiusi (2)" in pagina
    # il campo corretto non è più evidenziato, quello aperto sì
    assert pagina.count("⚠ Superficie poco leggibile.") == 1
    assert "⚠ Volume diverso tra i documenti." not in pagina


def test_verifiche_usano_il_valore_corretto(client):
    id_ = _pratica()
    _invia(client, id_, {"scheda.totale_taglio.volume": "51.5", "scheda.assortimenti.1.volume_m3": "20"})
    from saporesta.verifiche import esegui
    p = archivio.carica(id_)
    assert p.scheda.totale_taglio.volume == 51.5
    codici = {e.codice: e for e in esegui(p).esiti}
    assert "a023.assortimenti" not in codici  # 31,5 + 20 = 51,5: discordanza superata
    assert "a023.massa.intera superficie" in codici  # la massa va rivalutata sul nuovo volume


def test_correzioni_rispetto_all_estrazione(client, tmp_path):
    e = estrazione_esempio()
    id_ = archivio.crea("e", [("d.pdf", PDF.read_bytes())])
    archivio.salva_dati(id_, estrazione.in_pratica(e))
    grezza = e.model_dump()
    grezza.pop("classi_diametriche")  # estrazione salvata con uno schema precedente
    archivio.salva_estrazione(id_, grezza, [])
    _invia(client, id_, {"inquadramento.superficie_intervento_ha": "20"})
    pagina = client.get(f"/pratica/{id_}").text
    assert "Dati corretti rispetto ai PDF (1)" in pagina
    assert "Superficie intervento (ha)" in pagina and "21,5" in pagina
    client.post(f"/pratica/{id_}/genera", data={"tutti": "1"})
    rapporto = next(archivio.cartella_documenti(id_).glob("rapporto_*.docx"))
    d = Document(str(rapporto))
    celle = [c.text for t in d.tables for r in t.rows for c in r.cells]
    assert "Letto dai PDF" in celle and "21,5" in celle and "20" in celle
