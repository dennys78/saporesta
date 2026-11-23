"""Confronto tra i dati letti dai PDF e quelli correnti della pratica (corretti dall'istruttore).

Serve a: chiudere i dubbi dell'estrazione quando l'istruttore corregge il campo, ed elencare nel
rapporto e nella pagina le correzioni fatte rispetto ai documenti.
"""

from __future__ import annotations

from datetime import date
from typing import Any, get_origin

from pydantic import ValidationError

ESCLUSI = ("istruttoria",)  # dati dell'istruttore, non letti dai PDF

ALIAS_DUBBI = {
    "tipo_intervento": "intervento.tipo", "sottotipi": "intervento.sottotipi", "specie": "intervento.popolamento.specie",
    "eta_min": "intervento.popolamento.eta_min", "eta_max": "intervento.popolamento.eta_max",
    "anno_ultimo_taglio": "intervento.popolamento.anno_ultimo_taglio",
    "versamento_importo": "versamento.importo_totale",
    "tavola_cubatura": "cubatura.tavola", "tavola_cubatura_testo": "cubatura.tavola_dichiarata",
    "tariffa_tacal": "cubatura.tariffa", "classi_diametriche": "cubatura.classi",
    "comune": "inquadramento.comune", "localita": "inquadramento.localita", "provincia": "inquadramento.provincia",
    "particelle": "inquadramento.particelle", "superficie_intervento_ha": "inquadramento.superficie_intervento_ha",
    "superficie_catastale_ha": "inquadramento.superficie_catastale_ha",
}


def percorso_dubbio(campo: str) -> str:
    return ALIAS_DUBBI.get(campo, campo)


def _norm(v: Any) -> Any:
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if hasattr(v, "value") and not isinstance(v, (str, int, float, bool)):
        return v.value
    return v


def appiattisci(d: Any, prefisso: str = "") -> dict[str, Any]:
    """{'a': {'b': [1, {'c': 2}]}} -> {'a.b.0': 1, 'a.b.1.c': 2}; ignora valori vuoti."""
    piatto: dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            piatto.update(appiattisci(v, f"{prefisso}.{k}" if prefisso else str(k)))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            piatto.update(appiattisci(v, f"{prefisso}.{i}"))
    elif d not in (None, "", [], {}):
        piatto[prefisso] = _norm(d)
    return piatto


def _corrisponde(chiave: str, percorso: str) -> bool:
    return f".{percorso}." in f".{chiave}."


def valori_di(dati: dict, percorso: str) -> dict[str, Any]:
    return {k: v for k, v in appiattisci(dati).items() if _corrisponde(k, percorso)}


def campo_cambiato(vecchi: dict, nuovi: dict, campo_dubbio: str) -> bool:
    p = percorso_dubbio(campo_dubbio)
    return valori_di(_normalizza(vecchi or {}), p) != valori_di(_normalizza(nuovi or {}), p)


def dati_estratti(grezza: dict) -> dict | None:
    """Ricostruisce la pratica come l'aveva letta l'AI (anche da estrazioni salvate con uno schema precedente)."""
    from .estrazione import Estrazione, in_pratica
    if not grezza:
        return None
    completa = dict(grezza)
    for nome, info in Estrazione.model_fields.items():
        if nome not in completa:
            completa[nome] = [] if get_origin(info.annotation) is list else None
    try:
        return _normalizza(in_pratica(Estrazione.model_validate(completa)))
    except (ValidationError, ValueError):
        return None


def _normalizza(dati: dict) -> dict:
    """Passa dal modello Pratica: valori predefiniti, tipi e date uguali per i due lati del confronto."""
    from .models import Pratica
    try:
        return Pratica.model_validate(dati).model_dump(mode="json", exclude_none=True)
    except ValidationError:
        return dati


def elenco_correzioni(estratti: dict | None, attuali: dict) -> list[tuple[str, str, str]]:
    """[(dato, valore letto dai PDF, valore attuale)] per i dati che l'istruttore ha cambiato."""
    if not estratti:
        return []
    a = {k: v for k, v in appiattisci(estratti).items() if not k.startswith(ESCLUSI)}
    b = {k: v for k, v in appiattisci(_normalizza(attuali)).items() if not k.startswith(ESCLUSI)}
    righe = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            righe.append((etichetta_percorso(k), _testo(a.get(k)), _testo(b.get(k))))
    return righe


def _testo(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "sì" if v else "no"
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    return str(v)


def etichetta_percorso(chiave: str) -> str:
    from .web.moduli import ETICHETTE
    parti = []
    for p in chiave.split("."):
        parti.append(f"n. {int(p) + 1}" if p.isdigit() else ETICHETTE.get(p, p.replace("_", " ")))
    return " → ".join(parti)
