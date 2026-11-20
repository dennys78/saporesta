"""Boschi governati a ceduo (Capo V, artt. 29-37)."""

from __future__ import annotations

from ..formato import num_breve
from ..models import Pratica, Sottotipo, TipoIntervento
from ..regole import info_specie, regole
from .esito import Esito, Livello

S = Sottotipo


def eta_minima(p: Pratica) -> int | None:
    """Età minima del soprassuolo: la più bassa tra quella dichiarata e quella dall'ultimo taglio."""
    pop = p.intervento.popolamento
    candidati = []
    if pop.eta_min is not None:
        candidati.append(pop.eta_min)
    if pop.anno_ultimo_taglio is not None:
        candidati.append(p.data_protocollo.year - pop.anno_ultimo_taglio)
    return min(candidati) if candidati else None


def gruppo_turno(p: Pratica) -> tuple[str | None, str | None]:
    specie = p.intervento.popolamento.specie_prevalente
    info = info_specie(specie)
    return specie, (info or {}).get("turno")


def composizione(p: Pratica) -> list[Esito]:
    specie = p.intervento.popolamento.specie_prevalente
    if specie is None:
        return [Esito("ced.specie", "Composizione specifica", Livello.DA_VERIFICARE,
                      "L'istanza non indica la specie prevalente: non è possibile verificare turno minimo e matricinatura.",
                      "artt. 30, 34, 36",
                      integrazione="Indicazione della composizione specifica del soprassuolo (specie e relative percentuali)")]
    _, gruppo = gruppo_turno(p)
    if gruppo is None:
        return [Esito("ced.specie", "Composizione specifica", Livello.DA_VERIFICARE,
                      f"Specie «{specie}» non presente nella tabella dei turni: verificare manualmente il turno minimo.",
                      "art. 30")]
    return [Esito("ced.specie", "Composizione specifica", Livello.OK, f"Specie prevalente: {specie}.")]


def turno(p: Pratica) -> list[Esito]:
    if {S.SFOLLI, S.DIRADAMENTI} >= set(p.intervento.sottotipi) and p.intervento.sottotipi:
        return []
    specie, gruppo = gruppo_turno(p)
    if gruppo is None:
        return []
    r = regole()["ceduo"]
    t = r["turni_minimi"][gruppo]
    pop = p.intervento.popolamento
    eta = eta_minima(p)
    if eta is None:
        return [Esito("ced.turno", "Turno minimo", Livello.DA_VERIFICARE,
                      f"Età del bosco e data dell'ultimo taglio non dichiarate (turno minimo {specie}: {t} anni).",
                      "art. 30", integrazione="Indicazione dell'età del soprassuolo e della data dell'ultimo taglio")]
    esiti = []
    origine = f"età dichiarata {pop.descrizione_eta}"
    if pop.anno_ultimo_taglio:
        origine += f", ultimo taglio {pop.anno_ultimo_taglio}"
    if eta < t:
        if pop.eta_max is not None and pop.eta_max >= t:
            esiti.append(Esito("ced.turno", "Turno minimo", Livello.ATTENZIONE,
                               f"Turno minimo {specie} {t} anni; {origine}: parte del soprassuolo potrebbe non aver raggiunto il turno.",
                               "art. 30 c. 1",
                               integrazione=f"Dimostrazione del raggiungimento del turno minimo di {t} anni su tutta la superficie d'intervento (età dei polloni per sezione di taglio)"))
        else:
            esiti.append(Esito("ced.turno", "Turno minimo", Livello.NON_CONFORME,
                               f"Turno minimo {specie} {t} anni non raggiunto ({origine}).", "art. 30 c. 1"))
    else:
        esiti.append(Esito("ced.turno", "Turno minimo", Livello.OK,
                           f"Turno minimo {specie} {t} anni rispettato ({origine})."))
    eta_max = pop.eta_max or eta
    if eta_max > 2 * t and gruppo not in r["oltre_doppio_turno_ammessi"]:
        esiti.append(Esito("ced.doppio_turno", "Ceduo oltre il doppio del turno", Livello.NON_CONFORME,
                           f"Età {eta_max} anni oltre il doppio del turno ({2 * t}): la ceduazione è vietata.",
                           "art. 30 c. 5"))
    return esiti


def matricine(p: Pratica) -> list[Esito]:
    sotto = set(p.intervento.sottotipi)
    specie, gruppo = gruppo_turno(p)
    r = regole()["ceduo"]
    pend = p.vincoli.pendenza_media_pct
    esiti = []
    if S.SENZA_MATRICINE in sotto:
        nome = (specie or "").lower()
        ammesse = r["senza_matricine_ammessi"]
        if not specie:
            esiti.append(Esito("ced.senza_matricine", "Taglio senza riserva di matricine", Livello.DA_VERIFICARE,
                               f"Il taglio senza matricine è ammesso solo nei cedui puri di {', '.join(ammesse)}: specie non indicata.",
                               "art. 36"))
        elif any(a in nome for a in ammesse):
            esiti.append(Esito("ced.senza_matricine", "Taglio senza riserva di matricine", Livello.OK,
                               f"Ammesso per il ceduo puro di {specie}.", "art. 36 c. 1"))
        elif "castagno" in nome:
            esiti.append(Esito("ced.senza_matricine", "Taglio senza riserva di matricine", Livello.ATTENZIONE,
                               "Per il castagno è ammesso solo in presenza diffusa e virulenta di cancro corticale e cinipide, "
                               "previa autorizzazione specifica.", "art. 36 c. 3",
                               integrazione="Relazione fitosanitaria che documenti la presenza diffusa e virulenta di cancro corticale e cinipide (art. 36 c. 3)"))
        else:
            esiti.append(Esito("ced.senza_matricine", "Taglio senza riserva di matricine", Livello.NON_CONFORME,
                               f"Non ammesso per {specie}: è obbligatoria la riserva di almeno "
                               f"{r['matricine_min_ha']['default']} matricine/ha.", "artt. 34, 36"))
        if p.vincoli.pai_geomorfologico or p.vincoli.pai_idraulico:
            esiti.append(Esito("ced.senza_matricine_pai", "Senza matricine in area PAI", Livello.ATTENZIONE,
                               "In aree a rischio va privilegiato il rilascio di un numero maggiore di matricine.", "art. 23 c. 2 lett. c"))
        return esiti

    if S.SFOLLI in sotto or S.DIRADAMENTI in sotto:
        return esiti  # verifiche in sfolli_diradamenti()

    minimo = r["matricine_min_ha"]["castagno" if gruppo == "castagno" else "default"]
    if pend is not None and pend > r["pendenza_soglia_matricine_pct"]:
        minimo = r["matricine_min_ha_pendenza"]["castagno" if gruppo == "castagno" else "default"]
    articolo = "art. 34"
    if S.COMPOSTO in sotto:
        minimo, articolo = r["composto_matricine_min_ha"], "art. 35 c. 2"
    s = p.scheda
    dichiarate = s.matricine_ha if s else None
    if dichiarate is None:
        esiti.append(Esito("ced.matricine", "Matricine", Livello.DA_VERIFICARE,
                           f"Numero di matricine a ettaro non dichiarato (minimo {minimo}/ha).", articolo,
                           integrazione=f"Elenco delle matricine da riservare con indicazione del numero a ettaro (minimo {minimo}/ha) e del turno di riferimento"))
    elif dichiarate < minimo:
        esiti.append(Esito("ced.matricine", "Matricine", Livello.NON_CONFORME,
                           f"Matricine dichiarate {num_breve(dichiarate)}/ha, minimo {minimo}/ha.", articolo))
    else:
        esiti.append(Esito("ced.matricine", "Matricine", Livello.OK,
                           f"Matricine {num_breve(dichiarate)}/ha (minimo {minimo}/ha).", articolo))
    if s and s.matricine_doppio_turno_pct is not None and S.COMPOSTO not in sotto:
        if s.matricine_doppio_turno_pct < r["matricine_doppio_turno_min_pct"]:
            esiti.append(Esito("ced.matricine_eta", "Matricine di età doppia del turno", Livello.ATTENZIONE,
                               f"Solo il {num_breve(s.matricine_doppio_turno_pct)}% ha età pari al doppio del turno (minimo 50%, "
                               "se presenti soggetti idonei).", "art. 34 c. 3"))
    esiti[-1].prescrizione = (
        f"Dovranno essere rilasciate almeno {minimo} matricine a ettaro, distribuite uniformemente sulla tagliata, "
        "scelte fra le specie principali, salvaguardando le specie sporadiche, contrassegnate con vernice indelebile "
        f"({articolo}; art. 10 c. 4)."
    )
    return esiti


def sfolli_diradamenti(p: Pratica) -> list[Esito]:
    sotto = set(p.intervento.sottotipi)
    if not ({S.SFOLLI, S.DIRADAMENTI} & sotto):
        return []
    r = regole()["ceduo"]
    s = p.scheda
    prelievo = None
    if s and s.percentuale_dichiarata_piante is not None:
        prelievo = s.percentuale_dichiarata_piante
    elif s and s.ettaro_prima.n_piante and s.ettaro_taglio.n_piante is not None:
        prelievo = s.ettaro_taglio.n_piante / s.ettaro_prima.n_piante * 100
    massimo = r["sfolli_diradamenti_max_pct_polloni"]
    if prelievo is None:
        return [Esito("ced.diradamento", "Sfolli e diradamenti nel ceduo", Livello.DA_VERIFICARE,
                      f"Percentuale di polloni prelevati non ricavabile (massimo {massimo}% dei polloni sani).", "art. 33 c. 4")]
    livello = Livello.OK if prelievo <= massimo else Livello.ATTENZIONE
    return [Esito("ced.diradamento", "Sfolli e diradamenti nel ceduo", livello,
                  f"Prelievo {num_breve(prelievo, 1)}% dei polloni; ammesso fino al {massimo}% dei polloni in buone condizioni "
                  "oltre a morti, aduggiati, deperienti e malformati.", "art. 33 c. 4")]


def tagliate(p: Pratica) -> list[Esito]:
    if {S.SFOLLI, S.DIRADAMENTI} >= set(p.intervento.sottotipi) and p.intervento.sottotipi:
        return []
    r = regole()["ceduo"]
    sup = p.inquadramento.superficie_intervento_ha
    pend = p.vincoli.pendenza_media_pct
    esiti = []
    if pend is None:
        esiti.append(Esito("ced.pendenza", "Pendenza media", Livello.DA_VERIFICARE,
                           "Pendenza media non indicata: determina l'estensione massima della tagliata (40%) e il numero minimo di matricine (60%).",
                           "artt. 31, 34",
                           integrazione="Indicazione della pendenza media dell'area d'intervento e carta delle pendenze su base CTR 1:5.000"))
    massima = r["tagliata_max_ha_pendenza"] if (pend or 0) > r["pendenza_soglia_tagliata_pct"] else r["tagliata_max_ha"]
    nota_pend = f" (pendenza media {num_breve(pend)}%)" if pend is not None else " (pendenza non nota: si assume ≤ 40%)"

    if sup > r["superficie_max_piu_tagliate_ha"]:
        esiti.append(Esito("ced.oltre50", "Superficie oltre 50 ha", Livello.ATTENZIONE,
                           f"Superficie di {num_breve(sup)} ha: oltre i 50 ha l'art. 31 c. 2 non consente più tagliate per stagione; "
                           "verificare la necessità di uno strumento di pianificazione.", "artt. 9, 31"))

    if not p.tagliate:
        if sup <= massima:
            esiti.append(Esito("ced.tagliate", "Estensione della tagliata", Livello.OK,
                               f"Tagliata unica di {num_breve(sup, 2)} ha entro il limite di {num_breve(massima)} ha{nota_pend}.",
                               "art. 31 c. 1"))
        else:
            n_min = -(-sup // massima)
            esiti.append(Esito("ced.tagliate", "Estensione della tagliata", Livello.NON_CONFORME,
                               f"La superficie d'intervento di {num_breve(sup, 2)} ha supera il limite di {num_breve(massima)} ha per stagione "
                               f"silvana{nota_pend}: servono almeno {int(n_min)} tagliate non contigue con calendarizzazione progettuale.",
                               "art. 31 cc. 1-3",
                               integrazione=f"Suddivisione dell'area in tagliate di superficie non superiore a {num_breve(massima)} ha per stagione silvana, "
                               "non contigue, separate da aree boscate di pari superficie, con calendarizzazione progettuale degli interventi e "
                               "relativa cartografia (art. 31 cc. 1-3)"))
        return esiti

    troppo_grandi = [t for t in p.tagliate if t.superficie_ha > massima + 1e-6]
    if troppo_grandi:
        esiti.append(Esito("ced.tagliate", "Estensione delle tagliate", Livello.NON_CONFORME,
                           "Tagliate oltre il limite di " + num_breve(massima) + " ha: "
                           + ", ".join(f"{t.nome} ({num_breve(t.superficie_ha)} ha)" for t in troppo_grandi) + ".",
                           "art. 31 c. 1"))
    contigue = [
        (a.nome, b.nome) for i, a in enumerate(p.tagliate) for b in p.tagliate[i + 1:]
        if a.stagione_silvana and a.stagione_silvana == b.stagione_silvana
        and (b.nome in a.contigua_a or a.nome in b.contigua_a)
    ]
    if contigue:
        esiti.append(Esito("ced.contiguita", "Contiguità delle tagliate", Livello.NON_CONFORME,
                           "Tagliate contigue nella stessa stagione silvana: "
                           + ", ".join(f"{a}-{b}" for a, b in contigue) + ".", "art. 31 cc. 2-3"))
    somma = sum(t.superficie_ha for t in p.tagliate)
    if abs(somma - sup) > 0.01 * sup + 0.01:
        esiti.append(Esito("ced.somma_tagliate", "Somma delle tagliate", Livello.ATTENZIONE,
                           f"Le tagliate sommano {num_breve(somma)} ha contro {num_breve(sup)} ha d'intervento."))
    senza_stagione = [t.nome for t in p.tagliate if not t.stagione_silvana]
    if senza_stagione:
        esiti.append(Esito("ced.calendario", "Calendarizzazione", Livello.DA_VERIFICARE,
                           f"Stagione silvana non indicata per: {', '.join(senza_stagione)}.", "art. 31 c. 2",
                           integrazione="Calendarizzazione delle tagliate per stagione silvana"))
    if not (troppo_grandi or contigue):
        esiti.append(Esito("ced.tagliate", "Estensione delle tagliate", Livello.OK,
                           f"{len(p.tagliate)} tagliate entro {num_breve(massima)} ha ciascuna, non contigue nella stessa stagione.",
                           "art. 31",
                           prescrizione="Le tagliate dovranno essere eseguite secondo la calendarizzazione di progetto; la tagliata adiacente "
                           "potrà essere utilizzata trascorso almeno un anno dal termine della stagione silvana in cui è stato ultimato il taglio, "
                           "previa asseverazione del direttore dei lavori sull'avvenuta ripresa vegetativa (art. 31 c. 3)."))
    return esiti


def verifica(p: Pratica) -> list[Esito]:
    if p.intervento.tipo is not TipoIntervento.CEDUO:
        return []
    return composizione(p) + turno(p) + matricine(p) + sfolli_diradamenti(p) + tagliate(p)
