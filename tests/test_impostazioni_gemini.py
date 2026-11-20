"""Chiavi API nel portale e estrazione con Gemini (API simulata)."""

from __future__ import annotations

import stat
import types

import pytest
from fastapi.testclient import TestClient

from saporesta import estrazione, impostazioni
from saporesta.estrazione import ErroreEstrazione
from tests.test_estrazione_web import PDF_PROVA, estrazione_esempio

CHIAVE_FINTA = "AIzaFINTA-chiave-di-prova-1234"


@pytest.fixture(autouse=True)
def config_temporanea(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPORESTA_CONFIG", str(tmp_path / "cfg" / "impostazioni.json"))
    monkeypatch.setenv("SAPORESTA_DATI", str(tmp_path / "pratiche"))
    for nome in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(nome, raising=False)


# ------------------------------------------------------------------ archivio chiavi

def test_chiavi_salvate_con_permessi_ristretti():
    c = impostazioni.aggiungi("gemini", "Ufficio", CHIAVE_FINTA)
    modo = stat.S_IMODE(impostazioni.percorso().stat().st_mode)
    assert modo == 0o600
    assert impostazioni.chiave_attiva().id == c.id  # la prima diventa attiva
    assert c.mascherata.endswith("1234") and CHIAVE_FINTA not in c.mascherata


def test_attiva_e_rimuovi():
    a = impostazioni.aggiungi("gemini", "A", CHIAVE_FINTA)
    b = impostazioni.aggiungi("anthropic", "B", "sk-ant-finta-5678")
    impostazioni.attiva(b.id)
    assert impostazioni.chiave_attiva().fornitore == "anthropic"
    assert impostazioni.chiave_attiva().modello_effettivo == "claude-opus-5-5"
    impostazioni.rimuovi(b.id)
    assert impostazioni.chiave_attiva().id == a.id


def test_variabile_ambiente_come_riserva(monkeypatch):
    assert impostazioni.chiave_attiva() is None
    monkeypatch.setenv("GEMINI_API_KEY", CHIAVE_FINTA)
    c = impostazioni.chiave_attiva()
    assert c.fornitore == "gemini" and c.da_ambiente


# ------------------------------------------------------------------- Gemini

class GeminiFinto:
    def __init__(self, testo="", motivo="STOP", modelli=()):
        self.chiamate = []
        self._testo, self._motivo, self._modelli = testo, motivo, modelli
        self.models = types.SimpleNamespace(generate_content=self._genera, list=self._elenca)

    def _genera(self, **kw):
        self.chiamate.append(kw)
        return types.SimpleNamespace(
            text=self._testo, prompt_feedback=None,
            candidates=[types.SimpleNamespace(finish_reason=types.SimpleNamespace(name=self._motivo))])

    def _elenca(self):
        return [types.SimpleNamespace(name=f"models/{n}", supported_actions=a) for n, a in self._modelli]


def _chiave_gemini(modello="gemini-modello-prova"):
    return impostazioni.Chiave(id="x", fornitore="gemini", etichetta="prova", valore=CHIAVE_FINTA, modello=modello)


def test_estrazione_gemini(tmp_path):
    pdf = tmp_path / "istanza.pdf"
    pdf.write_bytes(PDF_PROVA.read_bytes())
    finto = GeminiFinto(testo=estrazione_esempio().model_dump_json())
    risultato = estrazione.estrai([pdf], client=finto, chiave=_chiave_gemini())
    assert risultato.protocollo == "100001"
    kw = finto.chiamate[0]
    assert kw["model"] == "gemini-modello-prova"
    assert kw["config"].response_mime_type == "application/json"
    assert kw["config"].response_json_schema["title"] == "Estrazione"
    assert any(getattr(c, "inline_data", None) and c.inline_data.mime_type == "application/pdf" for c in kw["contents"])


@pytest.mark.parametrize("motivo,testo", [("SPII", "dati personali"), ("MAX_TOKENS", "troncata")])
def test_gemini_risposta_bloccata(tmp_path, motivo, testo):
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ErroreEstrazione, match=testo):
        estrazione.estrai([pdf], client=GeminiFinto(motivo=motivo), chiave=_chiave_gemini())


def test_gemini_json_non_valido(tmp_path):
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ErroreEstrazione, match="schema"):
        estrazione.estrai([pdf], client=GeminiFinto(testo='{"protocollo": "1"}'), chiave=_chiave_gemini())


def test_gemini_senza_modello(tmp_path):
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ErroreEstrazione, match="modello"):
        estrazione.estrai([pdf], client=GeminiFinto(), chiave=_chiave_gemini(modello=None))


def test_elenco_modelli_gemini():
    finto = GeminiFinto(modelli=[("gemini-a", ["generateContent"]), ("embedding-x", ["embedContent"]),
                                 ("gemini-b", ["generateContent", "countTokens"])])
    assert estrazione.modelli_disponibili(_chiave_gemini(), client=finto) == ["gemini-a", "gemini-b"]


def test_senza_chiavi_errore_chiaro(tmp_path):
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ErroreEstrazione, match="Impostazioni"):
        estrazione.estrai([pdf])


# ---------------------------------------------------------------------- web

@pytest.fixture
def client(monkeypatch):
    from saporesta.web import app as modulo_app
    modulo_app.MODELLI_VERIFICATI.clear()

    def verifica(chiave):
        if chiave.valore == "sbagliata":
            raise ErroreEstrazione("Chiave Gemini non valida o senza permessi.")
        return ["gemini-modello-a", "gemini-modello-b"]

    monkeypatch.setitem(modulo_app.VERIFICATORE, "funzione", verifica)
    return TestClient(modulo_app.app)


def test_pagina_impostazioni_flusso_completo(client, monkeypatch):
    r = client.post("/impostazioni/aggiungi", data={"fornitore": "gemini", "etichetta": "Ufficio",
                                                    "valore": CHIAVE_FINTA})
    assert "Chiave verificata e salvata" in r.text
    assert CHIAVE_FINTA not in r.text and "1234" in r.text  # mai mostrata per intero
    assert "gemini-modello-b" in r.text and "gratuita" in r.text
    c = impostazioni.carica().chiavi[0]
    r = client.post(f"/impostazioni/{c.id}/modifica", data={"modello": "gemini-modello-b", "a_pagamento": "1"})
    assert impostazioni.chiave_attiva().modello == "gemini-modello-b"
    assert impostazioni.chiave_attiva().a_pagamento
    home = client.get("/").text
    assert "Google Gemini – Ufficio, gemini-modello-b" in home

    # caricamento: l'estrazione usa la chiave attiva
    usate = []
    from saporesta.web import app as modulo_app
    monkeypatch.setitem(modulo_app.ESTRATTORE, "funzione",
                        lambda percorsi: usate.append(impostazioni.chiave_attiva()) or estrazione_esempio())
    r = client.post("/nuova", files=[("documenti_pdf", ("istanza.pdf", PDF_PROVA.read_bytes(), "application/pdf"))],
                    data={"estrai": "1"})
    assert "con Google Gemini – Ufficio" in r.text
    assert usate[0].fornitore == "gemini"


def test_chiave_non_valida_non_salvata(client):
    r = client.post("/impostazioni/aggiungi", data={"fornitore": "gemini", "valore": "sbagliata"})
    assert "Chiave non salvata" in r.text
    assert impostazioni.carica().chiavi == []


def test_home_senza_chiave(client):
    assert "aggiungere una chiave" in client.get("/").text


def test_post_da_altro_sito_rifiutato(client):
    r = client.post("/impostazioni/aggiungi", data={"fornitore": "gemini", "valore": CHIAVE_FINTA},
                    headers={"origin": "https://sito-esterno.example"})
    assert r.status_code == 403
    assert impostazioni.carica().chiavi == []


# ------------------------------------------------------------------- accesso

def test_password_obbligatoria_se_impostata(client, monkeypatch):
    monkeypatch.setenv("SAPORESTA_PASSWORD", "parola-di-prova")
    r = client.get("/impostazioni", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/accesso")
    assert client.post("/impostazioni/aggiungi", data={"fornitore": "gemini", "valore": "x"}).status_code == 401
    r = client.post("/accesso", data={"utente": "admin", "password": "sbagliata", "dopo": "/"})
    assert "Utente o password errati" in r.text
    r = client.post("/accesso", data={"utente": "admin", "password": "parola-di-prova", "dopo": "/impostazioni"})
    assert r.status_code == 200 and "Aggiungi una chiave" in r.text and "Esci" in r.text
    client.post("/esci")
    assert client.get("/", follow_redirects=False).status_code == 303


def test_accesso_non_reindirizza_fuori(client, monkeypatch):
    monkeypatch.setenv("SAPORESTA_PASSWORD", "p")
    r = client.post("/accesso", data={"utente": "admin", "password": "p", "dopo": "//sito-esterno.example"}, follow_redirects=False)
    assert r.headers["location"] == "/"


def test_cookie_manomesso_rifiutato(monkeypatch):
    from saporesta.web import accesso
    monkeypatch.setenv("SAPORESTA_PASSWORD", "parola-di-prova")
    c = accesso.crea_cookie()
    assert accesso.cookie_valido(c)
    assert not accesso.cookie_valido(c[:-1] + ("0" if c[-1] != "0" else "1"))
    assert not accesso.cookie_valido(accesso.crea_cookie(adesso=0))  # scaduto


def test_carta_intestata_caricata(client, tmp_path, monkeypatch):
    from saporesta import modelli_word
    import docx
    monkeypatch.setattr(modelli_word, "CARTELLA_MODELLI", tmp_path / "modelli")
    monkeypatch.setattr(modelli_word, "BASE", tmp_path / "modelli" / "base_carta_intestata.docx")
    d = docx.Document()
    d.sections[0].header.paragraphs[0].text = "INTESTAZIONE DI PROVA"
    d.add_paragraph("testo da scartare")
    sorgente = tmp_path / "ufficio.docx"
    d.save(sorgente)
    r = client.post("/impostazioni/carta-intestata",
                    files={"documento": ("ufficio.docx", sorgente.read_bytes(), "application/octet-stream")})
    assert "Carta intestata caricata" in r.text
    base = docx.Document(str(tmp_path / "modelli" / "base_carta_intestata.docx"))
    assert "INTESTAZIONE DI PROVA" in base.sections[0].header.paragraphs[0].text
    assert "testo da scartare" not in "\n".join(p.text for p in base.paragraphs)
    assert not (tmp_path / "modelli" / "carta_intestata_caricata.docx").exists()
    r = client.post("/impostazioni/carta-intestata", files={"documento": ("x.docx", b"non zip", "application/octet-stream")})
    assert "non è un documento Word" in r.text


# ------------------------------------------------------- PDF grandi, modelli e quote

class GeminiConFile(GeminiFinto):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.caricati, self.cancellati = [], []
        self.files = types.SimpleNamespace(upload=self._carica, get=lambda name: self._file(name, "ACTIVE"),
                                           delete=lambda name: self.cancellati.append(name))

    def _file(self, nome, stato):
        return types.SimpleNamespace(name=nome, state=types.SimpleNamespace(name=stato))

    def _carica(self, file, config):
        self.caricati.append(config["display_name"])
        return self._file(f"files/{len(self.caricati)}", "PROCESSING")


def test_pdf_grandi_con_files_api(tmp_path, monkeypatch):
    monkeypatch.setattr(estrazione, "MAX_INLINE_GEMINI", 10)
    monkeypatch.setattr("time.sleep", lambda s: None)
    pdf = tmp_path / "grande.pdf"
    pdf.write_bytes(PDF_PROVA.read_bytes())
    finto = GeminiConFile(testo=estrazione_esempio().model_dump_json())
    assert estrazione.estrai([pdf], client=finto, chiave=_chiave_gemini()).protocollo == "100001"
    assert finto.caricati == ["grande.pdf"] and finto.cancellati == ["files/1"]
    assert not any(getattr(c, "inline_data", None) for c in finto.chiamate[0]["contents"])


def test_pdf_oltre_50_mb_rifiutato(tmp_path, monkeypatch):
    monkeypatch.setattr(estrazione, "MAX_FILE_GEMINI", 10)
    pdf = tmp_path / "enorme.pdf"
    pdf.write_bytes(PDF_PROVA.read_bytes())
    with pytest.raises(ErroreEstrazione, match="50 MB"):
        estrazione.estrai([pdf], client=GeminiConFile(), chiave=_chiave_gemini())


def test_modelli_gemini_adatti_e_consigliato():
    nomi = ["gemini-2.5-flash-image", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash",
            "gemini-2.5-flash-preview-tts", "gemini-embedding-001", "gemini-3-flash"]
    assert not estrazione.modello_gemini_adatto("gemini-2.5-flash-image")
    assert estrazione.modello_gemini_consigliato(nomi) == "gemini-3-flash"
    finto = GeminiFinto(modelli=[(n, ["generateContent"]) for n in nomi])
    assert "gemini-2.5-flash-image" not in estrazione.modelli_disponibili(_chiave_gemini(), client=finto)


def test_modello_immagini_rifiutato_con_spiegazione(tmp_path):
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ErroreEstrazione, match="non legge documenti"):
        estrazione.estrai([pdf], client=GeminiFinto(), chiave=_chiave_gemini("gemini-2.5-flash-image"))


@pytest.mark.parametrize("messaggio,quota,atteso", [
    ("Quota exceeded ... limit: 0", "GenerateContentRequestsPerDayPerProjectPerModel-FreeTier", "quota zero"),
    ("Quota exceeded", "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "giornaliera"),
    ("Quota exceeded", "GenerateContentInputTokensPerModelPerMinute-FreeTier", "token al minuto"),
])
def test_messaggi_quota_gemini(messaggio, quota, atteso):
    from google.genai import errors
    risposta = {"error": {"code": 429, "message": messaggio, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "30s"}]}}
    e = errors.ClientError(429, risposta)
    assert atteso in str(estrazione._errore_gemini(e))


def test_verifica_sostituisce_modello_non_adatto(client):
    c = impostazioni.aggiungi("gemini", "Ufficio", CHIAVE_FINTA, modello="gemini-2.5-flash-image")
    from saporesta.web import app as modulo_app
    modulo_app.VERIFICATORE["funzione"] = lambda chiave: ["gemini-2.5-flash", "gemini-2.5-flash-image"]
    r = client.post(f"/impostazioni/{c.id}/verifica")
    assert "impostato gemini-2.5-flash" in r.text
    assert impostazioni.trova(c.id).modello == "gemini-2.5-flash"


# ----------------------------------------------------------- Gemini sovraccarico

class GeminiSovraccarico(GeminiFinto):
    """Risponde 503 per i primi `errori` tentativi sul modello scelto (sempre, se errori=None)."""

    def __init__(self, errori, **kw):
        super().__init__(**kw)
        self._errori = errori

    def _genera(self, **kw):
        from google.genai import errors
        self.chiamate.append(kw)
        precedenti = sum(1 for c in self.chiamate if c["model"] == kw["model"]) - 1
        if kw["model"] == "gemini-modello-prova" and (self._errori is None or precedenti < self._errori):
            raise errors.ServerError(503, {"error": {"code": 503, "message": "The model is overloaded.",
                                                     "status": "UNAVAILABLE"}})
        self.chiamate.pop()
        return super()._genera(**kw)


@pytest.fixture
def senza_attese(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)


def test_503_si_riprova(tmp_path, senza_attese):
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    finto = GeminiSovraccarico(2, testo=estrazione_esempio().model_dump_json())
    assert estrazione.estrai([pdf], client=finto, chiave=_chiave_gemini()).protocollo == "100001"
    assert [c["model"] for c in finto.chiamate] == ["gemini-modello-prova"] * 3


def test_503_persistente_passa_al_modello_di_riserva(tmp_path, senza_attese):
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    finto = GeminiSovraccarico(None, testo=estrazione_esempio().model_dump_json(),
                               modelli=[("gemini-modello-prova", ["generateContent"]),
                                        ("gemini-2.5-flash", ["generateContent"]),
                                        ("gemini-2.5-flash-image", ["generateContent"])])
    assert estrazione.estrai([pdf], client=finto, chiave=_chiave_gemini()).protocollo == "100001"
    assert finto.chiamate[-1]["model"] == "gemini-2.5-flash"


def test_503_senza_riserva_messaggio_chiaro(tmp_path, senza_attese):
    pdf = tmp_path / "i.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ErroreEstrazione, match="sovraccarico"):
        estrazione.estrai([pdf], client=GeminiSovraccarico(None), chiave=_chiave_gemini())
