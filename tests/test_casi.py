"""Test sulle due pratiche di esempio (ceduo e fustaia, dati fittizi ricalcati su pratiche reali) e su loro varianti."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from saporesta import documenti
from saporesta.cli import carica
from saporesta.formato import ha_catastale, num
from saporesta.models import AreaSaggio, Dendro, SchedaA023, Specie, StatoVoce, Tagliata, VoceChecklist
from saporesta.verifiche import Livello, Proposta, esegui

CASI = Path(__file__).resolve().parents[1] / "casi"


@pytest.fixture
def ceduo():
    return carica(CASI / "esempio_ceduo.yaml")


@pytest.fixture
def fustaia():
    return carica(CASI / "esempio_fustaia.yaml")


def esito(r, codice):
    trovati = [e for e in r.esiti if e.codice == codice]
    assert trovati, f"nessun esito {codice}: {[e.codice for e in r.esiti]}"
    return trovati[0]


def tutta_checklist_si(p):
    from saporesta.checklist import voci_richieste
    for v in voci_richieste(p):
        p.istruttoria.checklist[v.id] = VoceChecklist(stato=StatoVoce.SI)


# ---------------------------------------------------------------- formattazione

def test_formati():
    assert ha_catastale(0.999) == "00.99.90"
    assert ha_catastale(26.1481) == "26.14.81"
    assert num(1234.5) == "1.234,50"


# ---------------------------------------------------------------------- ceduo

def test_ceduo_tagliate_oltre_10_ha(ceduo):
    r = esegui(ceduo)
    e = esito(r, "ced.tagliate")
    assert e.livello is Livello.NON_CONFORME
    assert "almeno 3 tagliate" in e.messaggio
    assert r.proposta is Proposta.INTEGRAZIONI


def test_ceduo_specie_mancante_e_modulo_pmpf(ceduo):
    r = esegui(ceduo)
    assert esito(r, "ced.specie").livello is Livello.DA_VERIFICARE
    assert esito(r, "ced.senza_matricine").livello is Livello.DA_VERIFICARE
    assert esito(r, "gen.modulo").livello is Livello.ATTENZIONE
    assert any("composizione specifica" in i for i in r.integrazioni)


def test_ceduo_art54_richiede_verbale_riconsegna(ceduo):
    from saporesta.checklist import voci_richieste
    assert "verbale_riconsegna" in {v.id for v in voci_richieste(ceduo)}


def test_ceduo_eucalipto_sotto_turno(ceduo):
    ceduo.intervento.popolamento.specie = [Specie(nome="Eucalipto", percentuale=100)]
    ceduo.intervento.popolamento.eta_min = 8
    ceduo.intervento.popolamento.eta_max = 8
    r = esegui(ceduo)
    assert esito(r, "ced.turno").livello is Livello.NON_CONFORME  # turno 10 anni
    assert esito(r, "ced.senza_matricine").livello is Livello.OK  # art. 36: ammesso per l'eucalipto


def test_ceduo_eta_a_cavallo_del_turno(ceduo):
    ceduo.intervento.popolamento.specie = [Specie(nome="Eucalipto")]
    r = esegui(ceduo)  # età 8-15, turno 10
    e = esito(r, "ced.turno")
    assert e.livello is Livello.ATTENZIONE and e.integrazione


def test_ceduo_quercia_senza_matricine_non_ammesso(ceduo):
    ceduo.intervento.popolamento.specie = [Specie(nome="Roverella")]
    ceduo.intervento.popolamento.eta_min = ceduo.intervento.popolamento.eta_max = 20
    ceduo.intervento.popolamento.anno_ultimo_taglio = 2006
    r = esegui(ceduo)
    assert esito(r, "ced.senza_matricine").livello is Livello.NON_CONFORME
    assert esito(r, "ced.turno").livello is Livello.OK


def test_tagliate_corrette_e_contigue(ceduo):
    ceduo.vincoli.pendenza_media_pct = 30
    ceduo.tagliate = [
        Tagliata(nome="A", superficie_ha=8, stagione_silvana="2026/27"),
        Tagliata(nome="B", superficie_ha=7.5, stagione_silvana="2026/27"),
        Tagliata(nome="C", superficie_ha=6, stagione_silvana="2027/28"),
    ]
    assert esito(esegui(ceduo), "ced.tagliate").livello is Livello.OK
    ceduo.tagliate[1].contigua_a = ["A"]
    assert esito(esegui(ceduo), "ced.contiguita").livello is Livello.NON_CONFORME


def test_tagliata_ridotta_con_pendenza_oltre_40(ceduo):
    ceduo.vincoli.pendenza_media_pct = 45
    ceduo.tagliate = [Tagliata(nome="A", superficie_ha=8, stagione_silvana="2026/27")]
    assert esito(esegui(ceduo), "ced.tagliate").livello is Livello.NON_CONFORME


def test_matricine_castagno_in_forte_pendenza(ceduo):
    ceduo.intervento.sottotipi = []  # ceduo matricinato
    ceduo.intervento.popolamento.specie = [Specie(nome="Castagno")]
    ceduo.vincoli.pendenza_media_pct = 65
    ceduo.scheda = SchedaA023(matricine_ha=40)
    e = esito(esegui(ceduo), "ced.matricine")
    assert e.livello is Livello.NON_CONFORME and "minimo 60" in e.messaggio


# -------------------------------------------------------------------- fustaia

def test_fustaia_provvigione_e_prelievo(fustaia):
    r = esegui(fustaia)
    assert esito(r, "fus.provvigione").livello is Livello.OK
    prel = esito(r, "fus.prelievo")
    assert prel.livello is Livello.OK and "17,8%" in prel.messaggio
    assert esito(r, "fus.invecchiamento").livello is Livello.OK


def test_fustaia_discordanze_volumi(fustaia):
    r = esegui(fustaia)
    assert esito(r, "a023.assortimenti").livello is Livello.NON_CONFORME  # 31,5 + 19,5 = 51 ≠ 51,97
    assert esito(r, "ris.volume prelevato (m³)").livello is Livello.NON_CONFORME  # 51,97 vs 51,5


def test_fustaia_sim_incendio_in_contrasto(fustaia):
    r = esegui(fustaia)
    assert esito(r, "uff.0").livello is Livello.NON_CONFORME
    assert r.proposta is Proposta.INTEGRAZIONI


def test_fustaia_sistemato_diventa_autorizzabile(fustaia):
    tutta_checklist_si(fustaia)
    fustaia.istruttoria.verifiche_ufficio[0].criticita = False
    fustaia.istruttoria.verifiche_ufficio[0].esito = "dalla consultazione del SIM le particelle non risultano percorse dal fuoco"
    fustaia.riscontri = []
    fustaia.scheda.assortimenti[1].volume_m3 = 20.47
    r = esegui(fustaia)
    assert r.proposta is Proposta.AUTORIZZABILE, [(e.codice, e.messaggio) for e in r.esiti if e.bloccante or e in r.da_completare]
    assert documenti.documenti_per_proposta(r) == ["verbale", "autorizzazione"]


def test_fustaia_prelievo_eccessivo(fustaia):
    fustaia.scheda = SchedaA023(
        ettaro_prima=Dendro(n_piante=500, area_basimetrica=40, volume=400),
        ettaro_taglio=Dendro(n_piante=150, area_basimetrica=13, volume=130),
        ettaro_dopo=Dendro(n_piante=350, area_basimetrica=27, volume=270),
        alberi_invecchiamento=2,
    )
    r = esegui(fustaia)
    assert esito(r, "fus.prelievo").livello is Livello.NON_CONFORME  # 32,5% > 25%


def test_scheda_a023_quadratura(fustaia):
    # dati dell'esempio nel foglio "Verifica_Taglio_Boschivo_AO2_3_con_Formule.xlsx"
    fustaia.inquadramento.superficie_intervento_ha = 1.6
    fustaia.martellata.n_piante = 360
    fustaia.scheda = SchedaA023(
        ettaro_prima=Dendro(n_piante=1225, area_basimetrica=86.49, volume=1077.3),
        ettaro_taglio=Dendro(n_piante=225, area_basimetrica=18.02, volume=221.86),
        ettaro_dopo=Dendro(n_piante=1000, area_basimetrica=68.47, volume=855.44),
        totale_prima=Dendro(n_piante=1960, area_basimetrica=138.38, volume=1723.68),
        totale_taglio=Dendro(n_piante=360, area_basimetrica=28.83, volume=354.98),
        totale_dopo=Dendro(n_piante=1600, area_basimetrica=109.55, volume=1368.7),
        peso_specifico_q_m3=8.5, massa_taglio_ettaro_q=1885.8, percentuale_dichiarata_volume=20.6,
        diametro_medio_cm=30, altezza_media_m=23.3,
        aree_saggio=[AreaSaggio(nome="AdS 1", superficie_m2=400, utm_e=620156, utm_n=4259038),
                     AreaSaggio(nome="AdS 2", superficie_m2=400, utm_e=620055, utm_n=4259127)],
        alberi_invecchiamento=4,
    )
    r = esegui(fustaia)
    assert not [e for e in r.esiti if e.codice.startswith("a023") and e.livello is Livello.NON_CONFORME]
    fustaia.scheda.totale_dopo.n_piante = 1650
    assert esito(esegui(fustaia), "a023.intera superficie.n_piante").livello is Livello.NON_CONFORME


# ------------------------------------------------------------------- documenti

@pytest.mark.parametrize("tipo", ["verbale", "autorizzazione", "integrazioni"])
@pytest.mark.parametrize("caso", ["ceduo", "fustaia"])
def test_documenti_senza_segnaposto(tipo, caso, request, tmp_path):
    p = request.getfixturevalue(caso)
    out = documenti.genera(p, tipo, tmp_path / f"{tipo}.docx")
    d = Document(str(out))
    testo = "\n".join(par.text for par in d.paragraphs)
    testo += "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)
    assert "{{" not in testo and "{%" not in testo
    assert p.protocollo in testo


def test_autorizzazione_fustaia_contenuti(fustaia, tmp_path):
    out = documenti.genera(fustaia, "autorizzazione", tmp_path / "a.docx")
    testo = "\n".join(par.text for par in Document(str(out)).paragraphs)
    assert "FG 5 part. 7, 8" in testo
    assert "Le piante martellate sono in numero di 27 di pino laricio" in testo
    assert "comma 14 dell'art. 40" in testo  # certificato di regolare esecuzione per le fustaie
    assert "Decreto di valutazione d'incidenza" in testo


def test_richiesta_integrazioni_ceduo(ceduo, tmp_path):
    out = documenti.genera(ceduo, "integrazioni", tmp_path / "i.docx")
    testo = "\n".join(par.text for par in Document(str(out)).paragraphs)
    assert "tagliate di superficie non superiore a 10 ha" in testo
    assert "ROSSI MARIO" in testo
