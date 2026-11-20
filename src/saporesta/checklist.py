"""Checklist di controllo documentale (da 'PER APP_FORESTALE.xlsx').

Ogni voce dice quando è richiesta, come compare nel verbale ('RILEVATO che
l'istante ha trasmesso...') e cosa chiedere se manca.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .models import Pratica, Sottotipo, TipoIntervento, TitoloRichiedente

T = TipoIntervento


@dataclass(frozen=True)
class Voce:
    id: str
    gruppo: str
    testo: str  # come appare nel verbale
    richiesta: str | None = None  # testo per la richiesta di integrazioni (default: testo)
    condizione: Callable[[Pratica], bool] = lambda p: True

    @property
    def testo_richiesta(self) -> str:
        return self.richiesta or self.testo


def _tipo(*tipi: TipoIntervento) -> Callable[[Pratica], bool]:
    return lambda p: p.intervento.tipo in tipi


def _ceduo_con_matricine(p: Pratica) -> bool:
    return p.intervento.tipo is T.CEDUO and Sottotipo.SENZA_MATRICINE not in p.intervento.sottotipi


DOC = "Documentazione amministrativa (A02.2)"
REL = "Relazione tecnica (A02.5)"
CART = "Cartografia progettuale"
ALTRI = "Altri elaborati"
ENTI = "Boschi di Comuni ed enti pubblici"
PISTE = "Progetto apertura nuove piste"

VOCI: list[Voce] = [
    Voce("istanza", DOC, "Istanza A02 con indicazione dell'ultimo taglio e dell'età del bosco"),
    Voce("elenco_a02_2", DOC, "Elenco documentazione ed elaborati progettuali allegati all'istanza di autorizzazione (A02.2)"),
    Voce("scheda_a02_3", DOC, "Scheda Tecnica Utilizzazione Forestale - Allegato A02.3"),
    Voce("versamento", DOC, "Ricevuta di versamento per Diritti di Segreteria e per Diritti d'Istruttoria secondo l'Allegato \"F\" Tariffario Vincolo Idrogeologico del Reg. n. 4/2024"),
    Voce("scheda_a02_4", DOC, "Scheda Statistica Forestale - Allegato A02.4"),
    Voce("documento_richiedente", DOC, "Copia fotostatica del documento di riconoscimento in corso di validità del soggetto richiedente / proprietario del fondo"),
    Voce("delega_tecnico", DOC, "Procura speciale/Delega conferita dal proprietario al tecnico incaricato della progettazione", condizione=lambda p: p.titolo_richiedente is TitoloRichiedente.DELEGATO),
    Voce("delega_comproprietari", DOC, "Procura speciale/Delega conferita dai comproprietari del fondo al soggetto richiedente", condizione=lambda p: False),
    Voce("incarico_tecnico", DOC, "Lettera di conferimento incarico professionale per la Progettazione e per la Direzione dei Lavori"),
    Voce("documento_tecnico", DOC, "Copia fotostatica del documento di riconoscimento del progettista e D.D.L."),
    Voce("titolo_proprieta", DOC, "Titolo di proprietà con atti registrati"),
    Voce("antimafia", DOC, "Dichiarazione antimafia del soggetto richiedente"),
    Voce("fattura_tecnico", DOC, "Dichiarazione di pagamento della fattura del tecnico incaricato (L.R. 25/2018)"),
    Voce("catasto_incendi", DOC, "Certificato del catasto incendi ai sensi dell'art. 10 della Legge 353/2000 rilasciato dal Comune, oppure asseverazione del tecnico progettista"),
    Voce("visure_mappa", DOC, "Certificazione catastale [visure per immobile catasto terreni; mappa catastale in scala 1:4.000]"),
    Voce("dichiarazione_art54", DOC, "Dichiarazione ai sensi degli artt. 46 e 47 del D.P.R. n. 445/2000 che sull'area VIGE/NON VIGE il vincolo di cui all'art. 54 del R.D. 3267/23"),
    Voce("progetto_esecutivo", DOC, "Progetto Esecutivo degli interventi di Utilizzazione Forestale [cartaceo in triplice copia]"),
    Voce("pendenza_media", DOC, "Indicazione della pendenza media dell'area d'intervento"),
    Voce("viabilita", DOC, "Descrizione degli interventi sulla viabilità (manutenzione ordinaria/straordinaria)", condizione=lambda p: bool(p.intervento.manutenzione_viabilita)),
    Voce("asseverazione_art18", DOC, "Asseverazione che verranno rispettate le condizioni previste ai rispettivi commi dell'art. 18 - Tutela della biodiversità"),
    Voce("verbale_riconsegna", DOC, "Verbale di riconsegna terreni ex art. 68 R.D. 1126/26 e Piano di Coltura e Conservazione ex art. 54 R.D. 3267/23", condizione=lambda p: p.vincoli.vincolo_art54 or p.intervento.popolamento.origine_artificiale),
    Voce("studio_geomorfologico", DOC, "Studio di compatibilità geomorfologica (art. 23 c. 2 lett. a)", condizione=lambda p: any(r in ("R3", "R4") for r in p.vincoli.pai_geomorfologico + p.vincoli.pai_idraulico)),
    Voce("nulla_osta_area_protetta", DOC, "Nulla osta dell'ente gestore dell'area naturale protetta (art. 25 c. 2)", condizione=lambda p: bool(p.vincoli.aree_protette)),

    Voce("relazione_tecnica", REL, "Relazione Tecnica predisposta secondo l'Allegato A02.5"),
    Voce("cronoprogramma", REL, "1.1 Cronoprogramma delle lavorazioni di utilizzazione forestale", "Cronoprogramma delle lavorazioni di utilizzazione forestale: schema che rappresenti graficamente la pianificazione delle lavorazioni secondo una sequenza logica dei tempi in riferimento al lasso temporale d'intervento"),
    Voce("piedilista_confine", REL, "1.2 Piedilista di cavallettamento delle piante di confine georeferenziate in UTM WGS84"),
    Voce("elenco_matricine", REL, "1.3 Elenco delle matricine da riservare a dotazione del bosco (art. 34 e art. 10 c. 4)", condizione=_ceduo_con_matricine),
    Voce("elenco_invecchiamento", REL, "1.4 Elenco degli alberi da rilasciare a invecchiamento indefinito e di quelli morti, con specie, diametro e coordinate UTM WGS84 (artt. 18-19)", condizione=_tipo(T.FUSTAIA, T.TRANSITORIO)),
    Voce("foto", REL, "1.5 Documentazione fotografica dello stato dei luoghi con indicazione delle coordinate dei punti di ripresa"),
    Voce("asseverazione_compatibilita", REL, "1.6 Relazione di asseverazione di compatibilità idrogeologica, PAI, forestale, paesaggistica e ambientale dell'intervento"),

    Voce("carta_catastale", CART, "2.1 Planimetria catastale in scala 1:5.000 o 1:4.000 con area di intervento, sezioni di taglio, viabilità e aree di saggio"),
    Voce("corografia", CART, "2.2 Corografia in scala 1:10.000 o 1:25.000 con area di intervento e viabilità di accesso"),
    Voce("ortofoto", CART, "2.3 Ortofoto in scala 1:5.000 con sovrapposizione catastale, unità colturali / sezioni di taglio, viabilità e aree di saggio"),
    Voce("carta_interventi", CART, "2.4 Carta degli interventi su base CTR in scala 1:5.000 - 1:10.000"),
    Voce("carta_pendenze", CART, "2.5 Carta delle pendenze su base CTR in scala 1:5.000 nelle classi 0-20%, 21-40%, 41-60%, 61-80%, >80%"),

    Voce("piedilista_martellata", ALTRI, "Piedilista di martellata delle piante assegnate al taglio", condizione=_tipo(T.FUSTAIA, T.TRANSITORIO, T.AVVERSITA, T.INCENDIO)),
    Voce("piedilista_ipsometrica", ALTRI, "Piedilista degli alberi rilevati per la costruzione della curva ipsometrica", condizione=_tipo(T.FUSTAIA, T.TRANSITORIO)),
    Voce("piedilista_morti", ALTRI, "Piedilista degli alberi morti da rilasciare nelle fustaie", condizione=_tipo(T.FUSTAIA)),
    Voce("rilievi_dendrometrici", ALTRI, "Rilievi dendrometrici (aree di saggio)"),
    Voce("vinca", ALTRI, "Procedura di Valutazione di Incidenza (Reg. reg. n. 16/2009, D.G.R. 749/09)", condizione=lambda p: p.vincoli.natura2000),
    Voce("quadro_riepilogativo", ALTRI, "Quadro riepilogativo delle piante da utilizzare per specie e classi diametriche"),

    Voce("enti_macchiatico", ENTI, "All. 1 - Analisi dei prezzi di macchiatico / stima del materiale legnoso", condizione=lambda p: p.ente_pubblico),
    Voce("enti_capitolato", ENTI, "All. 2 - Capitolato d'oneri", condizione=lambda p: p.ente_pubblico),
    Voce("enti_verbale_assegno", ENTI, "All. 3 - Verbale di assegno / martellata e stima", condizione=lambda p: p.ente_pubblico),
    Voce("enti_determina", ENTI, "All. 4 - Determina di conferimento incarico al progettista", condizione=lambda p: p.ente_pubblico),
    Voce("enti_convenzione", ENTI, "All. 5 - Convenzione di affidamento incarico al progettista", condizione=lambda p: p.ente_pubblico),
    Voce("enti_delibera_progetto", ENTI, "All. 6 - Atto deliberativo di approvazione del progetto esecutivo", condizione=lambda p: p.ente_pubblico),
    Voce("enti_delibera_somme", ENTI, "All. 7 - Atto deliberativo di accantonamento delle somme da versare alla Regione", condizione=lambda p: p.ente_pubblico),
    Voce("enti_avviso_asta", ENTI, "All. 8 - Schema di avviso d'asta", condizione=lambda p: p.ente_pubblico),

    Voce("piste_relazione", PISTE, "Tav. 1 - Relazione tecnico descrittiva delle nuove piste", condizione=lambda p: p.intervento.nuove_piste),
    Voce("piste_cartografia", PISTE, "Tav. 2 - Elaborati cartografici delle nuove piste", condizione=lambda p: p.intervento.nuove_piste),
    Voce("piste_geologica", PISTE, "Tav. 3 - Relazione geologica", condizione=lambda p: p.intervento.nuove_piste),
    Voce("piste_foto", PISTE, "Tav. 4 - Documentazione fotografica", condizione=lambda p: p.intervento.nuove_piste),
    Voce("piste_cronoprogramma", PISTE, "Tav. 5 - Cronoprogramma dei lavori", condizione=lambda p: p.intervento.nuove_piste),
    Voce("piste_art146", PISTE, "Autorizzazione paesaggistica art. 146 D.Lgs. 42/2004", condizione=lambda p: p.intervento.nuove_piste),
    Voce("piste_dpr380", PISTE, "Titolo autorizzativo previsto dal D.P.R. 380/2001", condizione=lambda p: p.intervento.nuove_piste),
]

VOCI_PER_ID = {v.id: v for v in VOCI}


def voci_richieste(pratica: Pratica) -> list[Voce]:
    return [v for v in VOCI if v.condizione(pratica)]
