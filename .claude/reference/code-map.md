# Code map — struttura reale del codice

> Indice sintetico dei file/moduli realmente presenti (verificato 2026-07-21). Una riga per
> file: cosa fa e dove. La fonte di verità resta il codice; questo file è una mappa di
> orientamento. Per l'architettura di design vedi `architecture.md`.

## Radice

```
run_collector.py   Entrypoint collector: init_db + avvia CollectorScheduler, shutdown pulito su SIGINT/SIGTERM.
run_gui.py         Entrypoint GUI: delega a gui.app.run (QApplication).
requirements.txt   Dipendenze pinnate per Python 3.10.x.
config/.env.example  Template variabili d'ambiente (API key, DB_URL, APP_LANG, soglia score, ecc.).
data/              DB SQLite (gamestracker.db) + cache; non committato (.gitkeep traccia la cartella).
```

## core/ — fondamenta (nessuna dipendenza dalla GUI)

```
core/config.py     Settings (dataclass) + load_settings/get_settings (cache). Validazione on-demand delle key (require_*), MissingConfigError. Non crasha se mancano le key.
core/db.py         Engine SQLAlchemy 2.x, sessionmaker, init_db()/create_all, context manager session_scope. SQLite con foreign_keys=ON, portabile a Postgres.
core/models.py     Modelli ORM typed. Tabelle: games, game_snapshots, social_accounts, social_snapshots, social_posts, analysis_reports. Enum applicativi (Platform, SocialPlatform, SnapshotType, Lang) come VARCHAR.
```

### core/sources/ — client sorgente (isolati, testabili, non scrivono sul DB)

```
core/sources/_http.py            build_client (httpx + User-Agent), request_json/request_text con retry/backoff su 429/5xx, Throttle thread-safe.
core/sources/steam_store.py      appdetails -> SteamStoreData (nome, dev/pub, generi, prezzo, demo, trailer). Parsing date multi-formato.
core/sources/steam_reviews.py    appreviews -> SteamReviewSummary (legge solo query_summary, 1 chiamata leggera).
core/sources/steam_players.py    GetNumberOfCurrentPlayers -> int. Usa la Steam Web API key se presente, altrimenti degrada.
core/sources/steam_discovery.py  Scraping leggero di explore/new + GetAppList con diff_new_appids. Funzioni pure.
core/sources/steamspy.py         steamspy.com/api.php appdetails -> SteamSpyData (owner range + midpoint, ccu, tag). Via httpx.
core/sources/itch.py             Discovery RSS (feedparser) + dettaglio pagina gioco via OpenGraph/JSON-LD/tabella (BeautifulSoup) -> ItchGameData.
```

### core/sources/social/ — sorgenti social

```
core/sources/social/base.py          Protocol SocialSource (find_accounts/collect_posts/snapshot_account) + dataclass NormalizedAccount/AccountSnapshot/Post/GameQuery.
core/sources/social/keywords.py      Liste default dal marketing-playbook: subreddit per genere, suffissi query YouTube, tag; subreddits_for_game().
core/sources/social/youtube.py       YouTubeSource (API v3): search/videos/channels con QuotaTracker + cache su disco. Degrada senza YOUTUBE_API_KEY.
core/sources/social/reddit.py        RedditSource (PRAW, read-only): cerca il titolo nei subreddit target + r/all, dedup su post_url. Degrada senza credenziali.
core/sources/social/tiktok.py        TikTokSource: enabled=False di default (import manuale). Parser URL is_tiktok_url/parse_tiktok_url.
core/sources/social/instagram.py     InstagramSource: come TikTok. Parser URL is_instagram_url/parse_instagram_url.
core/sources/social/manual_import.py import_manual_post(...): funzione che la GUI chiama per aggiungere un post a mano. Valida/normalizza/dedup su post_url.
core/sources/social/persistence.py   Upsert social_accounts, append-only social_snapshots, append_post idempotente. save_posts/save_account_with_snapshot.
```

## collector/ — orchestrazione (background, scrive sul DB)

```
collector/discovery.py       run_discovery(): scansiona Steam explore/new + itch RSS, crea i games nuovi, snapshot discovery, schedula gli snapshot futuri. set_scheduler().
collector/scheduler.py       CollectorScheduler (APScheduler BackgroundScheduler + SQLAlchemyJobStore persistente). compute_snapshot_schedule (pura, backfill). Job discovery + _job_social_snapshot (placeholder).
collector/persistence.py     Upsert idempotente games (Steam/itch), social_accounts, append_game_snapshot append-only (combina reviews/players/steamspy).
collector/jobs/snapshot.py   run_snapshot(platform, external_id, type): per Steam reviews+players+steamspy; per itch riga prezzo. Non crasha.
```

## analysis/ — scoring, crescita, trend, report (letto dalla GUI)

```
analysis/quality_score.py  compute_quality_score(game_data) -> (score 0-100, breakdown). 5 componenti pesati, log-norm, dati mancanti=0.5, penalità moltiplicative. score_game(session, game_id) persiste.
analysis/growth.py         Funzioni pure su snapshot: compute_deltas, growth_over_window (h24/h48/w1/m1), compute_growth_metrics, find_turning_points, follower_growth.
analysis/trends.py         pandas: build_games_frame, growth_by_genre, timing_stats/timing_by_genre, quality_distribution. collect_trend_input(session) = unico accesso DB.
analysis/reports.py        build_game_report/build_genre_report (pure) -> {summary, data}. generate_*_report leggono dal DB e salvano su analysis_reports. export_html sempre, export_pdf opzionale (weasyprint).
analysis/report_i18n.py    Stringhe IT/EN dei report (nessun testo hardcoded monolingua).
```

## gui/ — app PyQt6 (sola lettura dal DB, nessuna rete)

```
gui/app.py                  MainWindow (toolbar + QStackedWidget) + run(argv). Navigazione tra viste, menu Lingua (switch IT/EN runtime), init_db idempotente.
gui/data_access.py          GameRepository: tutte le query SQLAlchemy in sola lettura per le viste.
gui/workers.py              Esecuzione query pesanti fuori dal thread UI (QThreadPool).
gui/views/dashboard.py      Panoramica giochi, filtro piattaforma, slider soglia quality score.
gui/views/game_detail.py    Dettaglio gioco: anagrafica, quality score, timeline marketing, grafici, pulsante "Aggiungi post social".
gui/views/trends.py         Aggregazione per genere (quali generi crescono).
gui/views/reports.py        Viewer report generati (tabella analysis_reports): elenco + summary + export.
gui/views/manual_import.py  ManualImportDialog + save_manual_post(): import manuale post social (delega a import_manual_post). Logica pura testabile senza QApplication.
gui/widgets/charts.py       Grafici interattivi (pyqtgraph) + helper statici matplotlib per l'export (import ritardato).
gui/widgets/tables.py       DataclassTableModel + tabelle riutilizzabili (QTableView).
gui/widgets/common.py       Widget di supporto (stato vuoto, card metrica).
gui/widgets/quality_slider.py  Slider soglia quality score, segnale thresholdChanged(int).
gui/i18n/__init__.py        Sistema i18n: translator, tr(), available_languages(), subscribe (switch runtime).
gui/i18n/strings.py         Dizionari di traduzione IT/EN. Nessuna stringa UI hardcoded.
```

## tests/ — 118 passed, 2 skipped (i 2 skip = GUI PyQt6 non installato). Tutti mockati, nessuna rete.

```
tests/conftest_analysis.py         Dataset sintetici (buono/medio/trash) in SQLite in-memory per i test analysis.
tests/test_models.py               Schema, UNIQUE (platform, external_id), append-only, FK enforcement.
tests/test_steam_sources.py        appdetails/appreviews/players/steamspy/discovery (mock).
tests/test_itch_source.py          RSS + parsing pagina gioco itch.
tests/test_persistence.py          Upsert idempotente collector + snapshot append-only.
tests/test_scheduler.py            Backfill di compute_snapshot_schedule.
tests/test_social_youtube.py       Parsing search/videos/channels, quota, cache (mock).
tests/test_social_reddit.py        submission->post, dedup cross-subreddit (mock).
tests/test_social_persistence.py   Upsert/append/idempotenza social.
tests/test_social_manual_import.py Import manuale + parser URL TikTok/IG.
tests/test_analysis_*.py           quality / growth / trends / reports.
tests/test_gui_data_access.py      GameRepository (sola lettura).
tests/test_gui_i18n.py             i18n IT/EN + switch.
tests/test_gui_manual_import.py    save_manual_post + smoke dialog (skip se manca PyQt6).
tests/test_gui_widgets.py          Widget GUI (skip se manca PyQt6).
```


## web/ — dashboard web (FastAPI + HTMX, sola lettura dal DB)

```
web/__init__.py         Package marker.
web/app.py              FastAPI application factory: router registration, middleware, static files.
web/dependencies.py     get_db() dependency: inietta session SQLAlchemy nei router.
web/routers/games.py    GET /games — lista giochi ordinata per quality score, filtri genere/piattaforma.
web/routers/trends.py   GET /trends — trend aggregati per genere.
web/routers/health.py   GET /health — health check (game_count dal DB).
web/templates/          Jinja2 HTML templates (base.html, dashboard, game_detail, trends).
web/static/css/         Stili (Tailwind o custom CSS).
web/static/js/          HTMX + Chart.js init scripts.
```

## Nuove sorgenti in core/sources/ (in progress)

```
core/sources/rawg.py         RAWG game database: dettaglio gioco, rating, generi, screenshots.
core/sources/igdb.py         IGDB (Twitch): metadati autorevoli, calendario uscite.
core/sources/howlongtobeat.py  HowLongToBeat: playtime per categoria di completamento.
core/sources/opencritic.py   OpenCritic: aggregazione recensioni critici + score.
```

## Nuove sorgenti social in core/sources/social/ (in progress)

```
core/sources/social/x_twitter.py       X/Twitter scraper via Nitter (no-auth).
core/sources/social/reddit_noauth.py   Reddit public JSON fallback (/search.json senza OAuth).
```

## analysis/ — nuovi moduli AI e market intelligence (in progress)

```
analysis/sentiment.py    AI sentiment analysis su reviews e post social (transformer locale).
analysis/market_gap.py   Market gap finder: generi sotto-serviti con alto demand e basso supply.
analysis/launch_health.py  Launch health score: indicatore composito giorno-1 vs. breakout storici.
```

## Infrastructure (in progress)

```
Dockerfile               Multi-stage build: builder / collector / web.
docker-compose.yml       Full stack locale: collector + web + volume SQLite.
.dockerignore            Esclude .env, data/, venv/, __pycache__, .git.
.github/workflows/ci.yml GitHub Actions: ruff lint + pytest su ogni push/PR su main.
```

## Nuovi test (da aggiungere)

```
tests/test_rawg_source.py          RAWG parsing + degradazione senza key.
tests/test_igdb_source.py          IGDB parsing + auth Twitch.
tests/test_howlongtobeat_source.py HLtB parsing.
tests/test_opencritic_source.py    OpenCritic parsing.
tests/test_social_xtwitter.py      X/Nitter scraper (mock HTML).
tests/test_social_reddit_noauth.py Reddit public JSON fallback.
tests/test_analysis_sentiment.py   Sentiment pipeline (mock model).
tests/test_analysis_market_gap.py  Market gap con dataset sintetico.
tests/test_analysis_launch_health.py Launch health score.
tests/test_web_routes.py           FastAPI routes con TestClient (DB in-memory).
```
