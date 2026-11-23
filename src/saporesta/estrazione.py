"""Estrazione dei dati di una pratica A02 dai PDF (istanza, A02.3, A02.4, relazione...) con l'API di Claude.

Tutti i PDF di una pratica vengono inviati in un'unica richiesta: il modello legge
anche le caselle barrate dei moduli scansionati (riceve sia il testo sia l'immagine
delle pagine), confronta gli stessi dati tra documenti diversi e segnala i dubbi.
Il risultato è una bozza che l'istruttore controlla e corregge prima delle verifiche.
"""

from __future__ import annotations

import base64
from datetime import date
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, ConfigDict, ValidationError

from . import impostazioni
from .checklist import VOCI
from .impostazioni import Chiave
from .models import Pratica

MODELLO = "claude-opus-5-5"
MAX_PDF_BYTES = 30 * 1024 * 1024  # limite della richiesta: 32 MB in tutto

# --------------------------------------------------------------- schema di uscita
# Schema dedicato all'estrazione: tutti i campi obbligatori, "None" se il dato non
# c'è nei documenti. Viene poi convertito nel modello Pratica.


class _E(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EPersona(_E):
    cognome: str | None
    nome: str | None
    sesso: Literal["M", "F"] | None
    data_nascita: str | None  # AAAA-MM-GG
    luogo_nascita: str | None
    comune_residenza: str | None
    cap: str | None
    provincia: str | None
    indirizzo: str | None
    civico: str | None
    codice_fiscale: str | None
    pec: str | None
    email: str | None


class ETecnico(EPersona):
    titolo: str | None
    ordine_provincia: str | None
    numero_iscrizione: str | None
    sezione: str | None
    sigla_martello: str | None


class EParticelle(_E):
    foglio: str
    particelle: list[str]


class ESpecie(_E):
    nome: str
    percentuale: float | None


class EDendro(_E):
    n_piante: float | None
    area_basimetrica: float | None
    volume: float | None


class EAreaSaggio(_E):
    nome: str
    superficie_m2: float | None
    utm_e: float | None
    utm_n: float | None
    n_piante: int | None
    area_basimetrica_m2: float | None


class EAssortimento(_E):
    descrizione: str
    volume_m3: float


class ETagliata(_E):
    nome: str
    superficie_ha: float | None
    stagione_silvana: str | None


class EMartellata(_E):
    n_piante: int | None
    numero_da: int | None
    numero_a: int | None
    specie: str | None
    sigla_martello: str | None
    colore_vernice: str | None
    sezione: str | None


VociChecklist = Literal[tuple(v.id for v in VOCI)]  # type: ignore[valid-type]


class EDocumento(_E):
    voce: VociChecklist  # type: ignore[valid-type]
    file: str
    pagine: str | None


class ERiscontro(_E):
    campo: str
    documento: str
    valore: str


class EDubbio(_E):
    campo: str
    motivo: str


class EScheda(_E):
    ettaro_prima: EDendro
    ettaro_taglio: EDendro
    ettaro_dopo: EDendro
    totale_prima: EDendro
    totale_taglio: EDendro
    totale_dopo: EDendro
    peso_specifico_q_m3: float | None
    massa_taglio_ettaro_q: float | None
    massa_taglio_totale_q: float | None
    percentuale_dichiarata_piante: float | None
    percentuale_dichiarata_g: float | None
    percentuale_dichiarata_volume: float | None
    diametro_medio_cm: float | None
    altezza_media_m: float | None
    aree_saggio: list[EAreaSaggio]
    assortimenti: list[EAssortimento]
    matricine_ha: float | None
    matricine_doppio_turno_pct: float | None
    polloni_rilasciati_ha: float | None
    alberi_invecchiamento: int | None
    piante_morte_rilasciate_ha: float | None


class EClasse(_E):
    d_cm: float
    h_m: float | None
    n_piante: float | None
    v_unitario_m3: float | None
    v_totale_m3: float | None


class Estrazione(_E):
    protocollo: str | None
    data_protocollo: str | None
    data_istanza: str | None
    riferimento_normativo_modulo: str | None
    richiedente: EPersona | None
    titolo_richiedente: Literal[
        "proprietario", "usufruttuario", "affittuario", "soggetto delegato",
        "rappresentante di ente o società", "altro"] | None
    ente_pubblico: bool | None
    classe_eutr: str | None
    tecnico: ETecnico | None
    tipo_intervento: Literal["ceduo", "neoformazione", "fustaia", "transitorio", "incendio", "avversita", "art22"] | None
    sottotipi: list[Literal[
        "senza_matricine", "matricinato", "sterzo", "composto", "sfolli", "diradamenti", "sfollamenti",
        "rinnovazione", "primo_avviamento", "successivi_avviamento", "conversione", "infrastrutture",
        "manufatti", "elettrodotti", "viabilita", "idraulica"]]
    straordinario: bool | None
    previsto_da: str | None
    titolo_progetto: str | None
    specie: list[ESpecie]
    eta_min: int | None
    eta_max: int | None
    anno_ultimo_taglio: int | None
    origine_artificiale: bool | None
    comune: str | None
    provincia: str | None
    localita: str | None
    particelle: list[EParticelle]
    superficie_catastale_ha: float | None
    superficie_intervento_ha: float | None
    destinazione_urbanistica: str | None
    aree_protette: list[str]
    natura2000: bool | None
    sito_natura2000: str | None
    pai_geomorfologico: list[Literal["R1", "R2", "R3", "R4"]]
    pai_idraulico: list[Literal["R1", "R2", "R3", "R4"]]
    percorsa_incendio: bool | None
    vincolo_art54: bool | None
    pendenza_media_pct: float | None
    manutenzione_viabilita: str | None
    nuove_piste: bool | None
    versamento_importo: float | None
    versamento_segreteria: float | None
    versamento_istruttoria: float | None
    versamento_modalita: str | None
    scheda: EScheda | None
    tagliate: list[ETagliata]
    martellata: EMartellata | None
    tavola_cubatura: Literal["tabacchi_2011", "castellani_1984", "tacal_2016", "emilia_romagna_2002", "trento_sff",
                             "altra"] | None
    tavola_cubatura_testo: str | None
    specie_tavola: str | None
    tariffa_tacal: int | None
    classi_diametriche: list[EClasse]
    documenti_presenti: list[EDocumento]
    riscontri: list[ERiscontro]
    dubbi: list[EDubbio]


# ------------------------------------------------------------------------ prompt

def _elenco_voci() -> str:
    return "\n".join(f"- {v.id}: {v.testo}" for v in VOCI)


SISTEMA = f"""Sei l'assistente di un funzionario istruttore della Regione Calabria (U.O.A. Foreste) che esamina le istanze \
di autorizzazione al taglio boschivo (modulo A02) secondo il Regolamento regionale n. 4/2024. Ricevi i PDF di una pratica \
(istanza A02, schede A02.3 e A02.4, relazione tecnica, piedilisti, visure, ricevute...) e ne estrai i dati nello schema richiesto.

Regole:
- Riporta solo ciò che è scritto nei documenti. Se un dato manca o è illeggibile usa null (liste vuote per gli elenchi) \
e aggiungi una voce in "dubbi". Non dedurre valori che il documento non dichiara.
- Nei moduli le caselle barrate (☑, ■, X) indicano la scelta; quelle vuote (□) no. Guarda l'immagine della pagina \
per capire quali sono barrate.
- Date nel formato AAAA-MM-GG. Superfici in ettari decimali: "ha 00.99.90" o "ha 0.99.90" (ettari.are.centiare) = 0.999.
- "protocollo" e "data_protocollo" vengono dal timbro/segnatura di protocollo regionale (es. "Prot. N. 123456 del 01/01/2026").
- tipo_intervento: ceduo (bosco ceduo ≥ 2 ha, sfolli e diradamenti nel ceduo), neoformazione, fustaia, transitorio \
(soprassuoli transitori, avviamento all'alto fusto), incendio (boschi danneggiati dal fuoco), avversita (avversità \
meteoriche), art22 (tagli per pubblica incolumità, elettrodotti, viabilità, opere idrauliche).
- vincolo_art54: true se l'istante dichiara che VIGE il vincolo dell'art. 54 R.D. 3267/23. percorsa_incendio: true se \
dichiara che l'area è stata percorsa da incendio o è soggetta al vincolo dell'art. 10 L. 353/2000.
- riferimento_normativo_modulo: la norma che il modulo cita per i tagli (es. "PMPF D.G.R. n. 218 del 20.05.2011" oppure "Reg. n. 4/2024").
- Scheda A02.3: valori "ad ettaro" in ettaro_*, valori "sull'intera superficie" in totale_*; percentuali in punti (20 = 20%).
- Tavola di cubatura: cerca nella relazione e nella scheda A02.3 quale tavola o tariffa è stata usata per stimare i \
volumi e riporta in "tavola_cubatura_testo" la frase com'è scritta. In "tavola_cubatura" indica: "tabacchi_2011" per \
tavole INFC / Inventario Nazionale 2005 / Tabacchi et al. 2011; "castellani_1984" per tavole ISAFA / IFNI / Castellani \
et al. 1984 (tavole a doppia entrata dell'Inventario Forestale Nazionale Italiano); "tacal_2016" per TaCAL / ALForLab / \
tariffe dei volumi della Calabria (Scrinzi et al. 2016), con il numero di tariffa in "tariffa_tacal"; \
"emilia_romagna_2002" per le tavole dell'Emilia-Romagna (Bertani); "trento_sff" per i modelli della Provincia di Trento; \
"altra" per tavole locali o costruite dal progettista; null se la tavola non è indicata (e aggiungi un dubbio). \
"specie_tavola" solo se la tavola usata è di una specie diversa da quella prevalente.
- classi_diametriche: il quadro riepilogativo delle piante al taglio per classi diametriche (o la curva ipsometrica \
con i volumi): per ogni classe diametro in cm, altezza in m, numero di piante, volume di una pianta e/o volume della \
classe, in m³ (se il documento usa dm³ converti in m³ e segnalalo nei dubbi). Se manca, lista vuota.
- documenti_presenti: per ogni documento della checklist che trovi tra i PDF indica la voce, il nome del file e le pagine. \
Voci possibili:
{_elenco_voci()}
- riscontri: quando lo stesso dato (superficie, numero piante, volume, particelle, età, specie...) compare in più \
documenti, riporta ogni occorrenza (campo con nome uguale per tutte, documento, valore come scritto). Includili \
soprattutto quando i valori non coincidono.
- dubbi: ogni dato incerto, illeggibile, mancante ma atteso, o in contraddizione tra documenti, con il motivo in italiano. \
Usa per "campo" il nome del campo dello schema (es. "superficie_intervento_ha", "scheda.totale_taglio.volume").
"""


# ---------------------------------------------------------------------- chiamata

class ErroreEstrazione(RuntimeError):
    pass


def _controlla_dimensione(percorsi: list[Path], limite: int) -> None:
    totale = sum(p.stat().st_size for p in percorsi)
    if totale > limite:
        raise ErroreEstrazione(
            f"I PDF pesano {totale / 1e6:.1f} MB: oltre il limite di una richiesta ({limite / 1e6:.0f} MB). Caricare i "
            "documenti principali (istanza, A02.3, A02.4, relazione) e lasciare fuori le tavole cartografiche.")


def _blocchi_pdf(percorsi: list[Path]) -> list[dict]:
    _controlla_dimensione(percorsi, MAX_PDF_BYTES)
    blocchi: list[dict] = []
    for p in percorsi:
        blocchi.append({"type": "text", "text": f"File: {p.name}"})
        blocchi.append({
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf",
                       "data": base64.standard_b64encode(p.read_bytes()).decode("ascii")},
            "title": p.name,
        })
    return blocchi


ISTRUZIONE = "Estrai i dati della pratica da tutti i documenti allegati, confrontandoli tra loro."


def estrai(percorsi: list[Path], client=None, chiave: Chiave | None = None) -> Estrazione:
    """Invia i PDF al fornitore della chiave (attiva, se non indicata) e restituisce i dati da controllare."""
    if not percorsi:
        raise ErroreEstrazione("Nessun PDF da analizzare.")
    if chiave is None and client is None:
        chiave = impostazioni.chiave_attiva()
        if chiave is None:
            raise ErroreEstrazione("Nessuna chiave API impostata: aggiungerne una nella pagina Impostazioni.")
    if chiave is not None and chiave.fornitore == "gemini":
        return estrai_gemini(percorsi, chiave, client)
    return estrai_claude(percorsi, chiave, client)


# ------------------------------------------------------------------- Claude

def estrai_claude(percorsi: list[Path], chiave: Chiave | None = None,
                  client: anthropic.Anthropic | None = None) -> Estrazione:
    client = client or anthropic.Anthropic(api_key=chiave.valore if chiave else None)
    contenuto = _blocchi_pdf(percorsi) + [{"type": "text", "text": ISTRUZIONE}]
    try:
        risposta = client.beta.messages.parse(
            model=(chiave.modello_effettivo if chiave else None) or MODELLO,
            max_tokens=32000,
            system=SISTEMA,
            messages=[{"role": "user", "content": contenuto}],
            output_format=Estrazione,
            output_config={"effort": "high"},
            # se il modello declina la richiesta, l'API la ripete su un modello di riserva
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as e:
        raise ErroreEstrazione("Chiave API Anthropic mancante o non valida.") from e
    except anthropic.BadRequestError as e:
        raise ErroreEstrazione(f"Richiesta rifiutata dall'API: {e.message}") from e
    except anthropic.RateLimitError as e:
        raise ErroreEstrazione("Limite di richieste raggiunto: riprovare tra qualche minuto.") from e
    except anthropic.APIConnectionError as e:
        raise ErroreEstrazione("Impossibile raggiungere l'API Anthropic: verificare la connessione.") from e
    except anthropic.APIStatusError as e:
        raise ErroreEstrazione(f"Errore dell'API ({e.status_code}): riprovare più tardi.") from e

    if risposta.stop_reason == "refusal":
        raise ErroreEstrazione("Il modello ha declinato la richiesta di estrazione.")
    if risposta.stop_reason == "max_tokens":
        raise ErroreEstrazione("Risposta troncata: i documenti sono troppo lunghi per un'unica estrazione.")
    if risposta.parsed_output is None:
        raise ErroreEstrazione("La risposta non contiene dati strutturati.")
    return risposta.parsed_output


# ------------------------------------------------------------------- Gemini

MAX_PDF_BYTES_GEMINI = 19 * 1024 * 1024  # dati inline: 20 MB per richiesta

MOTIVI_BLOCCO_GEMINI = {
    "MAX_TOKENS": "Risposta troncata: i documenti sono troppo lunghi per un'unica estrazione.",
    "SAFETY": "Gemini ha bloccato la risposta per i suoi filtri di sicurezza.",
    "SPII": "Gemini ha bloccato la risposta perché contiene dati personali sensibili (es. codici fiscali).",
    "PROHIBITED_CONTENT": "Gemini ha bloccato la richiesta.",
    "BLOCKLIST": "Gemini ha bloccato la risposta.",
    "RECITATION": "Gemini ha interrotto la risposta.",
    "OTHER": "Gemini ha interrotto la risposta senza indicarne il motivo.",
}


def _errore_gemini(e: Exception) -> ErroreEstrazione:
    from google.genai import errors
    if isinstance(e, errors.ClientError):
        testo = str(getattr(e, "message", "") or "")
        if e.code in (401, 403) or "API_KEY" in testo or "API key" in testo:
            return ErroreEstrazione("Chiave Gemini non valida o senza permessi.")
        if e.code == 429:
            return ErroreEstrazione("Limite di richieste o quota Gemini esaurita: riprovare più tardi o usare un'altra chiave.")
        if e.code == 404:
            return ErroreEstrazione("Modello Gemini non trovato: sceglierne un altro nelle Impostazioni.")
        return ErroreEstrazione(f"Richiesta rifiutata da Gemini ({e.code}): {testo}")
    if isinstance(e, errors.ServerError):
        return ErroreEstrazione(f"Errore del servizio Gemini ({e.code}): riprovare più tardi.")
    return ErroreEstrazione(f"Impossibile raggiungere Gemini: {e.__class__.__name__}.")


def client_gemini(chiave: Chiave):
    from google import genai
    return genai.Client(api_key=chiave.valore)


def estrai_gemini(percorsi: list[Path], chiave: Chiave, client=None) -> Estrazione:
    from google.genai import types
    if not chiave.modello:
        raise ErroreEstrazione("Nessun modello Gemini scelto per questa chiave: usare «Verifica» nelle Impostazioni.")
    _controlla_dimensione(percorsi, MAX_PDF_BYTES_GEMINI)
    client = client or client_gemini(chiave)
    contenuti: list = []
    for p in percorsi:
        contenuti.append(f"File: {p.name}")
        contenuti.append(types.Part.from_bytes(data=p.read_bytes(), mime_type="application/pdf"))
    contenuti.append(ISTRUZIONE)
    try:
        risposta = client.models.generate_content(
            model=chiave.modello,
            contents=contenuti,
            config=types.GenerateContentConfig(
                system_instruction=SISTEMA,
                response_mime_type="application/json",
                response_json_schema=Estrazione.model_json_schema(),
                max_output_tokens=32768,
            ),
        )
    except Exception as e:  # errori di rete e dell'API tradotti in un messaggio leggibile
        raise _errore_gemini(e) from e

    feedback = getattr(risposta, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        raise ErroreEstrazione(f"Gemini ha bloccato la richiesta ({feedback.block_reason}).")
    candidati = risposta.candidates or []
    motivo = getattr(candidati[0], "finish_reason", None) if candidati else None
    nome_motivo = getattr(motivo, "name", str(motivo or ""))
    if nome_motivo in MOTIVI_BLOCCO_GEMINI:
        raise ErroreEstrazione(MOTIVI_BLOCCO_GEMINI[nome_motivo])
    testo = risposta.text
    if not testo:
        raise ErroreEstrazione("Gemini non ha restituito dati.")
    try:
        return Estrazione.model_validate_json(testo)
    except ValidationError as e:
        raise ErroreEstrazione(f"La risposta di Gemini non rispetta lo schema dei dati ({e.error_count()} errori).") from e


# ----------------------------------------------------------- verifica chiavi

def modelli_disponibili(chiave: Chiave, client=None) -> list[str]:
    """Modelli utilizzabili con la chiave; serve anche a verificarla."""
    if chiave.fornitore == "anthropic":
        client = client or anthropic.Anthropic(api_key=chiave.valore)
        try:
            return [m.id for m in client.models.list()]
        except anthropic.AuthenticationError as e:
            raise ErroreEstrazione("Chiave API Anthropic non valida.") from e
        except anthropic.APIError as e:
            raise ErroreEstrazione(f"Verifica non riuscita: {e.__class__.__name__}.") from e
    client = client or client_gemini(chiave)
    try:
        nomi = []
        for m in client.models.list():
            azioni = getattr(m, "supported_actions", None) or []
            nome = (m.name or "").removeprefix("models/")
            if "generateContent" in azioni and nome.startswith("gemini"):
                nomi.append(nome)
        return sorted(nomi)
    except Exception as e:
        raise _errore_gemini(e) from e


# -------------------------------------------------------------------- conversione

def _data(testo: str | None) -> date | None:
    if not testo:
        return None
    try:
        return date.fromisoformat(testo[:10])
    except ValueError:
        return None


def _persona(e: EPersona | None) -> dict | None:
    if e is None:
        return None
    d = e.model_dump()
    d["data_nascita"] = _data(d["data_nascita"])
    d["cognome"] = d["cognome"] or ""
    d["nome"] = d["nome"] or ""
    return {k: v for k, v in d.items() if v is not None}


def _dendro(e: EDendro) -> dict:
    return {k: v for k, v in e.model_dump().items() if v is not None}


def in_pratica(e: Estrazione) -> dict:
    """Converte l'estrazione nel formato della pratica (dict pronto per il file YAML).

    I dati obbligatori mancanti diventano stringhe vuote o segnaposto, segnalati nei dubbi.
    """
    oggi = date.today()
    scheda = None
    if e.scheda:
        s = e.scheda
        scheda = {k: v for k, v in s.model_dump(exclude={
            "ettaro_prima", "ettaro_taglio", "ettaro_dopo", "totale_prima", "totale_taglio", "totale_dopo",
            "aree_saggio", "assortimenti"}).items() if v is not None}
        for k in ("ettaro_prima", "ettaro_taglio", "ettaro_dopo", "totale_prima", "totale_taglio", "totale_dopo"):
            scheda[k] = _dendro(getattr(s, k))
        scheda["aree_saggio"] = [{k: v for k, v in a.model_dump().items() if v is not None}
                                 for a in s.aree_saggio if a.superficie_m2]
        scheda["assortimenti"] = [a.model_dump() for a in s.assortimenti]

    checklist = {}
    for d in e.documenti_presenti:
        nota = f"{d.file}{', pag. ' + d.pagine if d.pagine else ''} (rilevato automaticamente)"
        checklist[d.voce] = {"stato": "si", "nota": nota}

    dati = {
        "protocollo": e.protocollo or "",
        "data_protocollo": _data(e.data_protocollo) or oggi,
        "data_istanza": _data(e.data_istanza),
        "riferimento_normativo_modulo": e.riferimento_normativo_modulo,
        "richiedente": _persona(e.richiedente) or {"cognome": "", "nome": ""},
        "titolo_richiedente": e.titolo_richiedente or "proprietario",
        "ente_pubblico": bool(e.ente_pubblico),
        "classe_eutr": e.classe_eutr,
        "tecnico": _persona(e.tecnico),
        "intervento": {
            "tipo": e.tipo_intervento or "ceduo",
            "sottotipi": list(e.sottotipi),
            "straordinario": bool(e.straordinario),
            "previsto_da": e.previsto_da,
            "titolo_progetto": e.titolo_progetto,
            "manutenzione_viabilita": e.manutenzione_viabilita,
            "nuove_piste": bool(e.nuove_piste),
            "popolamento": {
                "specie": [s.model_dump() for s in e.specie],
                "eta_min": e.eta_min,
                "eta_max": e.eta_max,
                "anno_ultimo_taglio": e.anno_ultimo_taglio,
                "origine_artificiale": bool(e.origine_artificiale),
            },
        },
        "inquadramento": {
            "comune": e.comune or "",
            "provincia": e.provincia or "",
            "localita": e.localita or "",
            "particelle": [p.model_dump() for p in e.particelle],
            "superficie_catastale_ha": e.superficie_catastale_ha,
            "superficie_intervento_ha": e.superficie_intervento_ha or 0.0,
            "destinazione_urbanistica": e.destinazione_urbanistica,
        },
        "vincoli": {
            "aree_protette": e.aree_protette,
            "natura2000": bool(e.natura2000),
            "sito_natura2000": e.sito_natura2000,
            "pai_geomorfologico": list(e.pai_geomorfologico),
            "pai_idraulico": list(e.pai_idraulico),
            "percorsa_incendio": bool(e.percorsa_incendio),
            "vincolo_art54": bool(e.vincolo_art54),
            "pendenza_media_pct": e.pendenza_media_pct,
        },
        "versamento": {
            "importo_totale": e.versamento_importo,
            "segreteria": e.versamento_segreteria,
            "istruttoria": e.versamento_istruttoria,
            "modalita": e.versamento_modalita,
        },
        "scheda": scheda,
        "tagliate": [{k: v for k, v in t.model_dump().items() if v is not None}
                     for t in e.tagliate if t.superficie_ha is not None],
        "martellata": ({k: v for k, v in e.martellata.model_dump().items() if v is not None}
                       if e.martellata and e.martellata.n_piante else None),
        "cubatura": ({
            "tavola": e.tavola_cubatura,
            "tavola_dichiarata": e.tavola_cubatura_testo,
            "specie_tavola": e.specie_tavola,
            "tariffa": e.tariffa_tacal,
            "classi": [{k: v for k, v in c.model_dump().items() if v is not None} for c in e.classi_diametriche],
        } if (e.tavola_cubatura or e.tavola_cubatura_testo or e.classi_diametriche) else None),
        "riscontri": [r.model_dump() for r in e.riscontri],
        "istruttoria": {"checklist": checklist},
    }
    # valida subito: se qualcosa non torna l'errore emerge qui, non al momento delle verifiche
    Pratica.model_validate(dati)
    return dati


def dubbi_dopo_conversione(e: Estrazione) -> list[dict]:
    """Dubbi del modello più i dati obbligatori che la conversione ha dovuto riempire."""
    dubbi = [d.model_dump() for d in e.dubbi]
    obbligatori = {
        "protocollo": e.protocollo, "data_protocollo": e.data_protocollo, "tipo_intervento": e.tipo_intervento,
        "comune": e.comune, "localita": e.localita, "superficie_intervento_ha": e.superficie_intervento_ha,
        "richiedente": e.richiedente,
    }
    for campo, valore in obbligatori.items():
        if not valore and not any(d["campo"] == campo for d in dubbi):
            dubbi.append({"campo": campo, "motivo": "Dato obbligatorio non trovato nei documenti: inserirlo a mano."})
    return dubbi
