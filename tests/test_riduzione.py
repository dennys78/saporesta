"""Copia leggera dei PDF scansionati inviata all'AI."""

from __future__ import annotations

from PIL import Image
import pypdfium2 as pdfium

from saporesta import estrazione, riduzione
from tests.test_estrazione_web import PDF_PROVA, estrazione_esempio


def _scansione(percorso, pagine=3):
    fogli = [Image.effect_noise((2480, 3508), 40).convert("RGB") for _ in range(pagine)]
    fogli[0].save(percorso, "PDF", save_all=True, append_images=fogli[1:], quality=95, resolution=300)
    return percorso


def test_scansione_pesante_ridotta(tmp_path, monkeypatch):
    monkeypatch.setattr(riduzione, "SOGLIA_BYTES", 1000)
    originale = _scansione(tmp_path / "scansione.pdf")
    prima = originale.read_bytes()
    copia = riduzione.riduci(originale, tmp_path / "ridotti")
    assert copia != originale and copia.stat().st_size < len(prima) * 0.3
    assert originale.read_bytes() == prima  # l'originale non si tocca
    d = pdfium.PdfDocument(str(copia))
    assert len(d) == 3 and abs(d[0].get_size()[0] - 595) < 2  # stesse pagine, stesso formato A4
    d.close()


def test_pdf_piccolo_o_non_comprimibile_resta_originale(tmp_path, monkeypatch):
    piccolo = tmp_path / "piccolo.pdf"
    piccolo.write_bytes(PDF_PROVA.read_bytes())
    assert riduzione.riduci(piccolo, tmp_path / "r") == piccolo
    monkeypatch.setattr(riduzione, "SOGLIA_BYTES", 10)
    rotto = tmp_path / "rotto.pdf"
    rotto.write_bytes(b"%PDF-1.4 non valido" * 100)
    assert riduzione.riduci(rotto, tmp_path / "r") == rotto


def test_estrazione_invia_la_copia_ridotta(tmp_path, monkeypatch):
    monkeypatch.setattr(riduzione, "SOGLIA_BYTES", 1000)
    originale = _scansione(tmp_path / "istanza.pdf", pagine=2)
    inviati = []

    def finto_claude(percorsi, chiave=None, client=None):
        inviati.extend((p.name, p.stat().st_size, p.parent == originale.parent) for p in percorsi)
        return estrazione_esempio()
    monkeypatch.setattr(estrazione, "estrai_claude", finto_claude)
    estrazione.estrai([originale], client=object())
    nome, dimensione, stessa_cartella = inviati[0]
    assert nome == "istanza.pdf" and not stessa_cartella and dimensione < originale.stat().st_size
