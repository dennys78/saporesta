"""Quadratura della scheda tecnica A02.3 (stessa logica del foglio Excel di verifica)."""

from __future__ import annotations

import math

from ..formato import num, num_breve, pct
from ..models import Dendro, Pratica, TipoIntervento
from ..regole import regole
from .esito import Esito, Livello

T = TipoIntervento
GRANDEZZE = [("n_piante", "numero piante", 0), ("area_basimetrica", "area basimetrica", 2), ("volume", "volume", 2)]


def _quasi(a: float, b: float, rel: float, abs_: float = 0.0) -> bool:
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def _sottrazione(prima: Dendro, taglio: Dendro, dopo: Dendro, ambito: str) -> list[Esito]:
    esiti = []
    for campo, nome, dec in GRANDEZZE:
        a, b, c = getattr(prima, campo), getattr(taglio, campo), getattr(dopo, campo)
        if a is None or b is None or c is None:
            continue
        atteso = a - b
        if not _quasi(atteso, c, 0.005, 0.06 if dec else 1):
            esiti.append(Esito(
                f"a023.{ambito}.{campo}", f"A02.3 {ambito}: {nome} dopo il taglio", Livello.NON_CONFORME,
                f"Prima ({num(a, dec)}) − taglio ({num(b, dec)}) = {num(atteso, dec)}, ma la scheda riporta {num(c, dec)}.",
                integrazione=f"Correzione della scheda A02.3 ({ambito}): {nome} dopo l'intervento non coerente con prima − prelievo",
            ))
    return esiti


def _completa(d: Dendro, prima: Dendro, taglio: Dendro) -> Dendro:
    """Ricava i valori 'dopo' mancanti per differenza."""
    valori = {}
    for campo, _, _ in GRANDEZZE:
        v = getattr(d, campo)
        if v is None and getattr(prima, campo) is not None and getattr(taglio, campo) is not None:
            v = getattr(prima, campo) - getattr(taglio, campo)
        valori[campo] = v
    return Dendro(**valori)


def scheda(p: Pratica) -> list[Esito]:
    s = p.scheda
    r = regole()["a02_3"]
    if s is None:
        if p.intervento.tipo is T.ART22:
            return []
        # Se la scheda manca tra i documenti lo segnala la checklist; qui si
        # ricorda solo che i suoi dati non sono ancora stati inseriti.
        return [Esito("a023.assente", "Scheda tecnica A02.3", Livello.DA_VERIFICARE,
                      "Dati della scheda A02.3 non ancora inseriti: quadratura, provvigione e prelievo non verificabili.")]
    esiti: list[Esito] = []
    sup = p.inquadramento.superficie_intervento_ha

    # 1. dopo = prima - taglio (ad ettaro e sul totale)
    esiti += _sottrazione(s.ettaro_prima, s.ettaro_taglio, s.ettaro_dopo, "ad ettaro")
    esiti += _sottrazione(s.totale_prima, s.totale_taglio, s.totale_dopo, "intera superficie")

    # 2. totale ≈ ettaro × superficie
    coppie = [("prima", s.ettaro_prima, s.totale_prima), ("taglio", s.ettaro_taglio, s.totale_taglio),
              ("dopo", s.ettaro_dopo, s.totale_dopo)]
    for fase, ha, tot in coppie:
        for campo, nome, dec in GRANDEZZE:
            a, b = getattr(ha, campo), getattr(tot, campo)
            if a is None or b is None:
                continue
            atteso = a * sup
            if not _quasi(atteso, b, r["tolleranza_relativa"], 1.0 if not dec else 0.05):
                esiti.append(Esito(
                    f"a023.scala.{fase}.{campo}", f"A02.3: {nome} {fase} (ettaro × superficie)", Livello.NON_CONFORME,
                    f"{num(a, dec)}/ha × {num_breve(sup, 4)} ha = {num(atteso, dec)}, ma il totale dichiarato è {num(b, dec)} "
                    f"(superficie implicita {num_breve(b / a, 4) if a else '—'} ha).",
                    integrazione=f"Correzione della scheda A02.3: {nome} {fase} sull'intera superficie non coerente con il dato ad ettaro e la superficie d'intervento",
                ))

    # 3. percentuali dichiarate
    base = s.ettaro_prima if s.ettaro_prima.volume else s.totale_prima
    prel = s.ettaro_taglio if s.ettaro_prima.volume else s.totale_taglio
    for campo, dichiarata, nome in [("n_piante", s.percentuale_dichiarata_piante, "piante"),
                                    ("area_basimetrica", s.percentuale_dichiarata_g, "area basimetrica"),
                                    ("volume", s.percentuale_dichiarata_volume, "volume")]:
        a, b = getattr(base, campo), getattr(prel, campo)
        if dichiarata is None or not a or b is None:
            continue
        calcolata = b / a * 100
        if abs(calcolata - dichiarata) > r["tolleranza_percentuale"]:
            esiti.append(Esito(
                f"a023.pct.{campo}", f"A02.3: % prelievo {nome}", Livello.NON_CONFORME,
                f"Dichiarato {num_breve(dichiarata)}%, ricalcolato {num_breve(calcolata, 1)}%.",
                integrazione=f"Correzione della percentuale di prelievo in {nome} riportata nella scheda A02.3",
            ))

    # 4. massa = volume × peso specifico
    if s.peso_specifico_q_m3:
        for ambito, vol, massa in [("ad ettaro", s.ettaro_taglio.volume, s.massa_taglio_ettaro_q),
                                   ("intera superficie", s.totale_taglio.volume, s.massa_taglio_totale_q)]:
            if vol is None or massa is None:
                continue
            attesa = vol * s.peso_specifico_q_m3
            if not _quasi(attesa, massa, 0.005, 1.0):
                esiti.append(Esito(
                    f"a023.massa.{ambito}", f"A02.3: massa {ambito}", Livello.NON_CONFORME,
                    f"{num(vol)} m³ × {num_breve(s.peso_specifico_q_m3)} q/m³ = {num(attesa)} q, dichiarati {num(massa)} q.",
                    integrazione=f"Correzione della massa prelevata ({ambito}) nella scheda A02.3",
                ))

    # 5. aree di saggio
    if s.aree_saggio:
        piccole = [a.nome for a in s.aree_saggio if a.superficie_m2 < r["area_saggio_min_m2"]]
        if piccole:
            esiti.append(Esito("a023.ads.dim", "Aree di saggio: dimensione", Livello.NON_CONFORME,
                               f"Aree di saggio sotto i {r['area_saggio_min_m2']} m²: {', '.join(piccole)}.",
                               integrazione="Rilievi dendrometrici su aree di saggio di almeno 400 m² (20 × 20 m)"))
        if len(s.aree_saggio) < r["aree_saggio_min"]:
            esiti.append(Esito("a023.ads.num", "Aree di saggio: numero", Livello.ATTENZIONE,
                               f"Eseguita {len(s.aree_saggio)} sola area di saggio: verificarne la rappresentatività."))
        senza_coord = [a.nome for a in s.aree_saggio if a.utm_e is None]
        if senza_coord:
            esiti.append(Esito("a023.ads.coord", "Aree di saggio: coordinate", Livello.DA_VERIFICARE,
                               f"Coordinate UTM mancanti per: {', '.join(senza_coord)}.",
                               integrazione="Coordinate UTM WGS84 delle aree di saggio eseguite"))
    elif p.intervento.tipo in (T.CEDUO, T.FUSTAIA, T.TRANSITORIO, T.NEOFORMAZIONE):
        voce = p.istruttoria.checklist.get("rilievi_dendrometrici")
        if voce is not None and voce.stato.value == "si":
            esiti.append(Esito("a023.ads.assenti", "Aree di saggio", Livello.INFO,
                               "Rilievi dendrometrici presenti tra gli elaborati ma aree di saggio non inserite nel portale."))
        else:
            esiti.append(Esito("a023.ads.assenti", "Aree di saggio", Livello.DA_VERIFICARE,
                               "Nessuna area di saggio riportata.",
                               integrazione="Rilievi dendrometrici (aree di saggio con superficie, coordinate UTM WGS84 e dati rilevati)"))

    # 6. diametro medio coerente con G/N
    if s.diametro_medio_cm and prel.area_basimetrica and prel.n_piante:
        d_calc = math.sqrt(prel.area_basimetrica / prel.n_piante * 4 / math.pi) * 100
        livello = Livello.OK if _quasi(d_calc, s.diametro_medio_cm, 0.10) else Livello.ATTENZIONE
        esiti.append(Esito("a023.diametro", "A02.3: diametro medio delle piante al taglio", livello,
                           f"Dichiarato {num_breve(s.diametro_medio_cm, 1)} cm, da area basimetrica media "
                           f"{num_breve(d_calc, 1)} cm."))

    # 7. altezza media coerente con V/(G·f)
    if s.altezza_media_m and prel.area_basimetrica and prel.volume:
        h_calc = prel.volume / (prel.area_basimetrica * r["coefficiente_forma"])
        livello = Livello.OK if _quasi(h_calc, s.altezza_media_m, 0.15) else Livello.ATTENZIONE
        esiti.append(Esito("a023.altezza", "A02.3: altezza media", livello,
                           f"Dichiarata {num_breve(s.altezza_media_m, 1)} m, stimata da V/(G×{r['coefficiente_forma']}) "
                           f"{num_breve(h_calc, 1)} m."))

    # 8. assortimenti = volume prelevato
    vol_tot = s.totale_taglio.volume
    if s.assortimenti and vol_tot:
        somma = sum(a.volume_m3 for a in s.assortimenti)
        if not _quasi(somma, vol_tot, 0.01, 0.1):
            dettaglio = " + ".join(f"{num_breve(a.volume_m3)} ({a.descrizione})" for a in s.assortimenti)
            esiti.append(Esito("a023.assortimenti", "Ripartizione per assortimenti", Livello.NON_CONFORME,
                               f"{dettaglio} = {num_breve(somma)} m³, ma il volume prelevato è {num_breve(vol_tot)} m³.",
                               integrazione="Ripartizione del volume prelevato per assortimenti coerente con il volume totale (statistica forestale A02.4)"))

    # 9. piedilista di martellata vs scheda
    if p.martellata and s.totale_taglio.n_piante is not None:
        if p.martellata.n_piante != round(s.totale_taglio.n_piante):
            esiti.append(Esito("a023.martellata", "Piedilista di martellata", Livello.NON_CONFORME,
                               f"Piante martellate {p.martellata.n_piante}, piante al taglio nella scheda {num(s.totale_taglio.n_piante, 0)}.",
                               integrazione="Piedilista di martellata coerente con il numero di piante assegnate al taglio nella scheda A02.3"))

    if not any(e.livello in (Livello.NON_CONFORME, Livello.ATTENZIONE) for e in esiti):
        esiti.append(Esito("a023.quadratura", "Quadratura A02.3", Livello.OK,
                           "I conteggi tra dati ad ettaro, totali e percentuali risultano coerenti."))
    return esiti


def indici_prelievo(p: Pratica) -> dict[str, float | None]:
    """Provvigione e percentuali di prelievo, ricavando i dati mancanti quando possibile."""
    s = p.scheda
    sup = p.inquadramento.superficie_intervento_ha
    if s is None:
        return {}

    def per_ha(ha: float | None, tot: float | None) -> float | None:
        if ha is not None:
            return ha
        return tot / sup if tot is not None and sup else None

    prima = Dendro(**{c: per_ha(getattr(s.ettaro_prima, c), getattr(s.totale_prima, c)) for c, _, _ in GRANDEZZE})
    taglio = Dendro(**{c: per_ha(getattr(s.ettaro_taglio, c), getattr(s.totale_taglio, c)) for c, _, _ in GRANDEZZE})
    dopo = _completa(Dendro(**{c: per_ha(getattr(s.ettaro_dopo, c), getattr(s.totale_dopo, c)) for c, _, _ in GRANDEZZE}), prima, taglio)
    if prima.volume is None and dopo.volume is not None and taglio.volume is not None:
        prima = Dendro(n_piante=prima.n_piante, area_basimetrica=prima.area_basimetrica, volume=dopo.volume + taglio.volume)

    def frazione(a: float | None, b: float | None) -> float | None:
        return b / a if a and b is not None else None

    return {
        "provvigione_prima": prima.volume,
        "provvigione_dopo": dopo.volume,
        "prelievo_volume": frazione(prima.volume, taglio.volume),
        "prelievo_g": frazione(prima.area_basimetrica, taglio.area_basimetrica) if prima.area_basimetrica else (
            s.percentuale_dichiarata_g / 100 if s.percentuale_dichiarata_g is not None else None),
        "prelievo_piante": frazione(prima.n_piante, taglio.n_piante),
    }


__all__ = ["scheda", "indici_prelievo", "pct"]
