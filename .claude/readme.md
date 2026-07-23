# GamesTracker — handoff per nuove sessioni

> **Leggi questo file per primo.** Ti dice cos'è il progetto, com'è organizzato, cosa è fatto e cosa manca. Poi leggi solo i file reference che ti servono.

## Cos'è

Tool desktop + web (Python + PyQt6 + FastAPI) per **game dev**. Raccoglie costantemente le ultime uscite indie da **Steam** e **itch.io**, ne salva tutti i dati, e ne **traccia la crescita** a +24h/+48h/+1 settimana/+1 mese. Cerca online come i giochi validi sono diventati virali (TikTok, Reddit, Instagram, YouTube, X/Twitter), scarta il trash con un **quality score 0-100**, e produce **grafici + report bilingue (IT/EN)** che spiegano le strategie di marketing. Analisi AI per sentiment, market gap, launch health score. Progetto open-source di riferimento per indie dev.

## Come è strutturato il lavoro

- **Orchestratore** = la sessione Claude principale. Coordina, non fa tutto da sola: fa il dispatch degli agenti specializzati.
- **Agenti** in `.claude/agents/`:

| Agente | Ruolo |
|---|---|
| `research-scout` | Verifica endpoint/API, trova librerie, riusa codice parent |
| `data-collector-engineer` | Collector background + client sorgenti (core/, collector/) |
| `data-analyst` | Quality score, crescita, trend, AI analysis, report (analysis/) |
| `social-marketing-analyst` | Dominio marketing/social: cosa raccogliere e come interpretarlo |
| `social-scraper-engineer` | Scraping engine no-auth: TikTok, Instagram, X, Reddit fallback (core/sources/social/) |
| `gui-engineer` | App PyQt6, grafici, i18n (gui/) |
| `web-engineer` | Dashboard web FastAPI + HTMX + Jinja2 (web/) |
| `devops-engineer` | Docker, GitHub Actions CI/CD, infrastruttura (.github/, Dockerfile) |
| `codebase-documenter` | Mantiene readme/progress/reference allineati |

## Dove trovare cosa (`.claude/`)

- `readme.md` — questo file (entrypoint).
- `context/decisions.md` — **decisioni bloccate** con l'utente. Non ridiscuterle senza motivo.
- `context/progress.md` — **stato attuale** dei lavori. Aggiornalo sempre.
- `reference/architecture.md` — architettura, stack, struttura cartelle target, data flow.
- `reference/data-sources.md` — endpoint, auth, rate limit per ogni sorgente (Steam, itch, YouTube, Reddit, RAWG, IGDB, HLtB, OpenCritic, TikTok, Instagram, X).
- `reference/data-model.md` — schema DB (games, snapshots, social, report).
- `reference/quality-score.md` — spec anti-trash (score 0-100).
- `reference/tracking-schedule.md` — snapshot 24h/48h/1w/1mo + regole di backfill.
- `reference/marketing-playbook.md` — come si analizza una strategia di marketing.
- `reference/code-map.md` — mappa di tutti i file del progetto.

## Comandi slash in `.claude/commands/`

| Comando | Cosa fa |
|---|---|
| `/run-tests` | Esegue la suite di test completa con coverage |
| `/add-source` | Template guidato per aggiungere una nuova sorgente dati |
| `/health-check` | Verifica che tutti i servizi girino correttamente |
| `/scraping-status` | Stato dei job di scraping social attivi |

## Decisioni chiave (sintesi — dettagli in decisions.md)

1. **Collector + GUI separati**: un servizio background raccoglie su DB; la GUI PyQt6 legge dal DB. Web dashboard (FastAPI) legge anch'essa solo dal DB.
2. **API ufficiali dove possibile** (YouTube, Reddit, RAWG, IGDB); scraping no-auth per le piattaforme senza API (TikTok, Instagram, X). Priorità: dati corretti e riutilizzabili.
3. **TikTok/IG: import manuale sempre disponibile** come fallback ToS-safe, indipendente dallo stato dei scraper.
4. **Metriche proxy**: recensioni Steam, player count, SteamSpy (wishlist/vendite NON sono pubbliche).
5. **Quality score 0-100** con soglia configurabile (default 40).
6. **Bilingue IT/EN** — UI, report, i18n runtime.
7. **Snapshot append-only** — ogni raccolta è una nuova riga, mai overwrite.
8. API keys fornite dall'utente in `config/.env` — mai hardcoded, mai committato.

## Come si avvia

```bash
python -m venv venv && source venv/bin/activate   # (Windows: venv\Scripts\activate)
pip install -r requirements.txt
cp config/.env.example config/.env   # inserire le API key
python run_collector.py   # servizio di raccolta in background (APScheduler)
python run_gui.py         # interfaccia PyQt6
python -m uvicorn web.app:app --port 8080   # dashboard web (opzionale)
python -m pytest tests/ -q  # test (118 passed, 2 skipped su sessione 1)
```

## Stato attuale

**Sessione 1 completata (2026-07-21).** MVP completo: Steam, itch.io, YouTube, Reddit, quality score, GUI PyQt6, report IT/EN. 118 passed, 2 skipped.

**Sessione 2 in corso (2026-07-23).** Community docs + agenti .claude aggiornati. Prossimi: RAWG, IGDB, HLtB, OpenCritic, scraper social no-auth, AI analysis, web dashboard FastAPI, Docker, CI/CD.

| Componente | Stato |
|---|---|
| Scaffolding `.claude/` + reference | ✅ |
| Verifica endpoint (research) | ✅ |
| `core/` (config, db, models) | ✅ |
| Sorgenti Steam + itch | ✅ |
| Sorgenti YouTube + Reddit (API ufficiali) | ✅ |
| Sorgenti TikTok + IG (import manuale, ToS-safe) | ✅ |
| `collector/` (discovery, scheduler, snapshot, persistence) | ✅ |
| `analysis/` (quality score, growth, trends, reports) | ✅ |
| `gui/` (PyQt6, viste, grafici, i18n IT/EN) | ✅ |
| Marketing playbook | ✅ |
| Community docs (README, CONTRIBUTING, LICENSE, CHANGELOG, CoC) | ✅ |
| Nuovi agenti .claude (scraper, devops, web) | ✅ |
| Comandi slash .claude | ✅ |
| RAWG, IGDB, HLtB, OpenCritic | 🚧 |
| Scraper no-auth TikTok/Instagram/X | 🚧 |
| AI sentiment + market gap + launch score | 🚧 |
| FastAPI web dashboard | 🚧 |
| Docker + CI/CD | 🚧 |
| Discord/Telegram notifications | 🚧 |
