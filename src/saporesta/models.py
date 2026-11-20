"""Modello dati di una pratica A02 (istanza di autorizzazione al taglio boschivo).

I campi seguono il modulo regionale A02, la scheda tecnica A02.3 e la checklist
di controllo dell'ufficio. Tutti i campi non obbligatori possono restare vuoti:
le verifiche segnalano come "da verificare" ciò che manca.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class TipoIntervento(str, Enum):
    CEDUO = "ceduo"  # Taglio bosco governato a ceduo >= 2 ha
    NEOFORMAZIONE = "neoformazione"  # Soprassuoli di neoformazione (art. 4)
    FUSTAIA = "fustaia"  # Bosco governato a fustaia (artt. 38-40)
    TRANSITORIO = "transitorio"  # Soprassuoli transitori (art. 41)
    INCENDIO = "incendio"  # Boschi danneggiati dal fuoco (art. 49)
    AVVERSITA = "avversita"  # Aree danneggiate da avversità meteoriche (art. 50)
    ART22 = "art22"  # Tagli per pubblica incolumità / infrastrutture


class Sottotipo(str, Enum):
    # ceduo
    SENZA_MATRICINE = "senza_matricine"
    MATRICINATO = "matricinato"
    STERZO = "sterzo"
    COMPOSTO = "composto"
    SFOLLI = "sfolli"
    DIRADAMENTI = "diradamenti"
    # fustaia
    SFOLLAMENTI = "sfollamenti"
    RINNOVAZIONE = "rinnovazione"  # tagli colturali di rinnovazione
    # transitori
    PRIMO_AVVIAMENTO = "primo_avviamento"
    SUCCESSIVI_AVVIAMENTO = "successivi_avviamento"
    CONVERSIONE = "conversione"
    # art. 22
    INFRASTRUTTURE = "infrastrutture"
    MANUFATTI = "manufatti"
    ELETTRODOTTI = "elettrodotti"
    VIABILITA = "viabilita"
    IDRAULICA = "idraulica"


class TitoloRichiedente(str, Enum):
    PROPRIETARIO = "proprietario"
    USUFRUTTUARIO = "usufruttuario"
    AFFITTUARIO = "affittuario"
    DELEGATO = "soggetto delegato"
    RAPPRESENTANTE = "rappresentante di ente o società"
    ALTRO = "altro"


class Persona(BaseModel):
    cognome: str
    nome: str
    sesso: str | None = Field(None, description="'M' o 'F', per 'nato/nata'")
    data_nascita: date | None = None
    luogo_nascita: str | None = None
    comune_residenza: str | None = None
    cap: str | None = None
    provincia: str | None = None
    indirizzo: str | None = None
    civico: str | None = None
    codice_fiscale: str | None = None
    pec: str | None = None
    email: str | None = None

    @property
    def nome_completo(self) -> str:
        return f"{self.cognome.upper()} {self.nome.upper()}"

    @property
    def nato(self) -> str:
        return "nata" if (self.sesso or "").upper() == "F" else "nato"

    @property
    def residenza(self) -> str:
        parti = [p for p in [self.indirizzo, self.civico] if p]
        via = " ".join(parti)
        luogo = " ".join(p for p in [self.cap, self.comune_residenza] if p)
        prov = f" ({self.provincia})" if self.provincia else ""
        return ", ".join(p for p in [via, luogo + prov] if p.strip())


class Tecnico(Persona):
    titolo: str = "Dott. For."
    ordine_provincia: str | None = None
    numero_iscrizione: str | None = None
    sezione: str | None = None
    sigla_martello: str | None = None


class Firmatari(BaseModel):
    istruttore: str = ""
    responsabile_procedimento: str = ""
    dirigente: str = ""
    qualifica_dirigente: str = "Il Dirigente"


class GruppoParticelle(BaseModel):
    foglio: str
    particelle: list[str]


class Inquadramento(BaseModel):
    comune: str
    provincia: str
    localita: str
    particelle: list[GruppoParticelle]
    superficie_catastale_ha: float | None = None
    superficie_intervento_ha: float
    destinazione_urbanistica: str | None = None


class Vincoli(BaseModel):
    """Quanto dichiarato nell'istanza (sezione 'ricadente nei limiti...')."""

    aree_protette: list[str] = Field(default_factory=list)
    natura2000: bool = False
    sito_natura2000: str | None = None
    pai_geomorfologico: list[str] = Field(
        default_factory=list, description="es. ['R4'], vuoto = non ricade"
    )
    pai_idraulico: list[str] = Field(default_factory=list)
    percorsa_incendio: bool = False
    vincolo_art54: bool = False
    vincolo_paesaggistico: bool = True  # i boschi sono tutelati ex art. 142 c.1 lett. g
    sorgenti_50m: bool = False
    versante_massi: bool = False
    pendenza_media_pct: float | None = None


class Specie(BaseModel):
    nome: str
    percentuale: float | None = None


class Popolamento(BaseModel):
    specie: list[Specie] = Field(default_factory=list)
    eta_min: int | None = None
    eta_max: int | None = None
    anno_ultimo_taglio: int | None = None
    fine_lavori_ultimo_intervento: date | None = None
    origine_artificiale: bool = False

    @property
    def specie_prevalente(self) -> str | None:
        if not self.specie:
            return None
        return max(self.specie, key=lambda s: s.percentuale or 0).nome

    @property
    def descrizione_eta(self) -> str:
        if self.eta_min is None and self.eta_max is None:
            return "non dichiarata"
        if self.eta_max is None or self.eta_min == self.eta_max:
            return f"{self.eta_min} anni"
        if self.eta_min is None:
            return f"{self.eta_max} anni"
        return f"{self.eta_min}-{self.eta_max} anni"


class Intervento(BaseModel):
    tipo: TipoIntervento
    sottotipi: list[Sottotipo] = Field(default_factory=list)
    straordinario: bool = False
    previsto_da: str | None = Field(
        None, description="Piano di gestione, piano poliennale, art. 54 R.D. 3267/23..."
    )
    titolo_progetto: str | None = None
    popolamento: Popolamento = Field(default_factory=Popolamento)
    manutenzione_viabilita: str | None = Field(
        None, description="es. 'ordinaria (art. 53)'; vuoto = nessuna"
    )
    nuove_piste: bool = False


class Dendro(BaseModel):
    """Numero piante, area basimetrica (m²) e volume (m³)."""

    n_piante: float | None = None
    area_basimetrica: float | None = None
    volume: float | None = None


class AreaSaggio(BaseModel):
    nome: str
    superficie_m2: float
    utm_e: float | None = None
    utm_n: float | None = None
    n_piante: int | None = None
    area_basimetrica_m2: float | None = None


class Assortimento(BaseModel):
    descrizione: str  # es. "tronco o tondo da sega", "uso energetico"
    volume_m3: float


class Tagliata(BaseModel):
    nome: str
    superficie_ha: float
    stagione_silvana: str | None = None  # es. "2026/2027"
    contigua_a: list[str] = Field(default_factory=list)


class SchedaA023(BaseModel):
    """Scheda tecnica utilizzazione forestale (allegato A02.3)."""

    ettaro_prima: Dendro = Field(default_factory=Dendro)
    ettaro_taglio: Dendro = Field(default_factory=Dendro)
    ettaro_dopo: Dendro = Field(default_factory=Dendro)
    totale_prima: Dendro = Field(default_factory=Dendro)
    totale_taglio: Dendro = Field(default_factory=Dendro)
    totale_dopo: Dendro = Field(default_factory=Dendro)
    peso_specifico_q_m3: float | None = None
    massa_taglio_ettaro_q: float | None = None
    massa_taglio_totale_q: float | None = None
    percentuale_dichiarata_piante: float | None = None
    percentuale_dichiarata_g: float | None = None
    percentuale_dichiarata_volume: float | None = None
    diametro_medio_cm: float | None = None
    altezza_media_m: float | None = None
    aree_saggio: list[AreaSaggio] = Field(default_factory=list)
    assortimenti: list[Assortimento] = Field(default_factory=list)
    matricine_ha: float | None = None
    matricine_doppio_turno_pct: float | None = None
    polloni_rilasciati_ha: float | None = None
    alberi_invecchiamento: int | None = None
    piante_morte_rilasciate_ha: float | None = None


class Martellata(BaseModel):
    n_piante: int
    numero_da: int = 1
    numero_a: int | None = None
    specie: str | None = None
    sigla_martello: str | None = None
    colore_vernice: str | None = None
    sezione: str | None = None


class Riscontro(BaseModel):
    """Lo stesso dato riportato in più documenti dell'istanza.

    Serve a segnalare le discordanze (es. volume nel piedilista diverso da
    quello della statistica forestale).
    """

    campo: str
    documento: str
    valore: str  # come scritto nel documento; i numeri sono confrontati come numeri


class StatoVoce(str, Enum):
    SI = "si"
    NO = "no"
    NP = "np"  # non prevista / non pertinente
    DIFFORME = "difforme"


class VoceChecklist(BaseModel):
    stato: StatoVoce
    nota: str | None = None


class VerificaUfficio(BaseModel):
    sistema: str  # SIM, SIAN, PAI, catasto incendi, ...
    esito: str  # testo che va nel verbale
    data: date | None = None
    criticita: bool = False


class Versamento(BaseModel):
    importo_totale: float | None = None
    segreteria: float | None = None
    istruttoria: float | None = None
    modalita: str | None = None  # "c/c postale", "bonifico"


class Istruttoria(BaseModel):
    """Scelte e annotazioni dell'istruttore."""

    checklist: dict[str, VoceChecklist] = Field(default_factory=dict)
    verifiche_ufficio: list[VerificaUfficio] = Field(default_factory=list)
    integrazioni_aggiuntive: list[str] = Field(default_factory=list)
    prescrizioni_aggiuntive: list[str] = Field(default_factory=list)
    riferimento_vinca: str | None = None
    note_verbale: list[str] = Field(default_factory=list)
    validita_mesi: int = 24
    destinatari_conoscenza: list[str] = Field(
        default_factory=list,
        description="Blocchi indirizzo (righe separate da \\n) per e.p.c.: Carabinieri Forestali competenti, ecc.",
    )
    firmatari: Firmatari = Field(default_factory=Firmatari)
    data_documento: date | None = None


class Pratica(BaseModel):
    protocollo: str
    data_protocollo: date
    protocolli_integrazione: list[str] = Field(default_factory=list)
    data_istanza: date | None = None
    richiedente: Persona
    titolo_richiedente: TitoloRichiedente = TitoloRichiedente.PROPRIETARIO
    ente_pubblico: bool = Field(False, description="Bosco di proprietà di Comune o ente pubblico")
    classe_eutr: str | None = None
    tecnico: Tecnico | None = None
    intervento: Intervento
    inquadramento: Inquadramento
    vincoli: Vincoli = Field(default_factory=Vincoli)
    scheda: SchedaA023 | None = None
    tagliate: list[Tagliata] = Field(default_factory=list)
    martellata: Martellata | None = None
    versamento: Versamento = Field(default_factory=Versamento)
    riscontri: list[Riscontro] = Field(default_factory=list)
    istruttoria: Istruttoria = Field(default_factory=Istruttoria)
    riferimento_normativo_modulo: str | None = Field(
        None, description="Norma citata nel modulo, es. 'PMPF D.G.R. 218/2011'"
    )
