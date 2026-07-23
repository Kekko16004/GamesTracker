# Architettura — GamesTracker

Tool desktop che raccoglie le ultime uscite indie (Steam + itch.io), ne traccia la crescita nel tempo, analizza le strategie di marketing/viralità (TikTok, Reddit, Instagram, YouTube) e presenta grafici + report ai game dev per capire quali generi tirano e come farsi pubblicità.

## Componenti (data flow)

```
                 ┌─────────────────────────────────────────────┐
   SORGENTI      │  COLLECTOR (background, sempre attivo)         │
   Steam store   │  - scheduler (APScheduler)                     │
   Steam WebAPI  │  - discovery: nuove uscite Steam + itch.io     │
   SteamSpy      │  - snapshots programmati: +24h/+48h/+1w/+1mo   │
   SteamCharts   │  - social collectors (YouTube/Reddit/TikTok/IG)│
   itch.io       │  - dedup + normalizzazione                     │
   YouTube API   └───────────────┬────────────────────────────────┘
   Reddit API                    │ scrive
   TikTok/IG                     ▼
                          ┌──────────────┐
                          │   DATABASE    │  SQLite (default), schema
                          │  (SQLAlchemy) │  compatibile Postgres
                          └──────┬────────┘
                                 │ legge
             ┌───────────────────┼───────────────────┐
             ▼                                        ▼
     ┌───────────────┐                        ┌────────────────┐
     │  ANALYSIS      │  quality score,        │   GUI (PyQt6)   │
     │  growth, trend,│  trend per genere,     │  dashboard,     │
     │  report gen    │  report IT/EN          │  grafici, report│
     └───────────────┘                        └────────────────┘
```

## Struttura cartelle prevista (target)

```
GamesTracker/
├─ collector/          # servizio background: scheduler, discovery, snapshot jobs
│  ├─ scheduler.py     # APScheduler: pianifica snapshot +24h/+48h/+1w/+1mo
│  ├─ discovery.py     # trova nuove uscite Steam + itch.io
│  └─ jobs/            # job di snapshot per sorgente
├─ core/               # codice condiviso tra collector, analysis, gui
│  ├─ config.py        # carica config/.env, settings
│  ├─ db.py            # engine SQLAlchemy, session
│  ├─ models.py        # modelli ORM (vedi data-model.md)
│  └─ sources/         # client per ogni sorgente dati (vedi data-sources.md)
│     ├─ steam_store.py, steam_webapi.py, steamspy.py, steamcharts.py
│     ├─ itch.py
│     └─ social/ youtube.py, reddit.py, tiktok.py, instagram.py
├─ analysis/           # quality score, metriche crescita, trend, report
│  ├─ quality_score.py
│  ├─ growth.py
│  ├─ trends.py
│  └─ reports.py       # genera report IT/EN (in-app + export)
├─ gui/                # app PyQt6
│  ├─ app.py           # entrypoint GUI
│  ├─ views/           # dashboard, dettaglio gioco, trend, report
│  ├─ widgets/         # grafici (pyqtgraph/matplotlib), tabelle
│  └─ i18n/            # traduzioni IT/EN
├─ config/
│  ├─ .env             # NON committato — API keys
│  └─ .env.example     # nomi variabili
├─ data/               # DB SQLite + cache locale (NON committato)
├─ tests/
├─ run_collector.py    # avvia il collector
├─ run_gui.py          # avvia la GUI
├─ requirements.txt
└─ README.md
```

## Stack tecnologico

| Ambito | Scelta | Note |
|---|---|---|
| Linguaggio | Python 3.10.11 | versione installata sulla macchina |
| GUI | PyQt6 | desktop |
| Grafici | pyqtgraph (preferito, veloce) + matplotlib (export/report) | |
| DB / ORM | SQLite + SQLAlchemy 2.x | schema portabile a Postgres |
| Scheduler | APScheduler | job persistenti su DB |
| HTTP | httpx (o requests) | rispettare rate limit, retry/backoff |
| Analisi | pandas | aggregazioni, trend |
| Reddit | PRAW | API ufficiale |
| YouTube | google-api-python-client | Data API v3 |
| Scraping fragile | requests + parsing HTML / eventuale playwright | solo dove serve |
| Config | python-dotenv | legge config/.env |

## Principi

- **Idempotenza**: rieseguire discovery/snapshot non duplica record (dedup su chiavi stabili: appid Steam, url itch).
- **Ogni raccolta è uno snapshot timestamped**: mai sovrascrivere, sempre append. Il valore del tool è la serie storica.
- **Backfill graduale**: se manca lo snapshot +24h ma è passata 1 settimana, si registra comunque quello settimanale (vedi `tracking-schedule.md`).
- **Separazione netta**: `core/sources/` non sa nulla della GUI; la GUI non fa mai chiamate di rete dirette, legge solo dal DB.
- **i18n dall'inizio**: nessuna stringa UI hardcoded.
- **Rate limit & ToS**: rispettare i limiti, User-Agent identificabile, niente scraping aggressivo che rischia ban.
