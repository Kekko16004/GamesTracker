# GamesTracker — handoff per nuove sessioni

> **Leggi questo file per primo.** Ti dice cos'è il progetto, com'è organizzato, cosa è fatto e cosa manca. Poi leggi solo i file reference che ti servono.

## Cos'è
Tool desktop (Python + PyQt6) per **game dev**. Raccoglie costantemente le ultime uscite indie da **Steam** e **itch.io**, ne salva tutti i dati, e ne **traccia la crescita** a +24h/+48h/+1 settimana/+1 mese. Cerca online come i giochi validi sono diventati virali (TikTok, Reddit, Instagram, YouTube), scarta il trash con un **quality score 0-100**, e produce **grafici + report bilingue (IT/EN)** che spiegano le strategie di marketing (date demo, date release, date/canali dei post, correlazione con la crescita). Obiettivo: dati veri su quali generi tirano ora e su come farsi pubblicità.

## Come è strutturato il lavoro
- **Orchestratore** = la sessione Claude principale. Coordina, non fa tutto da sola: fa il dispatch degli agenti specializzati.
- **Agenti** in `.claude/agents/`:
  | Agente | Ruolo |
  |---|---|
  | `research-scout` | verifica endpoint/API, trova librerie, riusa codice parent |
  | `data-collector-engineer` | collector background + client sorgenti (core/, collector/) |
  | `data-analyst` | quality score, crescita, trend, report (analysis/) |
  | `social-marketing-analyst` | dominio marketing/social: cosa raccogliere e come interpretarlo |
  | `gui-engineer` | app PyQt6, grafici, i18n (gui/) |
  | `codebase-documenter` | tiene aggiornati readme/progress/reference |

## Dove trovare cosa (`.claude/`)
- `readme.md` — questo file (entrypoint).
- `context/decisions.md` — **decisioni bloccate** con l'utente. Non ridiscuterle senza motivo.
- `context/progress.md` — **stato attuale** dei lavori. Aggiornalo sempre.
- `reference/architecture.md` — architettura, stack, struttura cartelle target, data flow.
- `reference/data-sources.md` — endpoint, auth, rate limit per ogni sorgente.
- `reference/data-model.md` — schema DB (games, snapshots, social, report).
- `reference/quality-score.md` — spec anti-trash (score 0-100).
- `reference/tracking-schedule.md` — snapshot 24h/48h/1w/1mo + regole di backfill.
- `reference/marketing-playbook.md` — (da creare dal social-marketing-analyst) come si analizza una strategia.

## Decisioni chiave (sintesi — dettagli in decisions.md)
1. **Collector + GUI separati**: un servizio background raccoglie su DB; la GUI PyQt6 legge dal DB.
2. **API ufficiali dove possibile** (YouTube, Reddit); TikTok/IG best-effort. Priorità: dati corretti e riutilizzabili.
3. **Metriche**: recensioni Steam, player count, SteamSpy, follower/menzioni social (wishlist/vendite NON sono pubbliche).
4. **Quality score 0-100** con soglia configurabile.
5. **Bilingue IT/EN**.
6. **MVP**: Steam+itch → YouTube+Reddit → TikTok+IG → dashboard/report in-app.
7. API keys fornite dall'utente in `config/.env`.

## Come si avvia
```
python -m venv venv && venv\Scripts\activate   # (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
cp config/.env.example config/.env   # inserire le API key
python run_collector.py   # servizio di raccolta in background (APScheduler)
python run_gui.py         # interfaccia PyQt6
python -m pytest tests/ -q  # test
```
Verificato sul codice reale (2026-07-21): `run_collector.py` avvia lo scheduler + init_db;
`run_gui.py` avvia la QApplication via `gui.app.run`. Vedi `README.md` alla radice per la
guida utente completa.

## Stato attuale
**Sessione 1 completata (2026-07-21).** Tutte le fasi 1-6 implementate, suite di test verde:
**118 passed, 2 skipped** (i 2 skip = test GUI che richiedono PyQt6, non installato in questo
ambiente). Dettaglio e prossimi passi in `context/progress.md` → "Stato finale sessione 1".

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
| Marketing playbook (dominio social) | ✅ |

Nota: TikTok/IG sono coperti solo via **import manuale** (decisione locked §2), non con
scraping automatico. Le sorgenti social automatiche restano disabilitate finché non si
forniscono le API key.
