"""Tavole di cubatura, lettura dell'art. 38 c. 9 dell'ufficio, verbale e rapporto in Word."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from saporesta import cubatura, documenti
from saporesta.cli import carica
from saporesta.models import ClasseDiametrica, Cubatura, Dendro, SchedaA023, Specie
from saporesta.verifiche import Livello, Proposta, esegui

CASI = Path(__file__).resolve().parents[1] / "casi"

# quadro per classi di un foglio di calcolo dell'ufficio: faggio, volumi per pianta (3 classi errate)
CLASSI_FAGGIO = [(20, 20.7, 0.205), (25, 23.2, 0.565), (30, 25.2, 0.884), (35, 26.8, 1.282),
             (40, 28.3, 1.123), (45, 29.5, 2.325), (50, 30.5, 1.895)]


@pytest.fixture
def fustaia():
    return carica(CASI / "esempio_fustaia.yaml")


def esito(r, codice):
    trovati = [e for e in r.esiti if e.codice == codice]
    assert trovati, [e.codice for e in r.esiti]
    return trovati[0]


def test_valori_stampati_nelle_tavole():
    # Tabacchi faggio: v = 0,81151 + 0,038965 d²h (dm³)
    assert cubatura.volume_doppia_entrata("tabacchi_2011", "L-Fagus", 30, 25.2) == pytest.approx(0.885, abs=0.001)
    # Castellani castagno (ceduo), stessa tavola della scansione fornita dall'ufficio
    assert cubatura.volume_doppia_entrata("castellani_1984", "castagno (ceduo)", 15, 12) == pytest.approx(0.1135, abs=0.0005)
    # TaCAL pino laricio, tariffa 1, d 7 cm
    assert cubatura.tariffa_tacal("Pino laricio", 1, 7) == (10.0, 0.025)


def test_faggio_classi_sbagliate(fustaia):
    fustaia.intervento.popolamento.specie = [Specie(nome="Faggio", percentuale=100)]
    fustaia.cubatura = Cubatura(tavola="tabacchi_2011", classi=[
        ClasseDiametrica(d_cm=d, h_m=h, v_unitario_m3=v) for d, h, v in CLASSI_FAGGIO])
    r = esegui(fustaia)
    e = esito(r, "cub.volumi")
    assert e.livello is Livello.NON_CONFORME
    assert "3 classi su 7" in e.messaggio
    for d in ("d 20 cm", "d 40 cm", "d 50 cm"):
        assert d in e.messaggio
    assert "d 30 cm" not in e.messaggio
    assert "Faggio (Fagus sylvatica)" in esito(r, "cub.tavola").messaggio


def test_tacal_tariffa_dedotta_dalle_altezze(fustaia):
    fustaia.intervento.popolamento.specie = [Specie(nome="Castagno")]
    classi = [ClasseDiametrica(d_cm=d, h_m=cubatura.tariffa_tacal("Castagno", 4, d)[0],
                               v_unitario_m3=cubatura.tariffa_tacal("Castagno", 4, d)[1]) for d in (15, 20, 25, 30)]
    fustaia.cubatura = Cubatura(tavola="tacal_2016", classi=classi)
    r = esegui(fustaia)
    assert "tariffa n. 4 (dedotta" in esito(r, "cub.tavola").messaggio
    assert esito(r, "cub.volumi").livello is Livello.OK


def test_castellani_fustaia_su_ceduo_segnalata(fustaia):
    ceduo = carica(CASI / "esempio_ceduo.yaml")
    ceduo.intervento.popolamento.specie = [Specie(nome="Faggio")]
    ceduo.cubatura = Cubatura(tavola="castellani_1984", specie_tavola="Faggio",
                              classi=[ClasseDiametrica(d_cm=15, h_m=12, v_unitario_m3=0.11)])
    r = esegui(ceduo)
    assert esito(r, "cub.tavola").messaggio.count("faggio (ceduo)") == 1
    # tavola giusta (ceduo): nessuna segnalazione sul governo
    assert not [e for e in r.esiti if e.codice == "cub.governo"]
    fustaia.intervento.popolamento.specie = [Specie(nome="Castagno")]
    fustaia.cubatura = Cubatura(tavola="castellani_1984", classi=[ClasseDiametrica(d_cm=30, h_m=20, v_unitario_m3=0.7)])
    assert esito(esegui(fustaia), "cub.governo").livello is Livello.ATTENZIONE  # castagno: solo tavola del ceduo


def test_errore_di_unita(fustaia):
    v = cubatura.volume_doppia_entrata("tabacchi_2011", "C-PinusLaricio", 45, 23.9)
    fustaia.cubatura = Cubatura(tavola="tabacchi_2011", classi=[ClasseDiametrica(d_cm=45, h_m=23.9, v_unitario_m3=v * 1000)])
    assert esito(esegui(fustaia), "cub.unita").livello is Livello.NON_CONFORME


def test_tavola_di_altra_regione_e_tavola_mancante(fustaia):
    fustaia.cubatura = Cubatura(tavola="emilia_romagna_2002")
    e = esito(esegui(fustaia), "cub.manuale")
    assert e.livello is Livello.ATTENZIONE and "Emilia-Romagna" in e.messaggio
    fustaia.cubatura = Cubatura(tavola_dichiarata="tavole di cubatura")
    e = esito(esegui(fustaia), "cub.tavola")
    assert e.livello is Livello.DA_VERIFICARE and e.integrazione


# --------------------------------------------------- art. 38 c. 9 (foglio dell'ufficio)

def _fustaia_con(fustaia, prima: float, prelievo: float):
    fustaia.scheda = SchedaA023(
        ettaro_prima=Dendro(volume=prima), ettaro_taglio=Dendro(volume=prima * prelievo),
        ettaro_dopo=Dendro(volume=prima * (1 - prelievo)), alberi_invecchiamento=2)
    fustaia.martellata = None
    return esito(esegui(fustaia), "fus.prelievo")


@pytest.mark.parametrize("multiplo,prelievo,livello,testo", [
    (1.9, 0.24, Livello.OK, "entro il 25%"),
    (1.7, 0.22, Livello.NON_CONFORME, "massimo del 20%"),
    (1.5, 0.14, Livello.OK, "entro il 15%"),
    (1.3, 0.11, Livello.NON_CONFORME, "massimo del 10%"),
    (1.1, 0.05, Livello.NON_CONFORME, "non ammesso"),
    (2.2, 0.30, Livello.ATTENZIONE, "elevata provvigione"),
])
def test_soglie_prelievo(fustaia, multiplo, prelievo, livello, testo):
    e = _fustaia_con(fustaia, 250 * multiplo, prelievo)  # pino laricio: minimale 250 m³/ha
    assert e.livello is livello and testo in e.messaggio


# ------------------------------------------------------------- documenti Word

def _testo(percorso):
    d = Document(str(percorso))
    return "\n".join(p.text for p in d.paragraphs) + "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)


def test_verbale_anche_con_integrazioni(fustaia, tmp_path):
    r = esegui(fustaia)
    assert r.proposta is Proposta.INTEGRAZIONI
    assert documenti.documenti_per_proposta(r) == ["verbale", "integrazioni"]
    testo = _testo(documenti.genera(fustaia, "verbale", tmp_path / "v.docx", r))
    assert "Proposta di sospensione dei termini" in testo
    assert "richiesta dei seguenti elementi integrativi" in testo
    assert "Tavola di cubatura applicata" in testo
    assert "L'autorizzazione nei soli riguardi" not in testo


def test_rapporto_in_word(fustaia, tmp_path):
    fustaia.intervento.popolamento.specie = [Specie(nome="Faggio", percentuale=100)]
    fustaia.cubatura = Cubatura(tavola="tabacchi_2011", classi=[
        ClasseDiametrica(d_cm=d, h_m=h, v_unitario_m3=v) for d, h, v in CLASSI_FAGGIO])
    r = esegui(fustaia)
    testo = _testo(documenti.genera_rapporto(fustaia, r, tmp_path / "r.docx"))
    assert "Rapporto istruttorio" in testo and "Tavola di cubatura" in testo
    assert "v tavola (m³/pianta)" in testo and "1,765" in testo and "-36,4%" in testo


def test_estrazione_porta_tavola_e_classi():
    from saporesta import estrazione
    from saporesta.models import Pratica
    from tests.test_estrazione_web import estrazione_esempio
    e = estrazione_esempio().model_copy(update={
        "tavola_cubatura": "tacal_2016", "tavola_cubatura_testo": "Tariffe TaCAL, tariffa 5", "tariffa_tacal": 5,
        "classi_diametriche": [estrazione.EClasse(d_cm=20, h_m=14.0, n_piante=10, v_unitario_m3=0.2, v_totale_m3=None)]})
    p = Pratica.model_validate(estrazione.in_pratica(e))
    assert p.cubatura.tavola == "tacal_2016" and p.cubatura.tariffa == 5
    assert p.cubatura.classi[0].d_cm == 20 and p.cubatura.classi[0].n_piante == 10
