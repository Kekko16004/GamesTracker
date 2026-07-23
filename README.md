# GamesTracker

Tool desktop (Python + PyQt6) per game dev indie. Raccoglie in modo continuo le ultime
uscite da **Steam** e **itch.io**, ne salva tutti i dati e ne **traccia la crescita** nel
tempo (+24h / +48h / +1 settimana / +1 mese). Cerca come i giochi validi diventano virali
sui social (YouTube, Reddit, TikTok, Instagram), scarta il trash con un **quality score
0-100** e produce **grafici + report bilingue (IT/EN)** che ricostruiscono le strategie di
marketing (date demo, date release, canali/date dei post e la loro co-occorrenza con la
crescita). Obiettivo: dati veri su quali generi tirano ora e su come farsi pubblicità.

## Architettura

Due processi separati che comunicano solo attraverso il database.

- **Collector** (`run_collector.py`): servizio in background (APScheduler) che scopre i
  giochi nuovi e scrive snapshot append-only sul DB, anche a GUI chiusa.
- **GUI** (`run_gui.py`): app PyQt6 che legge **solo** dal DB, non fa mai chiamate di rete.
- **DB** (SQLite via SQLAlchemy 2.x): serie storiche in tabelle `*_snapshots`, mai
  sovrascritte. Schema portabile a Postgres.
- **Analisi** (`analysis/`): quality score, metriche di crescita, trend per genere e
  generazione report, letti dalla GUI.

```
Steam / itch / YouTube / Reddit ──> Collector ──> DB (SQLite) <── GUI (PyQt6)
        (client sorgenti)         (scheduler,        │            (sola lettura)
                                   append-only)      └──> Analisi (score, trend, report)
```

## Requisiti

- **Python 3.10.x** (sviluppato e testato su 3.10.11).
- Le API key sono opzionali per avviare l'app, ma servono per la raccolta reale (vedi sotto).

## Setup

```bash
# 1. Crea e attiva il virtualenv
python -m venv venv
venv\Scripts\activate           # Windows (PowerShell: venv\Scripts\Activate.ps1)
# source venv/bin/activate      # Linux / macOS

# 2. Installa le dipendenze
pip install -r requirements.txt

# 3. Configura le variabili d'ambiente
copy config\.env.example config\.env    # Windows
# cp config/.env.example config/.env     # Linux / macOS
```

Poi apri `config/.env` e inserisci le tue chiavi. `config/.env` non va mai committato.

### API key

| Variabile | Serve per | Come ottenerla | Obbligatoria |
|---|---|---|---|
| `STEAM_WEB_API_KEY` | Player count Steam (`GetNumberOfCurrentPlayers`) | https://steamcommunity.com/dev/apikey (gratuita) | Opzionale — senza chiave il collector degrada e continua |
| `YOUTUBE_API_KEY` | Ricerca video/canali (YouTube Data API v3, quota 10k/giorno) | Google Cloud Console → abilita "YouTube Data API v3" | Necessaria per la sorgente YouTube |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` | Ricerca post su Reddit (PRAW) | https://www.reddit.com/prefs/apps (app tipo "script") | Necessarie per la sorgente Reddit |

Senza una chiave la relativa sorgente resta disabilitata ma non fa crashare il collector.
Altre variabili utili in `config/.env`: `DB_URL` (default SQLite locale), `APP_LANG`
(`it`/`en`), `QUALITY_SCORE_THRESHOLD` (default 40), `DISCOVERY_INTERVAL_HOURS` (default 6),
`HTTP_USER_AGENT`.

## Come si avvia

```bash
python run_collector.py   # servizio di raccolta in background
python run_gui.py         # interfaccia desktop
```

Il collector va **lasciato girare** nel tempo: è il passaggio ripetuto degli snapshot
(+24h / +48h / +1w / +1mo) a produrre le serie storiche su cui si basa tutto il valore del
tool. La GUI può essere aperta e chiusa liberamente, legge quello che il collector ha già
salvato.

## Come si usa la GUI

- **Dashboard**: panoramica dei giochi tracciati, con filtro per piattaforma e uno **slider
  della soglia quality score** per nascondere il trash sotto la soglia scelta.
- **Dettaglio gioco**: dati anagrafici, quality score con breakdown, **timeline marketing**
  (demo, release, post social, punti di svolta della crescita) e i grafici di recensioni /
  player nel tempo. Da qui si fa anche l'**import manuale di un post social** (vedi sotto).
- **Trend**: aggrega i giochi per genere per vedere quali generi crescono di più.
- **Report**: viewer dei report generati (per gioco e per genere), con summary bilingue ed
  export HTML.
- **Import manuale post social**: TikTok e Instagram non hanno API affidabili, quindi i loro
  post si aggiungono a mano dal dettaglio gioco ("Aggiungi post social"): si incolla l'URL e
  le metriche visibili (i campi lasciati vuoti valgono "non raccolto", non zero).
- **Switch lingua IT/EN**: dal menu Lingua, a runtime, senza riavviare.

## Test

```bash
python -m pytest tests/ -q                       # intera suite
python -m pytest tests/test_analysis_quality.py  # singolo file
```

I test non fanno chiamate di rete (le sorgenti sono mockate). I test della GUI che
richiedono PyQt6 vengono saltati automaticamente se PyQt6 non è installato.

## Limiti noti

- **Wishlist e vendite Steam non sono pubbliche.** Si usano proxy: recensioni Steam, player
  count, stime SteamSpy, follower/menzioni social.
- **TikTok e Instagram**: solo import manuale (nessuno scraping attivo, per rispettare i ToS).
- **Stime SteamSpy** (owner/vendite): approssimative, da usare per il trend e non come valori
  esatti.
- **Parametri del quality score** (pesi, costanti di normalizzazione, soglia di discard): al
  momento tarati su dati sintetici, **da ricalibrare su dati reali**.
- L'analisi parla sempre di **co-occorrenza, mai di causalità**: correlazione ≠ causa.
