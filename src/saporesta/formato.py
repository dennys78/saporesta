"""Formattazione all'italiana di numeri, superfici e date."""

from __future__ import annotations

from datetime import date

MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def num(valore: float | None, decimali: int = 2) -> str:
    """1234.5 -> '1.234,50'. None -> '—'."""
    if valore is None:
        return "—"
    testo = f"{valore:,.{decimali}f}"
    return testo.replace(",", "X").replace(".", ",").replace("X", ".")


def num_breve(valore: float | None, max_decimali: int = 2) -> str:
    """Come num() ma senza zeri finali: 51.50 -> '51,5', 27.0 -> '27'."""
    if valore is None:
        return "—"
    testo = num(valore, max_decimali)
    if "," in testo:
        testo = testo.rstrip("0").rstrip(",")
    return testo


def pct(frazione: float | None, decimali: int = 1) -> str:
    """0.2059 -> '20,6%'."""
    if frazione is None:
        return "—"
    return f"{num_breve(frazione * 100, decimali)}%"


def ha_catastale(ettari: float | None) -> str:
    """Superficie in formato catastale ettari.are.centiare: 0.9990 -> '00.99.90'."""
    if ettari is None:
        return "—"
    centiare = round(ettari * 10000)
    ha, resto = divmod(centiare, 10000)
    are, ca = divmod(resto, 100)
    return f"{ha:02d}.{are:02d}.{ca:02d}"


def data(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def data_estesa(d: date | None) -> str:
    return f"{d.day} {MESI[d.month - 1]} {d.year}" if d else "—"


def elenco(voci: list[str], congiunzione: str = "e") -> str:
    voci = [v for v in voci if v]
    if not voci:
        return ""
    if len(voci) == 1:
        return voci[0]
    return f"{', '.join(voci[:-1])} {congiunzione} {voci[-1]}"
