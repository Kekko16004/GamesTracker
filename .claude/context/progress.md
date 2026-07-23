# Progress log

> Aggiornare a ogni milestone. Data assoluta obbligatoria. La verità è il codice; questo file racconta il "dove siamo".

## 2026-07-21 — Sessione 1 (setup)
- Progetto greenfield (cartella vuota all'inizio). Python 3.10.11 disponibile.
- Raccolte le decisioni di progetto con l'utente → `context/decisions.md`.
- Creata la scaffolding `.claude/`: reference (architecture, data-sources, data-model, quality-score, tracking-schedule), agenti (6), readme di handoff.
- Creato il team di agenti:
  - `research-scout`, `data-collector-engineer`, `data-analyst`, `social-marketing-analyst`, `gui-engineer`, `codebase-documenter`.
- Piano d'azione definito e in attesa di conferma utente (vedi readme.md / piano).

## 2026-07-21 — research-scout (verifica sorgenti + soluzioni esistenti)
- Verificati online gli endpoint delle sorgenti → `reference/data-sources.md` aggiornato (URL esatti, parametri, rate limit, requisiti auth; segnalato con ✅/⚠️/❓ cosa è confermato o meno).
- Scoperte principali: Steam `appreviews` con `query_summary` è la chiave del review tracking (basta 1 chiamata leggera); itch.io discovery via RSS ufficiale (`.xml`), non serve la server-side API; SteamCharts/SteamDB niente API → ricostruire serie storica con snapshot di `GetNumberOfCurrentPlayers`; YouTube 10k unità/giorno (search.list=100, videos.list=1); Reddit 100 QPM OAuth; TikTok/IG solo best-effort.
- Creato `reference/existing-solutions.md`: librerie GitHub (steamreviews, steamspypi MIT; PRAW, google-api-python-client; pyqtgraph), opzioni TikTok/IG con trade-off, inventario codice locale riusabile, stack finale per sorgente.
- Codice locale riusabile: template PyQt6 in `Instagram Tools\Not Following Back\check-follow-back.py` e pattern collector/polling in `Subito-Bot\subito-searcher.py`. ⚠️ `SteamAchievement\steam.py` ha una Steam Web API key hardcoded da bonificare.

## 2026-07-21 — social-marketing-analyst (playbook di dominio)
- Creato `reference/marketing-playbook.md`: documento di dominio marketing/social che guida data-analyst ed engineer social.
- Contenuti: (1) segnali di viralità/campagna con mapping esplicito sulle tabelle; (2) cosa raccogliere per YouTube/Reddit/TikTok/IG mappato su `social_accounts`/`social_snapshots`/`social_posts` con livello di affidabilità (API vs best-effort/manuale); (3) liste concrete di subreddit/hashtag/keyword YouTube, anche per genere; (4) metodo per ricostruire la "timeline strategia" e regole operative correlazione≠causalità per il report; (5) come alimentare la componente engagement social (20%) del quality score, con normalizzazione log/percentile, dati mancanti=neutro e penalità anti-spam/bot.
- Principio ribadito ovunque: wishlist/vendite non pubbliche → uso di proxy pubblici; co-occorrenza, mai causalità.

## 2026-07-21 — data-collector-engineer (Fase 1: fondamenta)
- Creata la struttura cartelle target da `architecture.md` (`core/`, `core/sources/`, `core/sources/social/`, `collector/`, `collector/jobs/`, `analysis/`, `gui/` + `views`/`widgets`/`i18n`, `config/`, `data/`, `tests/`) con `__init__.py` dove serve.
- `requirements.txt` con stack pinnato per Python 3.10.11. **Scostamento voluto**: NON usato `steamreviews` (richiede Py 3.11+) — la logica appreviews sarà incapsulata con `httpx` in Fase 2. Versioni chiave: PyQt6 6.7.1, pyqtgraph 0.13.7, matplotlib 3.9.2, SQLAlchemy>=2.0,<2.1, APScheduler 3.10.4, httpx 0.27.2, pandas 2.2.3, praw 7.8.1, google-api-python-client 2.149.0, python-dotenv 1.0.1, feedparser 6.0.11, beautifulsoup4 4.12.3, steamspypi 1.1.1, pytest 8.3.3.
- `config/.env.example` con tutte le variabili (STEAM_WEB_API_KEY, YOUTUBE_API_KEY, REDDIT_CLIENT_ID/SECRET/USER_AGENT, DB_URL, APP_LANG, QUALITY_SCORE_THRESHOLD, DISCOVERY_INTERVAL_HOURS, HTTP_USER_AGENT).
- `core/config.py`: `Settings` (dataclass) + `load_settings`/`get_settings` (cache). Import non fallisce mai per key mancanti; validazione on-demand con `require_steam_web_api_key`/`require_youtube_api_key`/`require_reddit_credentials` (sollevano `MissingConfigError`). Default DB = SQLite in `data/gamestracker.db`.
- `core/db.py`: engine SQLAlchemy 2.x (`future=True`), `sessionmaker`, `init_db()`/`create_all`, context manager `session_scope`. SQLite con `PRAGMA foreign_keys=ON`; crea la cartella del file DB se manca. Nessuna feature SQLite-only (portabile a Postgres).
- `core/models.py`: modelli typed (`mapped_column`) per TUTTE le tabelle: `games`, `game_snapshots`, `social_accounts`, `social_snapshots`, `social_posts`, `analysis_reports`. UNIQUE su (platform, external_id); enum applicativi (Platform, SocialPlatform, SnapshotType, Lang) come VARCHAR (`native_enum=False`); campi JSON (genres, tags, extra, data); FK con `ondelete=CASCADE`; indici su game_id/captured_at/platform/posted_at.
- `.gitignore` (config/.env, data/, __pycache__, *.pyc, .pytest_cache, venv). `data/.gitkeep` per tracciare la cartella.
- `run_collector.py` e `run_gui.py`: stub Fase 1 (import core OK, "not implemented yet"). `run_collector.py` chiama `init_db()`.
- `tests/test_models.py`: 4 test (init_db in memoria + grafo completo, UNIQUE (platform, external_id), append-only snapshot, FK enforcement). **Esito: 4 passed.** Verificati anche gli import degli stub. Nessuna chiamata di rete.
- Scostamenti dallo schema `data-model.md`: nessuno strutturale. `AnalysisReport` espone solo `game_id` (nessuna relationship `game`), coerente con la tabella. Aggiunti indici non elencati esplicitamente in data-model.md (scelta implementativa per query frequenti). `SocialPlatform.TWITTER` mappa il valore "twitter/x" della doc alla stringa `twitter`.

## 2026-07-21 — data-collector-engineer (Fase 2: sorgenti Steam + itch + collector)
- **Client sorgente** (`core/sources/`, isolati, testabili, nessuna dipendenza GUI):
  - `_http.py`: helper condiviso — `build_client` (httpx con User-Agent da config), `request_json`/`request_text` con retry/backoff su errori di rete e HTTP 429/5xx, classe `Throttle` thread-safe per i rate limit.
  - `steam_store.py`: `appdetails` → dataclass `SteamStoreData` (nome, dev/pub, generi, categorie, release_date, is_free, prezzo, header_image, screenshot, presenza trailer, tipo game/demo, demo collegate). `parse_appdetails` gestisce `success:false`/data assente. Parsing date multi-formato (`18 Apr, 2011` / `Apr 2011` / `2011`). Throttle 1.5s.
  - `steam_reviews.py`: `appreviews` → legge SOLO `query_summary` (1 chiamata, `num_per_page=0`, `review_type=all`+`purchase_type=all` per evitare la trappola del total sovrascritto). Dataclass `SteamReviewSummary`. NON usa la libreria `steamreviews` (Py3.11+).
  - `steamspy.py`: httpx su `steamspy.com/api.php?request=appdetails` → `SteamSpyData` (owners range + stima puntuale = midpoint, ccu, prezzo, tag). Throttle 1 req/s.
  - `steam_players.py`: `GetNumberOfCurrentPlayers` → int player count. Usa `require_steam_web_api_key` se disponibile; **se la key manca degrada** (prova senza key + log), non crasha.
  - `steam_discovery.py`: scraping leggero di `explore/new` (regex su `data-ds-appid`) + `GetAppList` con `diff_new_appids` per il diffing. Funzioni di parsing pure.
  - `itch.py`: discovery via RSS (`new-and-popular.xml`) con feedparser → `ItchFeedItem`; dettaglio pagina gioco via OpenGraph + JSON-LD + tabella metadati con BeautifulSoup → `ItchGameData` (titolo, autore, prezzo, data, generi/tag, presenza demo, link social autore). Throttle gentile 2.5s. **robots.txt verificato** (vedi sotto).
  - Ogni client: retry/backoff, non crasha (ritorna None/lista vuota + log), dati normalizzati (dataclass), NON scrive sul DB.
- **collector/** (orchestrazione):
  - `persistence.py`: upsert idempotente su `games` (dedup platform+external_id) per Steam e itch, upsert `social_accounts` (dedup game+platform+url), `append_game_snapshot` append-only che combina reviews/players/steamspy.
  - `jobs/snapshot.py`: `run_snapshot(platform, external_id, snapshot_type)` — per Steam chiama reviews+players+steamspy e fa append; per itch registra riga prezzo (no metriche pubbliche). Non crasha.
  - `scheduler.py`: `compute_snapshot_schedule` (funzione PURA, testabile) che implementa il **backfill** (salta le finestre passate, schedula solo le future). `CollectorScheduler` = APScheduler `BackgroundScheduler` con `SQLAlchemyJobStore` persistente sullo stesso DB. Job ricorrenti: discovery (intervallo da config, primo giro subito) + snapshot social (placeholder Fase 3, hook `_job_social_snapshot`).
  - `discovery.py`: `run_discovery()` scansiona Steam (explore/new) + itch (RSS), crea i games nuovi, append snapshot `discovery`, schedula gli snapshot futuri via scheduler iniettato (`set_scheduler`). Base temporale = release_date se disponibile, altrimenti first_seen (per backfill corretto). Limite `MAX_NEW_PER_CYCLE=40`.
- `run_collector.py`: avvia davvero lo scheduler (init_db + start), logging configurato, shutdown pulito su Ctrl+C/SIGTERM via `threading.Event`.
- **Test** (`tests/`, nessuna chiamata di rete): `test_steam_sources.py` (appdetails successo/failure, date variants, query_summary + fallback total, player count, SteamSpy midpoint, explore/new + GetAppList diff), `test_itch_source.py` (RSS di esempio, pagina gioco OpenGraph/JSON-LD, prezzi), `test_persistence.py` (upsert idempotente Steam/itch, merge tag SteamSpy, social account dedup, append snapshot append-only con DB SQLite in memoria), `test_scheduler.py` (backfill: scoperta in ritardo → solo w1/m1 o solo m1, tutte passate → vuoto). **Esito: 70 passed** (`python -m pytest tests/ -q`). Verificati anche gli import pesanti (APScheduler) e uno smoke test start/schedule/shutdown dello scheduler con jobstore su file.
- Dipendenze installate nel venv: httpx, feedparser, beautifulsoup4, APScheduler, steamspypi (+ requests/anyio/tzlocal ecc. transitive). SQLAlchemy/pytest gia' presenti.
- **Scostamenti**: (1) SteamSpy implementato con httpx diretto invece di `steamspypi` (endpoint banale, coerente con la nota di existing-solutions.md "meglio httpx nostro"); la lib resta installata/pinnata. (2) `data-sources.md`: sezione robots.txt itch aggiornata da ❓ a ✅ (letto e documentato). (3) itch snapshot non ha metriche review/player pubbliche → registra solo prezzo + nota in `extra`.

> NOTA (2026-07-21): le tabelle "Stato per componente" e "Prossimi passi" intermedie sono
> state rimosse perché superate. Lo stato consolidato è in fondo al file → "Stato finale
> sessione 1".

## Blocchi / da chiarire (nota storica Fase 2)
- API keys da fornire (Steam Web API, YouTube, Reddit) — l'utente le fornirà, andranno in config/.env.
- Per il **test reale** dei client Steam/itch (Fase 2) serve rete viva; i test attuali sono tutti mockati. `STEAM_WEB_API_KEY` migliora `steam_players` (player count) ma NON e' bloccante: senza key il client prova comunque senza (spesso funziona) e degrada con log. Gli altri endpoint Steam (appdetails/appreviews/steamspy) e itch (RSS + pagine) non richiedono key.

## 2026-07-21 — data-collector-engineer (Fase 3: sorgenti social YouTube + Reddit)
> Lavoro isolato in `core/sources/social/` + test `tests/test_social_*.py`. NON toccati i file Steam/itch né `collector/` (lavorati in parallelo da altro agente).
- **`core/sources/social/base.py`**: interfaccia `SocialSource` (Protocol runtime-checkable) con `find_accounts`/`collect_posts`/`snapshot_account` + dataclass di trasporto `NormalizedAccount`, `NormalizedAccountSnapshot`, `NormalizedPost`, `GameQuery` (con `from_game`). Principio "dato non raccolto ≠ 0": campi assenti = `None`. Nessun accoppiamento con Steam.
- **`core/sources/social/keywords.py`**: liste di default dal marketing-playbook §3 — subreddit generalisti/showcase/per-genere, `SUBREDDIT_SIZE_TIER` (peso engagement), suffissi query YouTube, tag di genere discovery. `subreddits_for_game(genres, tags)` combina generalisti + per-genere con dedup.
- **`core/sources/social/youtube.py`**: `YouTubeSource` su YouTube Data API v3 (`google-api-python-client`, client lazy/iniettabile). `search_video_ids` (search.list, 100u, con **cache su disco** in `data/cache/youtube/`), `fetch_video_stats` (videos.list, **batch da 50 = 1u**), `fetch_channels` (channels.list). `QuotaTracker` con limite configurabile (default 10k) che solleva `QuotaExceededError` PRIMA di sforare. Mappatura video→`social_posts`, canale→`social_accounts`/`social_snapshots`. Degrada se manca `YOUTUBE_API_KEY` (`enabled=False`, log chiaro).
- **`core/sources/social/reddit.py`**: `RedditSource` con PRAW (client lazy/iniettabile, `read_only=True`, `ratelimit_seconds=300`). `collect_posts` cerca il titolo esatto nei subreddit target (per genere/tag) + r/all, con **dedup su post_url**. `submission_to_post`: score→likes, num_comments→comments, created_utc→datetime UTC, subreddit, permalink→post_url; views=None (non pubblico). Degrada se mancano le credenziali REDDIT_*.
- **`core/sources/social/persistence.py`**: upsert su `social_accounts` (dedup game_id+platform+handle, arricchimento non distruttivo), append-only su `social_snapshots`, `append_post` **idempotente su post_url** (fallback (platform,title,posted_at) per post senza url), `save_posts`/`save_account_with_snapshot` con `session_scope` di core.db o session iniettata. `None` preservato in colonna.
- **Test** (`tests/test_social_youtube.py`, `test_social_reddit.py`, `test_social_persistence.py`): 19 test, tutti mock (nessuna chiamata reale, nessuna key). Coprono parsing search+videos+channels, conteggio/batching quota, quota-exceeded, cache hit, submission→post, dedup cross-subreddit, upsert dedup, append snapshot, idempotenza post. DB SQLite in-memory. **Esito: `python -m pytest tests/ -q` → 43 passed** (19 miei + 24 preesistenti). Nessun test rotto.
- **Dipendenze**: installate nel venv `praw==7.8.1` e `google-api-python-client==2.149.0` (erano nel requirements.txt ma non installate). SQLAlchemy 2.0.51 già presente.
- **Costo quota YouTube stimato**: scoperta di un gioco = 1 search.list (100u) + 1 videos.list (1u) + 1 channels.list (1u) ≈ **~102 unità**. Refresh statistiche successivo (solo videos.list, id da cache) ≈ **1-2 unità**. Con 10k/giorno: ~97 giochi nuovi/giorno OPPURE migliaia di refresh. Cache dei videoId su disco evita di ripagare la search.
- **Hook per il collector** (da integrare quando si tocca `collector/`):
  1. Costruire le sorgenti: `build_youtube_source(settings, quota=QuotaTracker(...))` e `build_reddit_source(settings)`. Condividere UNA `QuotaTracker` YouTube tra tutti i job della giornata per rispettare il budget globale.
  2. Per ogni gioco: `q = GameQuery.from_game(game)`; `posts = source.collect_posts(q)`; poi `save_posts(game.id, posts)`.
  3. Per il canale YouTube ufficiale (channelId noto, es. dal link store): `snap = yt.snapshot_account(NormalizedAccount(platform="youtube", handle=channel_id))` + `save_account_with_snapshot(game.id, account, snap)`.
  4. Controllare `source.enabled` prima di schedulare (evita lavoro inutile se le key mancano).
- **Per il test reale servono**: `YOUTUBE_API_KEY` (Google Cloud Console) e `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`/`REDDIT_USER_AGENT` (reddit.com/prefs/apps) in `config/.env`. Senza key le sorgenti restano disabilitate senza crashare.
- Nessuna modifica a `data-sources.md`: le sezioni YouTube/Reddit combaciano già con l'implementazione (costi quota, 100 QPM, endpoint).

## 2026-07-21 — data-analyst (Fase 4: analisi, scoring, report)
> Lavoro isolato in `analysis/` + test `tests/test_analysis_*.py`. NON toccati `core/`, `collector/`, `core/sources/`, `gui/`.
- **`analysis/quality_score.py`**: score 0-100 anti-trash.
  - `compute_quality_score(game_data, weights=None, social_subweights=None) -> (score, breakdown_dict)` = **funzione pura**. `game_data` = dict con `store/reviews/social/growth/care`. Ritorna score + breakdown json-serializzabile (componenti 0-1, contributi pesati, dettaglio 4 sotto-segnali social, penalità applicate, penalty_factor, flags, pesi usati) → pronto da spiegare nella GUI.
  - 5 componenti (pesi = `DEFAULT_WEIGHTS`, sovrascrivibili): store_page 25%, reviews 30%, social 20%, growth 15%, care 10%. Social scomposto nei 4 sotto-segnali del playbook §5.1 (active_accounts .25, mentions .35, post_volume .20, follower_trend .20).
  - Regole rispettate: log-normalizzazione dei conteggi (`log_norm`), **dati mancanti = neutro 0.5** (non zero, non penalizza dev piccoli/pre-release), penalità **moltiplicative** (no screenshot+trailer ×0.4, asset-flip ×0.3, shovelware prezzo0+zero social+zero reviews ×0.2).
  - `build_game_data(session, game_id)` estrae dal DB (usa `growth.compute_growth_metrics`); `score_game(session, game_id, weights, threshold, persist)` calcola e aggiorna `games.quality_score` + `games.discarded` (soglia da `Settings.quality_score_threshold`, default 40).
- **`analysis/growth.py`** (funzioni pure su liste di snapshot): `compute_deltas`, `growth_over_window` (finestre h24/h48/w1/m1, `now` iniettabile), `compute_growth_metrics` (riassunto per reviews+players con `*_growth_rate` sintetico), `find_turning_points` (cambi di pendenza / accelerazione, criterio playbook §4.2), `follower_growth`.
- **`analysis/trends.py`** (pandas): `build_games_frame` (funzione pura da list-of-dict), `growth_by_genre` (media crescita per genere, ordina i generi che tirano), `timing_stats`/`timing_by_genre` (mediana demo→release, release→picco), `quality_distribution` (istogramma). `collect_trend_input(session)` = unico accesso DB.
- **`analysis/reports.py`** + **`analysis/report_i18n.py`** (stringhe IT/EN separate, nessun testo hardcoded monolingua):
  - `build_game_report(game, snapshots, posts, lang)` e `build_genre_report(...)` = funzioni pure → `{"summary": str, "data": dict}`. `summary` ricostruisce la strategia (timeline demo/release/post/punti-svolta, top post, crescita) con **linguaggio di co-occorrenza** e disclaimer SEMPRE presenti (correlazione≠causalità, proxy/SteamSpy approssimativo, campione singolo). `data` json-serializzabile a supporto dei **5 grafici** del playbook §4.5.
  - `generate_game_report`/`generate_genre_report(session, ..., lang, persist)` leggono dal DB e salvano su `analysis_reports` via `save_report`. Export: `export_html` (sempre) + `export_pdf` (hook opzionale: usa weasyprint se presente, altrimenti ritorna None senza rompere).
- **Test** (`tests/test_analysis_quality.py`, `_growth.py`, `_trends.py`, `_reports.py` + helper `tests/conftest_analysis.py` con dataset sintetici buono/medio/trash in SQLite in-memory): ordinamento quality (buono>medio>trash), growth con snapshot noti, aggregazione trends per genere, report IT ed EN (summary non vuoto, data serializzabile, disclaimer presenti), rispetto soglia discarded, pesi configurabili, hook PDF. **Esito: `venv/Scripts/python -m pytest tests/ -q` → 98 passed** (24 miei + 74 preesistenti). Nessun test preesistente rotto. Dipendenza `pandas==2.2.3` installata nel venv.
- **Validazione pesi (taratura sintetica)**: sui 3 casi sintetici → good **93.75**, mid **63.83**, trash **0.49** (ordinamento corretto, trash sotto ogni soglia ragionevole). Pesi lasciati ai valori di `quality-score.md` (frutto dell'analisi di dominio). **DA RIVALIDARE SU DATI REALI**: (1) i valori di riferimento della log-normalizzazione (`REF_REVIEWS=2000`, `REF_MENTIONS_ENGAGEMENT=5000`, `REF_POST_COUNT=60`) sono costanti provvisorie → sostituire con percentili (es. 95°) del corpus reale; (2) la soglia di discard (default 40) va calibrata sulla distribuzione degli score reali; (3) i pesi vanno riverificati contro un set di giochi reali noti (buoni vs trash) e ritarati.
- **Firma funzioni per la GUI (Fase 5) — viewer report/score**:
  - Quality score: `analysis.quality_score.score_game(session, game_id, weights=None, threshold=None, persist=True) -> (score: float, breakdown: dict)`. Per il ricalcolo "a vuoto" senza DB: `compute_quality_score(game_data: dict, weights=None) -> (float, dict)`.
  - Report per-gioco: `analysis.reports.generate_game_report(session, game_id, lang="it"|"en", persist=True) -> {"summary": str, "data": dict, "report_id"?: int}`.
  - Report per-genere: `analysis.reports.generate_genre_report(session, genre: str, lang="it"|"en", persist=True) -> {"summary": str, "data": dict, "report_id"?: int}`.
  - Export: `analysis.reports.export_html(report: dict, title=None) -> str`; `analysis.reports.export_pdf(report: dict, out_path: str, title=None) -> str|None`.
  - Trend/grafici dashboard: `analysis.trends.collect_trend_input(session) -> list[dict]` → `build_games_frame(records) -> DataFrame` → `growth_by_genre(df)`, `timing_by_genre(df)`, `timing_stats(df)`, `quality_distribution(df)` (tutte ritornano strutture json-friendly).
  - Il dict `data` dei report contiene `charts` con: `reviews_timeseries`/`players_timeseries` (series+markers), `posts_by_platform`, `top_posts_engagement`, `growth_windows` + `events` (timeline). Il `breakdown` del quality score contiene `components`, `weighted`, `social_detail`, `penalties`, `flags` (per un pannello esplicativo).

## 2026-07-21 — data-collector-engineer (Fase 6: TikTok + Instagram, import manuale ToS-safe)
> Coerente con decisione locked §2: TikTok/IG senza API affidabili → **base = import manuale** dietro l'interfaccia `SocialSource`. Nessuno scraping attivo di default. Riusata la persistenza esistente (nessuna logica duplicata).
- **`core/sources/social/tiktok.py`** (`TikTokSource`) e **`instagram.py`** (`InstagramSource`): implementano `SocialSource`.
  - `enabled = False` di default; `collect_posts` ritorna `[]` e logga "sorgente automatica non disponibile, usare import manuale". Predisposto hook `collector` iniettabile (scraper/servizio a pagamento futuro): `enabled=True` ha effetto SOLO se si passa anche un `collector`, altrimenti resta disabilitata (niente scraping fittizio). `find_accounts`/`snapshot_account` → `[]`/`None` (no API).
  - Validazione/parsing URL: `is_tiktok_url`/`parse_tiktok_url` (estrae handle + video_id da `/@handle/video/<id>`; short link `vm./vt.` validi ma handle=None senza rete); `is_instagram_url`/`parse_instagram_url` (post `/p|reel|reels|tv/<code>/`, variante con username, profilo; esclude route riservate). Helper modulo `account_from_url` in entrambi.
- **`core/sources/social/manual_import.py`**: `import_manual_post(session, game_id, platform, url, posted_at=None, title=None, views=None, likes=None, comments=None, shares=None, handle=None) -> SocialPost|None`. È la funzione che la GUI chiama. Valida URL (per TikTok/IG usa i parser dedicati; altre piattaforme accettano URL non vuoto), normalizza (`_coerce_metric`: vuoto→`None`, negativo/non numerico→`ManualImportError`), deduce l'account da handle esplicito o dall'URL (upsert senza snapshot), e salva **idempotente su post_url** via `append_post`/`save_account_with_snapshot` (persistenza NON riscritta). Ritorna `None` sui duplicati. `ManualImportError(ValueError)` per input invalido.
- **GUI** — `gui/views/manual_import.py`: `ManualImportDialog(game_id, parent, session_factory=None)` + `save_manual_post(...)` (logica pura rispetto a Qt: apre transazione e delega a `import_manual_post`, ritorna `ImportOutcome.SAVED|DUPLICATE`; testabile senza QApplication). Combo piattaforma (TikTok/IG in cima), URL, handle, data (`YYYY-MM-DD`), titolo, metriche (vuote = non raccolto ≠ 0). i18n IT/EN completo (chiavi `manual.*` + `detail.add_post`). `gui/views/game_detail.py`: aggiunto pulsante "Aggiungi post social" nel gruppo Social (import ritardato della dialog); al salvataggio con successo ricarica il dettaglio fuori dal thread UI. Modifiche chirurgiche, stile esistente rispettato. La GUI scrive sul DB SOLO tramite `import_manual_post` (unica eccezione consentita: input utente, non rete).
- **Test**: `tests/test_social_manual_import.py` (17 test: validazione/parsing URL TikTok+IG, normalizzazione→`NormalizedPost`, salvataggio + link account, idempotenza su url, rifiuto url/piattaforma/metrica negativa, `enabled=False` di default e `collect_posts` vuoto, delega al collector iniettato, conformità al Protocol `SocialSource`); `tests/test_gui_manual_import.py` (`save_manual_post` persiste/dedup/propaga errori + smoke test dialog offscreen con `pytest.importorskip("PyQt6")`). DB SQLite in-memory, nessuna rete.
- **Esito**: `venv/Scripts/python -m pytest tests/ -q` → **118 passed, 2 skipped** (i 2 skip = test GUI che richiedono PyQt6, non installato in questo ambiente; la logica di import è coperta senza PyQt6). Nessun test preesistente rotto.
- **Come l'utente aggiunge un post dalla GUI**: apri il dettaglio di un gioco → gruppo "Social" → pulsante "Aggiungi post social" → incolla URL + metriche visibili (lascia vuoto ciò che non conosci) → Salva. Il post compare subito nella lista. TikTok/IG accettano solo URL della piattaforma corretta; il duplicato dello stesso URL non viene reinserito.

## 2026-07-21 — Stato finale sessione 1 (verifica codebase-documenter)

> Verifica finale e handoff. Tutte le fasi 1-6 completate nella sessione 1. Documentazione
> allineata al codice reale (README.md alla radice, `.claude/readme.md`, `reference/code-map.md`).

**Esito reale della suite** — `venv/Scripts/python -m pytest tests/ -q` → **118 passed,
2 skipped**. I 2 skip sono `test_gui_manual_import.py` e `test_gui_widgets.py`, saltati con
`pytest.importorskip("PyQt6")` perché PyQt6 non è installato in questo ambiente. Nessun
fallimento.

**Entrypoint verificati**: `import run_collector` → OK. `import gui.app` → fallisce solo con
`ModuleNotFoundError: No module named 'PyQt6'` (nota d'ambiente, non un bug: PyQt6/pyqtgraph/
matplotlib sono pinnati in requirements.txt ma non installati in questo venv).

**requirements.txt**: nessuna discrepanza da correggere. Tutte le dipendenze importate
direttamente dal codice (httpx, SQLAlchemy, APScheduler, pandas, praw,
google-api-python-client, python-dotenv, feedparser, beautifulsoup4, steamspypi, pytest)
sono già pinnate e le versioni combaciano con `pip freeze`. PyQt6 6.7.1 / pyqtgraph 0.13.7 /
matplotlib 3.9.2 restano pinnate ma non installate (GUI non esercitata in questo ambiente).

**Stato per componente (consolidato)**

| Componente | Stato |
|---|---|
| Scaffolding `.claude/` + reference | ✅ |
| Verifica endpoint (research-scout) | ✅ |
| `core/` (config, db, models) | ✅ (Fase 1) |
| Sorgenti Steam + itch | ✅ (Fase 2) |
| `collector/` (discovery, scheduler, snapshot, persistence) | ✅ (Fase 2) |
| Sorgenti YouTube + Reddit (API ufficiali) | ✅ (Fase 3) |
| `analysis/` (quality score, growth, trends, reports) | ✅ (Fase 4) |
| `gui/` (PyQt6: dashboard, trends, reports, game_detail, widgets, i18n) | ✅ (Fase 5) |
| Sorgenti TikTok + IG (import manuale, ToS-safe) | ✅ (Fase 6) |
| Marketing playbook (dominio social) | ✅ |

**Note di verità dal codice reale (rischi/incoerenze note)**
- Non esiste una entry di progress dedicata alla Fase 5 (GUI core: dashboard/trends/reports/
  game_detail/widgets/i18n): il codice è presente e importabile, ma la sua storia non è
  documentata qui. La Fase 6 (manual import) ha esteso la GUI ed è documentata sopra.
- Il job `_job_social_snapshot` dello scheduler è ancora un placeholder: le sorgenti social
  YouTube/Reddit NON sono integrate nel loop del collector (hook pronto, vedi Fase 3 §"Hook
  per il collector"). Oggi il collector raccoglie Steam+itch; i social vanno alimentati via
  integrazione futura + import manuale (TikTok/IG).
- Tutti i test sono mockati: nessun test end-to-end con rete viva è mai stato eseguito.

**Prossimi passi — sessione 2**
1. Procurare le API key (Steam Web API opzionale, YouTube, Reddit) e metterle in `config/.env`.
2. Test end-to-end reale con rete viva: far girare il collector su pochi appid Steam noti +
   qualche gioco itch, verificare che gli snapshot arrivino nel DB e che le sorgenti social
   YouTube/Reddit rispondano.
3. Integrare YouTube/Reddit nel job `_job_social_snapshot` dello scheduler (hook già pronto,
   condividere una sola `QuotaTracker` YouTube per il budget giornaliero).
4. Ricalibrare il quality score sui dati reali: sostituire le costanti provvisorie
   (`REF_REVIEWS=2000`, `REF_MENTIONS_ENGAGEMENT=5000`, `REF_POST_COUNT=60`) con percentili
   del corpus reale, ritarare la soglia di discard (default 40) e riverificare i pesi contro
   un set di giochi reali noti (buoni vs trash).
5. (Opzionale) Installare PyQt6/pyqtgraph/matplotlib per esercitare la GUI e i 2 test skippati.

## 2026-07-21 — Sessione 2 (primo run reale con rete viva)

> Prima raccolta dati REALE. L'utente ha fornito le key e ha chiesto di raccogliere dati
> stanotte (solo giochi usciti da max ~2 settimane) per consultarli domani.

- **Key configurate**: l'utente ha messo `STEAM_WEB_API_KEY` e `YOUTUBE_API_KEY` in
  `config/env.txt`; copiato in `config/.env` (che è git-ignored). ⚠️ `config/env.txt` NON è
  git-ignored e contiene le key in chiaro — segnalato all'utente (rotazione consigliata se
  il repo diventa pubblico).
- **Decisione Reddit (locked, aggiornata in decisions.md §2b)**: NIENTE scraping Reddit.
  Il `.json` non autenticato è stato chiuso da Reddit il 28/05/2026; lo scraping affidabile
  ora richiede proxy residenziali a pagamento. L'API ufficiale resta gratis/affidabile ma
  l'utente la configurerà con calma più avanti. Per ora `RedditSource` resta `enabled=False`
  e degrada con log (non blocca nulla).
- **Fix config**: `core/config.py` — `DB_URL=`/`APP_LANG=` vuoti nel .env venivano presi come
  valore (stringa vuota) invece del default → `create_engine("")` falliva. Corretto: env vuoto
  → fallback al default. DB inizializzato: 6 tabelle in `data/gamestracker.db`.
- **Filtro freschezza "max 2 settimane"** (`collector/discovery.py`): aggiunto
  `MAX_RELEASE_AGE_DAYS=14` + helper `_is_recent_release(release_date, coming_soon)`.
  Regole: senza data → tenuto; `coming_soon` → tenuto (uscita imminente); con data → solo se
  uscito da ≤14gg. Applicato sia a `discover_steam` (dopo appdetails) sia a `discover_itch`
  (dopo fetch_game_page). Verificato dai log: giochi di giugno/inizio luglio correttamente
  skippati.
- **Smoke test reale (poi rimosso)**: 6/6 sorgenti OK con dati veri — Steam appdetails
  (Stardew Valley), reviews (1.024.961, "Overwhelmingly Positive"), SteamSpy (~35M owners,
  50k ccu), discovery (86 appid da explore/new), itch (36 giochi da RSS), YouTube (25 video,
  key valida, ~100u quota). Nota: google-api-core avvisa che dropperà Python 3.10 da
  ottobre 2026.
- **Primo ciclo discovery reale**: **76 giochi** salvati (40 Steam + 36 itch) con snapshot
  `discovery` baseline. Giochi reali recenti confermati nel DB (Meowgic 2026-07-20, ZeroSpace
  2026-07-21, Palworld 2026-07-09, ecc.).
- **Collector avviato in BACKGROUND** (`python run_collector.py`, background task id
  `bigshw7sp`): scheduler APScheduler con jobstore persistente su DB, discovery ogni 6h.
  ⚠️ NOTA IMPORTANTE PER L'UTENTE: il collector gira solo finché la sessione/finestra resta
  aperta; se il PC si spegne o la sessione chiude, si ferma (i dati già nel DB restano). Per un
  vero servizio "sempre attivo" servirà autostart locale o deploy su VPS (previsto in
  architecture.md).

**Ancora da fare (invariato + nuovo)**
- Integrare YouTube nel job `_job_social_snapshot` (Reddit resta off finché l'utente non
  configura l'API). Oggi il collector raccoglie solo Steam+itch; YouTube è verificato come
  client ma non ancora agganciato al loop automatico.
- Ricalibrare quality score sul corpus reale ora che iniziano ad arrivare dati.

## 2026-07-21 — Sessione 3 (pipeline analisi: scoring + report + social + pre-lancio)

> L'utente ha segnalato: "non mi dà un quality score a nessuno, non mi fa i report".
> Diagnosi sul DB reale: la raccolta funzionava (76 giochi con snapshot), ma la pipeline di
> analisi NON era mai agganciata al collector. Tre cause di cablaggio (non di scraping: i JSON
> endpoint Steam danno già tutto, decisione §1b confermata).

**Cosa era rotto (confermato dal DB):** 0/76 giochi con `quality_score`, 0 report,
`game_snapshots.extra` NULL per tutti, `_job_social_snapshot` placeholder vuoto.

**Fase 1 — store data negli snapshot.** `collector/persistence.py`: nuovo `build_store_extra(details)`
che estrae da `SteamStoreData` (già raccolto) `has_trailer`/`screenshot_count`/`description_length`/
`placeholder_description`. Agganciato in `discovery.py` (Steam+itch) e `jobs/snapshot.py`
(`_snapshot_steam` ora ri-fetcha appdetails per popolare `extra`). Senza questo la componente
store_page (25%) era cieca e scattava la penalità ×0.4 su TUTTI → score inutile.

**Fase 2 — scoring + report agganciati.** Nuovo `collector/jobs/scoring.py::score_and_report(session, game_id, lang)`:
chiama `score_game` + `generate_game_report`, ognuno in try/except isolato (il collector non
crasha). Agganciato dopo ogni append snapshot in `discovery.py` e `jobs/snapshot.py`. Lang da
`Settings.app_lang`.

**Fase 3 — ricalibrazione sul corpus reale.** `analysis/quality_score.py`:
- `REF_REVIEWS` 2000 → **24000** (~p95 del corpus Steam reale; 2000 era ~p75 e saturava il
  segnale volume, schiacciando tutti in alto).
- **Fix penalità itch (importante, playbook §2.5):** distinzione "pagina ispezionata e vuota"
  (Steam trash → penalizza) vs "campo non raccoglibile" (itch non espone screenshot/trailer →
  NON penalizzare). Nuovo flag `store_inspected` (= presenza di `screenshot_count` in extra).
  Prima gli itch erano ingiustamente tutti a ~10; ora 58-62. Penalità no_shots/no_trailer/
  empty_desc/hard_trash applicate solo se `store_inspected`.
- Distribuzione reale post-fix: Steam 54-72, itch 58-62, Palworld 70.1 (alto ma non domina —
  log-scala corretta). Compressione onesta: social+growth neutri 0.5 (nessun dato social,
  1 solo snapshot) → gli score si allargheranno da soli col tempo. Soglia discard lasciata a 40.

**Fase 4 — riprocessamento dei 76 esistenti.** Nuovo `scripts/reprocess_existing.py` (rete viva,
`--no-fetch`, `--limit`): ri-fetcha store data, aggiorna l'ultimo snapshot, calcola score+report.
Eseguito: 76/76 con score, 40 snapshot Steam con `extra`, 0 errori.

**Fase 5 — ricerca social per dev/publisher (gated).** `GameQuery` (+`developer`/`publisher` in
`base.py`); `YouTubeSource.search_video_ids`/`collect_posts` con `include_team` (aggiunge
dev/publisher alla query + **cache_key distinta**) e `capture_pre_launch`. Nuovo
`collector/jobs/social.py::run_social_collection`: riempie `_job_social_snapshot`, condivide UNA
`QuotaTracker`, e attiva la ricerca allargata (dev/publisher + pre-launch) SOLO per i giochi
promettenti (`quality_score >= soglia`, `discarded=False`) per proteggere la quota. Reddit resta off.

**Fase 6 — analisi pre-lancio (hype pre-esistente vs crescita da lancio).** Nuovo
`analysis/reports.py::_prelaunch_analysis(game, posts)` (puro): conta post pre vs post release,
raccoglie segnali di maturità (early access, gap demo→release ≥30gg, first_seen→release ≥30gg,
molti video pre-release), emette verdict `preexisting|launch_driven|insufficient`. Sezione
dedicata nel summary IT/EN (nuove chiavi `report_i18n.py`) + payload `data["prelaunch"]`.
`youtube.py` con `capture_pre_launch` non limita più `publishedAfter` alla demo → cattura i
video pre-lancio. **Caso Palworld verificato**: flag "hype pre-esistente" alzato via Early Access
anche con 0 post YouTube raccolti; diventerà quantitativo quando arriveranno i video.

**Test:** `venv/Scripts/python -m pytest tests/ -q` → **129 passed, 2 skipped** (i 2 skip = GUI/PyQt6,
come sempre). 11 nuovi test (build_store_extra, scoring_job, query dev/publisher + cache key +
pre-launch YouTube, _prelaunch_analysis nei 3 casi, sezione report). Nessun test preesistente rotto.

**Stato DB dopo la sessione:** 76/76 con quality_score, report generati, 40 snapshot con store data.

**Ancora da fare — sessione 4**
- Far girare il collector con la key YouTube per popolare davvero i post social (oggi la
  componente social è ancora neutra 0.5): allora score e report pre/post-release diventano pieni.
- Ritarare `REF_MENTIONS_ENGAGEMENT`/`REF_POST_COUNT` sui percentili social reali (oggi ancora
  provvisori, nessun dato social).
- I report storici nel DB si accumulano (append-only su `analysis_reports`): valutare se la GUI
  deve mostrare solo l'ultimo per gioco (già ordinabile per `generated_at`).
- Preferenza utente registrata: usare **sempre e solo Opus** per i subagent (mai Sonnet/Haiku).

## 2026-07-21 — Sessione 4 (GUI: sort/data, grafico trend, social reale, simulatore, 10 idee)

> Feedback utente sulla GUI + richieste nuove. Alcuni subagent GUI/idee sono falliti per
> quota/errori del gateway (403/503, NON problemi di codice): il lavoro parzialmente committato è
> stato completato dall'orchestratore (Opus). Tutti gli agenti lanciati con model=opus.

- **Dashboard — data rilascio + colonne ordinabili** (`gui/widgets/tables.py`, `gui/widgets/sorting.py`,
  `gui/views/dashboard.py`): nuova colonna "Data rilascio"; header cliccabili con **sort a 3 stati**
  (crescente → decrescente → ordine originale) tramite `DataclassTableModel.cycle_sort` +
  `sort_rows` (funzione PURA in `sorting.py`: None sempre in fondo, tipi misti gestiti, testabile
  senza PyQt6). Indicatore freccia ▲▼ nell'header.
- **Grafico "Generi in crescita" illeggibile → score medio** (`gui/views/trends.py`,
  `gui/widgets/charts.py`): il grafico plottava la crescita recensioni = 0 per tutti (1 solo
  snapshot) → piatto. Nuovo `BarChart.plot_values` (float, scala Y 0-100, etichette accorciate);
  la vista Trend ora mostra lo **score medio per genere** (label `trends.avg_score_by_genre`).
- **Social non più a zero** (`collector/jobs/social.py`, già scritto in sessione 3): capito il
  perché (il job girava solo sullo scheduler, mai eseguito con rete). Verificata la pipeline live
  (Bookshop Simulator → 25 video YouTube, incl. trailer Early Access di **settembre 2025**) e poi
  **eseguita la raccolta reale**: **753 post social** salvati su 40 giochi Steam (34 con post).
  Ricalcolati score+report: componente social ora reale, top invariato ma coerente
  (Bookshop 75.7, Palworld 74.8). **Analisi pre-lancio ora quantitativa**: Bookshop = 24 video
  pre-release vs 1 post → verdetto "hype pre-esistente" (il caso citato dall'utente, confermato
  dai dati).
- **Simulatore Quality Score** (`gui/simulator_logic.py`, `gui/views/simulator.py`, `gui/app.py`):
  nuova vista in cui il dev inserisce le info del proprio gioco (descrizione, screenshot, trailer,
  prezzo, tag, recensioni stimate, demo, ecc.) e ottiene lo score 0-100 live + breakdown per
  componente + penalità tradotte. Logica pura `build_game_data_from_inputs`/`simulate_score`
  (testabile senza PyQt6, usa `compute_quality_score`). Agganciata a toolbar+menu (`nav.simulator`).
- **10 idee di prodotto**: `.claude/reference/product-ideas.md` (benchmark percentili, case study
  giochi esplosi, radar+alert, "il mio gioco vs i top", pattern timing, leaderboard+genre health,
  audit pagina store, watchlist, impatto streamer, report "State of Indie"). 7 alta priorità;
  la #1 (benchmark percentili) è la fondazione.
- **PyQt6 installato nel venv di sviluppo** (6.7.1/pyqtgraph 0.13.7/matplotlib 3.9.2, già pinnati
  in requirements.txt) per verificare davvero la GUI. Smoke test MainWindow offscreen OK (5 viste).
- **Test**: `venv/Scripts/python -m pytest tests/ -q` → **143 passed, 0 skipped** (i 2 test GUI
  prima skippati ora girano, PyQt6 presente). Nuovi test: sort 3-stati/None, plot_values,
  simulator_logic (gioco buono vs vuoto, conteggi 0→neutro, split recensioni, shape breakdown).

**Ancora da fare — sessione 5**
- Le idee di prodotto in `product-ideas.md` (iniziare dalla #1 benchmark percentili / #7 audit store).
- Ritarare `REF_MENTIONS_ENGAGEMENT`/`REF_POST_COUNT` ora che ci sono 753 post social reali.
- GUI: mostrare solo l'ultimo report per gioco (append-only accumula); marker pre-lancio sulla timeline.
- Raccolta social ricorrente: gira solo col collector attivo; per dati TikTok/IG serve import manuale.

## 2026-07-21 — Sessione 5 (simulatore "impeccabile" + valutazione immagini)
- **Benchmark per genere** (`analysis/genre_benchmarks.py`, PURO): tabella euristica di dominio
  (profilo tipico indie recente per ~40 generi/tag + alias/match parziale): n. recensioni tipico a
  ~1 mese, % positive, n. screenshot dei curati, trailer atteso, lunghezza descrizione. `lookup`
  media i campi se più generi combaciano; `estimate_reviews` produce un profilo recensioni
  "atteso al lancio". **Onesto**: sono stime di dominio, NON percentili sul corpus (quello resta
  l'idea #1); ogni output è marcato "stima".
- **Recensioni immaginate**: se il dev NON inserisce recensioni (gioco non ancora uscito), il
  simulatore mostra ANCHE uno score "atteso al lancio" ricalcolato con le recensioni tipiche del
  genere, etichettato come stima (non previsione).
- **Diagnostica "cosa manca"** (`gui/simulator_diagnostics.py`, PURO): approccio controfattuale —
  per ogni leva (trailer, screenshot, header, descrizione, tag, demo, sito, social) ricalcola lo
  score con QUELLA leva sistemata e misura il delta reale in punti; ordina i suggerimenti per
  impatto, con severità (critical/important/info), consigli concreti e confronto col benchmark di
  genere ("ne hai 2, i curati del genere ~12"). Estrae anche i punti di forza e un rating
  qualitativo (Eccellente/Buono/Discreto/Debole/A rischio scarto).
- **Valutazione immagini** (`analysis/image_quality.py`, PURO): il dev carica copertina/header/
  screenshot; il modulo confronta dimensioni e proporzioni con le specifiche Steam (header 460x215,
  cover 600x900, screenshot 1920x1080/16:9), segnalando troppo-piccola / ratio errato / sotto il
  consigliato. NON giudica l'estetica (fuori scopo), solo l'oggettivo. La GUI legge le dimensioni
  con `QImage` (solo dimensioni) e sincronizza n. screenshot/header nei campi di scoring.
- **GUI simulatore riscritta** (`gui/views/simulator.py`): sezione immagini con upload (QFileDialog),
  report tecnico RichText per asset, pannello diagnostica ordinato per impatto, doppio score
  (reale + atteso al lancio), rating qualitativo, punti di forza. Colonna destra ora scrollabile.
- **i18n**: aggiunte ~55 chiavi IT/EN (diagnostica, rating, atteso al lancio, immagini/issue).
- **15 nuove idee di prodotto** (11-25) in `product-ideas.md` — delegato a `social-marketing-analyst`
  (Opus), focalizzate su cosa fare / cosa migliorare nella pagina / criticità.
- **Test**: `python -m pytest -q` → **166 passed** (era 143; +23). Nuovi:
  `test_genre_benchmarks`, `test_image_quality`, `test_simulator_diagnostics`. Smoke test GUI
  simulatore offscreen OK (sync immagini: 2 screenshot validi, 640x360 flaggato errore).

## 2026-07-22 — Sessione 6 (calcolo QUALITÀ reale di immagini e descrizione — Livello A + B)
Richiesta utente: "non c'è un modo per far calcolare la qualità di quei banner descrizione e screenshot?" → scelta "Sia A che B (più A)". Il simulatore ora non misura solo dimensioni/lunghezza ma la qualità **oggettiva** degli asset.
- **Qualità pixel immagini** (`analysis/image_quality.py` esteso, PURO/numpy): metriche calcolate da un ndarray HxWx3 uint8 RGB — nitidezza (varianza del Laplaciano → sfocatura/upscaling), contrasto (std luminanza), luminosità (luminanza media), vivacità colore (Hasler-Süsstrunk). `measure()`, `analyze_image_content(kind,w,h,pixels)` emette codici-issue conservativi solo-WARN (blurry/very_blurry/too_dark/washed_out/low_contrast/dull_color); gli errori dimensionali restano ERROR e prevalgono. `analyze_images` accetta un 4° elemento opzionale = pixels. Soglie volutamente prudenti (meglio non segnalare che falso allarme). NON giudica l'estetica: solo difetti tecnici misurabili.
- **Qualità descrizione** (`analysis/text_quality.py` NUOVO, PURO): indice Gulpease (leggibilità IT), lunghezza/struttura (short/too_short/wall_of_text), allineamento tag↔testo (scopribilità Steam), densità fuffa (regex superlativi IT+EN), qualità dell'hook (la prima frase dice cosa si fa?). `measure_text`, `analyze_text(text, tags)` → codici `simulator.text.*`.
- **Confronto a percentili — Livello B** (`analysis/percentiles.py` NUOVO, PURO/no-numpy): fondamenta per "dove mi colloco vs i top del mio genere". `quantile` (interp. lineare), `percentile_of` (metodo ≤, corpus vuoto→50 neutro), `position()`→PercentileResult (percentile/mediana/p75/is_top/below_median + flag `estimated`), `synthetic_distribution()` fallback deterministico pre-corpus (marcato estimated=True). La distribuzione reale dal corpus `game_snapshots` resta l'idea #1; questo è lo stand-in onesto finché il corpus non è grande.
- **GUI** (`gui/views/simulator.py`): `_qimage_to_rgb()` estrae i pixel (QImage→Format_RGB888→numpy, UNICO punto che tocca Qt); `_images` ora conserva i pixel; il report immagini mostra una riga di metriche per asset; nuovo report qualità sotto il campo descrizione (`_render_text_report`). ~20 nuove chiavi i18n IT/EN.
- **Test**: `python -m pytest -q` → **194 passed** (era 166; +28). Nuovi: `test_text_quality` (10), `test_percentiles` (9), esteso `test_image_quality` (+9 pixel). i18n completa IT/EN, smoke GUI offscreen OK.
- **Onestà intellettuale**: metriche pixel = difetti tecnici misurabili, non gusto; percentili relativi al corpus fornito (flag estimated propagato); Livello C (analisi visiva AI) ancora NON attivato (costo API a pagamento/privacy).

## 2026-07-22 — Sessione 7 (autopsia post-lancio + bottone "Raccogli ora" nella GUI)

> Due richieste: (1) "Autopsia del post-lancio" — analizzare la fase DOPO il picco di
> lancio; (2) task extra — un bottone nella GUI per avviare la raccolta dati con barra di
> progresso live. Alcuni subagent (data-collector-engineer, gui-engineer) sono falliti
> ripetutamente per errori transitori del gateway (400 ValidationException/content-block,
> NON problemi di codice); su istruzione dell'utente ("riprovaci sempre fino a
> completamento") sono stati rilanciati e, dove il gateway restava instabile, il lavoro è
> stato completato dall'orchestratore (Opus) recuperando il parziale già scritto su disco.

- **Autopsia post-lancio** (`analysis/post_launch.py`, NUOVO, PURO — no rete/DB salvo un
  unico thin entrypoint). Funzioni: `find_launch_peak` (picco del lancio su
  reviews/players, modalità auto), `estimate_half_life` (decadimento esponenziale post-picco
  → `half_life_days`, `n`, `lambda_per_day`, `r_squared`; **degrada con `reason`** quando i
  dati sono insufficienti), `find_second_winds` (rilevazione "seconda vita": riaccelerazione
  della crescita dopo il picco, `accel_factor`), `detect_cooccurring_events` (eventi che
  CO-OCCORRONO col rimbalzo: sconto/uscita EA/festival/social_surge — le finestre festival
  sono **iniettate**, nessun calendario hardcoded), `analyze_post_launch` (orchestrazione per
  un gioco), `aggregate_genre_levers` + `analyze_genre_levers_from_db` (unico accesso DB,
  sottile). `MIN_SNAPSHOTS = 3`. Non importa `reports` (evita ciclo): replica 3 micro-helper.
- **Limite onesto dichiarato** (come richiesto dall'utente): tutto è **osservazionale, mai
  causale** (co-occorrenza, non causazione); half-life stimato su **proxy pubblici** (review/
  player, non vendite); campione per-genere piccolo sulla fase lunga (1mo) → **N sempre
  dichiarato**. Oggi quasi tutti i giochi hanno 1 solo snapshot → l'autopsia degrada
  correttamente ("dati insufficienti", con N), che è esattamente il comportamento onesto voluto.
- **Report** (`analysis/reports.py`): nuova sezione "## Autopsia post-lancio" (dopo Social,
  prima dei Limiti) via `_post_launch_lines`, payload in `data["post_launch"]`; snapshot letti
  in `generate_game_report` arricchiti con `price` ed `extra`. `analysis/report_i18n.py`:
  ~16 nuove chiavi IT+EN.
- **Bottone "Raccogli ora" con barra live** — vincolo architetturale rispettato: la GUI **non
  fa rete**, avvia il collector come **processo separato**.
  - `collector/run_once.py` (NUOVO): `run_once(include_social, emit)` esegue UN giro
    (discovery → snapshot MANUAL di tutti i giochi → social opzionale) ed emette il **contratto
    di progresso** su stdout: righe `@@PROGRESS@@ {json}` (marker esatto = prefisso + spazio),
    JSON compatto una-riga con flush; i log restano su stderr. Ultimo evento sempre
    `status="done"`. Ogni fase in try/except (non crasha; su errore emette `status="error"` e
    prosegue). `emit` è iniettabile per i test.
  - `run_collector.py`: aggiunto parsing argomenti `--once` / `--no-social` (il servizio in
    background con scheduler resta il default senza flag).
  - `gui/collect_runner.py` (NUOVO): `parse_progress_line` (PURA, no Qt, mai solleva) +
    `CollectRunner(QObject)` che incapsula un `QProcess` (`sys.executable run_collector.py
    --once [--no-social]`, cwd = project root, MergedChannels), bufferizza stdout per righe e
    emette `progressChanged(phase,status,current,total,message)` / `finished(bool)` /
    `failed(str)`. `total=-1` = sconosciuto (barra indeterminata).
  - `gui/views/dashboard.py`: riga raccolta in cima (bottone "Raccogli ora" + checkbox
    "Includi social (YouTube)" + label stato + `QProgressBar` nascosta). Slot: on click →
    disabilita controlli, barra indeterminata, `runner.start(include_social=...)`; on progress
    → barra determinata se `total>0` altrimenti indeterminata, label = fase tradotta; on
    finished → ripristina e `self.refresh()` (ricarica dal DB); on failed → mostra errore
    tradotto e ripristina. `gui/i18n/strings.py`: chiavi `collect.*` IT/EN.
- **Test**: `venv/Scripts/python -m pytest tests/ -q` → **224 passed** (era 194; +30).
  Nuovi: `tests/test_post_launch.py` (17 — peak/half-life/second-wind/eventi/aggregazione,
  degradazione con N basso) e `tests/test_collect_runner.py` (13 — `parse_progress_line`
  valido/log/malformato/array/None, `run_once` ordine eventi + `--no-social` salta social +
  `emit_progress` riparsabile, smoke offscreen `DashboardView`: widget presenti, slot progress/
  finished/failed non sollevano). Fixture di isolamento del translator singleton per non far
  leakare gli osservatori delle viste tra i test.

**Ancora da fare — sessione 8**
- L'autopsia post-lancio diventa quantitativa solo quando i giochi accumulano ≥3 snapshot su
  più finestre (h24/h48/w1/m1): far girare il collector nel tempo. Le finestre festival sono
  iniettabili → valutare una sorgente calendario (Steam Next Fest, ecc.) da passare all'analisi.
- Ritarare `REF_MENTIONS_ENGAGEMENT`/`REF_POST_COUNT` sui percentili social reali.
- GUI: mostrare solo l'ultimo report per gioco; marker pre-lancio/eventi sulla timeline.
