"""Tavola di cubatura: quale è stata applicata e se è stata applicata correttamente."""

from __future__ import annotations

from dataclasses import dataclass

from .. import cubatura as cub
from ..formato import num, num_breve
from ..models import Pratica, TipoIntervento
from ..regole import regole
from .esito import Esito, Livello

T = TipoIntervento


@dataclass
class RigaRicalcolo:
    d: float
    h: float | None
    n: float | None
    v_dichiarato: float | None  # m³ per pianta
    v_tavola: float | None  # m³ per pianta
    h_tavola: float | None = None  # TaCAL

    @property
    def scarto(self) -> float | None:
        if self.v_dichiarato is None or not self.v_tavola:
            return None
        return (self.v_dichiarato - self.v_tavola) / self.v_tavola


@dataclass
class Ricalcolo:
    tavola: str | None
    risoluzione: cub.Risoluzione | None
    tariffa: int | None
    tariffa_dedotta: bool
    righe: list[RigaRicalcolo]
    governo: str


def governo(p: Pratica) -> str:
    return "ceduo" if p.intervento.tipo in (T.CEDUO, T.TRANSITORIO) else "fustaia"


def ricalcola(p: Pratica) -> Ricalcolo | None:
    c = p.cubatura
    if c is None:
        return None
    gov = governo(p)
    specie = c.specie_tavola or p.intervento.popolamento.specie_prevalente
    ris = cub.risolvi(c.tavola, specie, gov) if c.tavola else None
    tariffa, dedotta = c.tariffa, False
    if c.tavola == "tacal_2016" and ris and ris.chiave and tariffa is None:
        coppie = [(k.d_cm, k.h_m) for k in c.classi if k.h_m]
        tariffa = cub.tariffa_piu_vicina(ris.chiave, coppie) if coppie else None
        dedotta = tariffa is not None
    righe = []
    for k in c.classi:
        v_dich = k.v_unitario_m3
        if v_dich is None and k.v_totale_m3 is not None and k.n_piante:
            v_dich = k.v_totale_m3 / k.n_piante
        v_tav = h_tav = None
        if ris and ris.chiave:
            if c.tavola == "tacal_2016":
                valori = cub.tariffa_tacal(ris.chiave, tariffa, k.d_cm) if tariffa else None
                if valori:
                    h_tav, v_tav = valori
            elif k.h_m:
                v_tav = cub.volume_doppia_entrata(c.tavola, ris.chiave, k.d_cm, k.h_m)
        righe.append(RigaRicalcolo(k.d_cm, k.h_m, k.n_piante, v_dich, v_tav, h_tav))
    return Ricalcolo(c.tavola, ris, tariffa, dedotta, righe, gov)


def verifica(p: Pratica) -> list[Esito]:
    c = p.cubatura
    if c is None:
        if p.intervento.tipo in (T.ART22, T.NEOFORMAZIONE):
            return []
        return [Esito("cub.assente", "Tavola di cubatura", Livello.DA_VERIFICARE,
                      "Tavola di cubatura e quadro per classi diametriche non ancora inseriti.")]
    r = regole()["cubatura"]
    tol = r["tolleranza_pct"] / 100
    esiti: list[Esito] = []

    if not c.tavola:
        esiti.append(Esito("cub.tavola", "Tavola di cubatura", Livello.DA_VERIFICARE,
                           f"La tavola usata non è indicata{' (dichiarato: «' + c.tavola_dichiarata + '»)' if c.tavola_dichiarata else ''}.",
                           integrazione="Indicazione della tavola di cubatura (o tariffa) utilizzata per la stima dei volumi"))
        return esiti

    rc = ricalcola(p)
    ris = rc.risoluzione
    descrizione = cub.NOMI_TAVOLE[c.tavola]
    dettagli = []
    if c.tavola_dichiarata:
        dettagli.append(f"indicata come «{c.tavola_dichiarata}»")
    if ris and ris.chiave:
        dettagli.append(f"tavola della specie: {ris.descrizione}")
    if c.tavola == "tacal_2016" and rc.tariffa:
        dettagli.append(f"tariffa n. {rc.tariffa}" + (" (dedotta dalle altezze dichiarate)" if rc.tariffa_dedotta else ""))
    esiti.append(Esito("cub.tavola", "Tavola di cubatura applicata", Livello.INFO,
                       f"{descrizione}{' – ' + '; '.join(dettagli) if dettagli else ''}."))

    if c.tavola not in cub.CON_RICALCOLO:
        regione = cub.REGIONALI_ALTRE.get(c.tavola)
        msg = (f"Tavola costruita per {regione}: va motivato nella relazione perché sia adatta ai boschi calabresi. "
               if regione else "Tavola non presente nella banca dati del portale. ")
        esiti.append(Esito("cub.manuale", "Verifica della cubatura", Livello.ATTENZIONE,
                           msg + "Il ricalcolo automatico dei volumi non è disponibile: verificare a mano."))
        return esiti

    if ris is None or ris.chiave is None:
        esiti.append(Esito("cub.specie", "Tavola e specie", Livello.NON_CONFORME,
                           f"La tavola {descrizione} non prevede la specie ({ris.descrizione if ris else 'non indicata'}).",
                           integrazione="Stima dei volumi con una tavola di cubatura prevista per la specie oggetto di taglio"))
        return esiti
    if ris.nota:
        esiti.append(Esito("cub.specie", "Tavola e specie", Livello.ATTENZIONE, ris.nota[0].upper() + ris.nota[1:] + "."))
    if ris.governo_tavola and ris.governo_tavola != rc.governo:
        esiti.append(Esito("cub.governo", "Tavola e forma di governo", Livello.ATTENZIONE,
                           f"Bosco governato a {rc.governo} cubato con la tavola Castellani per il {ris.governo_tavola} ({ris.chiave}): "
                           "verificarne la motivazione."))

    if not c.classi:
        esiti.append(Esito("cub.classi", "Ricalcolo dei volumi", Livello.DA_VERIFICARE,
                           "Manca il quadro per classi diametriche (diametro, altezza, volume): impossibile verificare l'applicazione della tavola.",
                           integrazione="Quadro riepilogativo delle piante al taglio per classi diametriche, con altezza (curva ipsometrica) e volume per classe"))
        return esiti

    if c.tavola == "tacal_2016" and rc.tariffa is None:
        esiti.append(Esito("cub.tariffa", "Tariffa TaCAL", Livello.DA_VERIFICARE,
                           "Numero di tariffa non indicato e altezze mancanti: impossibile verificare i volumi.",
                           integrazione="Indicazione del numero di tariffa TaCAL applicato e delle altezze per classe diametrica"))
        return esiti

    senza_h = [num_breve(rg.d) for rg in rc.righe if rg.h is None and c.tavola != "tacal_2016"]
    if senza_h:
        esiti.append(Esito("cub.altezze", "Altezze per classe", Livello.DA_VERIFICARE,
                           f"Altezza mancante per le classi di {', '.join(senza_h)} cm: con una tavola a doppia entrata serve l'altezza.",
                           integrazione="Altezze per classe diametrica (curva ipsometrica) usate per la cubatura"))
    fuori = [num_breve(rg.d) for rg in rc.righe if c.tavola == "tacal_2016" and rg.v_tavola is None]
    if fuori:
        esiti.append(Esito("cub.campo", "Campo di validità", Livello.ATTENZIONE,
                           f"Classi fuori dal campo delle tariffe TaCAL (7-100 cm): {', '.join(fuori)} cm."))

    confrontabili = [rg for rg in rc.righe if rg.scarto is not None]
    if not confrontabili:
        esiti.append(Esito("cub.volumi", "Ricalcolo dei volumi", Livello.DA_VERIFICARE,
                           "Nessuna classe con volume dichiarato da confrontare.",
                           integrazione="Volume per classe diametrica stimato con la tavola dichiarata"))
        return esiti

    # rapporto dichiarato/tavola vicino a 1000 o a 1/1000: volumi in dm³ scambiati per m³ o viceversa
    unita = [rg for rg in confrontabili if 800 < 1 + rg.scarto < 1250 or 0.0008 < 1 + rg.scarto < 0.00125]
    if unita and len(unita) >= len(confrontabili) / 2:
        esiti.append(Esito("cub.unita", "Unità di misura dei volumi", Livello.NON_CONFORME,
                           "I volumi dichiarati differiscono da quelli della tavola di circa 1000 volte: probabile confusione tra dm³ e m³.",
                           integrazione="Correzione dell'unità di misura dei volumi (m³) nel quadro per classi diametriche"))
        return esiti

    errate = [rg for rg in confrontabili if abs(rg.scarto) > tol]
    if errate:
        elenco = "; ".join(
            f"d {num_breve(rg.d)} cm{', h ' + num_breve(rg.h, 1) + ' m' if rg.h else ''}: dichiarati {num(rg.v_dichiarato, 3)} m³, "
            f"tavola {num(rg.v_tavola, 3)} m³ ({'+' if rg.scarto > 0 else ''}{num_breve(rg.scarto * 100, 1)}%)" for rg in errate)
        esiti.append(Esito("cub.volumi", "Applicazione della tavola", Livello.NON_CONFORME,
                           f"{len(errate)} classi su {len(confrontabili)} fuori tolleranza (±{num_breve(tol * 100)}%): {elenco}.",
                           integrazione=f"Ricalcolo dei volumi con la tavola dichiarata ({descrizione}) per le classi diametriche "
                           + ", ".join(num_breve(rg.d) for rg in errate) + " cm e conseguente aggiornamento della scheda A02.3"))
    else:
        n = len(confrontabili)
        quante = "l'unica classe diametrica è" if n == 1 else f"tutte le {n} classi diametriche sono"
        esiti.append(Esito("cub.volumi", "Applicazione della tavola", Livello.OK,
                           f"Tavola applicata correttamente: {quante} entro ±{num_breve(tol * 100)}% dal ricalcolo."))

    if c.tavola == "tacal_2016":
        lontane = [rg for rg in rc.righe if rg.h and rg.h_tavola and abs(rg.h - rg.h_tavola) > r["tolleranza_altezza_m"]]
        if lontane:
            esiti.append(Esito("cub.altezze_tariffa", "Altezze e tariffa", Livello.ATTENZIONE,
                               f"Altezze dichiarate lontane da quelle della tariffa n. {rc.tariffa} per le classi "
                               + ", ".join(f"{num_breve(rg.d)} cm ({num_breve(rg.h, 1)} m contro {num_breve(rg.h_tavola, 1)} m)" for rg in lontane)
                               + ": verificare la scelta della tariffa."))

    altezze = [(rg.d, rg.h) for rg in sorted(rc.righe, key=lambda x: x.d) if rg.h]
    cali = [f"{num_breve(d2)} cm" for (d1, h1), (d2, h2) in zip(altezze, altezze[1:]) if h2 < h1 - 0.5]
    if cali:
        esiti.append(Esito("cub.ipsometrica", "Curva ipsometrica", Livello.ATTENZIONE,
                           f"L'altezza diminuisce al crescere del diametro (classi {', '.join(cali)}): controllare la curva ipsometrica."))

    s = p.scheda
    if s and s.totale_taglio.volume and all(rg.n and rg.v_dichiarato is not None for rg in rc.righe):
        somma = sum(rg.n * rg.v_dichiarato for rg in rc.righe)
        if abs(somma - s.totale_taglio.volume) > 0.02 * s.totale_taglio.volume:
            esiti.append(Esito("cub.totale", "Totale per classi e scheda A02.3", Livello.ATTENZIONE,
                               f"Le classi diametriche sommano {num(somma)} m³, la scheda A02.3 riporta {num(s.totale_taglio.volume)} m³."))
    return esiti
