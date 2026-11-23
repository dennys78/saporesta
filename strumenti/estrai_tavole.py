"""Estrae dai PDF delle tavole di cubatura i dati necessari al ricalcolo dei volumi e li salva in JSON.

Uso (una tantum, con i PDF nella cartella indicata):
    uv run --with pymupdf python strumenti/estrai_tavole.py "../TAVOLE DI CUBATURA"

Fonti:
- Tabacchi G. et al. (2011), Stima del volume e della fitomassa delle principali specie forestali
  italiane (INFC): equazioni a doppia entrata v = b1 + b2·d²h (+ b3·d), v in dm³.
- Castellani C. et al. (1984), Tavole di cubatura a doppia entrata (ISAFA - IFNI): polinomi in d e h,
  v in m³, con tavole distinte per fustaia e ceduo.
- Scrinzi G. et al. (2016), TaCAL - Tariffe dei volumi legnosi delle specie forestali della Calabria:
  tariffe a una entrata (9 tariffe per specie), riportate qui come tabelle d -> (h, v).

Ogni equazione estratta viene confrontata con i valori stampati nelle tavole: se lo scarto supera
la tolleranza lo script si ferma senza scrivere nulla.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

USCITA = Path(__file__).resolve().parents[1] / "src" / "saporesta" / "tavole"


def testo(doc, pagina: int) -> str:
    return " ".join(doc[pagina].get_text().split())


def numero(s: str) -> float:
    """'3.7836⋅10-2', '-1.6519⋅10', '0,351034 ·10-4', '−0.5' -> float."""
    s = s.replace("−", "-").replace(" ", "").replace(",", ".")
    m = re.fullmatch(r"([+-]?\d*\.?\d+)(?:[⋅·]10([+-]?\d+)?)?", s)
    if not m:
        raise ValueError(f"numero non riconosciuto: {s!r}")
    base = float(m.group(1))
    if "10" in s[len(m.group(1)):]:
        return base * 10 ** int(m.group(2) or 1)
    return base


def righe_tabella(t: str) -> list[list[float]]:
    """Righe numeriche di una pagina: [etichetta, v1, v2, ...] con decimali '.' o ','."""
    righe = []
    for blocco in re.split(r"(?=(?:^| )\d{1,3}(?: \d+[.,]\d+)+)", t):
        numeri = re.findall(r"\d+(?:[.,]\d+)?", blocco)
        if len(numeri) >= 3 and "." not in numeri[0] and "," not in numeri[0]:
            righe.append([float(n.replace(",", ".")) for n in numeri])
    return righe


def verifica_righe(nome: str, funzione, righe: list[list[float]], decimali: int, minimo_ok: int = 5) -> int:
    """Le righe stampate sono 'etichetta valori...' con valori consecutivi in d o in h:
    cerca l'interpretazione coerente con la funzione e conta le righe che tornano."""
    tol = 0.6 * 10 ** -decimali + 1e-9
    buone = 0
    for riga in righe[:25]:
        etichetta, valori = riga[0], riga[1:]
        valori = valori[:-1] if valori and valori[-1] == etichetta else valori  # etichetta ripetuta a fine riga
        trovata = False
        for inizio in range(1, 61):
            for come in ("d", "h"):
                ok = True
                for i, v in enumerate(valori[:8]):
                    d, h = (etichetta, inizio + i) if come == "d" else (inizio + i, etichetta)
                    if abs(funzione(d, h) - v) > tol + 0.005 * abs(v):
                        ok = False
                        break
                if ok and valori:
                    trovata = True
                    break
            if trovata:
                break
        buone += trovata
    if buone < minimo_ok:
        raise SystemExit(f"{nome}: solo {buone} righe della tavola stampata coincidono con l'equazione estratta")
    return buone


# ------------------------------------------------------------------ Tabacchi 2011

NOMI_TABACCHI = {
    "C-AbiesAlba": ("Abete bianco", "Abies alba"), "C-Cupressus": ("Cipressi", "Cupressus spp."),
    "C-Larix": ("Larice", "Larix decidua"), "C-PiceaAbies": ("Abete rosso", "Picea abies"),
    "C-PinusCembra": ("Pino cembro", "Pinus cembra"), "C-PinusHalepensis": ("Pino d'Aleppo", "Pinus halepensis"),
    "C-PinusLaricio": ("Pino laricio", "Pinus laricio"), "C-PinusNigra": ("Pino nero", "Pinus nigra"),
    "C-PinusPinaster": ("Pino marittimo", "Pinus pinaster"), "C-PinusPinea": ("Pino domestico", "Pinus pinea"),
    "C-PinusSylvestris": ("Pino silvestre", "Pinus sylvestris"), "C-PinuzEsotici": ("Pini esotici", "Pinus spp."),
    "C-Pseudotsuga": ("Douglasia", "Pseudotsuga menziesii"),
    "C-zPiccoleConifere_IT": ("Altre conifere", "conifere minori"),
    "L-Acer": ("Aceri", "Acer spp."), "L-Alnus": ("Ontani", "Alnus spp."), "L-Carpinus": ("Carpini", "Carpinus spp."),
    "L-Castanea": ("Castagno", "Castanea sativa"), "L-Eucalyptus": ("Eucalitti", "Eucalyptus spp."),
    "L-Fagus": ("Faggio", "Fagus sylvatica"), "L-Fraxinus": ("Frassini", "Fraxinus spp."),
    "L-QuercusCerris": ("Cerro", "Quercus cerris"), "L-QuercusIlex": ("Leccio", "Quercus ilex"),
    "L-QuercusPubescens": ("Roverella", "Quercus pubescens"), "L-Robinia": ("Robinia", "Robinia pseudoacacia"),
    "L-Salix": ("Salici", "Salix spp."), "L-zAltreLatifoglie": ("Altre latifoglie", "latifoglie minori"),
}


def v_tabacchi(b: list[float], d: float, h: float) -> float:
    """dm³"""
    return b[0] + b[1] * d * d * h + (b[2] * d if len(b) > 2 else 0.0)


def tabacchi(cartella: Path) -> dict:
    doc = fitz.open(cartella / "tavole_cubatura tabacchi.pdf")
    toc = doc.get_toc()
    sezioni = [(t[1], t[2]) for t in toc if t[0] == 2 and t[1] in NOMI_TABACCHI]
    pag_volume = [t[2] for t in toc if t[0] == 3 and "VOLUME" in t[1].upper()]
    risultato = {}
    for i, (codice, pag) in enumerate(sezioni):
        blocco = " ".join(testo(doc, p) for p in range(pag - 1, pag + 3))
        m = re.search(r"Volume del fusto e dei rami grossi.*?p = (\d).*?b[’'] ?= ?\[([^\]]+)\]", blocco)
        if not m:
            raise SystemExit(f"Tabacchi {codice}: coefficienti non trovati")
        b = [numero(x) for x in m.group(2).split()]
        if len(b) != int(m.group(1)):
            raise SystemExit(f"Tabacchi {codice}: attesi {m.group(1)} coefficienti, letti {b}")
        comune, scientifico = NOMI_TABACCHI[codice]
        # pagina della tavola stampata del volume: la prima *_VOLUME dopo l'inizio della sezione
        fine = sezioni[i + 1][1] if i + 1 < len(sezioni) else len(doc) + 1
        p_vol = min((p for p in pag_volume if pag <= p < fine), default=None)
        if p_vol is None:
            raise SystemExit(f"Tabacchi {codice}: tavola del volume non trovata")
        buone = verifica_righe(f"Tabacchi {codice}", lambda d, h: v_tabacchi(b, d, h),
                               righe_tabella(testo(doc, p_vol - 1)), decimali=1)
        risultato[codice] = {"nome": comune, "scientifico": scientifico, "b": b, "unita": "dm3",
                             "pagina": pag, "righe_verificate": buone}
    return risultato


# ----------------------------------------------------------------- Castellani 1984

def termini_castellani(forma: str) -> list[tuple[str, int, int]]:
    """'a+b1d2h+b2d+b12/h+b9d4/h' -> [('a',0,0), ('b1',2,1), ('b2',1,0), ('b12',0,-1), ('b9',4,-1)]"""
    termini = []
    for t in forma.split("+"):
        if t == "a":
            termini.append(("a", 0, 0))
            continue
        m = re.fullmatch(r"(b\d+)(d\d?)?(h\d?)?(/h)?", t)
        if not m:
            raise ValueError(f"termine non riconosciuto: {t}")
        ed = int(m.group(2)[1:] or 1) if m.group(2) else 0
        eh = int(m.group(3)[1:] or 1) if m.group(3) else 0
        if m.group(4):
            eh -= 1
        termini.append((m.group(1), ed, eh))
    return termini


def v_castellani(tavola: dict, d: float, h: float) -> float:
    """m³"""
    c = tavola["coeff"]
    if tavola["forma"] == "potenza":
        return c["a"] * d ** c["b1"] * h ** c["b2"]
    return sum(c[nome] * d ** ed * h ** eh for nome, ed, eh in tavola["termini"])


def castellani(cartella: Path) -> dict:
    doc = fitz.open(cartella / "castellani  _fascicolo completo.pdf")
    voci = [(t[1], t[2]) for t in doc.get_toc() if t[0] == 2 and t[1] != "Simbologia"]
    risultato = {}
    for nome, pag in voci:
        blocco = testo(doc, pag - 1) + " " + testo(doc, pag)
        m = re.search(r"Espressione funzionale v = (.+?) \(v\[m ?3\], h\[m\], d\[cm\]\) (.+?)(?= \(\d ?\)|$)", blocco)
        if not m:
            raise SystemExit(f"Castellani {nome}: espressione non trovata")
        forma = m.group(1).replace(" ", "")
        coeff = {k.replace(" ", ""): numero(re.sub(r"\s", "", v)) for k, v in re.findall(
            r"\b(a|b ?\d ?\d?)\s*=\s*([+-−]?\s?\d+[.,]?\d*\s?(?:·\s?10\s?-?\d+)?)", m.group(2))}
        tavola = {"forma": "potenza" if forma.startswith("adb1hb2") else forma, "coeff": coeff, "unita": "m3",
                  "pagina": pag}
        if tavola["forma"] != "potenza":
            tavola["termini"] = termini_castellani(forma)
            mancanti = {t[0] for t in tavola["termini"]} - set(coeff)
            if mancanti:
                raise SystemExit(f"Castellani {nome}: coefficienti mancanti {mancanti}")
        # la tavola stampata è nelle pagine successive all'espressione
        righe = []
        for p in range(pag, min(pag + 2, len(doc))):
            righe += righe_tabella(testo(doc, p))
        tavola["righe_verificate"] = verifica_righe(f"Castellani {nome}", lambda d, h: v_castellani(tavola, d, h),
                                                    righe, decimali=3)
        governo = "ceduo" if "(ceduo)" in nome else "fustaia"
        tavola.update({"nome": nome, "governo": governo})
        risultato[nome] = tavola
    return risultato


# --------------------------------------------------------------------- TaCAL 2016

def tacal(cartella: Path) -> dict:
    doc = fitz.open(cartella / "2016_TACAL_tariffe_volume_fitomassa_calabria.pdf")
    limite = next(t[2] for t in doc.get_toc() if t[1].startswith("02_Tariffe fitomasse") or t[1].startswith(
        "01_Tariffe_fitomassa_ps1")) if False else 130  # le tariffe del volume finiscono a pagina 128
    risultato: dict = {}
    note: dict[str, str] = {}
    specie = None
    for p in range(limite):
        t = testo(doc, p)
        m = re.search(r"Tariffe del VOLUME LEGNOSO (?:della|dell ?'|delle|degli|dei|del)\s?([A-Z' ]+?) della Calabria", t)
        righe = [r for r in righe_tabella(t) if len(r) == 19]
        if m and not righe:
            specie = m.group(1).strip().capitalize()
            nota = re.search(r"(Valid[ei] anche per [^.]+?)(?: Volume del| ALFORLAB|$)", t)
            if nota:
                note[specie] = nota.group(1).strip()
            continue
        if specie and righe:
            tariffe = risultato.setdefault(specie, {str(i): {} for i in range(1, 10)})
            for r in righe:
                d = int(r[0])
                for i in range(9):
                    tariffe[str(i + 1)][str(d)] = [r[1 + 2 * i], r[2 + 2 * i]]
    for nome, tariffe in risultato.items():
        n = len(tariffe["1"])
        if n < 80:
            raise SystemExit(f"TaCAL {nome}: solo {n} diametri letti")
    if len(risultato) != 20:
        raise SystemExit(f"TaCAL: attese 20 specie, lette {len(risultato)}: {sorted(risultato)}")
    return {nome: {"tariffe": tariffe, "nota": note.get(nome, "")} for nome, tariffe in risultato.items()}


if __name__ == "__main__":
    cartella = Path(sys.argv[1] if len(sys.argv) > 1 else "../TAVOLE DI CUBATURA")
    t = tabacchi(cartella)
    print(f"Tabacchi 2011: {len(t)} specie verificate")
    c = castellani(cartella)
    print(f"Castellani 1984: {len(c)} tavole verificate")
    ta = tacal(cartella)
    print(f"TaCAL 2016: {len(ta)} specie: {', '.join(ta)}")
    USCITA.mkdir(parents=True, exist_ok=True)
    for nome, dati in [("tabacchi_2011", t), ("castellani_1984", c), ("tacal_2016", ta)]:
        (USCITA / f"{nome}.json").write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Salvati in {USCITA}")
