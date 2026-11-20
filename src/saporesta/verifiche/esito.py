from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Livello(str, Enum):
    OK = "ok"
    INFO = "info"
    ATTENZIONE = "attenzione"  # da valutare, non blocca
    DA_VERIFICARE = "da verificare"  # dato mancante o controllo non ancora fatto
    NON_CONFORME = "non conforme"  # blocca l'autorizzazione

    @property
    def simbolo(self) -> str:
        return {
            "ok": "✔",
            "info": "ℹ",
            "attenzione": "⚠",
            "da verificare": "?",
            "non conforme": "✘",
        }[self.value]


@dataclass
class Esito:
    codice: str
    titolo: str
    livello: Livello
    messaggio: str
    articolo: str | None = None
    # Testo da inserire nella richiesta di integrazioni (documenti/dati che
    # l'istante deve produrre). Se assente e il livello è NON_CONFORME, la
    # comunicazione chiederà controdeduzioni sul messaggio.
    integrazione: str | None = None
    # Testo da aggiungere alle prescrizioni dell'autorizzazione.
    prescrizione: str | None = None

    @property
    def bloccante(self) -> bool:
        """True se impedisce di proporre l'autorizzazione allo stato degli atti."""
        return self.livello is Livello.NON_CONFORME or (
            self.livello in (Livello.DA_VERIFICARE, Livello.ATTENZIONE) and self.integrazione is not None
        )
