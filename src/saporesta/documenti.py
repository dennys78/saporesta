"""Generazione di verbale istruttorio, autorizzazione e richiesta integrazioni.

Il contesto passato ai modelli Word è costruito tutto qui, con testi già
formattati: i modelli restano semplici e modificabili in Word.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate, Listing

from . import formato as f
from .checklist import voci_richieste
from .models import Pratica, Sottotipo, StatoVoce, TipoIntervento
from .verifiche import Livello, Proposta, Risultato, esegui
from .verifiche.scheda import indici_prelievo
from .modelli_word import CARTELLA_MODELLI, assicura_modelli

T = TipoIntervento
S = Sottotipo

LUOGO = "Catanzaro"

NORMA_TITOLO = ("Regolamento n. 4 del 30/04/2024 di attuazione della Legge Regionale 12 ottobre 2012 n. 45 "
                "“Gestione, Tutela e Valorizzazione del Patrimonio Forestale Regionale”")

VISTI = [
    "il R.D. 30.12.1923 n. 3267 e il R.D. 16.05.1926 n. 1126;",
    "l'art. 149 del D.Lgs. 42/2004;",
    "la L.R. n. 45/2012 «Gestione, tutela e valorizzazione del patrimonio forestale regionale»;",
    "la D.G.R. n. 548 del 16/12/2016 «Linee guida per la redazione dei Piani di gestione forestale della Regione Calabria»;",
    "la D.G.R. n. 274 del 30/06/2017 «Piano Forestale Regionale 2014/2021»;",
    "la L.R. n. 51 del 22 dicembre 2017 «Norme di attuazione della legge 21 novembre 2000, n. 353 (Legge quadro in materia d'incendi boschivi)»;",
    "il D.Lgs. 3 aprile 2018, n. 34 «Testo Unico in materia di foreste e filiere forestali»;",
    f"il {NORMA_TITOLO};",
]

ETICHETTE_SOTTOTIPO = {
    S.SENZA_MATRICINE: "senza riserva di matricine",
    S.MATRICINATO: "con riserva di matricine",
    S.STERZO: "a sterzo",
    S.COMPOSTO: "composto",
    S.SFOLLI: "tagli intercalari - sfolli",
    S.DIRADAMENTI: "tagli intercalari - diradamenti",
    S.SFOLLAMENTI: "tagli intercalari - sfollamenti",
    S.RINNOVAZIONE: "tagli colturali di rinnovazione",
    S.PRIMO_AVVIAMENTO: "primo taglio di avviamento",
    S.SUCCESSIVI_AVVIAMENTO: "successivi tagli di avviamento",
    S.CONVERSIONE: "taglio di conversione a fustaia",
    S.INFRASTRUTTURE: "infrastrutture a rete e impianti tecnologici esistenti",
    S.MANUFATTI: "manufatti esistenti",
    S.ELETTRODOTTI: "aree di pertinenza degli elettrodotti",
    S.VIABILITA: "viabilità e pertinenze stradali",
    S.IDRAULICA: "opere e funzionalità idraulica",
}

TIPOLOGIA = {
    T.CEDUO: ("Taglio bosco governato a ceduo di superficie maggiore o uguale a 2,00 ha", "artt. 29-37"),
    T.NEOFORMAZIONE: ("Taglio dei soprassuoli di neoformazione", "art. 4"),
    T.FUSTAIA: ("Taglio bosco governato a fustaia", "artt. 38-40"),
    T.TRANSITORIO: ("Taglio dei soprassuoli transitori", "art. 41"),
    T.INCENDIO: ("Taglio boschi danneggiati dal fuoco", "art. 49"),
    T.AVVERSITA: ("Taglio nelle aree danneggiate da avversità meteoriche", "art. 50"),
    T.ART22: ("Tagli per l'eliminazione di rischi per la pubblica incolumità e per l'efficienza e la sicurezza", "art. 29 c. 1 lett. c"),
}

PREFISSI_TECNICI = ("a023.", "ced.", "fus.", "tra.", "neo.", "inc.", "avv.", "a22.", "cub.")


# ------------------------------------------------------------------------ testi

def tipologia(p: Pratica) -> str:
    nome, art = TIPOLOGIA[p.intervento.tipo]
    sotto = ", ".join(ETICHETTE_SOTTOTIPO[s] for s in p.intervento.sottotipi)
    testo = f"{nome}{' – ' + sotto if sotto else ''} ({art} Reg. n. 4/2024)"
    pop = p.intervento.popolamento
    specie = ", ".join(
        f"{s.nome}{' ' + f.num_breve(s.percentuale) + '%' if s.percentuale and len(pop.specie) > 1 else ''}"
        for s in pop.specie
    )
    if specie:
        testo += f" □ Specie: {specie}"
    if pop.eta_min is not None or pop.eta_max is not None:
        testo += f", età {pop.descrizione_eta}"
    return testo


def particelle(p: Pratica) -> str:
    return "; ".join(f"FG {g.foglio} part. {', '.join(g.particelle)}" for g in p.inquadramento.particelle)


def oggetto(p: Pratica) -> str:
    prot = f"Prot. Gen. - Regcal n. {p.protocollo} del {f.data(p.data_protocollo)}"
    if p.protocolli_integrazione:
        prot += ", integrazione " + ", ".join(f"Prot. Gen. - Regcal n. {x}" for x in p.protocolli_integrazione)
    i = p.inquadramento
    return (f"{prot} □ Comune di {i.comune.upper()} [{i.provincia}] località: “{i.localita.upper()}” □ {particelle(p)} "
            f"estese catastalmente ha {f.ha_catastale(i.superficie_catastale_ha)} di cui ha "
            f"{f.ha_catastale(i.superficie_intervento_ha)} costituenti la superficie interessata da intervento.")


def _nega(cond: bool) -> str:
    return "" if cond else "non "


def dichiarazioni(p: Pratica) -> list[str]:
    v = p.vincoli
    d = []
    if v.aree_protette:
        d.append(f"le zone interessate dall'intervento ricadono nella perimetrazione di: {', '.join(v.aree_protette)};")
    else:
        d.append("le zone interessate dall'intervento non ricadono nella perimetrazione di aree protette e parchi regionali e nazionali;")
    if v.natura2000:
        d.append(f"le zone interessate dall'intervento ricadono in siti afferenti alla rete «Natura 2000»"
                 f"{' (' + v.sito_natura2000 + ')' if v.sito_natura2000 else ''};")
    for nome, classi, tipo_rischio in [("geomorfologico", v.pai_geomorfologico, "frana"),
                                       ("idraulico", v.pai_idraulico, "inondazione")]:
        if classi:
            d.append(f"in riferimento all'assetto {nome} PAI, le zone interessate dall'intervento ricadono in aree a rischio "
                     f"{tipo_rischio} {', '.join(classi)};")
        else:
            d.append(f"in riferimento all'assetto {nome} PAI, le zone interessate dall'intervento non ricadono in aree a rischio "
                     f"{tipo_rischio} R4, R3, R2, R1;")
    d.append("di avere effettuato ai competenti uffici della Regione Calabria il versamento delle somme per Diritti di Segreteria "
             "e per Diritti d'Istruttoria, secondo quanto previsto dall'Allegato «F» Tariffario Vincolo Idrogeologico del Reg. n. 4/2024;")
    d.append("di dare inizio alle operazioni di taglio ad avvenuto ricevimento dell'autorizzazione, che, corredata del progetto "
             "approvato e di ogni altro titolo abilitativo, sarà custodita sul luogo dei lavori a disposizione delle Autorità preposte;")
    d.append("di comunicare, prima dell'inizio delle operazioni di taglio, la data di inizio dei lavori, le generalità e i recapiti "
             "del soggetto esecutore nonché del tecnico incaricato della Direzione dei Lavori;")
    d.append("di essere a conoscenza che la mancata comunicazione della nomina del Direttore dei Lavori annulla la validità "
             "dell'autorizzazione e che in caso di mancata presentazione del «certificato di regolare esecuzione» si applicano le "
             "sanzioni previste;")
    if p.tecnico:
        d.append(f"che le modalità di esecuzione degli interventi sono indicate negli elaborati progettuali redatti dal "
                 f"{tecnico_nome(p)}{tecnico_iscrizione(p)}, e di aver corredato l'istanza della documentazione di cui agli "
                 "Allegati A02.2, A02.3 e A02.4;")
    d.append(f"che l'area interessata da intervento {_nega(v.percorsa_incendio)}è soggetta al vincolo di cui all'art. 10 della "
             "Legge 353/2000;")
    d.append(f"che sui terreni interessati da intervento, rinsaldati e rimboschiti per motivi di pubblica utilità, "
             f"{_nega(v.vincolo_art54)}vige il vincolo di cui all'art. 54 del R.D. 3267/23;")
    d.append("che gli interventi previsti non sono in contrasto con le disposizioni del D.Lgs. 22 gennaio 2004 n. 42 «Codice dei "
             "beni culturali e del paesaggio»;")
    d.append("che adotterà e farà adottare ogni cautela necessaria ad evitare alterazioni idrogeologiche dell'area oggetto dei "
             "lavori nonché danni a persone o cose, tenendo sollevata la Regione Calabria da ogni controversia o rivendicazione di terzi.")
    return d


def tecnico_nome(p: Pratica) -> str:
    t = p.tecnico
    return f"{t.titolo} {t.cognome.upper()} {t.nome}" if t else ""


def tecnico_iscrizione(p: Pratica) -> str:
    t = p.tecnico
    if not t or not t.numero_iscrizione:
        return ""
    sez = f" sez. {t.sezione}" if t.sezione else ""
    return (f", iscritto all'Ordine dei Dottori Agronomi e Dottori Forestali della provincia di {t.ordine_provincia} "
            f"al n. {t.numero_iscrizione}{sez}")


def documenti_presenti(p: Pratica) -> list[str]:
    righe = []
    for voce in voci_richieste(p):
        stato = p.istruttoria.checklist.get(voce.id)
        if stato and stato.stato is StatoVoce.SI:
            nota = f" ({stato.nota})" if stato.nota else ""
            righe.append(f"{voce.testo}{nota};")
    return righe


def martellata_testo(p: Pratica, dispositivo: bool) -> str:
    m = p.martellata
    if not m:
        return ""
    a = m.numero_a or (m.numero_da + m.n_piante - 1)
    specie = f" di {m.specie.lower()}" if m.specie else ""
    sezione = f", sezione di taglio «{m.sezione}»," if m.sezione else ""
    martello = f" e con l'impronta del martello forestale riportante la dicitura «{m.sigla_martello}»" if m.sigla_martello else ""
    vernice = f", con vernice indelebile di colore {m.colore_vernice}" if m.colore_vernice else ""
    corpo = (f"contrassegnate su apposita specchiatura praticata al piede della pianta, con numero progressivo dal n. "
             f"{m.numero_da} al n. {a} compreso{martello}{vernice}")
    if dispositivo:
        return f"Le piante martellate sono in numero di {m.n_piante}{specie}{sezione} cavallettate a m 1,30, {corpo} [art. 10 Reg. n. 4/2024]."
    return f"Piedilista di martellata delle {m.n_piante} piante{specie} assegnate al taglio{sezione} {corpo}."


def prelievo_testo(p: Pratica) -> str:
    s = p.scheda
    if not s or s.totale_taglio.volume is None:
        return ""
    testo = (f"Il prelievo di legname su tutta la superficie di intervento, come da statistica forestale allegata alla "
             f"progettazione, è pari a m³ {f.num_breve(s.totale_taglio.volume)}")
    if s.assortimenti:
        parti = [f"m³ {f.num_breve(a.volume_m3)} di materiale legnoso per {a.descrizione}" for a in s.assortimenti]
        testo += ", suddiviso come segue: " + f.elenco(parti)
    return testo + "."


def tabella_prelievo(p: Pratica) -> list[dict[str, str]]:
    s = p.scheda
    if not s or s.totale_taglio.volume is None:
        return []
    ind = indici_prelievo(p)
    quota = s.percentuale_dichiarata_g / 100 if s.percentuale_dichiarata_g is not None else (
        ind.get("prelievo_g") or ind.get("prelievo_volume"))
    tt = s.totale_taglio
    massa = s.massa_taglio_totale_q or (tt.volume * s.peso_specifico_q_m3 if s.peso_specifico_q_m3 else None)
    riga = {
        "specie": p.intervento.popolamento.specie_prevalente or "—",
        "n": f.num(tt.n_piante, 0) if tt.n_piante is not None else "—",
        "g": f.num(tt.area_basimetrica),
        "v": f.num(tt.volume),
        "ps": f.num_breve(s.peso_specifico_q_m3),
        "massa": f.num(massa, 1),
        "pct": f.pct(quota) if quota is not None else "—",
    }
    return [riga, {**riga, "specie": "Totale"}]


def verifiche_tecniche(r: Risultato) -> list[str]:
    return [
        f"{e.titolo}: {e.messaggio.rstrip('.')}{' (' + e.articolo + ')' if e.articolo else ''};"
        for e in r.esiti if e.codice.startswith(PREFISSI_TECNICI) and e.livello in (Livello.OK, Livello.INFO)
    ]


def note_istruttore(p: Pratica, r: Risultato) -> list[str]:
    note = [f"{e.titolo}: {e.messaggio}" for e in r.esiti if e.livello is Livello.ATTENZIONE]
    return note + p.istruttoria.note_verbale


def preso_atto(p: Pratica) -> list[str]:
    ck = p.istruttoria.checklist

    def si(voce: str) -> bool:
        return voce in ck and ck[voce].stato is StatoVoce.SI

    righe = [f"degli elaborati tecnici costituenti il Progetto Esecutivo segnato a margine, redatti da"
             f"{' ' + tecnico_nome(p) + tecnico_iscrizione(p) if p.tecnico else 'l tecnico incaricato'}, presentati a corredo "
             "dell'istanza di autorizzazione;"]
    if si("asseverazione_compatibilita"):
        righe.append("dell'Asseverazione di compatibilità idrogeologica ed ambientale dell'intervento selvicolturale, resa in atti "
                     "dal tecnico progettista;")
    if si("fattura_tecnico"):
        righe.append("della Dichiarazione sostitutiva di atto di notorietà del professionista sottoscrittore degli elaborati "
                     "progettuali, redatta nelle forme di cui al D.P.R. n. 445/2000 secondo il modello di cui all'allegato A alla "
                     "L.R. 3 agosto 2018 n. 25;")
    if si("catasto_incendi"):
        nota = (ck["catasto_incendi"].nota or "").lower()
        fonte = "dell'asseverazione" if "assever" in nota else "del certificato del catasto incendi"
        righe.append(f"{fonte} che l'area oggetto dell'intervento non è stata interessata da incendi;")
    if si("dichiarazione_art54"):
        righe.append(f"della dichiarazione ai sensi degli artt. 46 e 47 del D.P.R. n. 445/2000 che sull'area interessata da "
                     f"intervento {_nega(p.vincoli.vincolo_art54)}vige il vincolo di cui all'art. 54 del R.D. 3267/23;")
    righe.append("che la documentazione amministrativa/progettuale è stata valutata positivamente in ordine alla "
                 "completezza/conformità rispetto alla modulistica ed al Reg. n. 4/2024 vigente;")
    righe.append("che l'istanza ed i relativi allegati tecnico/amministrativi sono conformi, coerenti ed esaustivi rispetto alla "
                 "vigente normativa di settore;")
    s = p.scheda
    if p.intervento.tipo in (T.FUSTAIA, T.TRANSITORIO) and s and s.alberi_invecchiamento:
        righe.append(f"che, per come previsto dall'art. 19 del Reg. n. 4/2024, sono stati rilasciati n. {s.alberi_invecchiamento} "
                     "alberi ad invecchiamento indefinito;")
    if p.intervento.tipo is T.CEDUO and s and s.matricine_ha:
        righe.append(f"che è previsto il rilascio di n. {f.num_breve(s.matricine_ha, 0)} matricine a ettaro;")
    return righe


def prescrizioni_standard(p: Pratica) -> list[str]:
    fustaia = p.intervento.tipo in (T.FUSTAIA, T.TRANSITORIO)
    art_ddl = "comma 8 dell'art. 40" if fustaia else "commi 12 e 13 dell'art. 31"
    art_cre = "comma 14 dell'art. 40" if fustaia else "comma 21 dell'art. 31"
    art_imprese = "comma 9 dell'art. 40" if fustaia else "comma 20 dell'art. 31"
    art_proroga = "comma 10 dell'art. 40" if fustaia else "comma 18 dell'art. 31"
    mesi = p.istruttoria.validita_mesi
    return [
        "Almeno 10 giorni prima dell'avvio delle operazioni di taglio, il concessionario del presente provvedimento deve comunicare "
        "alla Regione Calabria – U.O.A. Foreste, Forestazione e Difesa del Suolo nonché all'autorità di controllo competente per "
        "territorio, in indirizzo, la data presunta di inizio delle lavorazioni forestali, le generalità e i recapiti dell'Operatore "
        "incaricato della loro esecuzione ovvero del responsabile del cantiere, qualora si tratti di soggetto diverso dal titolare "
        "dell'impresa affidataria, nonché la nomina del Direttore dei Lavori.",
        "Il Direttore dei Lavori deve trasmettere copia del verbale di consegna del lotto boschivo interessato dall'intervento "
        "all'Operatore incaricato dell'esecuzione dei lavori di utilizzazione boschiva, che è tenuto agli adempimenti di «dovuta "
        "diligenza» previsti dalla normativa europea sulla commercializzazione del legname.",
        f"Atteso quanto stabilito al {art_ddl} del Reg. n. 4/2024, la mancata comunicazione della nomina del Direttore dei Lavori "
        "o la sua mancata nomina annulla la validità dell'autorizzazione concessa e comporta l'avvio del procedimento di sospensione "
        "dell'efficacia e di revoca della stessa, ai sensi della Legge 241/90 e della L.R. 19/2001.",
        "Prima dell'avvio effettivo delle operazioni di taglio deve essere apposto sul cantiere forestale, in posizione facilmente "
        "visibile, un cartello di dimensioni minime 40 x 50 cm riportante il tipo d'intervento, la proprietà, gli estremi della "
        "presente autorizzazione e il soggetto o ditta esecutrice (art. 31 c. 14).",
        f"Gli interventi devono essere eseguiti da imprese iscritte all'Albo Regionale delle Imprese Forestali ({art_imprese} del "
        "Reg. n. 4/2024).",
        f"Per come stabilito al {art_cre} del Reg. n. 4/2024, entro sessanta giorni dalla data di ultimazione dei lavori forestali "
        "deve essere presentato il certificato di regolare esecuzione a cura del Direttore dei Lavori, completo dell'indicazione dei "
        "volumi degli assortimenti mercantili prodotti. In caso di violazioni si applica la sanzione amministrativa di cui all'Allegato F.",
        "Al fine della tutela del bosco, l'Amministrazione si riserva di dettare ulteriori prescrizioni durante l'esecuzione delle "
        "operazioni di taglio e di sospendere l'efficacia dell'autorizzazione qualora, su segnalazione dell'Autorità di Polizia "
        "Giudiziaria o del Direttore dei Lavori, vengano rilevate inosservanze al Reg. n. 4/2024 o alle leggi in materia forestale, "
        "ambientale, paesaggistica e urbanistica; l'utilizzazione non potrà essere ripresa fino al versamento della relativa "
        "sanzione amministrativa.",
        "La presente autorizzazione, rilasciata nei soli riguardi forestali e idrogeologici, non pregiudica i diritti di terzi né "
        "quanto possa essere disposto da altri organismi tecnici e/o amministrativi dello Stato, della Regione, della Provincia e del "
        "Comune. Per quanto non espressamente previsto valgono tutte le disposizioni di legge in materia paesaggistica, forestale ed "
        "ambientale.",
        f"La presente autorizzazione ha validità di {mesi} mesi dalla data di rilascio. In caso di particolari condizioni "
        "meteorologiche o cause di forza maggiore, il Direttore dei Lavori deve comunicare la sospensione e la successiva ripresa "
        "dei lavori, con stato di avanzamento, restando immutato il termine di durata dell'autorizzazione; può essere concessa una "
        f"sola proroga su richiesta motivata presentata almeno trenta giorni prima della scadenza ({art_proroga}).",
        "L'autorizzazione ha carattere personale: in caso di subentro, l'avente causa deve chiedere alla Regione Calabria la "
        "novazione della titolarità; la mancata novazione comporta la sospensione della sua validità.",
        "L'autorizzazione, corredata di ogni altro titolo abilitativo, deve essere custodita sul luogo dei lavori a disposizione "
        "delle Autorità preposte; la mancata esibizione comporta l'avvio del procedimento di sospensione e revoca del provvedimento.",
        "Ferme restando le sanzioni penali previste dal D.P.R. 445/2000, le dichiarazioni false o mendaci e le violazioni delle "
        "prescrizioni impartite comportano la revoca del provvedimento.",
        "Il concessionario e la Direzione dei Lavori, ciascuno per la parte di propria competenza, devono inoltrare ogni "
        "comunicazione correlata al presente procedimento, oltre che alla Regione Calabria, anche al Comando Carabinieri Forestali "
        "competente per territorio, in indirizzo.",
    ]


# ---------------------------------------------------------------------- contesto

def contesto(p: Pratica, r: Risultato | None = None) -> dict[str, Any]:
    r = r or esegui(p)
    rich = p.richiedente
    i = p.inquadramento
    pop = p.intervento.popolamento
    t = p.tecnico
    specifiche = r.prescrizioni + p.istruttoria.prescrizioni_aggiuntive
    ind_rich = [rich.indirizzo and f"{rich.indirizzo}{', ' + rich.civico if rich.civico else ''}",
                " ".join(x for x in [rich.cap, rich.comune_residenza] if x) + (f" ({rich.provincia})" if rich.provincia else "")]
    rec_tec = []
    if t:
        rec_tec = [t.indirizzo and f"{t.indirizzo}{', ' + t.civico if t.civico else ''}",
                   " ".join(x for x in [t.cap, t.comune_residenza] if x) + (f" ({t.provincia})" if t.provincia else ""),
                   t.pec or t.email]
    data_doc = p.istruttoria.data_documento
    ctx: dict[str, Any] = {
        "norma_titolo": NORMA_TITOLO,
        "richiedente": rich,
        "richiedente_indirizzo": Listing("\n".join(x for x in ind_rich if x and x.strip())),
        "richiedente_indirizzo_riga": rich.residenza or "—",
        "richiedente_data_nascita": f.data(rich.data_nascita),
        "titolo_richiedente": p.titolo_richiedente.value,
        "classe_eutr": p.classe_eutr or "non indicata",
        "tecnico": t,
        "tecnico_nome": tecnico_nome(p),
        "tecnico_iscrizione": tecnico_iscrizione(p),
        "tecnico_recapito": Listing("\n".join(x for x in rec_tec if x and x.strip())),
        "destinatari_conoscenza": [Listing(d) for d in p.istruttoria.destinatari_conoscenza],
        "oggetto": oggetto(p),
        "tipologia": tipologia(p),
        "autorizzabile": r.proposta is Proposta.AUTORIZZABILE,
        "titolo_proposta": ("Proposta di autorizzazione con prescrizioni nei soli riguardi forestali e idrogeologici"
                            if r.proposta is Proposta.AUTORIZZABILE else
                            "Proposta di sospensione dei termini e richiesta di integrazioni"),
        "visti": VISTI,
        "straordinario": p.intervento.straordinario,
        "previsto_da": p.intervento.previsto_da,
        "titolo_progetto": p.intervento.titolo_progetto,
        "dichiarazioni": dichiarazioni(p),
        "documenti_presenti": documenti_presenti(p),
        "martellata": p.martellata,
        "martellata_testo": martellata_testo(p, dispositivo=False),
        "martellata_dispositivo": martellata_testo(p, dispositivo=True),
        "inquadramento": i,
        "particelle_testo": particelle(p),
        "sup_catastale": f.ha_catastale(i.superficie_catastale_ha),
        "sup_intervento": f.ha_catastale(i.superficie_intervento_ha),
        "specie": pop.specie_prevalente,
        "eta": pop.descrizione_eta,
        "ultimo_taglio": str(pop.anno_ultimo_taglio) if pop.anno_ultimo_taglio else "dato non rilevabile",
        "destinazione_urbanistica": i.destinazione_urbanistica or "non indicata",
        "verifiche_tecniche": verifiche_tecniche(r),
        "tabella_prelievo": tabella_prelievo(p),
        "verifiche_ufficio": [f"{v.esito};" for v in p.istruttoria.verifiche_ufficio] or ["nessuna verifica registrata;"],
        "note_istruttore": note_istruttore(p, r),
        "prelievo_testo": prelievo_testo(p),
        "viabilita_testo": f"È prevista la manutenzione {p.intervento.manutenzione_viabilita}." if p.intervento.manutenzione_viabilita else "",
        "prescrizioni_specifiche": specifiche or ["nessuna prescrizione specifica oltre a quelle di legge."],
        "prescrizioni": specifiche + prescrizioni_standard(p),
        "preso_atto": preso_atto(p),
        "versamento_testo": f" (€ {f.num(p.versamento.importo_totale)})" if p.versamento.importo_totale else "",
        "luogo_data": f"{LUOGO}, {f.data(data_doc)}" if data_doc else f"{LUOGO}, lì ____________",
        "firmatari": p.istruttoria.firmatari,
        "integrazioni": r.integrazioni + p.istruttoria.integrazioni_aggiuntive,
        "rilievi": [f"{e.titolo}: {e.messaggio}{' (' + e.articolo + ' Reg. n. 4/2024)' if e.articolo else ''}" for e in r.rilievi],
    }
    return ctx


# ---------------------------------------------------------------------- render

MODELLI = {
    "verbale": "verbale_istruttorio.docx",
    "autorizzazione": "autorizzazione.docx",
    "integrazioni": "richiesta_integrazioni.docx",
}


def genera(p: Pratica, tipo: str, destinazione: Path, r: Risultato | None = None,
           cartella_modelli: Path = CARTELLA_MODELLI) -> Path:
    if cartella_modelli == CARTELLA_MODELLI:
        assicura_modelli()
    modello = DocxTemplate(str(cartella_modelli / MODELLI[tipo]))
    modello.render(contesto(p, r), autoescape=True)
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    modello.save(str(destinazione))
    return destinazione


def documenti_per_proposta(r: Risultato) -> list[str]:
    """Il verbale istruttorio esce sempre; poi la richiesta di integrazioni o l'autorizzazione secondo l'esito."""
    if r.proposta is Proposta.INTEGRAZIONI:
        return ["verbale", "integrazioni"]
    if r.proposta is Proposta.AUTORIZZABILE:
        return ["verbale", "autorizzazione"]
    return ["verbale"]


# ----------------------------------------------------------- rapporto in Word

ORDINE_LIVELLI = [Livello.NON_CONFORME, Livello.DA_VERIFICARE, Livello.ATTENZIONE, Livello.INFO, Livello.OK]
TITOLI_LIVELLI = {
    Livello.NON_CONFORME: "Non conformità", Livello.DA_VERIFICARE: "Da verificare", Livello.ATTENZIONE: "Attenzione",
    Livello.INFO: "Informazioni", Livello.OK: "Controlli superati",
}


def genera_rapporto(p: Pratica, r: Risultato, destinazione: Path,
                    correzioni: list[tuple[str, str, str]] | None = None) -> Path:
    """Rapporto dell'analisi istruttoria (uso interno dell'ufficio) in formato Word."""
    from docx import Document
    from docx.shared import Pt, RGBColor

    from .verifiche.cubatura import ricalcola

    doc = Document()
    stile = doc.styles["Normal"]
    stile.font.name = "Times New Roman"
    stile.font.size = Pt(11)
    colori = {Livello.NON_CONFORME: RGBColor(0xA3, 0x3A, 0x2B), Livello.DA_VERIFICARE: RGBColor(0xA0, 0x6B, 0x00),
              Livello.ATTENZIONE: RGBColor(0xA0, 0x6B, 0x00), Livello.INFO: RGBColor(0x2D, 0x5F, 0x87),
              Livello.OK: RGBColor(0x2F, 0x6B, 0x45)}

    doc.add_heading(f"Rapporto istruttorio – Prot. {p.protocollo or 'n.d.'}", level=1)
    i = p.inquadramento
    doc.add_paragraph(f"{p.richiedente.nome_completo} – Comune di {i.comune} ({i.provincia}), località {i.localita} – "
                      f"{particelle(p)} – superficie d'intervento ha {f.ha_catastale(i.superficie_intervento_ha)}")
    doc.add_paragraph(tipologia(p))
    esito = doc.add_paragraph()
    esito.add_run("Esito proposto: ").bold = True
    esito.add_run(r.proposta.value.upper()).bold = True

    # tavola di cubatura
    doc.add_heading("Tavola di cubatura", level=2)
    for e in r.esiti:
        if e.codice.startswith("cub."):
            par = doc.add_paragraph(style="List Bullet")
            run = par.add_run(f"{e.titolo}: ")
            run.bold = True
            run.font.color.rgb = colori[e.livello]
            par.add_run(e.messaggio)
    rc = ricalcola(p)
    if rc and rc.righe:
        tacal = rc.tavola == "tacal_2016"
        intest = ["d (cm)", "h dichiarata (m)"] + (["h tariffa (m)"] if tacal else []) + \
                 ["n. piante", "v dichiarato (m³/pianta)", "v tavola (m³/pianta)", "scarto"]
        t = doc.add_table(rows=1, cols=len(intest))
        t.style = "Table Grid"
        for cella, testo in zip(t.rows[0].cells, intest):
            cella.text = testo
            cella.paragraphs[0].runs[0].bold = True
        for rg in rc.righe:
            valori = [f.num_breve(rg.d), f.num_breve(rg.h, 1)] + ([f.num_breve(rg.h_tavola, 1)] if tacal else []) + [
                f.num_breve(rg.n, 0), f.num(rg.v_dichiarato, 3), f.num(rg.v_tavola, 3),
                (f"{'+' if rg.scarto > 0 else ''}{f.num_breve(rg.scarto * 100, 1)}%" if rg.scarto is not None else "—")]
            for cella, testo in zip(t.add_row().cells, valori):
                cella.text = testo

    # tutti i controlli per livello
    for livello in ORDINE_LIVELLI:
        esiti = [e for e in r.per_livello(livello) if not e.codice.startswith("cub.")]
        if not esiti:
            continue
        doc.add_heading(f"{TITOLI_LIVELLI[livello]} ({len(esiti)})", level=2)
        for e in esiti:
            par = doc.add_paragraph(style="List Bullet")
            run = par.add_run(f"{e.titolo}: ")
            run.bold = True
            run.font.color.rgb = colori[livello]
            par.add_run(e.messaggio + (f" ({e.articolo})" if e.articolo else ""))
    accertati = p.istruttoria.dati_accertati
    if correzioni or accertati:
        doc.add_heading("Dati corretti o accertati dall'istruttore", level=2)
        if correzioni:
            t = doc.add_table(rows=1, cols=3)
            t.style = "Table Grid"
            for cella, testo in zip(t.rows[0].cells, ["Dato", "Letto dai PDF", "Valore usato"]):
                cella.text = testo
                cella.paragraphs[0].runs[0].bold = True
            for riga in correzioni:
                for cella, testo in zip(t.add_row().cells, riga):
                    cella.text = testo
        for a in accertati:
            doc.add_paragraph(f"{a.campo}: valore accertato {a.valore}" + (f" – {a.nota}" if a.nota else ""),
                              style="List Bullet")
    if r.integrazioni:
        doc.add_heading("Integrazioni da chiedere all'istante", level=2)
        for x in r.integrazioni:
            doc.add_paragraph(x, style="List Number")
    if r.prescrizioni:
        doc.add_heading("Prescrizioni specifiche proposte", level=2)
        for x in r.prescrizioni:
            doc.add_paragraph(x, style="List Bullet")
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(destinazione))
    return destinazione
