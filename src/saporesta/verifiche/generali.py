"""Verifiche comuni a tutti i tipi di intervento."""

from __future__ import annotations

from collections import defaultdict

from ..checklist import voci_richieste
from ..formato import num, num_breve
from ..models import Pratica, StatoVoce, TipoIntervento, Sottotipo
from ..regole import regole
from .esito import Esito, Livello

T = TipoIntervento


def checklist(p: Pratica) -> list[Esito]:
    esiti = []
    mancanti_da_controllare = []
    for voce in voci_richieste(p):
        stato = p.istruttoria.checklist.get(voce.id)
        if stato is None:
            mancanti_da_controllare.append(voce.testo)
            continue
        if stato.stato is StatoVoce.NO:
            esiti.append(Esito(
                f"doc.{voce.id}", voce.testo, Livello.NON_CONFORME,
                "Documento non presente.", integrazione=voce.testo_richiesta,
            ))
        elif stato.stato is StatoVoce.DIFFORME:
            nota = f": {stato.nota}" if stato.nota else ""
            esiti.append(Esito(
                f"doc.{voce.id}", voce.testo, Livello.NON_CONFORME,
                f"Documento difforme{nota}.",
                integrazione=f"{voce.testo_richiesta} - da regolarizzare{nota}",
            ))
    if mancanti_da_controllare:
        esiti.append(Esito(
            "doc.da_controllare", "Checklist documentale", Livello.DA_VERIFICARE,
            f"{len(mancanti_da_controllare)} voci della checklist ancora da spuntare (prima: "
            f"{mancanti_da_controllare[0]}).",
        ))
    else:
        esiti.append(Esito("doc.completa", "Checklist documentale", Livello.OK,
                           "Tutte le voci richieste sono state controllate."))
    return esiti


def soglia_superficie(p: Pratica) -> list[Esito]:
    sup = p.inquadramento.superficie_intervento_ha
    soglia = regole()["superficie_soglia_autorizzazione_ha"]
    tipo = p.intervento.tipo
    if tipo is T.CEDUO and sup < soglia:
        return [Esito(
            "gen.soglia", "Procedimento", Livello.ATTENZIONE,
            f"Superficie d'intervento {num_breve(sup, 4)} ha inferiore a {num_breve(soglia)} ha: "
            "per il ceduo è sufficiente la comunicazione di taglio, salvo superficie accorpata "
            "maggiore di 2 ha che non può essere frazionata.", "art. 32 c. 1 e 6",
        )]
    return []


def superfici(p: Pratica) -> list[Esito]:
    inq = p.inquadramento
    if inq.superficie_catastale_ha is None:
        return [Esito("gen.superfici", "Superfici", Livello.DA_VERIFICARE,
                      "Superficie catastale non indicata.",
                      integrazione="Indicazione della superficie catastale complessiva delle particelle interessate")]
    if inq.superficie_intervento_ha > inq.superficie_catastale_ha + 1e-6:
        return [Esito("gen.superfici", "Superfici", Livello.NON_CONFORME,
                      f"La superficie d'intervento ({num_breve(inq.superficie_intervento_ha, 4)} ha) supera "
                      f"quella catastale ({num_breve(inq.superficie_catastale_ha, 4)} ha).")]
    return [Esito("gen.superfici", "Superfici", Livello.OK,
                  f"Superficie d'intervento {num_breve(inq.superficie_intervento_ha, 4)} ha su "
                  f"{num_breve(inq.superficie_catastale_ha, 4)} ha catastali.")]


def versamento(p: Pratica) -> list[Esito]:
    d = regole()["diritti"]
    atteso = d["segreteria"] + d["istruttoria"]
    v = p.versamento
    if v.importo_totale is None:
        return [Esito("gen.versamento", "Diritti di segreteria e istruttoria", Livello.DA_VERIFICARE,
                      "Importo del versamento non indicato.", "Allegato F")]
    if v.importo_totale + 1e-6 < atteso:
        return [Esito("gen.versamento", "Diritti di segreteria e istruttoria", Livello.NON_CONFORME,
                      f"Versati € {num(v.importo_totale)} invece di € {num(atteso)}.", "Allegato F",
                      integrazione=f"Ricevuta del versamento integrativo dei diritti di segreteria e istruttoria (dovuti € {num(atteso)})")]
    return [Esito("gen.versamento", "Diritti di segreteria e istruttoria", Livello.OK,
                  f"Versati € {num(v.importo_totale)}.", "Allegato F")]


def norma_modulo(p: Pratica) -> list[Esito]:
    rif = (p.riferimento_normativo_modulo or "").upper()
    if "PMPF" in rif or "218" in rif:
        return [Esito("gen.modulo", "Modulistica", Livello.ATTENZIONE,
                      "Il modulo d'istanza richiama le PMPF (D.G.R. 218/2011), superate dal Reg. n. 4/2024: "
                      "le dichiarazioni vanno lette con riferimento al regolamento vigente.")]
    return []


def tecnico(p: Pratica) -> list[Esito]:
    t = p.tecnico
    if t is None:
        return [Esito("gen.tecnico", "Tecnico progettista", Livello.NON_CONFORME,
                      "Progettista non indicato.", "art. 10 c. 1",
                      integrazione="Generalità e iscrizione all'albo del tecnico progettista")]
    if not t.numero_iscrizione:
        return [Esito("gen.tecnico", "Tecnico progettista", Livello.DA_VERIFICARE,
                      "Numero di iscrizione all'albo non indicato.", "art. 10 c. 1",
                      integrazione="Estremi di iscrizione all'albo professionale del tecnico progettista")]
    return [Esito("gen.tecnico", "Tecnico progettista", Livello.OK,
                  f"{t.titolo} {t.cognome} {t.nome}, iscritto all'Ordine di {t.ordine_provincia} al n. {t.numero_iscrizione}.")]


def vincoli(p: Pratica) -> list[Esito]:
    v = p.vincoli
    esiti = []
    if v.natura2000:
        esiti.append(Esito(
            "vin.natura2000", "Rete Natura 2000", Livello.ATTENZIONE,
            f"L'intervento ricade in sito Natura 2000{' (' + v.sito_natura2000 + ')' if v.sito_natura2000 else ''}: "
            "serve la Valutazione di Incidenza e l'autorizzazione va comunicata al Dipartimento competente.",
            "art. 25 c. 3",
            prescrizione="Dovranno essere rispettate tutte le prescrizioni del provvedimento di Valutazione di Incidenza"
            + (f" {p.istruttoria.riferimento_vinca}" if p.istruttoria.riferimento_vinca else "") + ".",
        ))
    if v.aree_protette:
        esiti.append(Esito(
            "vin.aree_protette", "Aree naturali protette", Livello.ATTENZIONE,
            f"Ricade in: {', '.join(v.aree_protette)}. Serve il nulla osta dell'ente gestore.", "art. 25 c. 2",
        ))
    rischio = [r for r in v.pai_geomorfologico + v.pai_idraulico if r in ("R3", "R4")]
    if rischio:
        esiti.append(Esito(
            "vin.pai", "Rischio PAI", Livello.ATTENZIONE,
            f"Aree a rischio {', '.join(sorted(set(rischio)))}: progetto integrato da studio di compatibilità "
            "geomorfologica; tagliate a contorno irregolare, esbosco senza rottura del cotico.", "art. 23 c. 2",
            prescrizione="Nelle aree a rischio R3/R4 l'esbosco dovrà essere eseguito con canalette, fili a sbalzo o altri "
            "sistemi atti a evitare la rottura del cotico erboso, l'asportazione della lettiera e il sentieramento (art. 23 c. 2 lett. d).",
        ))
    if v.percorsa_incendio and p.intervento.tipo is not T.INCENDIO:
        esiti.append(Esito(
            "vin.incendio", "Aree percorse dal fuoco", Livello.ATTENZIONE,
            "L'area risulta percorsa da incendio: si applicano i divieti dell'art. 10 L. 353/2000.", "art. 49 c. 1",
        ))
    if v.sorgenti_50m:
        esiti.append(Esito(
            "vin.sorgenti", "Sorgenti idropotabili", Livello.ATTENZIONE,
            "Bosco entro 50 m da captazione idropotabile.", "art. 27",
            prescrizione="Entro 50 m dal punto di captazione della sorgente dovrà essere effettuata una matricinatura intensiva "
            "(cedui) ovvero rilasciata una provvigione aumentata di almeno il 20% (fustaie) (art. 27).",
        ))
    if v.versante_massi:
        esiti.append(Esito(
            "vin.massi", "Versanti con rotolamento massi", Livello.ATTENZIONE,
            "Versante incombente su abitati o vie di comunicazione.", "art. 22 c. 2",
            prescrizione="Dovrà essere rilasciata una fascia di protezione larga almeno 20 m nella porzione inferiore della pendice (art. 22 c. 2).",
        ))
    if not esiti:
        esiti.append(Esito("vin.nessuno", "Vincoli dichiarati", Livello.OK,
                           "Non ricade in aree protette, siti Natura 2000 o aree PAI R3/R4."))
    return esiti


def verifiche_ufficio(p: Pratica) -> list[Esito]:
    esiti = []
    if not p.istruttoria.verifiche_ufficio:
        esiti.append(Esito("uff.assenti", "Verifiche d'ufficio", Livello.DA_VERIFICARE,
                           "Non sono ancora registrate le consultazioni d'ufficio (SIM, SIAN, PAI)."))
    for i, vu in enumerate(p.istruttoria.verifiche_ufficio):
        if vu.criticita:
            esiti.append(Esito(
                f"uff.{i}", f"Verifica d'ufficio {vu.sistema}", Livello.NON_CONFORME,
                f"{vu.esito} — in contrasto con quanto dichiarato.",
                integrazione=f"Chiarimenti in merito all'esito della consultazione {vu.sistema}: {vu.esito}",
            ))
    return esiti


def riscontri(p: Pratica) -> list[Esito]:
    """Lo stesso dato riportato con valori diversi in documenti diversi."""
    gruppi: dict[str, list] = defaultdict(list)
    for r in p.riscontri:
        gruppi[r.campo].append(r)
    esiti = []
    for campo, voci in gruppi.items():
        valori = {_norm(r.valore) for r in voci}
        if len(valori) > 1:
            dettaglio = "; ".join(f"{r.documento}: {r.valore}" for r in voci)
            esiti.append(Esito(
                f"ris.{campo}", f"Coerenza dati: {campo}", Livello.NON_CONFORME,
                f"Valori discordanti tra i documenti ({dettaglio}).",
                integrazione=f"Allineamento del dato «{campo}» tra gli elaborati ({dettaglio})",
            ))
    return esiti


def _norm(valore: str) -> str:
    """Normalizza per il confronto: '51,50' e '51.5' sono uguali; il testo ignora maiuscole e spazi."""
    testo = " ".join(str(valore).lower().split())
    numero = testo.replace(".", "").replace(",", ".") if "," in testo else testo
    try:
        return f"{float(numero):.4f}"
    except ValueError:
        return testo


def stagione_e_validita(p: Pratica) -> list[Esito]:
    esiti = []
    tipo = p.intervento.tipo
    sotto = set(p.intervento.sottotipi)
    taglio_ceduo = tipo is T.CEDUO and not sotto <= {Sottotipo.SFOLLI, Sottotipo.DIRADAMENTI}
    if taglio_ceduo:
        s = regole()["ceduo"]["stagione_silvana"]
        esiti.append(Esito(
            "gen.stagione", "Epoca di taglio", Livello.INFO,
            f"Taglio ed esbosco del ceduo consentiti dal {s['da']} al {s['a']}.", "art. 29 c. 2",
            prescrizione=f"Il taglio e l'esbosco dovranno essere eseguiti esclusivamente dal {s['da']} al {s['a']} (art. 29 c. 2).",
        ))
    return esiti


TUTTE = [
    checklist, soglia_superficie, superfici, versamento, norma_modulo, tecnico,
    vincoli, verifiche_ufficio, riscontri, stagione_e_validita,
]
