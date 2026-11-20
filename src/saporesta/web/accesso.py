"""Accesso al portale con nome utente e password.

L'accesso è attivo se è impostata SAPORESTA_PASSWORD (utente di emergenza "admin") oppure se nella
pagina Impostazioni è stato creato almeno un utente (vedi saporesta.utenti).

La sessione è un cookie firmato con HMAC: "<utente>.<istante>.<firma>". La chiave di firma deriva da
un segreto casuale salvato accanto alle impostazioni (permessi 600) e dall'impronta della password
dell'utente, quindi cambiare la password o eliminare l'utente invalida le sue sessioni aperte.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from .. import impostazioni, utenti

NOME_COOKIE = "saporesta_sessione"
DURATA_SECONDI = 12 * 3600


def attivo() -> bool:
    return utenti.attivo()


def _segreto() -> bytes:
    p = impostazioni.percorso().with_name("segreto_sessione")
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(secrets.token_hex(32))
    return p.read_text().strip().encode()


def _firma(utente: str, istante: str) -> str | None:
    segreto_utente = utenti.segreto_utente(utente)
    if segreto_utente is None:
        return None
    chiave = hmac.new(_segreto(), segreto_utente.encode(), hashlib.sha256).digest()
    return hmac.new(chiave, f"{utente}.{istante}".encode(), hashlib.sha256).hexdigest()


def crea_cookie(utente: str = utenti.UTENTE_EMERGENZA, adesso: float | None = None) -> str:
    istante = str(int(time.time() if adesso is None else adesso))
    return f"{utente}.{istante}.{_firma(utente, istante)}"


def utente_da_cookie(valore: str | None, adesso: float | None = None) -> str | None:
    """Nome dell'utente della sessione, o None se il cookie manca, è manomesso o scaduto."""
    if not valore or valore.count(".") < 2:
        return None
    utente, istante, firma = valore.rsplit(".", 2)
    if not istante.isdigit():
        return None
    attesa = _firma(utente, istante)
    if attesa is None or not hmac.compare_digest(firma, attesa):
        return None
    eta = (time.time() if adesso is None else adesso) - int(istante)
    return utente if 0 <= eta <= DURATA_SECONDI else None


def cookie_valido(valore: str | None, adesso: float | None = None) -> bool:
    return utente_da_cookie(valore, adesso) is not None


def destinazione_sicura(dopo: str | None) -> str:
    """Solo percorsi interni: niente '//host', 'http://...' o barre rovesciate."""
    if not dopo or not dopo.startswith("/") or dopo.startswith("//") or "\\" in dopo or "://" in dopo:
        return "/"
    return dopo
