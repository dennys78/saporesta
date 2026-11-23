"""Archivio locale delle pratiche: una cartella per pratica.

    pratiche/<id>/pratica.yaml      dati della pratica (bozza estratta, poi corretta dall'istruttore)
    pratiche/<id>/estrazione.json   risposta grezza dell'estrazione e dubbi segnalati
    pratiche/<id>/pdf/              documenti caricati
    pratiche/<id>/documenti/        rapporto e documenti Word generati
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from .models import Pratica

RADICE_DEFAULT = Path(__file__).resolve().parents[2] / "pratiche"
ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9_-]{0,80}$")


def radice() -> Path:
    return Path(os.environ.get("SAPORESTA_DATI", RADICE_DEFAULT))


class PraticaNonTrovata(LookupError):
    pass


def _cartella(id_: str) -> Path:
    if not ID_VALIDO.match(id_):
        raise PraticaNonTrovata(id_)
    c = radice() / id_
    if not c.is_dir():
        raise PraticaNonTrovata(id_)
    return c


def nuovo_id(etichetta: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", etichetta.lower()).strip("-")[:40] or "pratica"
    base = f"{datetime.now():%Y%m%d-%H%M%S}-{base}"
    id_, n = base, 2
    while (radice() / id_).exists():
        id_, n = f"{base}-{n}", n + 1
    return id_


def crea(etichetta: str, pdf: list[tuple[str, bytes]]) -> str:
    id_ = nuovo_id(etichetta)
    c = radice() / id_
    (c / "pdf").mkdir(parents=True)
    for nome, contenuto in pdf:
        nome_sicuro = Path(nome).name or "documento.pdf"
        (c / "pdf" / nome_sicuro).write_bytes(contenuto)
    return id_


def elimina(id_: str) -> None:
    shutil.rmtree(_cartella(id_))


@dataclass
class Voce:
    id: str
    titolo: str
    modificata: datetime
    ha_dati: bool


def elenco() -> list[Voce]:
    r = radice()
    if not r.is_dir():
        return []
    voci = []
    for c in r.iterdir():
        if not c.is_dir() or not ID_VALIDO.match(c.name):
            continue
        titolo = c.name
        yaml_ = c / "pratica.yaml"
        if yaml_.exists():
            try:
                d = yaml.safe_load(yaml_.read_text(encoding="utf-8")) or {}
                rich = d.get("richiedente") or {}
                inq = d.get("inquadramento") or {}
                titolo = " – ".join(x for x in [
                    f"Prot. {d.get('protocollo')}" if d.get("protocollo") else "",
                    f"{rich.get('cognome', '')} {rich.get('nome', '')}".strip(),
                    inq.get("comune", ""), inq.get("localita", "")] if x) or c.name
            except yaml.YAMLError:
                pass
        voci.append(Voce(c.name, titolo, datetime.fromtimestamp(c.stat().st_mtime), yaml_.exists()))
    return sorted(voci, key=lambda v: v.modificata, reverse=True)


def pdf(id_: str) -> list[Path]:
    return sorted((_cartella(id_) / "pdf").glob("*.pdf"), key=lambda p: p.name.lower())


def file_pdf(id_: str, nome: str) -> Path:
    p = _cartella(id_) / "pdf" / Path(nome).name
    if not p.is_file():
        raise PraticaNonTrovata(nome)
    return p


def cartella_documenti(id_: str) -> Path:
    c = _cartella(id_) / "documenti"
    c.mkdir(exist_ok=True)
    return c


def file_documento(id_: str, nome: str) -> Path:
    p = cartella_documenti(id_) / Path(nome).name
    if not p.is_file():
        raise PraticaNonTrovata(nome)
    return p


def dati(id_: str) -> dict | None:
    p = _cartella(id_) / "pratica.yaml"
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def carica(id_: str) -> Pratica:
    d = dati(id_)
    if d is None:
        raise PraticaNonTrovata(id_)
    return Pratica.model_validate(d)


def _serializzabile(valore):
    if isinstance(valore, dict):
        return {k: _serializzabile(v) for k, v in valore.items()}
    if isinstance(valore, list):
        return [_serializzabile(v) for v in valore]
    if isinstance(valore, (date, datetime)):
        return valore.isoformat()
    if hasattr(valore, "value") and not isinstance(valore, (str, int, float, bool)):
        return valore.value
    return valore


def salva_dati(id_: str, d: dict) -> None:
    testo = yaml.safe_dump(_serializzabile(d), allow_unicode=True, sort_keys=False, width=120)
    (_cartella(id_) / "pratica.yaml").write_text(testo, encoding="utf-8")


def salva(id_: str, pratica: Pratica) -> None:
    salva_dati(id_, pratica.model_dump(mode="json", exclude_none=True))


def salva_estrazione(id_: str, grezza: dict, dubbi: list[dict], fonte: str = "") -> None:
    (_cartella(id_) / "estrazione.json").write_text(
        json.dumps({"estrazione": grezza, "dubbi": dubbi, "fonte": fonte,
                    "data": datetime.now().isoformat(timespec="seconds")},
                   ensure_ascii=False, indent=2), encoding="utf-8")


def estrazione(id_: str) -> dict | None:
    p = _cartella(id_) / "estrazione.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def aggiorna_dubbi(id_: str, dubbi: list[dict]) -> None:
    """Riscrive i dubbi dell'estrazione (con lo stato risolto/aperto) lasciando il resto invariato."""
    p = _cartella(id_) / "estrazione.json"
    if not p.exists():
        return
    contenuto = json.loads(p.read_text(encoding="utf-8"))
    contenuto["dubbi"] = dubbi
    p.write_text(json.dumps(contenuto, ensure_ascii=False, indent=2), encoding="utf-8")
