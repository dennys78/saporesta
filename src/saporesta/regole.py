"""Caricamento dei parametri del Regolamento 4/2024 da regole.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

FILE_REGOLE = Path(__file__).with_name("regole.yaml")


@lru_cache(maxsize=1)
def regole() -> dict[str, Any]:
    with FILE_REGOLE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def info_specie(nome: str | None) -> dict[str, str] | None:
    """Gruppo di turno e categoria di provvigione per una specie.

    Cerca prima il nome esatto, poi la voce più lunga contenuta nel nome
    (es. 'Pino laricio calabro' -> 'pino laricio').
    """
    if not nome:
        return None
    tabella: dict[str, dict[str, str]] = regole()["specie"]
    chiave = nome.strip().lower()
    if chiave in tabella:
        return tabella[chiave]
    candidati = [k for k in tabella if k in chiave]
    if not candidati:
        return None
    return tabella[max(candidati, key=len)]
