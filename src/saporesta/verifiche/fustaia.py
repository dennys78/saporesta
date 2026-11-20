"""Boschi governati a fustaia (Capo VI, artt. 38-40) e tutela della biodiversità (artt. 18-19)."""

from __future__ import annotations

import math

from ..formato import num_breve, pct
from ..models import Pratica, Sottotipo, TipoIntervento
from ..regole import info_specie, regole
from .esito import Esito, Livello
from .scheda import indici_prelievo

S = Sottotipo
T = TipoIntervento

NOMI_CATEGORIA = {
    "pini_querceti_mediterranei": "pini e querceti mediterranei",
    "cerro_latifoglie_mesofile_misti_pino_nero_laricio": "cerro, latifoglie mesofile, popolamenti misti, pinete di pino nero e laricio",
    "faggio_misti_montani": "faggio e popolamenti misti montani di conifere e latifoglie",
}


def provvigione_minimale(p: Pratica) -> tuple[float | None, str | None]:
    info = info_specie(p.intervento.popolamento.specie_prevalente)
    categoria = (info or {}).get("fustaia")
    if categoria is None:
        return None, None
    minima = regole()["fustaia"]["provvigione_minimale"][categoria]
    if p.vincoli.sorgenti_50m:
        minima *= 1 + regole()["fustaia"]["aumento_provvigione_sorgenti_pct"] / 100
    return minima, categoria


def prelievo_massimo(provvigione: float, minima: float) -> float | None:
    rapporto = provvigione / minima * 100
    for fascia in regole()["fustaia"]["prelievo_per_provvigione"]:
        if rapporto >= fascia["da_pct"]:
            return fascia["max_prelievo_pct"] / 100
    return None


def provvigione(p: Pratica) -> list[Esito]:
    specie = p.intervento.popolamento.specie_prevalente
    minima, categoria = provvigione_minimale(p)
    if minima is None:
        return [Esito("fus.categoria", "Provvigione minimale", Livello.DA_VERIFICARE,
                      f"Specie prevalente {'non indicata' if not specie else '«' + specie + '» non in tabella'}: "
                      "impossibile individuare la provvigione minimale.", "art. 38 c. 8",
                      integrazione=None if specie else "Indicazione della composizione specifica del soprassuolo")]
    ind = indici_prelievo(p)
    prima, dopo = ind.get("provvigione_prima"), ind.get("provvigione_dopo")
    esiti = []
    descr = f"{NOMI_CATEGORIA[categoria]}: {num_breve(minima)} m³/ha"
    if dopo is None:
        esiti.append(Esito("fus.provvigione", "Provvigione dopo il taglio", Livello.DA_VERIFICARE,
                           f"Provvigione a ettaro dopo il taglio non ricavabile (minimale {descr}).", "art. 38 c. 8",
                           integrazione="Provvigione a ettaro prima e dopo l'intervento (scheda A02.3)"))
    elif dopo <= minima:
        esiti.append(Esito("fus.provvigione", "Provvigione dopo il taglio", Livello.NON_CONFORME,
                           f"Provvigione residua {num_breve(dopo, 1)} m³/ha non superiore alla minimale ({descr}).", "art. 38 c. 8"))
    else:
        esiti.append(Esito("fus.provvigione", "Provvigione dopo il taglio", Livello.OK,
                           f"Provvigione residua {num_breve(dopo, 1)} m³/ha superiore alla minimale ({descr}).", "art. 38 c. 8"))

    prel = ind.get("prelievo_volume")
    if prima is not None and prel is not None:
        massimo = prelievo_massimo(prima, minima)
        if massimo is None:
            esiti.append(Esito("fus.prelievo", "Intensità del prelievo", Livello.NON_CONFORME,
                               f"Provvigione {num_breve(prima, 1)} m³/ha inferiore al 20% della minimale: prelievo non ammesso.",
                               "art. 38 c. 9"))
        elif prel > massimo + 1e-9:
            esiti.append(Esito("fus.prelievo", "Intensità del prelievo", Livello.NON_CONFORME,
                               f"Prelievo {pct(prel)} della massa oltre il massimo del {pct(massimo, 0)} "
                               f"(provvigione {num_breve(prima, 1)} m³/ha). Superabile solo per elevata fertilità o provvigione per mancate utilizzazioni, da motivare.",
                               "art. 38 cc. 9-10",
                               integrazione="Motivazione tecnica del prelievo superiore al limite (art. 38 c. 10) o riduzione dell'intensità del taglio"))
        else:
            esiti.append(Esito("fus.prelievo", "Intensità del prelievo", Livello.OK,
                               f"Prelievo {pct(prel)} della massa entro il {pct(massimo, 0)} (provvigione prima del taglio "
                               f"{num_breve(prima, 1)} m³/ha).", "art. 38 c. 9"))
        if prel >= 0.999:
            esiti.append(Esito("fus.raso", "Taglio raso", Livello.NON_CONFORME,
                               "Nelle fustaie il taglio raso è vietato salvo impianti di specie esotiche o da arboricoltura.", "art. 38 cc. 2-3"))
    return esiti


def diradamenti(p: Pratica) -> list[Esito]:
    sotto = set(p.intervento.sottotipi)
    if not ({S.DIRADAMENTI, S.SFOLLAMENTI} & sotto):
        return []
    r = regole()["fustaia"]
    pop = p.intervento.popolamento
    eta = pop.eta_max or pop.eta_min
    prel_g = indici_prelievo(p).get("prelievo_g")
    if eta is None or prel_g is None:
        return [Esito("fus.diradamento", "Diradamento: area basimetrica", Livello.DA_VERIFICARE,
                      "Età o prelievo in area basimetrica non disponibili.", "art. 39 c. 5")]
    if eta > 60:
        return [Esito("fus.diradamento", "Diradamento oltre 60 anni", Livello.INFO,
                      "Fustaia di oltre 60 anni: si applicano i limiti dell'art. 38.", "art. 39 c. 7")]
    massimo = (r["diradamento_g_max_pct_sotto_30"] if eta < 30 else r["diradamento_g_max_pct_30_60"]) / 100
    livello = Livello.OK if prel_g <= massimo + 1e-9 else Livello.NON_CONFORME
    return [Esito("fus.diradamento", "Diradamento: area basimetrica", livello,
                  f"Prelievo {pct(prel_g)} dell'area basimetrica; massimo {pct(massimo, 0)} per età {eta} anni.", "art. 39 c. 5")]


def intervallo(p: Pratica) -> list[Esito]:
    fine = p.intervento.popolamento.fine_lavori_ultimo_intervento
    if fine is None:
        return []
    anni = (p.data_protocollo - fine).days / 365.25
    minimo = regole()["fustaia"]["intervallo_minimo_anni"]
    livello = Livello.OK if anni >= minimo else Livello.NON_CONFORME
    return [Esito("fus.intervallo", "Intervallo dal taglio precedente", livello,
                  f"{num_breve(anni, 1)} anni dalla fine lavori del precedente intervento (minimo {minimo}).", "art. 38 c. 11")]


def biodiversita(p: Pratica) -> list[Esito]:
    r = regole()["fustaia"]
    sup = p.inquadramento.superficie_intervento_ha
    richiesti = r["alberi_invecchiamento_per_ha"] * math.ceil(sup - 1e-9)
    s = p.scheda
    rilasciati = s.alberi_invecchiamento if s else None
    esiti = []
    if rilasciati is None:
        esiti.append(Esito("fus.invecchiamento", "Alberi a invecchiamento indefinito", Livello.DA_VERIFICARE,
                           f"Numero non indicato: ne servono almeno {richiesti} (2 per ettaro o frazione).", "art. 19",
                           integrazione=f"Piedilista georeferenziato degli alberi da destinare all'invecchiamento indefinito (almeno {richiesti})"))
    elif rilasciati < richiesti:
        esiti.append(Esito("fus.invecchiamento", "Alberi a invecchiamento indefinito", Livello.NON_CONFORME,
                           f"Rilasciati {rilasciati}, richiesti almeno {richiesti} (2 per ettaro o frazione).", "art. 19",
                           integrazione=f"Integrazione del piedilista degli alberi a invecchiamento indefinito fino ad almeno {richiesti}"))
    else:
        esiti.append(Esito("fus.invecchiamento", "Alberi a invecchiamento indefinito", Livello.OK,
                           f"Rilasciati {rilasciati} alberi (minimo {richiesti}).", "art. 19"))
    esiti[-1].prescrizione = (
        f"Dovranno essere rilasciati almeno {richiesti} alberi a invecchiamento indefinito, georeferenziati e contrassegnati, "
        f"nonché, se presenti, almeno {r['piante_morte_min_ha']} piante morte di medie dimensioni per ettaro e gli alberi con cavità "
        "utilizzate dalla fauna; sono salvaguardate le specie sporadiche (artt. 18-19)."
    )
    return esiti


def verifica(p: Pratica) -> list[Esito]:
    if p.intervento.tipo is not T.FUSTAIA:
        return []
    esiti = provvigione(p) + diradamenti(p) + intervallo(p) + biodiversita(p)
    if p.martellata is None:
        esiti.append(Esito("fus.martellata", "Martellata", Livello.DA_VERIFICARE,
                           "Dati della martellata (numero piante, numerazione, sigla del martello) non inseriti.", "art. 10 c. 3"))
    return esiti
