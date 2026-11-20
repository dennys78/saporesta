"""Utenti del portale con nome e password, gestiti dalla pagina Impostazioni.

Gli utenti sono salvati in utenti.json accanto alle impostazioni (permessi 600). Le password non
sono mai salvate in chiaro: si tiene solo l'impronta scrypt con un sale casuale per utente.

La password di SAPORESTA_PASSWORD resta valida come accesso di emergenza con il nome utente
"admin" (amministratore): serve per il primo accesso e se si perdono le altre password.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path

from pydantic import BaseModel, Field

from . import impostazioni

UTENTE_EMERGENZA = "admin"
LUNGHEZZA_MINIMA = 8
NOME_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


class Utente(BaseModel):
    nome: str
    impronta: str  # "scrypt$<sale hex>$<impronta hex>"
    amministratore: bool = False


class Archivio(BaseModel):
    utenti: list[Utente] = Field(default_factory=list)


class ErroreUtenti(ValueError):
    pass


def percorso() -> Path:
    return impostazioni.percorso().with_name("utenti.json")


def password_emergenza() -> str | None:
    return os.environ.get("SAPORESTA_PASSWORD") or None


def carica() -> Archivio:
    p = percorso()
    if not p.exists():
        return Archivio()
    return Archivio.model_validate_json(p.read_text(encoding="utf-8"))


def _salva(a: Archivio) -> None:
    p = percorso()
    p.parent.mkdir(parents=True, exist_ok=True)
    temporaneo = p.with_suffix(".tmp")
    fd = os.open(temporaneo, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(a.model_dump(), ensure_ascii=False, indent=2))
    os.replace(temporaneo, p)


def _impronta(password: str, sale: bytes | None = None) -> str:
    sale = sale or secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=sale, **_SCRYPT)
    return f"scrypt${sale.hex()}${h.hex()}"


def _verifica_impronta(password: str, impronta: str) -> bool:
    try:
        schema, sale, attesa = impronta.split("$")
    except ValueError:
        return False
    if schema != "scrypt":
        return False
    return hmac.compare_digest(_impronta(password, bytes.fromhex(sale)), impronta)


def normalizza(nome: str) -> str:
    return (nome or "").strip().lower()


def _controlla_password(password: str) -> None:
    if len(password) < LUNGHEZZA_MINIMA:
        raise ErroreUtenti(f"La password deve avere almeno {LUNGHEZZA_MINIMA} caratteri.")


def elenco() -> list[Utente]:
    return sorted(carica().utenti, key=lambda u: u.nome)


def trova(nome: str) -> Utente | None:
    nome = normalizza(nome)
    return next((u for u in carica().utenti if u.nome == nome), None)


def attivo() -> bool:
    """L'accesso è richiesto se c'è la password di emergenza o almeno un utente."""
    return password_emergenza() is not None or bool(carica().utenti)


def aggiungi(nome: str, password: str, amministratore: bool = False) -> Utente:
    nome = normalizza(nome)
    if nome == UTENTE_EMERGENZA:
        raise ErroreUtenti(f"Il nome «{UTENTE_EMERGENZA}» è riservato all'accesso di emergenza.")
    if not NOME_VALIDO.match(nome):
        raise ErroreUtenti("Nome utente non valido: 2-32 caratteri tra lettere minuscole, cifre, punto, trattino e _.")
    _controlla_password(password)
    a = carica()
    if any(u.nome == nome for u in a.utenti):
        raise ErroreUtenti(f"L'utente «{nome}» esiste già.")
    if password_emergenza() is None and not any(x.amministratore for x in a.utenti):
        amministratore = True  # senza password di emergenza il primo utente deve poter gestire gli altri
    u = Utente(nome=nome, impronta=_impronta(password), amministratore=amministratore)
    a.utenti.append(u)
    _salva(a)
    return u


def _resta_un_amministratore(a: Archivio) -> bool:
    return password_emergenza() is not None or any(u.amministratore for u in a.utenti) or not a.utenti


def imposta_password(nome: str, password: str) -> None:
    _controlla_password(password)
    a = carica()
    for u in a.utenti:
        if u.nome == normalizza(nome):
            u.impronta = _impronta(password)
            _salva(a)
            return
    raise KeyError(nome)


def imposta_amministratore(nome: str, amministratore: bool) -> None:
    a = carica()
    for u in a.utenti:
        if u.nome == normalizza(nome):
            u.amministratore = amministratore
            if not _resta_un_amministratore(a):
                raise ErroreUtenti("Deve restare almeno un amministratore.")
            _salva(a)
            return
    raise KeyError(nome)


def rimuovi(nome: str) -> None:
    a = carica()
    rimasti = [u for u in a.utenti if u.nome != normalizza(nome)]
    if len(rimasti) == len(a.utenti):
        raise KeyError(nome)
    nuovo = Archivio(utenti=rimasti)
    if not _resta_un_amministratore(nuovo):
        raise ErroreUtenti("Deve restare almeno un amministratore.")
    _salva(nuovo)


def autentica(nome: str, password: str) -> str | None:
    """Restituisce il nome dell'utente se nome e password sono corretti."""
    nome = normalizza(nome)
    emergenza = password_emergenza()
    if nome == UTENTE_EMERGENZA:
        if emergenza and hmac.compare_digest(password.encode(), emergenza.encode()):
            return UTENTE_EMERGENZA
        return None
    u = trova(nome)
    if u and _verifica_impronta(password, u.impronta):
        return u.nome
    return None


def segreto_utente(nome: str) -> str | None:
    """Valore che cambia quando cambia la password: entra nella firma del cookie di sessione."""
    if nome == UTENTE_EMERGENZA:
        return password_emergenza()
    u = trova(nome)
    return u.impronta if u else None


def is_amministratore(nome: str | None) -> bool:
    if nome is None:
        return not attivo()  # portale locale senza accesso: tutto consentito
    if nome == UTENTE_EMERGENZA:
        return password_emergenza() is not None
    u = trova(nome)
    return bool(u and u.amministratore)
