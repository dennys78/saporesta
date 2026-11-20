"""Motore delle verifiche: esegue tutti i controlli e propone l'esito dell'istruttoria."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..models import Pratica
from . import altri, ceduo, fustaia, generali, scheda
from .esito import Esito, Livello

__all__ = ["Esito", "Livello", "Proposta", "Risultato", "esegui"]


class Proposta(str, Enum):
    AUTORIZZABILE = "autorizzabile"
    INTEGRAZIONI = "richiesta integrazioni"
    DA_COMPLETARE = "istruttoria da completare"


@dataclass
class Risultato:
    esiti: list[Esito] = field(default_factory=list)

    def per_livello(self, *livelli: Livello) -> list[Esito]:
        return [e for e in self.esiti if e.livello in livelli]

    @property
    def integrazioni(self) -> list[str]:
        """Elementi da chiedere all'istante (documenti e dati)."""
        voci: list[str] = []
        for e in self.esiti:
            if e.integrazione and e.livello in (Livello.NON_CONFORME, Livello.DA_VERIFICARE, Livello.ATTENZIONE) \
                    and e.integrazione not in voci:
                voci.append(e.integrazione)
        return voci

    @property
    def rilievi(self) -> list[Esito]:
        """Non conformità che non si risolvono con un documento: richiedono controdeduzioni."""
        return [e for e in self.esiti if e.livello is Livello.NON_CONFORME and not e.integrazione]

    @property
    def prescrizioni(self) -> list[str]:
        voci: list[str] = []
        for e in self.esiti:
            if e.prescrizione and e.prescrizione not in voci:
                voci.append(e.prescrizione)
        return voci

    @property
    def da_completare(self) -> list[Esito]:
        """Controlli che spettano all'istruttore (dato mancante senza richiesta all'istante)."""
        return [e for e in self.esiti if e.livello is Livello.DA_VERIFICARE and not e.integrazione]

    @property
    def proposta(self) -> Proposta:
        if any(e.bloccante for e in self.esiti):
            return Proposta.INTEGRAZIONI
        if self.da_completare:
            return Proposta.DA_COMPLETARE
        return Proposta.AUTORIZZABILE


def esegui(pratica: Pratica) -> Risultato:
    controlli = [
        *generali.TUTTE,
        scheda.scheda,
        ceduo.verifica,
        fustaia.verifica,
        *altri.TUTTE,
    ]
    risultato = Risultato()
    for controllo in controlli:
        risultato.esiti.extend(controllo(pratica))
    return risultato
