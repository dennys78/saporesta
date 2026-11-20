"""Riga di comando: verifica di una pratica e generazione dei documenti.

    saporesta modelli --carta-intestata documento_ufficio.docx
    saporesta verifica casi/esempio_fustaia.yaml
    saporesta genera casi/esempio_fustaia.yaml --uscita output --tutti
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import documenti
from .models import Pratica
from .modelli_word import crea_tutti
from .verifiche import Livello, Risultato, esegui

ORDINE = [Livello.NON_CONFORME, Livello.DA_VERIFICARE, Livello.ATTENZIONE, Livello.INFO, Livello.OK]


def carica(percorso: Path) -> Pratica:
    with percorso.open(encoding="utf-8") as fh:
        return Pratica.model_validate(yaml.safe_load(fh))


def rapporto(p: Pratica, r: Risultato) -> str:
    righe = [
        f"# Istruttoria Prot. {p.protocollo} – {p.richiedente.nome_completo}",
        "",
        f"**{p.inquadramento.comune} ({p.inquadramento.provincia}), località {p.inquadramento.localita}** – "
        f"{documenti.tipologia(p)}",
        "",
        f"**Esito proposto: {r.proposta.value.upper()}**",
        "",
    ]
    for livello in ORDINE:
        esiti = r.per_livello(livello)
        if not esiti:
            continue
        righe += [f"## {livello.simbolo} {livello.value.capitalize()} ({len(esiti)})", ""]
        for e in esiti:
            art = f" _({e.articolo})_" if e.articolo else ""
            righe.append(f"- **{e.titolo}**{art}: {e.messaggio}")
        righe.append("")
    if r.integrazioni:
        righe += ["## Integrazioni da chiedere all'istante", ""] + [f"{i}. {x}" for i, x in enumerate(r.integrazioni, 1)] + [""]
    if r.da_completare:
        righe += ["## Controlli che restano all'istruttore", ""] + [f"- {e.titolo}: {e.messaggio}" for e in r.da_completare] + [""]
    if r.prescrizioni:
        righe += ["## Prescrizioni specifiche proposte", ""] + [f"- {x}" for x in r.prescrizioni] + [""]
    return "\n".join(righe)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="saporesta", description="Istruttoria istanze A02 - Reg. Calabria n. 4/2024")
    sub = ap.add_subparsers(dest="comando", required=True)

    m = sub.add_parser("modelli", help="(ri)crea i modelli Word")
    m.add_argument("--carta-intestata", type=Path, help="documento dell'ufficio da cui prendere intestazione e piè di pagina")

    v = sub.add_parser("verifica", help="esegue le verifiche e stampa il rapporto")
    v.add_argument("pratica", type=Path)

    g = sub.add_parser("genera", help="verifica e genera i documenti Word")
    g.add_argument("pratica", type=Path)
    g.add_argument("--uscita", type=Path, default=Path("output"))
    g.add_argument("--tutti", action="store_true",
                   help="genera verbale, autorizzazione e richiesta integrazioni anche se l'esito non li prevede (bozze)")

    e = sub.add_parser("estrai", help="crea una pratica dai PDF estraendo i dati con l'API di Claude")
    e.add_argument("pdf", type=Path, nargs="+")
    e.add_argument("--nome", default="", help="nome della pratica")

    w = sub.add_parser("web", help="avvia l'applicazione web locale")
    w.add_argument("--porta", type=int, default=8000)
    w.add_argument("--host", default="127.0.0.1",
                   help="indirizzo di ascolto; diverso da 127.0.0.1 solo con SAPORESTA_PASSWORD impostata")

    a = ap.parse_args(argv)

    if a.comando == "web":
        import os
        import uvicorn
        locale = a.host in ("127.0.0.1", "localhost", "::1")
        if not locale and not os.environ.get("SAPORESTA_PASSWORD"):
            print("Per rendere il portale raggiungibile da altri dispositivi impostare SAPORESTA_PASSWORD: "
                  "contiene dati personali e chiavi API.")
            return 1
        import logging
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        print(f"Portale in ascolto su {a.host}:{a.porta}  (Ctrl+C per fermare)")
        uvicorn.run("saporesta.web.app:app", host=a.host, port=a.porta, proxy_headers=False)
        return 0

    if a.comando == "estrai":
        from . import archivio, estrazione
        mancanti = [p for p in a.pdf if not p.is_file()]
        if mancanti:
            print("File non trovati: " + ", ".join(map(str, mancanti)))
            return 1
        id_ = archivio.crea(a.nome or a.pdf[0].stem, [(p.name, p.read_bytes()) for p in a.pdf])
        try:
            est = estrazione.estrai(archivio.pdf(id_))
        except estrazione.ErroreEstrazione as err:
            print(f"Estrazione non riuscita: {err}")
            print(f"Pratica creata senza dati: {archivio.radice() / id_}")
            return 1
        dubbi = estrazione.dubbi_dopo_conversione(est)
        archivio.salva_dati(id_, estrazione.in_pratica(est))
        from .impostazioni import chiave_attiva
        attiva = chiave_attiva()
        archivio.salva_estrazione(id_, est.model_dump(), dubbi, attiva.descrizione if attiva else "")
        print(f"Pratica {id_} creata in {archivio.radice() / id_}")
        print(f"{len(dubbi)} dati da controllare:")
        for d in dubbi:
            print(f"  - {d['campo']}: {d['motivo']}")
        return 0

    if a.comando == "modelli":
        for percorso in crea_tutti(a.carta_intestata):
            print(f"creato {percorso}")
        return 0

    pratica = carica(a.pratica)
    r = esegui(pratica)
    testo = rapporto(pratica, r)

    if a.comando == "verifica":
        print(testo)
        return 0

    cartella = a.uscita / a.pratica.stem
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / "rapporto_istruttoria.md").write_text(testo, encoding="utf-8")
    tipi = list(documenti.MODELLI) if a.tutti else documenti.documenti_per_proposta(r)
    print(f"Esito proposto: {r.proposta.value}")
    print(f"  {cartella / 'rapporto_istruttoria.md'}")
    for tipo in tipi:
        nome = documenti.MODELLI[tipo].replace(".docx", f"_{pratica.protocollo}.docx")
        print(f"  {documenti.genera(pratica, tipo, cartella / nome, r)}")
    if not tipi:
        print("  Nessun documento generato: completare prima i controlli indicati nel rapporto (oppure usare --tutti).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
