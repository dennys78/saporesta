"""Tavole di cubatura: ricalcolo del volume di una pianta con la tavola dichiarata nell'istanza.

Banche dati (estratte dai PDF con strumenti/estrai_tavole.py e verificate sulle tavole stampate):
- tabacchi_2011    Tabacchi et al. 2011, INFC: v = b1 + b2·d²h (+ b3·d), v in dm³
- castellani_1984  Castellani et al. 1984, ISAFA-IFNI: polinomi in d e h, tavole per fustaia e per ceduo, v in m³
- tacal_2016       TaCAL 2016, tariffe a una entrata della Calabria: 9 tariffe per specie, d 7-100 cm
Le altre tavole (Emilia-Romagna, Trento, tavole locali) non hanno ricalcolo automatico.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CARTELLA = Path(__file__).with_name("tavole")

NOMI_TAVOLE = {
    "tabacchi_2011": "Tabacchi et al. (2011) – tavole INFC nazionali a doppia entrata",
    "castellani_1984": "Castellani et al. (1984) – tavole ISAFA-IFNI a doppia entrata",
    "tacal_2016": "TaCAL (2016) – tariffe a una entrata delle specie forestali della Calabria",
    "emilia_romagna_2002": "Bertani (2002) – tavole della massa legnosa in piedi dell'Emilia-Romagna",
    "trento_sff": "Scrinzi et al. – modelli dendrometrici della Provincia di Trento",
    "altra": "tavola locale o non presente nella banca dati",
}
CON_RICALCOLO = {"tabacchi_2011", "castellani_1984", "tacal_2016"}
REGIONALI_ALTRE = {"emilia_romagna_2002": "Emilia-Romagna", "trento_sff": "Provincia di Trento"}


@lru_cache(maxsize=None)
def dati(tavola: str) -> dict:
    return json.loads((CARTELLA / f"{tavola}.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ specie -> tavola
# (parole chiave nel nome della specie, chiave nella banca dati, nota)

MAPPA_TABACCHI = [
    (("abete bianco",), "C-AbiesAlba", ""), (("abete rosso",), "C-PiceaAbies", ""),
    (("cipress",), "C-Cupressus", ""), (("larice",), "C-Larix", ""), (("cembro",), "C-PinusCembra", ""),
    (("aleppo",), "C-PinusHalepensis", ""), (("laricio",), "C-PinusLaricio", ""), (("pino nero",), "C-PinusNigra", ""),
    (("marittimo",), "C-PinusPinaster", ""), (("domestico",), "C-PinusPinea", ""),
    (("silvestre",), "C-PinusSylvestris", ""), (("strobo", "radiata", "esotic", "allocton"), "C-PinuzEsotici", ""),
    (("douglas",), "C-Pseudotsuga", ""), (("acer",), "L-Acer", ""), (("ontan",), "L-Alnus", ""),
    (("carpin", "orniello", "ostrya"), "L-Carpinus", ""), (("castagn",), "L-Castanea", ""),
    (("eucalipt", "eucalitt"), "L-Eucalyptus", ""), (("faggio",), "L-Fagus", ""), (("frassin",), "L-Fraxinus", ""),
    (("cerro",), "L-QuercusCerris", ""),
    (("farnetto", "rovere", "farnia", "quercia", "querce"), "L-QuercusCerris",
     "nelle tavole INFC le querce caducifoglie diverse da cerro e roverella si cubano con il cerro"),
    (("leccio",), "L-QuercusIlex", ""), (("sughera",), "L-QuercusIlex", "la sughera si cuba con il leccio"),
    (("roverella",), "L-QuercusPubescens", ""), (("robinia",), "L-Robinia", ""), (("salic", "salice"), "L-Salix", ""),
]

MAPPA_CASTELLANI = [
    (("abete rosso",), "abete rosso", ""), (("abete bianco",), "abete bianco", ""), (("larice",), "larice", ""),
    (("silvestre",), "pino silvestre", ""), (("laricio", "pino nero"), "pini neri", "il pino laricio si cuba con la tavola dei pini neri"),
    (("domestico",), "pino domestico", ""), (("marittimo",), "pino marittimo", ""), (("aleppo",), "pino d'Aleppo", ""),
    (("faggio",), "faggio", ""), (("cerro", "roverella", "farnetto", "rovere", "farnia", "quercia", "querce", "leccio"), "quercie", ""),
    (("eucalipt", "eucalitt"), "eucalitti", ""), (("pioppo", "pioppi"), "pioppi", ""), (("castagn",), "castagno", ""),
]

MAPPA_TACAL = [
    (("abete bianco",), "Abete bianco", ""), (("laricio", "pino nero"), "Pino laricio", ""),
    (("aleppo",), "Pino d'aleppo", ""), (("domestico",), "Pino domestico", ""), (("marittimo",), "Pino marittimo", ""),
    (("strobo", "radiata", "esotic", "allocton"), "Pini alloctoni", ""), (("douglas",), "Douglasia", ""),
    (("cipress",), "Cipressi", ""), (("faggio",), "Faggio", ""), (("leccio",), "Leccio", ""),
    (("sughera",), "Leccio", "TaCAL: tariffe del leccio valide anche per la sughera"),
    (("roverella",), "Roverella", ""), (("cerro",), "Cerro", ""),
    (("farnetto", "rovere", "farnia", "quercia", "querce"), "Cerro",
     "TaCAL: tariffe del cerro valide per tutte le querce caducifoglie esclusa la roverella"),
    (("castagn",), "Castagno", ""), (("ontan",), "Ontani", ""), (("acer",), "Aceri", ""), (("frassin",), "Frassini", ""),
    (("carpin", "orniello", "ostrya"), "Carpini", ""), (("robinia",), "Robinia", ""), (("eucalipt", "eucalitt"), "Eucalipti", ""),
]


@dataclass
class Risoluzione:
    chiave: str | None
    descrizione: str
    nota: str = ""
    governo_tavola: str | None = None  # Castellani: "fustaia" o "ceduo"


def _cerca(mappa, nome: str) -> tuple[str, str] | None:
    n = nome.lower()
    for parole, chiave, nota in mappa:
        if any(p in n for p in parole):
            return chiave, nota
    return None


def risolvi(tavola: str, specie: str | None, governo: str) -> Risoluzione:
    """Individua nella banca dati la tavola della specie. governo: 'fustaia' o 'ceduo'."""
    if tavola not in CON_RICALCOLO:
        return Risoluzione(None, NOMI_TAVOLE.get(tavola, tavola))
    if not specie:
        return Risoluzione(None, "specie non indicata")
    if tavola == "tabacchi_2011":
        trovata = _cerca(MAPPA_TABACCHI, specie)
        if trovata is None:
            altre = "C-zPiccoleConifere_IT" if any(p in specie.lower() for p in ("pino", "abete", "conifer")) else "L-zAltreLatifoglie"
            trovata = (altre, f"«{specie}» non ha una tavola propria: si usa quella delle {dati(tavola)[altre]['nome'].lower()}")
        chiave, nota = trovata
        return Risoluzione(chiave, f"{dati(tavola)[chiave]['nome']} ({dati(tavola)[chiave]['scientifico']})", nota)
    if tavola == "castellani_1984":
        trovata = _cerca(MAPPA_CASTELLANI, specie)
        tavole = dati(tavola)
        if trovata is None:
            if governo == "ceduo":
                return Risoluzione("altre latifoglie (ceduo)", "altre latifoglie (ceduo)",
                                   f"«{specie}» non ha una tavola propria: si usa quella delle altre latifoglie (ceduo)", "ceduo")
            return Risoluzione(None, f"nessuna tavola Castellani per «{specie}»")
        base, nota = trovata
        if base in tavole:  # tavola unica (conifere)
            return Risoluzione(base, base, nota, tavole[base]["governo"])
        preferita, alternativa = f"{base} ({governo})", f"{base} ({'fustaia' if governo == 'ceduo' else 'ceduo'})"
        if preferita in tavole:
            return Risoluzione(preferita, preferita, nota, governo)
        if alternativa in tavole:
            return Risoluzione(alternativa, alternativa,
                               (nota + "; " if nota else "") + f"esiste solo la tavola per il {alternativa.split('(')[1][:-1]}",
                               tavole[alternativa]["governo"])
        return Risoluzione(None, f"nessuna tavola Castellani per «{specie}»")
    trovata = _cerca(MAPPA_TACAL, specie) or ("Altre latifoglie", f"«{specie}» non ha tariffe proprie: si usano le altre latifoglie")
    chiave, nota = trovata
    return Risoluzione(chiave, chiave, nota)


# ------------------------------------------------------------------------ volumi

def volume_doppia_entrata(tavola: str, chiave: str, d: float, h: float) -> float:
    """Volume in m³ di una pianta di diametro d (cm) e altezza h (m)."""
    if tavola == "tabacchi_2011":
        b = dati(tavola)[chiave]["b"]
        return (b[0] + b[1] * d * d * h + (b[2] * d if len(b) > 2 else 0.0)) / 1000
    t = dati(tavola)[chiave]
    c = t["coeff"]
    if t["forma"] == "potenza":
        return c["a"] * d ** c["b1"] * h ** c["b2"]
    return sum(c[nome] * d ** ed * h ** eh for nome, ed, eh in t["termini"])


def tariffa_tacal(chiave: str, tariffa: int, d: float) -> tuple[float, float] | None:
    """(h, v in m³) della tariffa TaCAL al diametro d; interpolazione lineare tra i diametri interi."""
    tabella = dati("tacal_2016")[chiave]["tariffe"].get(str(tariffa))
    if tabella is None or d < 7 or d > 100:
        return None
    sotto, sopra = math.floor(d), math.ceil(d)
    a, b = tabella.get(str(sotto)), tabella.get(str(sopra))
    if a is None or b is None:
        return None
    if sotto == sopra:
        return a[0], a[1]
    f = d - sotto
    return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f


def tariffa_piu_vicina(chiave: str, coppie_d_h: list[tuple[float, float]]) -> int | None:
    """Tariffa TaCAL le cui altezze sono più vicine a quelle dichiarate (minimi quadrati)."""
    migliore, errore_min = None, None
    for t in range(1, 10):
        errori = []
        for d, h in coppie_d_h:
            valori = tariffa_tacal(chiave, t, d)
            if valori:
                errori.append((valori[0] - h) ** 2)
        if errori:
            e = sum(errori) / len(errori)
            if errore_min is None or e < errore_min:
                migliore, errore_min = t, e
    return migliore
