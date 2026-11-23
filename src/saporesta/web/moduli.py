"""Modulo HTML generato dal modello dati della pratica, e lettura del modulo inviato.

I campi si chiamano col percorso puntato del dato (es. "inquadramento.particelle.0.foglio").
Suffissi speciali nei nomi:
    nome[]          caselle multiple -> lista
    nome:csv        testo separato da virgole -> lista
    nome:righe      una voce per riga -> lista
    nome:blocchi    voci separate da una riga vuota -> lista
"""

from __future__ import annotations

import types
from datetime import date
from enum import Enum
from html import escape
from inspect import isclass
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from ..checklist import voci_richieste
from ..models import Pratica, StatoVoce

ETICHETTE = {
    "protocollo": "N. protocollo", "data_protocollo": "Data protocollo", "protocolli_integrazione": "Protocolli integrazioni",
    "data_istanza": "Data dell'istanza", "riferimento_normativo_modulo": "Norma citata nel modulo",
    "richiedente": "Richiedente", "titolo_richiedente": "In qualità di", "ente_pubblico": "Bosco di ente pubblico",
    "classe_eutr": "Classificazione EUTR", "tecnico": "Tecnico progettista", "intervento": "Intervento",
    "inquadramento": "Inquadramento", "vincoli": "Vincoli dichiarati", "scheda": "Scheda tecnica A02.3",
    "tagliate": "Tagliate (cedui)", "martellata": "Martellata", "versamento": "Versamento diritti",
    "riscontri": "Stesso dato in più documenti", "cognome": "Cognome", "nome": "Nome", "sesso": "Sesso (M/F)",
    "data_nascita": "Data di nascita", "luogo_nascita": "Luogo di nascita", "comune_residenza": "Comune di residenza",
    "cap": "CAP", "provincia": "Provincia", "indirizzo": "Indirizzo", "civico": "N. civico",
    "codice_fiscale": "Codice fiscale", "pec": "PEC", "email": "E-mail", "titolo": "Titolo",
    "ordine_provincia": "Ordine della provincia di", "numero_iscrizione": "N. iscrizione", "sezione": "Sezione",
    "sigla_martello": "Sigla martello forestale", "tipo": "Tipo di intervento", "sottotipi": "Specifica",
    "straordinario": "Taglio straordinario", "previsto_da": "Previsto da (piano)", "titolo_progetto": "Titolo del progetto",
    "popolamento": "Popolamento", "manutenzione_viabilita": "Manutenzione viabilità", "nuove_piste": "Nuove piste",
    "specie": "Specie", "percentuale": "%", "eta_min": "Età min (anni)", "eta_max": "Età max (anni)",
    "anno_ultimo_taglio": "Anno ultimo taglio", "fine_lavori_ultimo_intervento": "Fine lavori ultimo intervento",
    "origine_artificiale": "Origine artificiale", "comune": "Comune", "localita": "Località", "particelle": "Particelle",
    "foglio": "Foglio", "superficie_catastale_ha": "Superficie catastale (ha)",
    "superficie_intervento_ha": "Superficie intervento (ha)", "destinazione_urbanistica": "Destinazione urbanistica",
    "aree_protette": "Aree protette", "natura2000": "Natura 2000", "sito_natura2000": "Sito Natura 2000",
    "pai_geomorfologico": "PAI geomorfologico", "pai_idraulico": "PAI idraulico", "percorsa_incendio": "Percorsa da incendio",
    "vincolo_art54": "Vincolo art. 54 R.D. 3267/23", "vincolo_paesaggistico": "Vincolo paesaggistico",
    "sorgenti_50m": "Entro 50 m da sorgenti", "versante_massi": "Versante con caduta massi",
    "pendenza_media_pct": "Pendenza media (%)", "ettaro_prima": "Ad ettaro – prima", "ettaro_taglio": "Ad ettaro – al taglio",
    "ettaro_dopo": "Ad ettaro – dopo", "totale_prima": "Intera superficie – prima",
    "totale_taglio": "Intera superficie – al taglio", "totale_dopo": "Intera superficie – dopo", "n_piante": "N. piante",
    "area_basimetrica": "Area basimetrica (m²)", "volume": "Volume (m³)", "peso_specifico_q_m3": "Peso specifico (q/m³)",
    "massa_taglio_ettaro_q": "Massa al taglio ad ettaro (q)", "massa_taglio_totale_q": "Massa al taglio totale (q)",
    "percentuale_dichiarata_piante": "% piante dichiarata", "percentuale_dichiarata_g": "% area basimetrica dichiarata",
    "percentuale_dichiarata_volume": "% volume dichiarata", "diametro_medio_cm": "Diametro medio (cm)",
    "altezza_media_m": "Altezza media (m)", "aree_saggio": "Aree di saggio", "superficie_m2": "Superficie (m²)",
    "utm_e": "UTM E", "utm_n": "UTM N", "area_basimetrica_m2": "Area basimetrica (m²)", "assortimenti": "Assortimenti",
    "descrizione": "Descrizione", "volume_m3": "Volume (m³)", "matricine_ha": "Matricine/ha",
    "matricine_doppio_turno_pct": "% matricine età doppia del turno", "polloni_rilasciati_ha": "Polloni rilasciati/ha",
    "alberi_invecchiamento": "Alberi a invecchiamento indefinito", "piante_morte_rilasciate_ha": "Piante morte rilasciate/ha",
    "superficie_ha": "Superficie (ha)", "stagione_silvana": "Stagione silvana", "contigua_a": "Contigua a",
    "numero_da": "Numerazione dal n.", "numero_a": "al n.", "colore_vernice": "Colore vernice",
    "importo_totale": "Importo totale (€)", "segreteria": "Diritti segreteria (€)", "istruttoria": "Diritti istruttoria (€)",
    "modalita": "Modalità", "campo": "Dato", "documento": "Documento", "valore": "Valore",
    "verifiche_ufficio": "Verifiche d'ufficio", "sistema": "Sistema", "esito": "Esito", "data": "Data",
    "criticita": "In contrasto con le dichiarazioni", "integrazioni_aggiuntive": "Altre integrazioni da chiedere (una per riga)",
    "prescrizioni_aggiuntive": "Altre prescrizioni (una per riga)", "riferimento_vinca": "Riferimento Valutazione di Incidenza",
    "note_verbale": "Note per il verbale (una per riga)", "validita_mesi": "Validità autorizzazione (mesi)",
    "firmatari": "Firmatari", "istruttore": "Funzionario istruttore", "responsabile_procedimento": "Responsabile del procedimento",
    "dirigente": "Dirigente", "qualifica_dirigente": "Qualifica del dirigente", "data_documento": "Data dei documenti",
    "destinatari_conoscenza": "Destinatari per conoscenza (separare gli indirizzi con una riga vuota)",
    "cubatura": "Tavola di cubatura", "tavola": "Tavola applicata",
    "tavola_dichiarata": "Come è indicata nell'istanza", "specie_tavola": "Specie della tavola (se diversa)",
    "tariffa": "Tariffa TaCAL n.", "classi": "Classi diametriche", "d_cm": "Diametro (cm)", "h_m": "Altezza (m)",
    "v_unitario_m3": "Volume per pianta (m³)", "v_totale_m3": "Volume della classe (m³)",
}

VALORI_LEGGIBILI = {
    "tabacchi_2011": "Tabacchi 2011 – INFC (doppia entrata)",
    "castellani_1984": "Castellani 1984 – ISAFA (doppia entrata)",
    "tacal_2016": "TaCAL 2016 – tariffe Calabria (una entrata)",
    "emilia_romagna_2002": "Emilia-Romagna 2002 (Bertani)",
    "trento_sff": "Provincia di Trento (modelli SFF)",
    "altra": "Altra tavola / locale",
}

RIGHE = {"integrazioni_aggiuntive", "prescrizioni_aggiuntive", "note_verbale", "aree_protette", "protocolli_integrazione"}
BLOCCHI = {"destinatari_conoscenza"}
TESTI_LUNGHI = {"titolo_progetto", "esito", "manutenzione_viabilita", "riferimento_vinca", "classe_eutr", "tavola_dichiarata"}


def etichetta(nome: str) -> str:
    return ETICHETTE.get(nome, nome.replace("_", " ").capitalize())


# --------------------------------------------------------------------- tipi

def analizza(annotazione: Any) -> tuple[str, Any]:
    """('model'|'list'|'dict'|'enum'|'literal'|'date'|'bool'|'int'|'float'|'str', tipo interno)."""
    origine = get_origin(annotazione)
    if origine in (Union, types.UnionType):
        argomenti = [a for a in get_args(annotazione) if a is not type(None)]
        return analizza(argomenti[0])
    if origine is list:
        return "list", get_args(annotazione)[0]
    if origine is dict:
        return "dict", get_args(annotazione)
    if origine is Literal:
        return "literal", get_args(annotazione)
    if isclass(annotazione):
        if issubclass(annotazione, BaseModel):
            return "model", annotazione
        if issubclass(annotazione, Enum):
            return "enum", annotazione
        if issubclass(annotazione, bool):
            return "bool", None
        if issubclass(annotazione, date):
            return "date", None
        if issubclass(annotazione, int):
            return "int", None
        if issubclass(annotazione, float):
            return "float", None
    return "str", None


def _scelte(tipo: str, interno: Any) -> list[str]:
    if tipo == "enum":
        return [m.value for m in interno]
    return [str(v) for v in interno]


# ------------------------------------------------------------------ rendering

class Rendering:
    def __init__(self, campi_dubbi: dict[str, str]):
        self.dubbi = campi_dubbi  # percorso -> motivo

    def _dubbio(self, percorso: str) -> str:
        for chiave, motivo in self.dubbi.items():
            if percorso == chiave or percorso.endswith("." + chiave):
                return motivo
        return ""

    def campo(self, nome: str, annotazione: Any, valore: Any, percorso: str) -> str:
        tipo, interno = analizza(annotazione)
        if tipo == "model":
            return self.gruppo(interno, valore or {}, percorso, etichetta(nome))
        if tipo == "list":
            t_int, i_int = analizza(interno)
            if t_int == "model":
                return self.lista(i_int, valore or [], percorso, etichetta(nome))
            if t_int in ("enum", "literal"):
                return self._caselle(nome, percorso, _scelte(t_int, i_int), valore or [])
            return self._testo_lista(nome, percorso, valore or [])
        if tipo == "dict":
            return ""
        return self._scalare(nome, tipo, interno, valore, percorso)

    def _avvolgi(self, nome: str, percorso: str, controllo: str, largo: bool = False) -> str:
        motivo = self._dubbio(percorso)
        classe = "campo" + (" largo" if largo else "") + (" dubbio" if motivo else "")
        nota = f'<span class="nota-dubbio">⚠ {escape(motivo)}</span>' if motivo else ""
        return (f'<label class="{classe}" title="{escape(motivo)}"><span>{escape(etichetta(nome))}</span>'
                f'{controllo}{nota}</label>')

    def _scalare(self, nome: str, tipo: str, interno: Any, valore: Any, percorso: str) -> str:
        n = escape(percorso)
        if isinstance(valore, Enum):
            valore = valore.value
        v = "" if valore is None else str(valore)
        if tipo in ("enum", "literal"):
            opzioni = '<option value=""></option>' + "".join(
                f'<option value="{escape(s)}"{" selected" if s == v else ""}>{escape(VALORI_LEGGIBILI.get(s, s))}</option>'
                for s in _scelte(tipo, interno))
            return self._avvolgi(nome, percorso, f'<select name="{n}">{opzioni}</select>')
        if tipo == "bool":
            sel = {"True": "true", "False": "false", "true": "true", "false": "false"}.get(v, "")
            opzioni = "".join(f'<option value="{k}"{" selected" if k == sel else ""}>{t}</option>'
                              for k, t in [("", ""), ("true", "Sì"), ("false", "No")])
            return self._avvolgi(nome, percorso, f'<select name="{n}">{opzioni}</select>')
        if tipo == "date":
            return self._avvolgi(nome, percorso, f'<input type="date" name="{n}" value="{escape(v[:10])}">')
        if tipo in ("int", "float"):
            passo = "1" if tipo == "int" else "any"
            return self._avvolgi(nome, percorso, f'<input type="number" step="{passo}" name="{n}" value="{escape(v)}">')
        if nome in TESTI_LUNGHI:
            return self._avvolgi(nome, percorso, f'<textarea name="{n}" rows="2">{escape(v)}</textarea>', largo=True)
        return self._avvolgi(nome, percorso, f'<input type="text" name="{n}" value="{escape(v)}">')

    def _caselle(self, nome: str, percorso: str, scelte: list[str], valori: list) -> str:
        scelti = {v.value if isinstance(v, Enum) else str(v) for v in valori}
        caselle = "".join(
            f'<label class="casella"><input type="checkbox" name="{escape(percorso)}[]" value="{escape(s)}"'
            f'{" checked" if s in scelti else ""}> {escape(s.replace("_", " "))}</label>' for s in scelte)
        return self._avvolgi(nome, percorso, f'<div class="caselle">{caselle}</div>', largo=True)

    def _testo_lista(self, nome: str, percorso: str, valori: list) -> str:
        n = escape(percorso)
        if nome in BLOCCHI:
            return self._avvolgi(nome, percorso, f'<textarea name="{n}:blocchi" rows="6">'
                                 f'{escape(chr(10) * 2).join(escape(str(x)) for x in valori)}</textarea>', largo=True)
        if nome in RIGHE:
            return self._avvolgi(nome, percorso, f'<textarea name="{n}:righe" rows="3">'
                                 f'{escape(chr(10).join(str(x) for x in valori))}</textarea>', largo=True)
        return self._avvolgi(nome, percorso, f'<input type="text" name="{n}:csv" '
                             f'value="{escape(", ".join(str(x) for x in valori))}" placeholder="separare con virgole">')

    def campi(self, modello: type[BaseModel], dati: dict, prefisso: str, solo: list[str] | None = None,
              escludi: set[str] = frozenset()) -> str:
        parti = []
        nomi = solo if solo is not None else list(modello.model_fields)
        for nome in nomi:
            if nome in escludi:
                continue
            info = modello.model_fields[nome]
            percorso = f"{prefisso}.{nome}" if prefisso else nome
            parti.append(self.campo(nome, info.annotation, (dati or {}).get(nome), percorso))
        return "".join(parti)

    def gruppo(self, modello: type[BaseModel], dati: dict, percorso: str, titolo: str) -> str:
        motivo = self._dubbio(percorso)
        nota = f'<p class="nota-dubbio">⚠ {escape(motivo)}</p>' if motivo else ""
        return (f'<fieldset class="gruppo{" dubbio" if motivo else ""}"><legend>{escape(titolo)}</legend>{nota}'
                f'<div class="griglia">{self.campi(modello, dati, percorso)}</div></fieldset>')

    def lista(self, modello: type[BaseModel], voci: list, percorso: str, titolo: str) -> str:
        p = escape(percorso)
        elementi = "".join(self._elemento(modello, v, f"{percorso}.{i}") for i, v in enumerate(voci))
        modello_vuoto = self._elemento(modello, {}, f"{percorso}.__i__")
        motivo = self._dubbio(percorso)
        nota = f'<p class="nota-dubbio">⚠ {escape(motivo)}</p>' if motivo else ""
        return (f'<fieldset class="gruppo lista{" dubbio" if motivo else ""}" data-lista="{p}"><legend>{escape(titolo)}</legend>'
                f'{nota}<div class="voci">{elementi}</div>'
                f'<template>{modello_vuoto}</template>'
                f'<button type="button" class="aggiungi">+ Aggiungi</button></fieldset>')

    def _elemento(self, modello: type[BaseModel], dati: dict, percorso: str) -> str:
        return (f'<div class="voce"><div class="griglia">{self.campi(modello, dati, percorso)}</div>'
                f'<button type="button" class="rimuovi" title="Rimuovi">✕</button></div>')


def checklist_html(pratica: Pratica | None, dati: dict) -> str:
    """Tabella della checklist con le sole voci richieste per la pratica."""
    from ..checklist import VOCI
    voci = voci_richieste(pratica) if pratica else VOCI
    attuali = ((dati or {}).get("istruttoria") or {}).get("checklist") or {}
    righe = []
    gruppo = None
    for v in voci:
        if v.gruppo != gruppo:
            gruppo = v.gruppo
            righe.append(f'<tr class="gruppo-checklist"><th colspan="3">{escape(gruppo)}</th></tr>')
        stato_corr = (attuali.get(v.id) or {}).get("stato") or ""
        if isinstance(stato_corr, Enum):
            stato_corr = stato_corr.value
        nota = (attuali.get(v.id) or {}).get("nota") or ""
        radio = "".join(
            f'<label class="stato s-{s or "vuoto"}"><input type="radio" name="istruttoria.checklist.{v.id}.stato" '
            f'value="{s}"{" checked" if s == stato_corr else ""}>{t}</label>'
            for s, t in [("", "–"), ("si", "Sì"), ("no", "No"), ("difforme", "Diff."), ("np", "N.P.")])
        righe.append(
            f'<tr><td>{escape(v.testo)}</td><td class="radio">{radio}</td>'
            f'<td><input type="text" name="istruttoria.checklist.{v.id}.nota" value="{escape(nota)}"></td></tr>')
    return (f'<table class="checklist"><thead><tr><th>Documento</th><th>Presente</th><th>Nota</th></tr></thead>'
            f'<tbody>{"".join(righe)}</tbody></table>')


# --------------------------------------------------------------------- lettura

def _imposta(radice: dict, chiavi: list[str], valore: Any, multiplo: bool) -> None:
    nodo = radice
    for k in chiavi[:-1]:
        nodo = nodo.setdefault(k, {})
    ultimo = chiavi[-1]
    if multiplo:
        nodo.setdefault(ultimo, []).append(valore)
    else:
        nodo[ultimo] = valore


def _a_liste(nodo: Any) -> Any:
    if isinstance(nodo, dict):
        nodo = {k: _a_liste(v) for k, v in nodo.items()}
        if nodo and all(k.lstrip("-").isdigit() for k in nodo):
            return [nodo[k] for k in sorted(nodo, key=int)]
        return nodo
    if isinstance(nodo, list):
        return [_a_liste(v) for v in nodo]
    return nodo


def _pulisci(nodo: Any) -> Any:
    """Toglie valori vuoti: i campi tornano ai valori predefiniti, i gruppi opzionali vuoti a None."""
    if isinstance(nodo, dict):
        pulito = {k: _pulisci(v) for k, v in nodo.items()}
        return {k: v for k, v in pulito.items() if v not in (None, "", {})}
    if isinstance(nodo, list):
        return [v for v in (_pulisci(x) for x in nodo) if v not in (None, "", {})]
    return nodo


def da_modulo(voci: list[tuple[str, str]]) -> dict:
    radice: dict = {}
    for nome, valore in voci:
        if nome.startswith("_"):
            continue
        multiplo = nome.endswith("[]")
        if multiplo:
            nome = nome[:-2]
        modo = None
        if ":" in nome:
            nome, modo = nome.rsplit(":", 1)
        if "__i__" in nome:
            continue  # modello vuoto nel <template>
        if modo == "csv":
            valore = [x.strip() for x in valore.split(",") if x.strip()]
        elif modo == "righe":
            valore = [x.strip() for x in valore.splitlines() if x.strip()]
        elif modo == "blocchi":
            testo = valore.replace("\r\n", "\n")
            valore = [b.strip() for b in testo.split("\n\n") if b.strip()]
        else:
            valore = valore.strip()
        _imposta(radice, nome.split("."), valore, multiplo)
    return _pulisci(_a_liste(radice))


def unisci(vecchi: dict | None, nuovi: dict) -> dict:
    """I dati inviati sostituiscono i vecchi; restano solo le chiavi che il modulo non mostra."""
    risultato = dict(vecchi or {})
    for k in Pratica.model_fields:
        risultato.pop(k, None)
    risultato.update(nuovi)
    return risultato


def html_errori(errori: list[dict]) -> list[str]:
    traduzioni = {
        "missing": "dato obbligatorio", "float_parsing": "numero non valido", "int_parsing": "numero intero non valido",
        "date_from_datetime_parsing": "data non valida", "date_parsing": "data non valida", "enum": "valore non ammesso",
        "literal_error": "valore non ammesso", "bool_parsing": "valore non valido",
    }
    righe = []
    for e in errori:
        percorso = " → ".join(etichetta(str(x)) if not str(x).isdigit() else f"n. {int(x) + 1}" for x in e["loc"])
        righe.append(f"{percorso}: {traduzioni.get(e['type'], e['msg'])}")
    return righe


__all__ = ["Rendering", "checklist_html", "da_modulo", "unisci", "html_errori", "StatoVoce"]


def accertati_html(dati: dict) -> str:
    """Per ogni dato discordante tra i documenti, il valore che l'istruttore ritiene corretto."""
    from collections import defaultdict
    from ..verifiche.generali import _norm
    gruppi: dict[str, list] = defaultdict(list)
    for r in (dati or {}).get("riscontri") or []:
        if r.get("campo"):
            gruppi[r["campo"]].append(r)
    discordanti = {c: v for c, v in gruppi.items() if len({_norm(str(x.get("valore", ""))) for x in v}) > 1}
    if not discordanti:
        return ""
    attuali = {a.get("campo", "").strip().lower(): a
               for a in ((dati.get("istruttoria") or {}).get("dati_accertati") or [])}
    righe = []
    for i, (campo, voci) in enumerate(discordanti.items()):
        a = attuali.get(campo.strip().lower(), {})
        dettaglio = "; ".join(f"{escape(str(x.get('documento', '')))}: <strong>{escape(str(x.get('valore', '')))}</strong>"
                              for x in voci)
        pref = f"istruttoria.dati_accertati.{i}"
        righe.append(
            f'<div class="accertato"><p><strong>{escape(campo)}</strong> — {dettaglio}</p>'
            f'<input type="hidden" name="{pref}.campo" value="{escape(campo)}">'
            f'<div class="griglia"><label class="campo"><span>Valore accertato dall\'istruttore</span>'
            f'<input type="text" name="{pref}.valore" value="{escape(str(a.get("valore") or ""))}" '
            f'placeholder="es. il valore corretto"></label>'
            f'<label class="campo largo"><span>Motivazione (facoltativa)</span>'
            f'<input type="text" name="{pref}.nota" value="{escape(str(a.get("nota") or ""))}" '
            f'placeholder="es. verificato sul piedilista di martellata"></label></div></div>')
    return ('<fieldset class="gruppo accertati"><legend>Dati discordanti tra i documenti</legend>'
            '<p class="nota-accertati">Indicando il valore corretto, la discordanza non viene più segnalata come '
            'non conformità né chiesta all\'istante; resta annotata nel rapporto.</p>' + "".join(righe) + '</fieldset>')
