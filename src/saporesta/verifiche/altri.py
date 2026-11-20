"""Soprassuoli transitori, neoformazione, boschi percorsi dal fuoco, avversità meteoriche, art. 22."""

from __future__ import annotations

from ..formato import num_breve, pct
from ..models import Pratica, Sottotipo, TipoIntervento
from ..regole import info_specie, regole
from .esito import Esito, Livello
from .fustaia import biodiversita, provvigione_minimale
from .scheda import indici_prelievo

S = Sottotipo
T = TipoIntervento


def transitorio(p: Pratica) -> list[Esito]:
    if p.intervento.tipo is not T.TRANSITORIO:
        return []
    r = regole()["transitorio"]
    sotto = set(p.intervento.sottotipi)
    esiti = []
    if S.PRIMO_AVVIAMENTO in sotto:
        rilasciati = p.scheda.polloni_rilasciati_ha if p.scheda else None
        minimo = r["primo_avviamento_piante_ha"]
        if rilasciati is None:
            esiti.append(Esito("tra.primo", "Primo taglio di avviamento", Livello.DA_VERIFICARE,
                               f"Piante/polloni rilasciati a ettaro non indicati (circa {minimo}/ha o almeno "
                               f"{r['primo_avviamento_polloni_ceppaia']} polloni per ceppaia, oltre alle matricine).", "art. 41 c. 3",
                               integrazione="Numero di piante o polloni rilasciati a ettaro dopo il primo taglio di avviamento"))
        else:
            livello = Livello.OK if rilasciati >= minimo * 0.95 else Livello.ATTENZIONE
            esiti.append(Esito("tra.primo", "Primo taglio di avviamento", livello,
                               f"Rilasciati {num_breve(rilasciati, 0)} soggetti/ha (riferimento {minimo}/ha o "
                               f"{r['primo_avviamento_polloni_ceppaia']} polloni per ceppaia).", "art. 41 c. 3"))
    if S.SUCCESSIVI_AVVIAMENTO in sotto:
        prel = indici_prelievo(p).get("prelievo_volume")
        massimo = r["successivi_max_prelievo_pct"] / 100
        if prel is None:
            esiti.append(Esito("tra.successivi", "Tagli di avviamento successivi", Livello.DA_VERIFICARE,
                               "Percentuale di prelievo della massa non ricavabile.", "art. 41 c. 4"))
        else:
            livello = Livello.OK if prel <= massimo + 1e-9 else Livello.NON_CONFORME
            esiti.append(Esito("tra.successivi", "Tagli di avviamento successivi", livello,
                               f"Prelievo {pct(prel)} della massa (massimo {pct(massimo, 0)}).", "art. 41 c. 4"))
    if S.CONVERSIONE in sotto or S.RINNOVAZIONE in sotto:
        pop = p.intervento.popolamento
        info = info_specie(pop.specie_prevalente) or {}
        turno = regole()["ceduo"]["turni_minimi"].get(info.get("turno", ""), None)
        eta = pop.eta_min
        minima, _ = provvigione_minimale(p)
        prima = indici_prelievo(p).get("provvigione_prima")
        cond_eta = turno is not None and eta is not None and eta > r["rinnovazione_multiplo_turno"] * turno
        cond_prov = minima is not None and prima is not None and prima > minima
        if cond_eta or cond_prov:
            motivo = (f"età {eta} anni oltre {r['rinnovazione_multiplo_turno']}× il turno ({turno})" if cond_eta
                      else f"provvigione {num_breve(prima, 1)} m³/ha oltre la minimale ({num_breve(minima)})")
            esiti.append(Esito("tra.rinnovazione", "Taglio di rinnovazione / conversione", Livello.OK,
                               f"Condizione soddisfatta: {motivo}.", "art. 41 c. 5"))
        else:
            esiti.append(Esito("tra.rinnovazione", "Taglio di rinnovazione / conversione", Livello.ATTENZIONE,
                               "Non risultano né l'età (4 volte il turno) né la provvigione minimale: ammissibile solo in presenza di "
                               "incipiente senescenza e deperimento, da documentare.", "art. 41 cc. 5, 7",
                               integrazione="Documentazione dei requisiti per il taglio di rinnovazione (età, provvigione o stato di senescenza e deperimento, art. 41 cc. 5 e 7)"))
    esiti.append(Esito("tra.divieto_ceduo", "Divieto di riconversione a ceduo", Livello.INFO,
                       "È vietato riconvertire in cedui i soprassuoli transitori.", "art. 41 cc. 1, 8",
                       prescrizione="È vietata la riconversione a ceduo del soprassuolo transitorio; i tagli dovranno preservare le specie sporadiche (art. 41)."))
    return esiti + biodiversita(p)


def neoformazione(p: Pratica) -> list[Esito]:
    if p.intervento.tipo is not T.NEOFORMAZIONE:
        return []
    d = p.scheda.diametro_medio_cm if p.scheda else None
    if d is None:
        return [Esito("neo.diametro", "Soprassuolo di neoformazione", Livello.DA_VERIFICARE,
                      "Diametro medio non indicato: l'autorizzazione è prevista per diametro medio ≥ 10 cm.", "art. 4 c. 1",
                      integrazione="Diametro medio a petto d'uomo del soprassuolo di neoformazione")]
    if d >= 10:
        return [Esito("neo.diametro", "Soprassuolo di neoformazione", Livello.INFO,
                      f"Diametro medio {num_breve(d, 1)} cm ≥ 10 cm: la Regione valuta la forma di governo più adeguata "
                      "(condizioni stazionali, capacità pollonifera, perpetuazione delle specie).", "art. 4 c. 1")]
    return [Esito("neo.diametro", "Soprassuolo di neoformazione", Livello.ATTENZIONE,
                  f"Diametro medio {num_breve(d, 1)} cm < 10 cm: se il soprassuolo non costituisce bosco basta la comunicazione.",
                  "art. 4 c. 2")]


def incendio(p: Pratica) -> list[Esito]:
    if p.intervento.tipo is not T.INCENDIO:
        return []
    esiti = [Esito("inc.l353", "Divieti L. 353/2000", Livello.ATTENZIONE,
                   "Si applicano i divieti, le prescrizioni e le sanzioni dell'art. 10 L. 353/2000; serve il certificato del "
                   "catasto incendi del Comune.", "art. 49 cc. 1, 6")]
    esiti.append(Esito("inc.modalita", "Modalità di ricostituzione", Livello.INFO,
                       "Cedui: succisione tempestiva entro la stagione silvana successiva; fustaie di conifere: rilascio delle piante "
                       "vive con strobili; fustaie non danneggiate: criteri degli artt. 38-39.", "art. 49 cc. 2-5",
                       prescrizione="Nelle fustaie di conifere dovranno essere rilasciate tutte le piante vive provviste di strobili con "
                       "funzione di porta seme; nei cedui la succisione dovrà avvenire entro la stagione silvana successiva (art. 49)."))
    return esiti


def avversita(p: Pratica) -> list[Esito]:
    if p.intervento.tipo is not T.AVVERSITA:
        return []
    if p.martellata is None:
        return [Esito("avv.martellata", "Piedilista di martellata", Livello.DA_VERIFICARE,
                      "Il taglio è ammesso per fusti troncati, sradicati, schiantati o senza possibilità di ripresa, indicati in un "
                      "piedilista di martellata.", "art. 50 c. 1",
                      integrazione="Piedilista di martellata delle piante danneggiate da prelevare, con valutazione quantitativa delle asportazioni")]
    return [Esito("avv.martellata", "Piedilista di martellata", Livello.OK,
                  f"Martellate {p.martellata.n_piante} piante danneggiate.", "art. 50 c. 1")]


def art22(p: Pratica) -> list[Esito]:
    if p.intervento.tipo is not T.ART22:
        return []
    esiti = [Esito("a22.finalita", "Tagli per sicurezza di infrastrutture", Livello.INFO,
                   "Tagli consentiti in qualsiasi periodo dell'anno per la manutenzione e la sicurezza di manufatti, elettrodotti, "
                   "viabilità e opere idrauliche.", "art. 29 c. 1 lett. c")]
    if S.ELETTRODOTTI in p.intervento.sottotipi:
        esiti.append(Esito("a22.servitu", "Servitù di elettrodotto", Livello.DA_VERIFICARE,
                           "Verificare che le piante ricadano nella fascia di servitù dell'elettrodotto (art. 121 R.D. 1775/33).",
                           integrazione="Planimetria della fascia di servitù dell'elettrodotto con le piante da abbattere"))
    return esiti


TUTTE = [transitorio, neoformazione, incendio, avversita, art22]
