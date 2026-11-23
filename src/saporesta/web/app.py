"""Applicazione web locale per caricare i PDF, rivedere i dati estratti e generare i documenti.

Avvio:  uv run saporesta web   (poi aprire http://127.0.0.1:8000)
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from pydantic import ValidationError

from .. import archivio, documenti, estrazione, impostazioni, modelli_word
from . import accesso
from ..models import Intervento, Istruttoria, Pratica
from ..verifiche import Livello, esegui
from .moduli import Rendering, analizza, checklist_html, da_modulo, html_errori, unisci

CARTELLA = Path(__file__).parent
modelli = Jinja2Templates(directory=str(CARTELLA / "templates"))
modelli.env.globals["accesso_attivo"] = accesso.attivo

app = FastAPI(title="Saporesta – istruttoria A02", docs_url=None, redoc_url=None)

# Funzioni sostituibili nei test
ESTRATTORE = {"funzione": estrazione.estrai}
VERIFICATORE = {"funzione": estrazione.modelli_disponibili}
MODELLI_VERIFICATI: dict[str, list[str]] = {}  # id chiave -> modelli trovati con l'ultima verifica


LIBERI = {"/accesso", "/esci"}


@app.middleware("http")
async def richiede_accesso(request: Request, call_next):
    """Con SAPORESTA_PASSWORD impostata, ogni pagina richiede l'accesso."""
    if accesso.attivo() and request.url.path not in LIBERI \
            and not accesso.cookie_valido(request.cookies.get(accesso.NOME_COOKIE)):
        if request.method == "GET":
            return _vai("/accesso", dopo=request.url.path)
        return PlainTextResponse("Accesso richiesto.", status_code=401)
    return await call_next(request)


@app.middleware("http")
async def stessa_origine(request: Request, call_next):
    """Rifiuta i POST inviati da altri siti aperti nel browser (protezione CSRF dell'app locale)."""
    if request.method == "POST":
        origine = request.headers.get("origin") or request.headers.get("referer")
        if origine and urlparse(origine).netloc != request.headers.get("host"):
            return PlainTextResponse("Richiesta proveniente da un altro sito: rifiutata.", status_code=403)
    return await call_next(request)

SEZIONI_PRATICA = [
    ("Protocollo e richiedente", ["protocollo", "data_protocollo", "protocolli_integrazione", "data_istanza",
                                  "riferimento_normativo_modulo", "titolo_richiedente", "ente_pubblico", "classe_eutr",
                                  "richiedente"]),
    ("Tecnico progettista", ["tecnico"]),
    ("Intervento", ["intervento"]),
    ("Inquadramento territoriale", ["inquadramento"]),
    ("Vincoli dichiarati", ["vincoli"]),
    ("Scheda tecnica A02.3", ["scheda"]),
    ("Tavola di cubatura e classi diametriche", ["cubatura"]),
    ("Tagliate e martellata", ["tagliate", "martellata"]),
    ("Versamento e coerenza tra documenti", ["versamento", "riscontri"]),
]
SEZIONI_ISTRUTTORIA = [
    ("Verifiche d'ufficio", ["verifiche_ufficio"]),
    ("Esito, prescrizioni e firme", ["riferimento_vinca", "integrazioni_aggiuntive", "prescrizioni_aggiuntive",
                                     "note_verbale", "validita_mesi", "data_documento", "firmatari",
                                     "destinatari_conoscenza"]),
]


def _vai(percorso: str, **parametri: str) -> RedirectResponse:
    query = urlencode({k: v for k, v in parametri.items() if v})
    return RedirectResponse(f"{percorso}{'?' + query if query else ''}", status_code=303)


def _404(funzione):
    try:
        return funzione()
    except archivio.PraticaNonTrovata as e:
        raise HTTPException(404, "Pratica o file non trovato") from e


def _campi_dubbi(id_: str) -> dict[str, str]:
    """Dubbi dell'estrazione tradotti nei percorsi del modulo."""
    est = archivio.estrazione(id_) or {}
    alias = {
        "tipo_intervento": "intervento.tipo", "sottotipi": "intervento.sottotipi", "specie": "intervento.popolamento.specie",
        "eta_min": "intervento.popolamento.eta_min", "eta_max": "intervento.popolamento.eta_max",
        "anno_ultimo_taglio": "intervento.popolamento.anno_ultimo_taglio",
        "versamento_importo": "versamento.importo_totale",
        "tavola_cubatura": "cubatura.tavola", "tavola_cubatura_testo": "cubatura.tavola_dichiarata",
        "tariffa_tacal": "cubatura.tariffa", "classi_diametriche": "cubatura.classi",
    }
    risultato: dict[str, str] = {}
    for d in est.get("dubbi", []):
        campo = alias.get(d["campo"], d["campo"])
        risultato[campo] = (risultato.get(campo, "") + " " + d["motivo"]).strip()
    return risultato


def _modulo(id_: str, dati: dict, pratica: Pratica | None) -> Markup:
    r = Rendering(_campi_dubbi(id_))
    parti = []
    for titolo, campi in SEZIONI_PRATICA:
        tipo, sottomodello = analizza(Pratica.model_fields[campi[0]].annotation)
        if len(campi) == 1 and tipo == "model":
            # sezione dedicata a un solo gruppo: niente doppio titolo
            interno = r.campi(sottomodello, (dati or {}).get(campi[0]) or {}, campi[0])
        else:
            interno = r.campi(Pratica, dati, "", solo=campi)
        parti.append(f'<section class="sezione"><h2>{titolo}</h2><div class="griglia">{interno}</div></section>')
    parti.append(f'<section class="sezione"><h2>Checklist documentale</h2>{checklist_html(pratica, dati)}</section>')
    istr = (dati or {}).get("istruttoria") or {}
    for titolo, campi in SEZIONI_ISTRUTTORIA:
        parti.append(f'<section class="sezione"><h2>{titolo}</h2><div class="griglia">'
                     f'{r.campi(Istruttoria, istr, "istruttoria", solo=campi)}</div></section>')
    return Markup("".join(parti))


def _pagina(request: Request, id_: str, dati: dict | None, errori: list[str] | None = None, messaggio: str = ""):
    dati = dati or {}
    pratica = None
    risultato = None
    if not errori:
        try:
            pratica = Pratica.model_validate(dati)
            risultato = esegui(pratica)
        except ValidationError as e:
            errori = html_errori(e.errors())
    gruppi = []
    if risultato:
        for livello in [Livello.NON_CONFORME, Livello.DA_VERIFICARE, Livello.ATTENZIONE, Livello.INFO, Livello.OK]:
            esiti = risultato.per_livello(livello)
            if esiti:
                gruppi.append((livello, esiti))
    cartella_doc = archivio.cartella_documenti(id_)
    return modelli.TemplateResponse(request, "pratica.html", {
        "id": id_,
        "pdf": [p.name for p in archivio.pdf(id_)],
        "modulo": _modulo(id_, dati, pratica),
        "errori": errori or [],
        "messaggio": messaggio,
        "risultato": risultato,
        "gruppi": gruppi,
        "dubbi": (archivio.estrazione(id_) or {}).get("dubbi", []),
        "documenti": sorted(p.name for p in cartella_doc.iterdir() if p.is_file()),
        "titolo": next((v.titolo for v in archivio.elenco() if v.id == id_), id_),
    })


# ------------------------------------------------------------------------ rotte

@app.get("/", response_class=HTMLResponse)
def home(request: Request, errore: str = ""):
    return modelli.TemplateResponse(request, "home.html", {
        "pratiche": archivio.elenco(), "errore": errore, "chiave": impostazioni.chiave_attiva()})


@app.post("/nuova")
async def nuova(request: Request, documenti_pdf: list[UploadFile], etichetta: str = Form(""),
                estrai: str = Form("")):
    file = []
    for f in documenti_pdf:
        if not f.filename:
            continue
        contenuto = await f.read()
        if not contenuto.startswith(b"%PDF"):
            return _vai("/", errore=f"Il file {f.filename} non è un PDF")
        file.append((f.filename, contenuto))
    if not file:
        return _vai("/", errore="Nessun PDF caricato")
    id_ = archivio.crea(etichetta or Path(file[0][0]).stem, file)
    messaggio = ""
    if estrai:
        chiave = impostazioni.chiave_attiva()
        try:
            e = ESTRATTORE["funzione"](archivio.pdf(id_))
            dati = estrazione.in_pratica(e)
            archivio.salva_dati(id_, dati)
            archivio.salva_estrazione(id_, e.model_dump(), estrazione.dubbi_dopo_conversione(e),
                                      chiave.descrizione if chiave else "")
            messaggio = (f"Dati estratti dai PDF{' con ' + chiave.descrizione if chiave else ''}: controllarli, "
                         "soprattutto i campi evidenziati, poi salvare.")
        except estrazione.ErroreEstrazione as err:
            messaggio = f"Estrazione non riuscita: {err} Compilare i dati a mano."
        except ValidationError as err:
            messaggio = "I dati estratti non sono validi: " + "; ".join(html_errori(err.errors()))
    return _vai(f"/pratica/{id_}", messaggio=messaggio)


@app.get("/pratica/{id_}", response_class=HTMLResponse)
def pratica(request: Request, id_: str, messaggio: str = ""):
    dati = _404(lambda: archivio.dati(id_))
    if dati is None:
        dati = {"intervento": Intervento(tipo="ceduo").model_dump(mode="json")}
        return _pagina(request, id_, dati, errori=["Pratica senza dati: compilare il modulo e salvare."],
                       messaggio=messaggio)
    return _pagina(request, id_, dati, messaggio=messaggio)


@app.post("/pratica/{id_}", response_class=HTMLResponse)
async def salva(request: Request, id_: str):
    vecchi = _404(lambda: archivio.dati(id_))
    modulo = await request.form()
    nuovi = unisci(vecchi, da_modulo(list(modulo.multi_items())))
    try:
        p = Pratica.model_validate(nuovi)
    except ValidationError as e:
        return _pagina(request, id_, nuovi, errori=html_errori(e.errors()),
                       messaggio="Dati non salvati: correggere i campi indicati.")
    archivio.salva(id_, p)
    return _vai(f"/pratica/{id_}", messaggio="Salvato.")


@app.post("/pratica/{id_}/genera")
def genera(id_: str, tutti: str = Form("")):
    p = _404(lambda: archivio.carica(id_))
    r = esegui(p)
    cartella = archivio.cartella_documenti(id_)
    vecchio = cartella / "rapporto_istruttoria.md"
    vecchio.unlink(missing_ok=True)
    documenti.genera_rapporto(p, r, cartella / f"rapporto_istruttoria_{p.protocollo or 'bozza'}.docx")
    tipi = list(documenti.MODELLI) if tutti else documenti.documenti_per_proposta(r)
    for tipo in tipi:
        nome = documenti.MODELLI[tipo].replace(".docx", f"_{p.protocollo or 'bozza'}.docx")
        documenti.genera(p, tipo, cartella / nome, r)
    msg = (f"Generati: {', '.join(tipi)}." if tipi
           else "Nessun documento previsto: completare i controlli o scegliere 'tutte le bozze'.")
    return _vai(f"/pratica/{id_}", messaggio=msg)


@app.get("/pratica/{id_}/pdf/{nome}")
def mostra_pdf(id_: str, nome: str):
    return FileResponse(_404(lambda: archivio.file_pdf(id_, nome)), media_type="application/pdf",
                        content_disposition_type="inline")


@app.get("/pratica/{id_}/documenti/{nome}")
def scarica(id_: str, nome: str):
    percorso = _404(lambda: archivio.file_documento(id_, nome))
    return FileResponse(percorso, filename=percorso.name)


@app.post("/pratica/{id_}/elimina")
def elimina(id_: str):
    _404(lambda: archivio.elimina(id_))
    return _vai("/")


# ------------------------------------------------------------------ impostazioni

def _pagina_impostazioni(request: Request, messaggio: str = "", errore: str = ""):
    imp = impostazioni.carica()
    return modelli.TemplateResponse(request, "impostazioni.html", {
        "chiavi": imp.chiavi, "attiva": imp.chiave_attiva, "modelli_verificati": MODELLI_VERIFICATI,
        "nomi": impostazioni.NOMI_FORNITORE, "messaggio": messaggio, "errore": errore,
        "file": str(impostazioni.percorso()), "carta_intestata": modelli_word.ha_carta_intestata(), "da_ambiente": (lambda c: c if c and c.da_ambiente else None)(
            impostazioni.chiave_attiva()),
    })


@app.get("/impostazioni", response_class=HTMLResponse)
def pagina_impostazioni(request: Request, messaggio: str = "", errore: str = ""):
    return _pagina_impostazioni(request, messaggio, errore)


@app.post("/impostazioni/aggiungi")
def aggiungi_chiave(fornitore: str = Form(...), valore: str = Form(...), etichetta: str = Form(""),
                    a_pagamento: str = Form("")):
    if fornitore not in impostazioni.NOMI_FORNITORE:
        return _vai("/impostazioni", errore="Fornitore non valido.")
    if not valore.strip():
        return _vai("/impostazioni", errore="Inserire la chiave.")
    provvisoria = impostazioni.Chiave(id="prova", fornitore=fornitore, etichetta=etichetta, valore=valore.strip())
    try:
        trovati = VERIFICATORE["funzione"](provvisoria)
    except estrazione.ErroreEstrazione as e:
        return _vai("/impostazioni", errore=f"Chiave non salvata: {e}")
    chiave = impostazioni.aggiungi(fornitore, etichetta, valore, a_pagamento=bool(a_pagamento))
    MODELLI_VERIFICATI[chiave.id] = trovati
    msg = "Chiave verificata e salvata."
    if fornitore == "gemini":
        msg += " Scegliere ora il modello Gemini da usare."
    return _vai("/impostazioni", messaggio=msg)


@app.post("/impostazioni/{id_}/verifica")
def verifica_chiave(id_: str):
    try:
        chiave = impostazioni.trova(id_)
    except KeyError as e:
        raise HTTPException(404) from e
    try:
        MODELLI_VERIFICATI[id_] = VERIFICATORE["funzione"](chiave)
    except estrazione.ErroreEstrazione as e:
        return _vai("/impostazioni", errore=f"{chiave.etichetta}: {e}")
    return _vai("/impostazioni", messaggio=f"{chiave.etichetta}: chiave valida, {len(MODELLI_VERIFICATI[id_])} modelli disponibili.")


@app.post("/impostazioni/{id_}/modifica")
def modifica_chiave(id_: str, modello: str = Form(""), etichetta: str = Form(""), a_pagamento: str = Form("")):
    campi: dict = {"a_pagamento": bool(a_pagamento)}
    if modello:
        campi["modello"] = modello
    if etichetta.strip():
        campi["etichetta"] = etichetta.strip()
    try:
        impostazioni.aggiorna(id_, **campi)
    except KeyError as e:
        raise HTTPException(404) from e
    return _vai("/impostazioni", messaggio="Impostazioni aggiornate.")


@app.post("/impostazioni/{id_}/attiva")
def attiva_chiave(id_: str):
    try:
        impostazioni.attiva(id_)
    except KeyError as e:
        raise HTTPException(404) from e
    return _vai("/impostazioni", messaggio="Chiave attiva cambiata.")


@app.post("/impostazioni/{id_}/elimina")
def elimina_chiave(id_: str):
    impostazioni.rimuovi(id_)
    MODELLI_VERIFICATI.pop(id_, None)
    return _vai("/impostazioni", messaggio="Chiave eliminata.")


# ----------------------------------------------------------------------- accesso

@app.get("/accesso", response_class=HTMLResponse)
def pagina_accesso(request: Request, dopo: str = "/"):
    if not accesso.attivo():
        return _vai("/")
    return modelli.TemplateResponse(request, "accesso.html", {"dopo": accesso.destinazione_sicura(dopo), "errore": ""})


@app.post("/accesso")
def entra(request: Request, password: str = Form(""), dopo: str = Form("/")):
    if not accesso.password_corretta(password):
        time.sleep(1)  # rallenta i tentativi a forza bruta
        return modelli.TemplateResponse(request, "accesso.html", {
            "dopo": accesso.destinazione_sicura(dopo), "errore": "Password errata."}, status_code=401)
    risposta = RedirectResponse(accesso.destinazione_sicura(dopo), status_code=303)
    risposta.set_cookie(accesso.NOME_COOKIE, accesso.crea_cookie(), max_age=accesso.DURATA_SECONDI, httponly=True,
                        samesite="lax", secure=os.environ.get("SAPORESTA_HTTPS") == "1")
    return risposta


@app.post("/esci")
def esci():
    risposta = _vai("/accesso" if accesso.attivo() else "/")
    risposta.delete_cookie(accesso.NOME_COOKIE)
    return risposta


@app.post("/impostazioni/carta-intestata")
async def carta_intestata(documento: UploadFile):
    """Carica un documento Word dell'ufficio: se ne usano intestazione e piè di pagina per i modelli."""
    import io
    import zipfile
    contenuto = await documento.read()
    try:
        with zipfile.ZipFile(io.BytesIO(contenuto)) as z:
            valido = "word/document.xml" in z.namelist()
    except zipfile.BadZipFile:
        valido = False
    if not valido:
        return _vai("/impostazioni", errore="Il file non è un documento Word (.docx).")
    cartella = modelli_word.CARTELLA_MODELLI
    cartella.mkdir(parents=True, exist_ok=True)
    sorgente = cartella / "carta_intestata_caricata.docx"
    sorgente.write_bytes(contenuto)
    try:
        modelli_word.crea_tutti(sorgente)
    except Exception as e:  # documento Word non leggibile da python-docx
        return _vai("/impostazioni", errore=f"Documento non utilizzabile come carta intestata ({e.__class__.__name__}).")
    finally:
        sorgente.unlink(missing_ok=True)  # si tiene solo la base svuotata, non il documento originale
    return _vai("/impostazioni", messaggio="Carta intestata caricata: i nuovi documenti la useranno.")
