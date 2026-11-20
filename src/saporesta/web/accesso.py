"""Accesso con password al portale (attivo solo se è impostata SAPORESTA_PASSWORD).

La sessione è un cookie firmato con HMAC: "<istante>.<firma>". La chiave di firma deriva da
un segreto casuale salvato accanto alle impostazioni (permessi 600) e dalla password, quindi
cambiare la password invalida tutte le sessioni aperte.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from .. import impostazioni

NOME_COOKIE = "saporesta_sessione"
DURATA_SECONDI = 12 * 3600


def password() -> str | None:
    return os.environ.get("SAPORESTA_PASSWORD") or None


def attivo() -> bool:
    return password() is not None


def _segreto() -> bytes:
    p = impostazioni.percorso().with_name("segreto_sessione")
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(secrets.token_hex(32))
    return p.read_text().strip().encode()


def _chiave() -> bytes:
    return hmac.new(_segreto(), (password() or "").encode(), hashlib.sha256).digest()


def _firma(istante: str) -> str:
    return hmac.new(_chiave(), istante.encode(), hashlib.sha256).hexdigest()


def crea_cookie(adesso: float | None = None) -> str:
    istante = str(int(time.time() if adesso is None else adesso))
    return f"{istante}.{_firma(istante)}"


def cookie_valido(valore: str | None, adesso: float | None = None) -> bool:
    if not valore or "." not in valore:
        return False
    istante, firma = valore.split(".", 1)
    if not istante.isdigit() or not hmac.compare_digest(firma, _firma(istante)):
        return False
    eta = (time.time() if adesso is None else adesso) - int(istante)
    return 0 <= eta <= DURATA_SECONDI


def password_corretta(tentativo: str) -> bool:
    attesa = password()
    if attesa is None:
        return True
    return hmac.compare_digest(tentativo.encode(), attesa.encode())


def destinazione_sicura(dopo: str | None) -> str:
    """Solo percorsi interni: niente '//host', 'http://...' o barre rovesciate."""
    if not dopo or not dopo.startswith("/") or dopo.startswith("//") or "\\" in dopo or "://" in dopo:
        return "/"
    return dopo
