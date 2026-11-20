# Saporesta – istruttoria istanze A02

Strumento per l'istruttoria delle istanze di autorizzazione al taglio boschivo (modulo A02,
Regione Calabria) secondo il **Regolamento n. 4/2024** di attuazione della L.R. 45/2012.

Dalla pratica (dati dell'istanza, scheda A02.3, checklist, verifiche d'ufficio) il programma:

1. esegue i controlli: checklist documentale, quadratura della scheda A02.3, regole del
   regolamento per tipo di intervento (ceduo, fustaia, transitori, neoformazione, incendi,
   avversità, art. 22), coerenza dello stesso dato tra documenti diversi;
2. propone l'esito: **autorizzabile**, **richiesta integrazioni** o **istruttoria da completare**;
3. genera in Word il **verbale istruttorio**, l'**autorizzazione** e la **richiesta di integrazioni**.

Fase 1: verifiche e documenti. Fase 2: estrazione dei dati dai PDF con l'API di Claude e pagina web
locale di revisione. Fase 3 (portale online con login) è ancora da fare.

## Pagina di revisione (fase 2)

```bash
uv run saporesta web                # poi aprire http://127.0.0.1:8000
```

Le chiavi API si impostano nella pagina **Impostazioni** del portale: si possono salvare più chiavi Google Gemini
e Anthropic Claude e scegliere quella attiva. Ogni chiave viene verificata prima del salvataggio; per Gemini si sceglie
il modello dall'elenco di quelli disponibili per la chiave. Le chiavi sono salvate in `~/.config/saporesta/impostazioni.json`
(permessi 600, fuori dal progetto) e la pagina ne mostra solo le ultime 4 cifre. In alternativa valgono le variabili
`ANTHROPIC_API_KEY` o `GEMINI_API_KEY`.

Si caricano i PDF della pratica (istanza, A02.3, A02.4, relazione…): il modello della chiave attiva legge testo e
caselle barrate, compila i campi, confronta lo stesso dato tra documenti diversi e segnala i dubbi, che la pagina
evidenzia in giallo accanto al PDF. L'istruttore corregge, salva (le verifiche si rieseguono a ogni salvataggio) e
genera i documenti Word. Senza chiave API si può caricare la pratica togliendo la spunta "Estrai i dati" e compilare a mano.

Le pratiche sono salvate in `pratiche/` (esclusa da git: contiene dati personali). **I PDF caricati con l'estrazione
attiva vengono inviati al fornitore della chiave attiva** (con una chiave Gemini gratuita Google può usarli per
migliorare i propri prodotti: per dati reali usare un account a pagamento): verificare con l'ente che sia ammesso per i dati delle istanze.

Da riga di comando: `uv run saporesta estrai istanza.pdf a023.pdf --nome "Rossi Crotone"`.

## Uso da riga di comando

```bash
uv run saporesta verifica casi/esempio_fustaia.yaml
uv run saporesta genera casi/esempio_fustaia.yaml          # solo i documenti previsti dall'esito
uv run saporesta genera casi/esempio_fustaia.yaml --tutti  # tutte e tre le bozze
uv run pytest
```

I file vengono scritti in `output/<nome pratica>/`, insieme a `rapporto_istruttoria.md`.

## Dove intervenire

| Cosa | File |
|---|---|
| Parametri del regolamento (turni, matricine, provvigioni, tagliate…) e tabella delle specie | `src/saporesta/regole.yaml` |
| Voci della checklist e quando sono richieste | `src/saporesta/checklist.py` |
| Controlli | `src/saporesta/verifiche/` |
| Testi standard (visti, prescrizioni, dichiarazioni) | `src/saporesta/documenti.py` |
| Impaginazione dei documenti | `modelli/*.docx` (rigenerabili con `uv run saporesta modelli`) |

I modelli Word partono dalla carta intestata dell'ufficio, che **non è nel repository**: si carica
dalla pagina Impostazioni (un qualunque documento Word dell'ufficio: se ne tengono intestazione, logo e
piè di pagina) oppure con `uv run saporesta modelli --carta-intestata <documento.docx>`. Senza carta
intestata i documenti escono su foglio bianco. I modelli si possono ritoccare in Word senza spezzare i
segnaposto `{{ ... }}` e `{%p ... %}`.

## Dati di esempio

`casi/esempio_ceduo.yaml` e `casi/esempio_fustaia.yaml` sono pratiche **fittizie** ricalcate su due
istanze reali (dati tecnici e incongruenze originali, nomi, codici, località e particelle inventati).
Le pratiche reali non vanno mai nel repository: `pratiche/`, `casi_reali/`, `dati/` e `modelli/` sono
esclusi da git.

## Installazione con Docker (es. Mac mini)

```bash
git clone https://github.com/dennys78/saporesta.git
cd saporesta
cp .env.example .env        # e scrivere una password lunga in SAPORESTA_PASSWORD
docker compose up -d --build
```

Il portale è poi su `http://<indirizzo-del-mac-mini>:8765` e chiede la password. Pratiche, PDF, chiavi
API e carta intestata restano sul Mac mini nella cartella `dati/` accanto al file `docker-compose.yml`
(da includere nei backup). Per aggiornare: `git pull && docker compose up -d --build`.

Il portale usa HTTP semplice: va bene sulla rete di casa o d'ufficio, non va esposto su Internet
senza un proxy HTTPS davanti (in quel caso impostare anche `SAPORESTA_HTTPS=1`).
