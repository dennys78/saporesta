"""Costruisce i modelli Word (docxtpl) di verbale, autorizzazione e richiesta integrazioni.

I modelli partono dalla carta intestata dell'ufficio: un qualunque documento Word dell'ufficio
di cui si tengono intestazione, piè di pagina e stili, svuotandone il corpo. La carta intestata
NON è nel repository: si carica dalla pagina Impostazioni (o con `saporesta modelli
--carta-intestata`) e resta nella cartella dei modelli. Senza carta intestata i modelli
vengono creati su un foglio bianco. I modelli contengono segnaposto Jinja ({{ ... }}) che
documenti.py riempie con i dati della pratica.

Dopo la generazione i modelli si possono ritoccare in Word: basta non spezzare i
segnaposto {{ ... }} e {%p ... %} / {%tr ... %}.
"""

from __future__ import annotations

import os
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

CARTELLA_MODELLI = Path(os.environ.get("SAPORESTA_MODELLI", Path(__file__).resolve().parents[2] / "modelli"))
BASE = CARTELLA_MODELLI / "base_carta_intestata.docx"
NOMI_MODELLI = ["verbale_istruttorio.docx", "autorizzazione.docx", "richiesta_integrazioni.docx"]
# aumentare quando cambia il testo dei modelli: le installazioni esistenti li rigenerano da sole
VERSIONE_MODELLI = "2"

FONT = "Times New Roman"


# --------------------------------------------------------------------------- base

def crea_base(sorgente: Path, destinazione: Path | None = None) -> Path:
    """Copia intestazioni e stili di un documento dell'ufficio svuotandone il corpo."""
    destinazione = destinazione or BASE
    doc = Document(str(sorgente))
    body = doc.element.body
    sect = body[-1] if body[-1].tag == qn("w:sectPr") else None
    for elemento in list(body):
        if elemento is not sect:
            body.remove(elemento)
    if sect is not None:
        cols = sect.find(qn("w:cols"))
        if cols is not None:
            cols.set(qn("w:num"), "1")
    # Il documento d'origine ha più sezioni: le intestazioni sono collegate all'ultima.
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    doc.core_properties.author = "Regione Calabria - U.O.A. Foreste"
    doc.core_properties.title = ""
    doc.core_properties.last_modified_by = ""
    doc.core_properties.comments = ""
    doc.save(str(destinazione))
    return destinazione


# ----------------------------------------------------------------------- helper

class Scrittore:
    def __init__(self, base: Path | None = None):
        base = base or BASE
        if base.exists():
            self.doc = Document(str(base))
        else:  # foglio bianco A4
            self.doc = Document()
            sezione = self.doc.sections[0]
            sezione.page_width, sezione.page_height = Cm(21), Cm(29.7)
            sezione.left_margin = sezione.right_margin = Cm(1.7)
            sezione.top_margin, sezione.bottom_margin = Cm(1.5), Cm(2)
        stile = self.doc.styles["Normal"]
        stile.font.name = FONT
        stile.font.size = Pt(11)
        rpr = stile.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = rpr.makeelement(qn("w:rFonts"), {})
            rpr.append(rfonts)
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rfonts.set(qn(attr), FONT)
        pf = stile.paragraph_format
        pf.space_after = Pt(4)
        pf.space_before = Pt(0)
        pf.line_spacing = 1.1

    def par(self, *parti, allinea="giustifica", rientro: float | None = None, dopo: float | None = None,
            prima: float | None = None, dimensione: float | None = None, sporgente: float | None = None):
        """parti: stringhe oppure (testo, 'b'/'i'/'u'/'bi'...)."""
        p = self.doc.add_paragraph()
        p.alignment = {
            "giustifica": WD_ALIGN_PARAGRAPH.JUSTIFY,
            "centro": WD_ALIGN_PARAGRAPH.CENTER,
            "destra": WD_ALIGN_PARAGRAPH.RIGHT,
            "sinistra": WD_ALIGN_PARAGRAPH.LEFT,
        }[allinea]
        if rientro is not None:
            p.paragraph_format.left_indent = Cm(rientro)
        if sporgente is not None:
            p.paragraph_format.first_line_indent = Cm(-sporgente)
            if rientro is not None:
                # il testo dopo il trattino/numero si allinea al rientro
                p.paragraph_format.tab_stops.add_tab_stop(Cm(rientro))
        if dopo is not None:
            p.paragraph_format.space_after = Pt(dopo)
        if prima is not None:
            p.paragraph_format.space_before = Pt(prima)
        for parte in parti:
            testo, fmt = (parte, "") if isinstance(parte, str) else parte
            run = p.add_run(testo)
            run.bold = "b" in fmt
            run.italic = "i" in fmt
            run.underline = "u" in fmt
            if dimensione:
                run.font.size = Pt(dimensione)
        return p

    def tag(self, testo: str):
        """Paragrafo che contiene solo un tag docxtpl {%p ... %}."""
        p = self.doc.add_paragraph()
        p.add_run(testo)
        return p

    def elenco(self, variabile: str, punto: str = "–", rientro: float = 0.8, campo: str = "x"):
        self.tag(f"{{%p for x in {variabile} %}}")
        self.par(f"{punto}\t{{{{ {campo} }}}}", rientro=rientro, sporgente=0.5)
        self.tag("{%p endfor %}")

    def se(self, condizione: str):
        self.tag(f"{{%p if {condizione} %}}")

    def fine_se(self):
        self.tag("{%p endif %}")

    def tabella(self, intestazioni: list[str], variabile: str, campi: list[str], larghezze: list[float],
                riga_totale: list[str] | None = None, dimensione: float = 10):
        t = self.doc.add_table(rows=1, cols=len(intestazioni))
        t.style = "Table Grid" if "Table Grid" in [s.name for s in self.doc.styles] else None
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, testo in enumerate(intestazioni):
            self._cella(t.rows[0].cells[i], testo, True, dimensione)
        # riga di apertura ciclo, riga dati, riga di chiusura ciclo
        r = t.add_row()
        r.cells[0].text = f"{{%tr for r in {variabile} %}}"
        r = t.add_row()
        for i, campo in enumerate(campi):
            self._cella(r.cells[i], f"{{{{ r.{campo} }}}}", False, dimensione)
        r = t.add_row()
        r.cells[0].text = "{%tr endfor %}"
        if riga_totale:
            r = t.add_row()
            for i, testo in enumerate(riga_totale):
                self._cella(r.cells[i], testo, True, dimensione)
        for riga in t.rows:
            for i, cella in enumerate(riga.cells):
                cella.width = Cm(larghezze[i])
        self._bordi(t)
        self.doc.add_paragraph()
        return t

    def tabella_chiave_valore(self, righe: list[tuple[str, str]], larghezze=(6.0, 11.0), dimensione: float = 10):
        t = self.doc.add_table(rows=0, cols=2)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for chiave, valore in righe:
            r = t.add_row()
            self._cella(r.cells[0], chiave, False, dimensione)
            self._cella(r.cells[1], valore, True, dimensione)
            r.cells[0].width, r.cells[1].width = Cm(larghezze[0]), Cm(larghezze[1])
        self._bordi(t)
        self.doc.add_paragraph()
        return t

    @staticmethod
    def _cella(cella, testo, grassetto, dimensione):
        cella.text = ""
        p = cella.paragraphs[0]
        p.paragraph_format.space_after = Pt(1)
        run = p.add_run(testo)
        run.bold = grassetto
        run.font.size = Pt(dimensione)

    @staticmethod
    def _bordi(tabella):
        tbl_pr = tabella._tbl.tblPr
        bordi = tbl_pr.makeelement(qn("w:tblBorders"), {})
        for lato in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = bordi.makeelement(qn(f"w:{lato}"), {
                qn("w:val"): "single", qn("w:sz"): "4", qn("w:space"): "0", qn("w:color"): "808080"})
            bordi.append(el)
        tbl_pr.append(bordi)

    def salva(self, nome: str) -> Path:
        percorso = CARTELLA_MODELLI / nome
        self.doc.save(str(percorso))
        return percorso


# ------------------------------------------------------------------ blocchi comuni

def _norma(s: Scrittore):
    s.par(("{{ norma_titolo }}", "i"), allinea="centro", dimensione=9, dopo=0)
    s.par(("[R.D. 30 dicembre 1923, n. 3267, R.D. 16.05.1926 n. 1126, D. Lgs. 3 aprile 2018, n. 34]", "i"),
          allinea="centro", dimensione=9, dopo=10)


def _destinatari(s: Scrittore, etichetta_richiedente: str):
    s.par((etichetta_richiedente, "i"), allinea="destra", dopo=0, rientro=9)
    s.par(("{{ richiedente.nome_completo }}", "b"), allinea="sinistra", rientro=9, dopo=0)
    s.par("{{ richiedente_indirizzo }}", allinea="sinistra", rientro=9, dopo=8)
    s.par(("E.p.c.", "i"), allinea="sinistra", rientro=9, dopo=0)
    s.se("tecnico")
    s.par(("{{ tecnico_nome }}", "b"), allinea="sinistra", rientro=9, dopo=0)
    s.par("Progettista", allinea="sinistra", rientro=9, dopo=0)
    s.par("{{ tecnico_recapito }}", allinea="sinistra", rientro=9, dopo=8)
    s.fine_se()
    s.tag("{%p for d in destinatari_conoscenza %}")
    s.par("{{ d }}", allinea="sinistra", rientro=9, dopo=8)
    s.tag("{%p endfor %}")


def _oggetto(s: Scrittore, coda: str):
    s.par(("OGGETTO: ", "b"), ("{{ oggetto }}", "b"), prima=6)
    s.par(("{{ tipologia }}", "b"))
    s.par(("□ " + coda, "bu"), dopo=10)


def _visti(s: Scrittore):
    s.par(("Visti,", "b"))
    s.elenco("visti")


def _firme(s: Scrittore, con_dirigente: bool):
    s.par("", dopo=12)
    t = s.doc.add_table(rows=2, cols=3 if con_dirigente else 2)
    etichette = ["Il Funzionario Istruttore", "Il Responsabile del Procedimento"]
    nomi = ["{{ firmatari.istruttore or '______________________' }}",
            "{{ firmatari.responsabile_procedimento or '______________________' }}"]
    if con_dirigente:
        etichette.append("{{ firmatari.qualifica_dirigente }}")
        nomi.append("{{ firmatari.dirigente or '______________________' }}")
    for i, (e, n) in enumerate(zip(etichette, nomi)):
        Scrittore._cella(t.rows[0].cells[i], e, False, 10)
        Scrittore._cella(t.rows[1].cells[i], n, True, 10)
        for r in t.rows:
            r.cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER


# ------------------------------------------------------------------------ verbale

def modello_verbale() -> Path:
    s = Scrittore()
    _norma(s)
    s.par(("VERBALE ISTRUTTORIO", "b"), allinea="centro", dimensione=13, dopo=2)
    s.par("Al Dirigente", allinea="destra", dopo=0)
    s.par(("S E D E", "u"), allinea="destra", dopo=10)
    _oggetto(s, "{{ titolo_proposta }}")

    s.par("L'istanza è stata presentata, su iniziativa di parte, da {{ richiedente.nome_completo }}, "
          "{{ richiedente.nato }} a {{ richiedente.luogo_nascita or '—' }} il {{ richiedente_data_nascita }} e residente in "
          "{{ richiedente_indirizzo_riga }}, in qualità di {{ titolo_richiedente }}.")
    s.par("Classificazione ai fini EUTR (Reg. (UE) n. 995/2010): {{ classe_eutr }}.")
    s.par("L'Istruttore, in esito al procedimento segnato a margine:", prima=4)
    _visti(s)

    s.par(("RILEVATO", "b"), " che l'istante, sull'apposita modulistica, ha avanzato istanza di autorizzazione all'esecuzione "
          "dei seguenti interventi selvicolturali:", prima=4)
    s.par("□ {{ tipologia }}", rientro=0.8)
    s.par("Taglio {{ 'straordinario' if straordinario else 'ordinario' }}{{ ', previsto da: ' ~ previsto_da if previsto_da else '' }}.",
          rientro=0.8)

    s.par(("RILEVATO", "b"), " che l'istante, sull'apposita modulistica, ha dichiarato, tra l'altro, quanto segue:", prima=4)
    s.elenco("dichiarazioni")

    s.par(("RILEVATO", "b"), " che l'istante, sulla scorta dell'elenco A02.2 della documentazione ed elaborati del progetto "
          "esecutivo, ha trasmesso quanto segue:", prima=4)
    s.elenco("documenti_presenti")

    s.se("martellata")
    s.par("{{ martellata_testo }}", prima=4)
    s.fine_se()

    s.par(("ESAMINATA", "b"), " la suddetta documentazione amministrativa/progettuale e valutata la stessa in ordine alla "
          "completezza/conformità rispetto alla modulistica ed al Reg. n. 4/2024 vigente, fermo restando che il merito, secondo "
          "le vigenti disposizioni normative, resta di esclusiva responsabilità dei dichiaranti/tecnici che hanno redatto la "
          "documentazione di che trattasi;", prima=4)

    s.par(("VERIFICATO", "b"), " che i terreni interessati da intervento, per come si evince dalla dichiarazione, presentano il "
          "seguente inquadramento territoriale:", prima=4)
    s.tabella_chiave_valore([
        ("COMUNE", "{{ inquadramento.comune|upper }} ({{ inquadramento.provincia }})"),
        ("LOCALITÀ", "{{ inquadramento.localita|upper }}"),
        ("FOGLI E PARTICELLE", "{{ particelle_testo }}"),
        ("SFC. CATASTALE", "ha {{ sup_catastale }}"),
        ("SFC. INTERVENTO", "ha {{ sup_intervento }}"),
        ("SPECIE PREVALENTE", "{{ specie or 'non indicata' }}"),
        ("ETÀ DEL BOSCO", "{{ eta }}"),
        ("DATA ULTIMO TAGLIO", "{{ ultimo_taglio }}"),
        ("STRUMENTO URBANISTICO", "{{ destinazione_urbanistica }}"),
    ])

    s.se("verifiche_tecniche")
    s.par(("VERIFICATO", "b"), " altresì, rispetto al Reg. n. 4/2024, che:")
    s.elenco("verifiche_tecniche")
    s.fine_se()

    s.se("tabella_prelievo")
    s.par("Entità dell'intervento selvicolturale (piante assegnate al taglio sull'intera superficie d'intervento):", prima=4)
    s.tabella(
        ["Specie", "N. piante", "Area basimetrica G [m²]", "Volume dendrometrico [m³]", "Peso specifico [q/m³]", "Massa [q]", "% asportato"],
        "tabella_prelievo",
        ["specie", "n", "g", "v", "ps", "massa", "pct"],
        [3.2, 1.8, 2.4, 2.6, 2.2, 2.0, 2.0],
    )
    s.fine_se()

    s.par(("CONSIDERATO", "b"), " che, anche esulando dal competente parere ai soli fini forestali ed idrogeologici, sono state "
          "espletate d'ufficio le seguenti ulteriori verifiche:", prima=4)
    s.elenco("verifiche_ufficio")

    s.se("note_istruttore")
    s.par(("RILEVATO", "b"), " inoltre:", prima=4)
    s.elenco("note_istruttore")
    s.fine_se()

    s.par("Il Responsabile del Procedimento, in esito all'istanza in esame ed alla relativa istruttoria:", prima=6)
    s.par(("VISTI", "b"), " l'istanza e la relativa documentazione tecnica/amministrativa e l'istruttoria sopra riportata;")
    s.se("autorizzabile")
    s.par(("RITENUTO", "b"), ", pertanto, che l'istanza e i relativi allegati tecnico/amministrativi sono conformi, coerenti ed "
          "esaustivi rispetto alla vigente normativa di settore;")
    s.par(("PROPONE", "b"), allinea="centro", prima=6)
    s.par("L'autorizzazione nei soli riguardi forestali e idrogeologici, nel Comune di {{ inquadramento.comune|upper }} "
          "[{{ inquadramento.provincia }}] località «{{ inquadramento.localita|upper }}», {{ particelle_testo }}, estese "
          "catastalmente ha {{ sup_catastale }} di cui ha {{ sup_intervento }} costituenti la superficie ragguagliata interessata "
          "da intervento, per:")
    s.par("□ {{ tipologia }}{{ ' come da Progetto «' ~ titolo_progetto ~ '»' if titolo_progetto else '' }} [{{ norma_titolo }}].",
          rientro=0.8)
    s.se("martellata")
    s.par("{{ martellata_dispositivo }}")
    s.fine_se()
    s.se("prelievo_testo")
    s.par("{{ prelievo_testo }}")
    s.fine_se()
    s.se("viabilita_testo")
    s.par("{{ viabilita_testo }}")
    s.fine_se()
    s.par("Quanto sopra, fatti salvi i diritti di terzi, la veridicità dei dati riportati in progetto, altri vincoli di qualsiasi "
          "natura esistenti sull'area oggetto di intervento e subordinatamente all'osservanza del Reg. n. 4/2024 e delle "
          "prescrizioni di seguito indicate:")
    s.elenco("prescrizioni_specifiche")
    s.tag("{%p else %}")
    s.par(("RITENUTO", "b"), " che, allo stato degli atti, non sussistono i requisiti, le condizioni di ammissibilità ed i "
          "presupposti rilevanti per l'adozione del provvedimento di autorizzazione;")
    s.par(("PROPONE", "b"), allinea="centro", prima=6)
    s.par("La comunicazione all'istante della sospensione dei termini per concludere il procedimento e la richiesta dei "
          "seguenti elementi integrativi:")
    s.tag("{%p for x in integrazioni %}")
    s.par("{{ loop.index }}.\t{{ x }};", rientro=0.8, sporgente=0.6)
    s.tag("{%p endfor %}")
    s.se("rilievi")
    s.par("nonché la presentazione di controdeduzioni, ovvero la rimodulazione del progetto, in merito ai seguenti profili di "
          "non conformità al Reg. n. 4/2024:")
    s.tag("{%p for x in rilievi %}")
    s.par("–\t{{ x }}", rientro=0.8, sporgente=0.5)
    s.tag("{%p endfor %}")
    s.fine_se()
    s.fine_se()
    s.par("Letto, confermato e sottoscritto, il presente verbale viene sottoposto al Dirigente per il seguito di competenza.",
          prima=6)
    s.par("{{ luogo_data }}", allinea="sinistra", prima=6)
    _firme(s, con_dirigente=False)
    return s.salva("verbale_istruttorio.docx")


# ------------------------------------------------------------------ autorizzazione

def modello_autorizzazione() -> Path:
    s = Scrittore()
    _destinatari(s, "Al Concessionario")
    _oggetto(s, "Autorizzazione con prescrizioni nei soli riguardi forestali e idrogeologici")
    s.par("Concessionario: ", ("{{ richiedente.nome_completo }}", "b"), " – {{ richiedente.nato }} a "
          "{{ richiedente.luogo_nascita or '—' }} il {{ richiedente_data_nascita }} e residente in {{ richiedente_indirizzo_riga }}, "
          "in qualità di {{ titolo_richiedente }}.")
    _visti(s)
    s.par("In esito al procedimento di cui all'istanza segnata a margine, avviato su iniziativa di parte da "
          "{{ richiedente.nome_completo }}, in qualità di {{ titolo_richiedente }};", prima=4)
    s.par(("Preso atto,", "b"), prima=4)
    s.elenco("preso_atto")
    s.par(("Tenuto conto", "b"), ", che gli interventi selvicolturali illustrati nella Relazione Tecnica di progetto verrebbero ad "
          "essere eseguiti e circoscritti nei limiti fisiografici e catastali dei mappali interessati da intervento riportati in "
          "epigrafe, altresì georeferenziati e raffigurati negli elaborati cartografici allegati;")
    s.par(("Considerando", "b"), ", che le forme di trattamento colturale previste nella proposta progettuale, per quanto possibile "
          "desumere dall'esame dei relativi elaborati tecnici, rientrerebbero nell'ordinaria attività silvana e sarebbero tali da "
          "assicurare la rinnovazione e la perpetuazione del bosco, le potenzialità evolutive del soprassuolo, la biodiversità "
          "esistente e la conservazione del suolo, altresì compatibili con le disposizioni recate dal Reg. n. 4/2024 e con gli "
          "indirizzi concernenti la gestione forestale sostenibile di cui al vigente Programma Forestale Regionale;")
    s.par(("Dato atto", "b"), ", che fatta salva l'applicazione dell'art. 143, comma 4, lett. a) e dell'art. 156, comma 4, agli "
          "effetti del disposto dell'art. 149 del D.Lgs. 22/01/2004 n. 42, per il taglio colturale, la forestazione, la "
          "riforestazione, le opere di bonifica, antincendio e di conservazione da eseguirsi nei boschi e nelle foreste indicati "
          "dall'art. 142, comma 1, lettera g), non è comunque richiesta l'autorizzazione prescritta dagli artt. 146, 147 e 159, "
          "purché previsti ed autorizzati in base alla normativa in materia;")
    s.par(("Dato atto", "b"), " che, in ogni caso, il merito di tutta la documentazione amministrativa e tecnica resta di esclusiva "
          "responsabilità dei dichiaranti/tecnici che l'hanno redatta, rispondendone circa la completezza progettuale ed "
          "amministrativa e circa l'acquisizione di tutti gli altri pareri, nulla osta e assensi previsti per legge;")
    s.par(("Preso atto", "b"), ", che il Richiedente ha versato a favore della Regione Calabria l'importo dovuto per diritti di "
          "segreteria ed istruttoria di cui al Tariffario del Vincolo Idrogeologico{{ versamento_testo }};")
    s.par("Su conforme proposta formulata alla stregua dell'istruttoria compiuta dalla struttura interessata nonché dell'espressa "
          "dichiarazione di fattibilità resa dal funzionario preposto in qualità di Responsabile del Procedimento, allo stato "
          "degli atti a disposizione,")
    s.par(("AUTORIZZA", "b"), allinea="centro", prima=6, dimensione=12)
    s.par("nei soli riguardi forestali e idrogeologici, fatti salvi i diritti di terzi, l'esecuzione del trattamento colturale "
          "appresso specificato{{ ', di cui al Progetto «' ~ titolo_progetto ~ '»' if titolo_progetto else '' }}, in agro del "
          "Comune di {{ inquadramento.comune|upper }} [{{ inquadramento.provincia }}] località «{{ inquadramento.localita|upper }}», "
          "{{ particelle_testo }}, estese catastalmente ha {{ sup_catastale }} di cui ha {{ sup_intervento }} costituenti la "
          "superficie ragguagliata interessata da intervento, di cui agli elaborati tecnici redatti da{{ ' ' ~ tecnico_nome ~ tecnico_iscrizione if tecnico else 'l tecnico incaricato' }}, "
          "presentati a corredo dell'istanza, compiutamente descritti nella scheda tecnica utilizzazione forestale, costituente parte "
          "integrante del presente provvedimento e riassunti nella seguente descrizione:")
    s.par(("□ {{ tipologia }} [{{ norma_titolo }}].", "b"), rientro=0.8)
    s.se("martellata")
    s.par("{{ martellata_dispositivo }}")
    s.fine_se()
    s.se("prelievo_testo")
    s.par("{{ prelievo_testo }}")
    s.fine_se()
    s.se("viabilita_testo")
    s.par("{{ viabilita_testo }}")
    s.fine_se()
    s.par(("Subordina", "b"), " la validità del presente provvedimento all'adempimento delle condizioni appresso specificate e al "
          "rispetto del {{ norma_titolo }}:", prima=6)
    s.tag("{%p for x in prescrizioni %}")
    s.par("{{ loop.index }}.\t{{ x }}", rientro=0.8, sporgente=0.6)
    s.tag("{%p endfor %}")
    s.par("{{ luogo_data }}", allinea="sinistra", prima=6)
    _firme(s, con_dirigente=True)
    return s.salva("autorizzazione.docx")


# --------------------------------------------------------- richiesta integrazioni

def modello_integrazioni() -> Path:
    s = Scrittore()
    _destinatari(s, "Al Committente")
    _oggetto(s, "Comunicazione di sospensione dei termini per concludere il procedimento e richiesta di integrazioni")
    s.par("In riferimento all'istanza segnata a margine e, tenuto conto della sostenibilità dei tempi sotto il profilo "
          "dell'organizzazione amministrativa, della complessità del procedimento e del carico di lavoro, rispetto alla data di "
          "presentazione della domanda medesima, su conforme proposta formulata alla stregua dell'istruttoria compiuta dalla "
          "struttura interessata, si rende evidente che allo stato degli atti a disposizione non sussistono i requisiti, le "
          "condizioni di ammissibilità ed i presupposti che sono rilevanti per l'adozione del provvedimento.")
    s.se("integrazioni")
    s.par("In altri termini, ai fini della prosecuzione del procedimento, è necessario perfezionare quanto già presentato con gli "
          "elementi integrativi di seguito specificati:")
    s.tag("{%p for x in integrazioni %}")
    s.par("{{ loop.index }}.\t{{ x }};", rientro=0.8, sporgente=0.6)
    s.tag("{%p endfor %}")
    s.fine_se()
    s.se("rilievi")
    s.par("Si rilevano inoltre i seguenti profili di non conformità al Reg. n. 4/2024, sui quali l'istante potrà presentare "
          "controdeduzioni ovvero rimodulare il progetto:", prima=4)
    s.tag("{%p for x in rilievi %}")
    s.par("–\t{{ x }}", rientro=0.8, sporgente=0.5)
    s.tag("{%p endfor %}")
    s.fine_se()
    s.par("Per quanto precede, si comunica la sospensione dei termini per concludere il procedimento in questione, che riprendono "
          "a decorrere dalla data di presentazione della documentazione integrativa{{ ' e/o delle controdeduzioni' if rilievi else '' }}.",
          prima=4)
    s.par("{{ luogo_data }}", allinea="sinistra", prima=6)
    _firme(s, con_dirigente=True)
    return s.salva("richiesta_integrazioni.docx")


def ha_carta_intestata() -> bool:
    return BASE.exists()


def assicura_modelli() -> None:
    """Crea i modelli mancanti o di una versione precedente (la carta intestata caricata resta)."""
    versione = CARTELLA_MODELLI / "versione.txt"
    aggiornati = versione.exists() and versione.read_text().strip() == VERSIONE_MODELLI
    if not aggiornati or not all((CARTELLA_MODELLI / n).exists() for n in NOMI_MODELLI):
        crea_tutti()


def crea_tutti(sorgente_carta_intestata: Path | None = None) -> list[Path]:
    CARTELLA_MODELLI.mkdir(parents=True, exist_ok=True)
    if sorgente_carta_intestata is not None:
        crea_base(sorgente_carta_intestata)
    creati = [modello_verbale(), modello_autorizzazione(), modello_integrazioni()]
    (CARTELLA_MODELLI / "versione.txt").write_text(VERSIONE_MODELLI)
    return creati


__all__ = ["crea_base", "crea_tutti", "assicura_modelli", "ha_carta_intestata", "CARTELLA_MODELLI"]
