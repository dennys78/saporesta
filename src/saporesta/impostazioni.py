"""Chiavi API e fornitore AI per l'estrazione, impostati dall'istruttore nel portale.

Le chiavi sono salvate in un file locale leggibile solo dall'utente del Mac
(~/.config/saporesta/impostazioni.json, permessi 600), fuori dalla cartella del progetto
e quindi fuori da git. La pagina web non le mostra mai per intero.
Se nel file non c'è una chiave attiva si usano le variabili d'ambiente
ANTHROPIC_API_KEY oppure GEMINI_API_KEY / GOOGLE_API_KEY.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Fornitore = Literal["gemini", "anthropic"]

NOMI_FORNITORE = {"gemini": "Google Gemini", "anthropic": "Anthropic Claude"}
MODELLO_ANTHROPIC = "claude-opus-5-5"


class Chiave(BaseModel):
    id: str
    fornitore: Fornitore
    etichetta: str
    valore: str
    modello: str | None = None
    a_pagamento: bool = False
    da_ambiente: bool = Field(False, exclude=True)

    @property
    def mascherata(self) -> str:
        return maschera(self.valore)

    @property
    def descrizione(self) -> str:
        modello = f", {self.modello_effettivo}" if self.modello_effettivo else ""
        return f"{NOMI_FORNITORE[self.fornitore]} – {self.etichetta}{modello}"

    @property
    def modello_effettivo(self) -> str | None:
        if self.fornitore == "anthropic":
            return self.modello or MODELLO_ANTHROPIC
        return self.modello


class Impostazioni(BaseModel):
    chiavi: list[Chiave] = Field(default_factory=list)
    chiave_attiva: str | None = None
    logo: str = "01"


def maschera(valore: str) -> str:
    return f"••••••{valore[-4:]}" if len(valore) > 8 else "••••"


def percorso() -> Path:
    return Path(os.environ.get("SAPORESTA_CONFIG", Path.home() / ".config" / "saporesta" / "impostazioni.json"))


def carica() -> Impostazioni:
    p = percorso()
    if not p.exists():
        return Impostazioni()
    return Impostazioni.model_validate_json(p.read_text(encoding="utf-8"))


def salva(imp: Impostazioni) -> None:
    p = percorso()
    p.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(p.parent, 0o700)
    temporaneo = p.with_suffix(".tmp")
    # file creato già con permessi 600, poi rinominato: la chiave non è mai leggibile da altri
    fd = os.open(temporaneo, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(imp.model_dump(), ensure_ascii=False, indent=2))
    os.replace(temporaneo, p)


def aggiungi(fornitore: Fornitore, etichetta: str, valore: str, a_pagamento: bool = False,
             modello: str | None = None) -> Chiave:
    valore = valore.strip()
    if not valore:
        raise ValueError("Chiave vuota.")
    imp = carica()
    chiave = Chiave(id=secrets.token_hex(4), fornitore=fornitore, etichetta=etichetta.strip() or NOMI_FORNITORE[fornitore],
                    valore=valore, a_pagamento=a_pagamento, modello=modello)
    imp.chiavi.append(chiave)
    if imp.chiave_attiva is None:
        imp.chiave_attiva = chiave.id
    salva(imp)
    return chiave


def trova(id_: str) -> Chiave:
    for c in carica().chiavi:
        if c.id == id_:
            return c
    raise KeyError(id_)


def aggiorna(id_: str, **campi) -> None:
    imp = carica()
    for i, c in enumerate(imp.chiavi):
        if c.id == id_:
            imp.chiavi[i] = c.model_copy(update=campi)
            salva(imp)
            return
    raise KeyError(id_)


def attiva(id_: str) -> None:
    imp = carica()
    if not any(c.id == id_ for c in imp.chiavi):
        raise KeyError(id_)
    imp.chiave_attiva = id_
    salva(imp)


def rimuovi(id_: str) -> None:
    imp = carica()
    imp.chiavi = [c for c in imp.chiavi if c.id != id_]
    if imp.chiave_attiva == id_:
        imp.chiave_attiva = imp.chiavi[0].id if imp.chiavi else None
    salva(imp)


def imposta_logo(logo: str) -> None:
    imp = carica()
    imp.logo = logo
    salva(imp)


def chiave_attiva() -> Chiave | None:
    imp = carica()
    for c in imp.chiavi:
        if c.id == imp.chiave_attiva:
            return c
    if os.environ.get("ANTHROPIC_API_KEY"):
        return Chiave(id="ambiente", fornitore="anthropic", etichetta="variabile ANTHROPIC_API_KEY",
                      valore=os.environ["ANTHROPIC_API_KEY"], da_ambiente=True)
    for nome in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(nome):
            return Chiave(id="ambiente", fornitore="gemini", etichetta=f"variabile {nome}",
                          valore=os.environ[nome], modello=os.environ.get("SAPORESTA_GEMINI_MODELLO"), da_ambiente=True)
    return None
