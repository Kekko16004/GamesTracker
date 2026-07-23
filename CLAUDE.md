# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Prima di tutto
Leggi `.claude/readme.md` — è il punto d'ingresso per ogni sessione. Poi `.claude/context/decisions.md` (decisioni bloccate) e `.claude/context/progress.md` (stato lavori). I file in `.claude/reference/` sono la fonte di verità per architettura, endpoint, schema DB, quality score e schedule.

## Cos'è il progetto
Tool desktop Python + PyQt6 per game dev: raccoglie le ultime uscite indie da Steam e itch.io, traccia la loro crescita a +24h/+48h/+1w/+1mo, analizza le strategie di marketing social (TikTok, Reddit, Instagram, YouTube), scarta il trash con un quality score 0-100, e produce grafici + report bilingue IT/EN.

## Modello di lavoro: orchestratore + agenti
La sessione principale **orchestra**; il lavoro specializzato va delegato ai subagent in `.claude/agents/`:
- `research-scout` — verifica endpoint/API e trova/riusa librerie e codice (incluse le cartelle parent `../`). **Dispatch prima** di implementare una nuova sorgente.
- `data-collector-engineer` — `core/` + `collector/` (scheduler, discovery, snapshot, client sorgenti).
- `data-analyst` — `analysis/` (quality score, crescita, trend, report).
- `social-marketing-analyst` — logica di dominio marketing/social (cosa raccogliere, come interpretarlo).
- `gui-engineer` — `gui/` (PyQt6, grafici, i18n).
- `codebase-documenter` — mantiene readme/progress/reference allineati.

Dopo ogni milestone, aggiorna `.claude/context/progress.md`.

## Architettura (vincoli non negoziabili)
- **Collector e GUI sono processi separati.** Il collector (background, APScheduler) scrive sul DB anche a GUI chiusa; la GUI legge **solo** dal DB. La GUI non fa mai chiamate di rete dirette.
- **Snapshot append-only.** Ogni metrica nel tempo è una nuova riga in `*_snapshots`; mai sovrascrivere. Il valore del prodotto è la serie storica.
- **Idempotenza & dedup** su `(platform, external_id)` — appid Steam / url itch.
- **Backfill**: se mancano snapshot precedenti, registrare comunque quello disponibile andando a ritroso; nessuna finestra blocca le altre.
- `core/sources/` non conosce la GUI; ogni client sorgente è isolato e testabile.
- **i18n dall'inizio**: nessuna stringa UI hardcoded (IT/EN).
- Rispettare rate limit e ToS; User-Agent identificabile; retry/backoff; il collector non deve crashare su errori di rete (logga e continua).

## Stack
Python 3.10.11 · PyQt6 (GUI) · pyqtgraph (grafici interattivi) + matplotlib (export) · SQLAlchemy 2.x + SQLite (schema portabile a Postgres) · APScheduler (job persistenti) · httpx/requests · pandas · PRAW (Reddit) · google-api-python-client (YouTube) · python-dotenv.

## Comandi (target, quando implementato)
```
pip install -r requirements.txt
cp config/.env.example config/.env    # inserire le API key
python run_collector.py               # servizio di raccolta in background
python run_gui.py                     # interfaccia PyQt6
python -m pytest                      # test
python -m pytest tests/test_x.py::test_y   # singolo test
```
Nota: al 2026-07-21 il codice di produzione non è ancora scritto; questi comandi sono la convenzione target definita in `reference/architecture.md`. Aggiornali quando l'implementazione parte.

## Dati e segreti
- API key (Steam Web API, YouTube, Reddit) in `config/.env` — mai committato, mai hardcodato. Nomi in `config/.env.example`.
- `data/` (DB SQLite + cache) non committato.
- Wishlist e vendite Steam NON sono pubbliche: i proxy di crescita sono recensioni Steam, player count, stime SteamSpy, follower/menzioni social. Le stime SteamSpy sono approssimative → usare per trend, segnalare l'incertezza.

## Lingua
Il progetto e l'utente lavorano in **italiano**. Scrivi risposte, doc e report in italiano; UI e report finali bilingue IT/EN.
