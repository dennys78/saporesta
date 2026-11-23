"""Copia leggera dei PDF scansionati da inviare all'AI.

Le istanze arrivano spesso come scansioni pesanti (es. 64 pagine, 20 MB). Per l'estrazione basta una
risoluzione da lettura: ogni pagina viene ridisegnata a RISOLUZIONE dpi e salvata in JPEG. La copia si usa
solo per la richiesta all'AI; l'originale resta intatto nella pratica e nel visore.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("saporesta")

SOGLIA_BYTES = 3 * 1024 * 1024  # sotto questa dimensione il PDF si invia così com'è
RISOLUZIONE = 150  # dpi: le scritte a mano e le caselle barrate restano leggibili
QUALITA_JPEG = 60
LATO_MASSIMO = 2000  # pixel: limita le tavole in formato grande
GUADAGNO_MINIMO = 0.7  # la copia si usa solo se pesa meno del 70% dell'originale


def riduci(origine: Path, cartella: Path) -> Path:
    """Restituisce il PDF da inviare: la copia ridotta in `cartella` se conviene, altrimenti l'originale."""
    if origine.stat().st_size <= SOGLIA_BYTES:
        return origine
    try:
        import io

        import pypdfium2 as pdfium

        cartella.mkdir(parents=True, exist_ok=True)
        destinazione = cartella / origine.name
        documento = pdfium.PdfDocument(str(origine))
        nuovo = pdfium.PdfDocument.new()
        pagine = 0
        try:
            # una pagina alla volta: anche 100 pagine scansionate restano leggere in memoria
            for pagina in documento:
                larghezza, altezza = pagina.get_size()  # punti (1/72 di pollice)
                scala = min(RISOLUZIONE / 72, LATO_MASSIMO / max(larghezza, altezza))
                buffer = io.BytesIO()
                pagina.render(scale=scala).to_pil().convert("RGB").save(buffer, "JPEG", quality=QUALITA_JPEG,
                                                                        optimize=True)
                pagina.close()
                buffer.seek(0)
                immagine = pdfium.PdfImage.new(nuovo)
                immagine.load_jpeg(buffer, inline=True)
                immagine.set_matrix(pdfium.PdfMatrix().scale(larghezza, altezza))
                foglio = nuovo.new_page(larghezza, altezza)
                foglio.insert_obj(immagine)
                foglio.gen_content()
                foglio.close()
                pagine += 1
            if not pagine:
                return origine
            nuovo.save(str(destinazione))
        finally:
            nuovo.close()
            documento.close()
    except Exception as e:  # PDF protetto o danneggiato: si invia l'originale
        log.warning("Riduzione di %s non riuscita (%s): si invia l'originale.", origine.name, e)
        return origine
    prima, dopo = origine.stat().st_size, destinazione.stat().st_size
    if dopo > prima * GUADAGNO_MINIMO:
        return origine
    log.info("PDF ridotto per l'AI: %s %.1f MB -> %.1f MB (%d pagine)", origine.name, prima / 1e6, dopo / 1e6,
             pagine)
    return destinazione


def riduci_tutti(percorsi: list[Path], cartella: Path) -> list[Path]:
    return [riduci(p, cartella) for p in percorsi]
