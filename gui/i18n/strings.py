"""Dizionari di traduzione IT/EN per l'interfaccia.

Nessuna stringa visibile nella GUI deve essere hardcoded: ogni testo passa
da una chiave definita qui e viene risolto da :func:`gui.i18n.tr`.

Struttura: ``STRINGS[chiave][lingua] -> testo``. Le chiavi usano un
namespace a punti (``area.elemento``) per leggibilita'. I testi possono
contenere segnaposto ``{nome}`` risolti con ``str.format`` in ``tr``.
"""

from __future__ import annotations

# Lingue supportate (coerenti con core.models.Lang e config APP_LANG).
SUPPORTED_LANGS: tuple[str, ...] = ("it", "en")

# Etichette leggibili delle lingue (per il selettore).
LANG_LABELS: dict[str, str] = {"it": "Italiano", "en": "English"}

# Dizionario principale. Ogni chiave DEVE avere sia 'it' sia 'en'.
STRINGS: dict[str, dict[str, str]] = {
    # --- Applicazione / finestra ---
    "app.title": {"it": "GamesTracker", "en": "GamesTracker"},
    "app.language": {"it": "Lingua", "en": "Language"},
    "app.menu.view": {"it": "Vista", "en": "View"},
    "app.menu.language": {"it": "Lingua", "en": "Language"},
    # --- Navigazione tra le viste ---
    "nav.dashboard": {"it": "Dashboard", "en": "Dashboard"},
    "nav.trends": {"it": "Trend", "en": "Trends"},
    "nav.reports": {"it": "Report", "en": "Reports"},
    "nav.simulator": {"it": "Simulatore", "en": "Simulator"},
    "nav.game_detail": {"it": "Dettaglio gioco", "en": "Game detail"},
    "nav.back": {"it": "Indietro", "en": "Back"},
    # --- Comuni ---
    "common.platform": {"it": "Piattaforma", "en": "Platform"},
    "common.platform.all": {"it": "Tutte", "en": "All"},
    "common.platform.steam": {"it": "Steam", "en": "Steam"},
    "common.platform.itch": {"it": "itch.io", "en": "itch.io"},
    "common.genre": {"it": "Genere", "en": "Genre"},
    "common.genre.all": {"it": "Tutti", "en": "All"},
    "common.title": {"it": "Titolo", "en": "Title"},
    "common.developer": {"it": "Sviluppatore", "en": "Developer"},
    "common.publisher": {"it": "Editore", "en": "Publisher"},
    "common.quality_score": {"it": "Quality score", "en": "Quality score"},
    "common.release_date": {"it": "Data rilascio", "en": "Release date"},
    "common.reviews": {"it": "Recensioni", "en": "Reviews"},
    "common.players": {"it": "Giocatori", "en": "Players"},
    "common.na": {"it": "n/d", "en": "n/a"},
    "common.loading": {"it": "Caricamento...", "en": "Loading..."},
    "common.refresh": {"it": "Aggiorna", "en": "Refresh"},
    "common.open": {"it": "Apri", "en": "Open"},
    "common.free": {"it": "Gratis", "en": "Free"},
    # --- Slider soglia quality score ---
    "quality.threshold_label": {
        "it": "Soglia quality score",
        "en": "Quality score threshold",
    },
    "quality.threshold_tooltip": {
        "it": "Nasconde i giochi con punteggio sotto la soglia (trash)",
        "en": "Hides games scoring below the threshold (trash)",
    },
    "quality.value": {"it": "Soglia: {value}", "en": "Threshold: {value}"},
    # --- Stati vuoti ---
    "empty.no_data.title": {
        "it": "Nessun dato disponibile",
        "en": "No data available",
    },
    "empty.no_data.body": {
        "it": "Non ci sono ancora dati raccolti. Avvia il collector per iniziare a tracciare i giochi.",
        "en": "No data has been collected yet. Start the collector to begin tracking games.",
    },
    "empty.no_games": {
        "it": "Nessun gioco supera la soglia o i filtri attuali.",
        "en": "No game passes the current threshold or filters.",
    },
    "empty.no_snapshots": {
        "it": "Nessuno snapshot di crescita registrato per questo gioco.",
        "en": "No growth snapshot recorded for this game.",
    },
    "empty.no_social": {
        "it": "Nessun account o post social collegato.",
        "en": "No linked social account or post.",
    },
    "empty.no_reports": {
        "it": "Nessun report generato. I report compaiono qui dopo l'analisi.",
        "en": "No report generated. Reports appear here after analysis.",
    },
    "empty.select_report": {
        "it": "Seleziona un report dalla lista per vederne i dettagli.",
        "en": "Select a report from the list to see its details.",
    },
    # --- Dashboard ---
    "dashboard.title": {"it": "Panoramica", "en": "Overview"},
    "dashboard.tracked_games": {
        "it": "Giochi tracciati",
        "en": "Tracked games",
    },
    "dashboard.visible_games": {
        "it": "Sopra soglia",
        "en": "Above threshold",
    },
    "dashboard.discarded_games": {
        "it": "Scartati (trash)",
        "en": "Discarded (trash)",
    },
    "dashboard.recent_releases": {
        "it": "Uscite recenti (30 gg)",
        "en": "Recent releases (30 days)",
    },
    "dashboard.top_growth": {
        "it": "Top per crescita",
        "en": "Top by growth",
    },
    "dashboard.genre_distribution": {
        "it": "Distribuzione per genere",
        "en": "Genre distribution",
    },
    "dashboard.games_list": {"it": "Giochi", "en": "Games"},
    "dashboard.growth_reviews": {
        "it": "Crescita recensioni",
        "en": "Review growth",
    },
    # --- Dettaglio gioco ---
    "detail.overview": {"it": "Dati anagrafici", "en": "Overview"},
    "detail.timeline": {
        "it": "Timeline marketing e crescita",
        "en": "Marketing & growth timeline",
    },
    "detail.social": {"it": "Social", "en": "Social"},
    "detail.posts": {"it": "Post", "en": "Posts"},
    "detail.accounts": {"it": "Account", "en": "Accounts"},
    "detail.event.demo": {"it": "Uscita demo", "en": "Demo release"},
    "detail.event.release": {"it": "Uscita", "en": "Release"},
    "detail.event.post": {"it": "Post social", "en": "Social post"},
    "detail.has_demo": {"it": "Demo disponibile", "en": "Demo available"},
    "detail.no_demo": {"it": "Nessuna demo", "en": "No demo"},
    "detail.price": {"it": "Prezzo", "en": "Price"},
    "detail.add_post": {
        "it": "Aggiungi post social",
        "en": "Add social post",
    },
    # --- Import manuale post social ---
    "manual.title": {
        "it": "Aggiungi post social (manuale)",
        "en": "Add social post (manual)",
    },
    "manual.intro": {
        "it": "Incolla il link del post e le metriche visibili. TikTok e Instagram non hanno API affidabili: l'inserimento manuale e' l'unico metodo conforme ai ToS.",
        "en": "Paste the post link and the visible metrics. TikTok and Instagram lack reliable APIs: manual entry is the only ToS-compliant method.",
    },
    "manual.platform": {"it": "Piattaforma", "en": "Platform"},
    "manual.url": {"it": "URL del post", "en": "Post URL"},
    "manual.handle": {"it": "Handle (opzionale)", "en": "Handle (optional)"},
    "manual.posted_at": {
        "it": "Data pubblicazione (opzionale)",
        "en": "Publication date (optional)",
    },
    "manual.post_title": {"it": "Titolo/descrizione (opzionale)", "en": "Title/description (optional)"},
    "manual.views": {"it": "Views", "en": "Views"},
    "manual.likes": {"it": "Like", "en": "Likes"},
    "manual.comments": {"it": "Commenti", "en": "Comments"},
    "manual.shares": {"it": "Condivisioni", "en": "Shares"},
    "manual.metrics_hint": {
        "it": "Lascia vuoto cio' che non conosci (vuoto = non raccolto, diverso da 0).",
        "en": "Leave blank what you don't know (blank = not collected, different from 0).",
    },
    "manual.save": {"it": "Salva", "en": "Save"},
    "manual.cancel": {"it": "Annulla", "en": "Cancel"},
    "manual.saved": {
        "it": "Post salvato.",
        "en": "Post saved.",
    },
    "manual.duplicate": {
        "it": "Post gia' presente: nessun duplicato inserito.",
        "en": "Post already present: no duplicate inserted.",
    },
    "manual.error.url_required": {
        "it": "Inserisci l'URL del post.",
        "en": "Please enter the post URL.",
    },
    "manual.error.invalid": {
        "it": "Dati non validi: {error}",
        "en": "Invalid data: {error}",
    },
    "manual.error.save_failed": {
        "it": "Salvataggio fallito: {error}",
        "en": "Save failed: {error}",
    },
    # --- Trend ---
    "trends.title": {"it": "Trend per genere", "en": "Trends by genre"},
    "trends.growing_genres": {
        "it": "Generi in crescita",
        "en": "Growing genres",
    },
    "trends.avg_score_by_genre": {
        "it": "Score medio per genere",
        "en": "Average score by genre",
    },
    "trends.avg_score": {"it": "Score medio", "en": "Avg score"},
    "trends.game_count": {"it": "N. giochi", "en": "Game count"},
    "trends.total_growth": {
        "it": "Crescita totale recensioni",
        "en": "Total review growth",
    },
    "trends.avg_time_to_traction": {
        "it": "Tempo tipico al primo traino (gg)",
        "en": "Typical time to traction (days)",
    },
    # --- Report ---
    "reports.title": {"it": "Report generati", "en": "Generated reports"},
    "reports.list": {"it": "Elenco report", "en": "Report list"},
    "reports.summary": {"it": "Sintesi", "en": "Summary"},
    "reports.data": {"it": "Dati a supporto", "en": "Supporting data"},
    "reports.generated_at": {"it": "Generato il", "en": "Generated at"},
    "reports.scope.game": {"it": "Per gioco", "en": "Per game"},
    "reports.scope.genre": {"it": "Per genere", "en": "Per genre"},
    "reports.export_pdf": {"it": "Esporta PDF", "en": "Export PDF"},
    "reports.export_html": {"it": "Esporta HTML", "en": "Export HTML"},
    "reports.export_unavailable": {
        "it": "Export non ancora disponibile (modulo analisi in arrivo).",
        "en": "Export not available yet (analysis module coming soon).",
    },
    "reports.export_done": {
        "it": "Report esportato in: {path}",
        "en": "Report exported to: {path}",
    },
    # --- Simulatore Quality Score ---
    "simulator.title": {
        "it": "Simulatore Quality Score",
        "en": "Quality Score Simulator",
    },
    "simulator.intro": {
        "it": "Inserisci le informazioni del tuo gioco per stimare il quality score PRIMA di pubblicare. I campi che non compili restano neutri.",
        "en": "Enter your game's info to estimate the quality score BEFORE publishing. Fields you leave blank stay neutral.",
    },
    "simulator.section.store": {"it": "Pagina store", "en": "Store page"},
    "simulator.section.reviews": {
        "it": "Recensioni (stima)",
        "en": "Reviews (estimate)",
    },
    "simulator.section.social": {
        "it": "Social (opzionale)",
        "en": "Social (optional)",
    },
    "simulator.section.care": {"it": "Segnali di cura", "en": "Care signals"},
    "simulator.field.game_title": {
        "it": "Titolo del gioco",
        "en": "Game title",
    },
    "simulator.field.description": {
        "it": "Descrizione della pagina",
        "en": "Store page description",
    },
    "simulator.field.description_hint": {
        "it": "Una scheda decente supera i 600 caratteri.",
        "en": "A decent page description exceeds 600 characters.",
    },
    "simulator.field.screenshots": {
        "it": "Numero di screenshot",
        "en": "Number of screenshots",
    },
    "simulator.field.has_trailer": {"it": "Ha un trailer", "en": "Has a trailer"},
    "simulator.field.has_header": {
        "it": "Ha immagine di copertina",
        "en": "Has header image",
    },
    "simulator.field.genres": {
        "it": "Generi (separati da virgola)",
        "en": "Genres (comma separated)",
    },
    "simulator.field.tags": {
        "it": "Tag (separati da virgola)",
        "en": "Tags (comma separated)",
    },
    "simulator.field.price": {"it": "Prezzo", "en": "Price"},
    "simulator.field.is_free": {"it": "Gratis", "en": "Free"},
    "simulator.field.has_demo": {"it": "Ha una demo", "en": "Has a demo"},
    "simulator.field.other_games": {
        "it": "Ho gia' pubblicato altri giochi",
        "en": "I have released other games",
    },
    "simulator.field.official_site": {
        "it": "Ha un sito ufficiale",
        "en": "Has an official site",
    },
    "simulator.field.review_pct": {
        "it": "% recensioni positive (stima)",
        "en": "Positive reviews % (estimate)",
    },
    "simulator.field.review_count": {
        "it": "Numero recensioni (stima)",
        "en": "Number of reviews (estimate)",
    },
    "simulator.field.review_hint": {
        "it": "Lascia il conteggio a 0 se il gioco non e' ancora uscito.",
        "en": "Leave the count at 0 if the game is not released yet.",
    },
    "simulator.field.social_platforms": {
        "it": "Piattaforme social attive",
        "en": "Active social platforms",
    },
    "simulator.field.social_posts": {
        "it": "Numero di post pubblicati",
        "en": "Number of published posts",
    },
    "simulator.field.optional_zero": {
        "it": "Lascia a 0 per non specificare (resta neutro).",
        "en": "Leave at 0 to skip (stays neutral).",
    },
    "simulator.calculate": {"it": "Calcola", "en": "Calculate"},
    "simulator.live_update": {
        "it": "Ricalcolo automatico",
        "en": "Auto recalculate",
    },
    "simulator.result.score": {"it": "Quality score", "en": "Quality score"},
    "simulator.result.components": {
        "it": "Contributo delle componenti",
        "en": "Component contributions",
    },
    "simulator.result.penalties": {
        "it": "Penalita' applicate",
        "en": "Applied penalties",
    },
    "simulator.result.no_penalties": {
        "it": "Nessuna penalita': ottimo lavoro.",
        "en": "No penalties: great job.",
    },
    "simulator.result.penalty_factor": {
        "it": "Fattore penalita': {value}",
        "en": "Penalty factor: {value}",
    },
    "simulator.result.hard_trash": {
        "it": "Attenzione: il gioco rientra nei pattern \"trash\" (contenuti quasi assenti).",
        "en": "Warning: this game matches \"trash\" patterns (almost no content).",
    },
    # Nomi leggibili delle 5 componenti.
    "simulator.component.store_page": {
        "it": "Pagina store",
        "en": "Store page",
    },
    "simulator.component.reviews": {"it": "Recensioni", "en": "Reviews"},
    "simulator.component.social": {"it": "Social", "en": "Social"},
    "simulator.component.growth": {"it": "Crescita", "en": "Growth"},
    "simulator.component.care": {"it": "Cura", "en": "Care"},
    # Traduzioni delle penalita' emesse da compute_quality_score.
    "simulator.penalty.no_screenshots_and_no_trailer": {
        "it": "Nessuno screenshot e nessun trailer",
        "en": "No screenshots and no trailer",
    },
    "simulator.penalty.no_screenshots": {
        "it": "Nessuno screenshot",
        "en": "No screenshots",
    },
    "simulator.penalty.no_trailer": {"it": "Nessun trailer", "en": "No trailer"},
    "simulator.penalty.empty_or_placeholder_description": {
        "it": "Descrizione vuota o segnaposto",
        "en": "Empty or placeholder description",
    },
    "simulator.penalty.asset_flip_tags": {
        "it": "Tag da asset-flip",
        "en": "Asset-flip tags",
    },
    "simulator.penalty.suspicious_social_engagement": {
        "it": "Engagement social sospetto",
        "en": "Suspicious social engagement",
    },
    "simulator.penalty.probable_shovelware_zero_content": {
        "it": "Probabile shovelware (contenuti a zero)",
        "en": "Probable shovelware (zero content)",
    },
    # --- Diagnostica "cosa manca" ---
    "simulator.section.diagnosis": {
        "it": "Cosa manca / come migliorare",
        "en": "What's missing / how to improve",
    },
    "simulator.diag.intro": {
        "it": "Suggerimenti ordinati per impatto reale sul punteggio (delta misurato ricalcolando lo score).",
        "en": "Suggestions ranked by real impact on the score (delta measured by recomputing the score).",
    },
    "simulator.diag.none": {
        "it": "Nessun miglioramento evidente: la scheda e' gia' solida.",
        "en": "No obvious improvements: the page is already solid.",
    },
    "simulator.diag.delta": {"it": "+{value} pt", "en": "+{value} pts"},
    "simulator.diag.add_trailer": {
        "it": "Aggiungi un trailer: e' il segnale piu' importante della pagina e la sua assenza fa scattare una penalita'.",
        "en": "Add a trailer: it's the strongest page signal and its absence triggers a penalty.",
    },
    "simulator.diag.more_screenshots": {
        "it": "Aggiungi screenshot: ne hai {current}, i giochi curati del tuo genere ne hanno circa {target}.",
        "en": "Add screenshots: you have {current}, curated games in your genre have about {target}.",
    },
    "simulator.diag.add_header": {
        "it": "Aggiungi l'immagine di copertina (header capsule): senza, la pagina appare incompleta.",
        "en": "Add the header capsule image: without it the page looks incomplete.",
    },
    "simulator.diag.longer_description": {
        "it": "Amplia la descrizione: hai {current} caratteri, una scheda curata del genere ne usa circa {target}.",
        "en": "Expand the description: you have {current} characters, a curated page in your genre uses about {target}.",
    },
    "simulator.diag.more_tags": {
        "it": "Aggiungi tag/generi sensati: ne hai {current}, punta ad almeno {target} per la scopribilita'.",
        "en": "Add sensible tags/genres: you have {current}, aim for at least {target} for discoverability.",
    },
    "simulator.diag.add_demo": {
        "it": "Pubblica una demo: e' un forte segnale di cura e apre la porta ai Next Fest.",
        "en": "Ship a demo: it's a strong care signal and opens the door to Next Fests.",
    },
    "simulator.diag.add_site": {
        "it": "Aggiungi un sito ufficiale: piccolo segnale di serieta' e utile per la stampa.",
        "en": "Add an official site: a small credibility signal, useful for press.",
    },
    "simulator.diag.add_social": {
        "it": "Attiva almeno un paio di canali social e pubblica con costanza: alimenta la componente social.",
        "en": "Activate a couple of social channels and post consistently: it feeds the social component.",
    },
    "simulator.strengths.caption": {
        "it": "Punti di forza",
        "en": "Strengths",
    },
    "simulator.strength.trailer": {"it": "Trailer presente", "en": "Trailer present"},
    "simulator.strength.screenshots": {
        "it": "Buon numero di screenshot",
        "en": "Good number of screenshots",
    },
    "simulator.strength.description": {
        "it": "Descrizione di lunghezza adeguata",
        "en": "Adequately long description",
    },
    "simulator.strength.demo": {"it": "Demo disponibile", "en": "Demo available"},
    # --- Valutazione qualitativa dello score ---
    "simulator.rating.excellent": {"it": "Eccellente", "en": "Excellent"},
    "simulator.rating.good": {"it": "Buono", "en": "Good"},
    "simulator.rating.fair": {"it": "Discreto", "en": "Fair"},
    "simulator.rating.weak": {"it": "Debole", "en": "Weak"},
    "simulator.rating.trash": {"it": "A rischio scarto", "en": "At risk of discard"},
    # --- Score atteso al lancio (recensioni immaginate) ---
    "simulator.expected.caption": {
        "it": "Atteso al lancio",
        "en": "Expected at launch",
    },
    "simulator.expected.hint": {
        "it": "Stima con recensioni tipiche del genere ({genres}) — non e' una previsione, solo un ordine di grandezza.",
        "en": "Estimate using reviews typical of the genre ({genres}) — not a prediction, just an order of magnitude.",
    },
    "simulator.expected.hint_generic": {
        "it": "Stima con recensioni tipiche di un indie medio (genere non riconosciuto).",
        "en": "Estimate using reviews typical of an average indie (genre not recognized).",
    },
    # --- Sezione immagini ---
    "simulator.section.images": {
        "it": "Immagini (copertina, header, screenshot)",
        "en": "Images (cover, header, screenshots)",
    },
    "simulator.images.hint": {
        "it": "Carica gli asset per farli valutare (dimensioni e proporzioni vs specifiche Steam). Non giudichiamo il gusto estetico, solo cio' che e' oggettivo.",
        "en": "Upload assets to have them checked (size and aspect ratio vs Steam specs). We don't judge aesthetics, only what's objective.",
    },
    "simulator.images.load_header": {
        "it": "Carica header (460x215)",
        "en": "Load header (460x215)",
    },
    "simulator.images.load_cover": {
        "it": "Carica copertina (600x900)",
        "en": "Load cover (600x900)",
    },
    "simulator.images.load_screenshots": {
        "it": "Carica screenshot (1920x1080)",
        "en": "Load screenshots (1920x1080)",
    },
    "simulator.images.clear": {"it": "Rimuovi immagini", "en": "Clear images"},
    "simulator.images.none": {
        "it": "Nessuna immagine caricata.",
        "en": "No images loaded.",
    },
    "simulator.images.summary": {
        "it": "{shots} screenshot · header: {header} · copertina: {cover}",
        "en": "{shots} screenshots · header: {header} · cover: {cover}",
    },
    "simulator.images.dialog_filter": {
        "it": "Immagini (*.png *.jpg *.jpeg *.webp *.bmp)",
        "en": "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
    },
    "simulator.images.item_ok": {
        "it": "{kind} {w}x{h}: ok",
        "en": "{kind} {w}x{h}: ok",
    },
    "simulator.images.item_issue": {
        "it": "{kind} {w}x{h}: {issue}",
        "en": "{kind} {w}x{h}: {issue}",
    },
    "simulator.image.kind.header": {"it": "Header", "en": "Header"},
    "simulator.image.kind.cover": {"it": "Copertina", "en": "Cover"},
    "simulator.image.kind.screenshot": {"it": "Screenshot", "en": "Screenshot"},
    "simulator.image.unreadable": {
        "it": "immagine illeggibile",
        "en": "unreadable image",
    },
    "simulator.image.header_too_small": {
        "it": "troppo piccola (minimo 460x215)",
        "en": "too small (min 460x215)",
    },
    "simulator.image.header_ratio": {
        "it": "proporzioni sbagliate (attese ~2.14:1)",
        "en": "wrong aspect ratio (expected ~2.14:1)",
    },
    "simulator.image.cover_too_small": {
        "it": "troppo piccola (minimo 600x900)",
        "en": "too small (min 600x900)",
    },
    "simulator.image.cover_ratio": {
        "it": "proporzioni sbagliate (attese 2:3 verticale)",
        "en": "wrong aspect ratio (expected 2:3 vertical)",
    },
    "simulator.image.shot_too_small": {
        "it": "troppo piccolo (minimo 1280x720)",
        "en": "too small (min 1280x720)",
    },
    "simulator.image.shot_below_recommended": {
        "it": "sotto il consigliato (1920x1080)",
        "en": "below recommended (1920x1080)",
    },
    "simulator.image.shot_ratio": {
        "it": "proporzioni non 16:9",
        "en": "aspect ratio not 16:9",
    },
    "simulator.image.unknown_kind": {
        "it": "tipo non riconosciuto",
        "en": "unrecognized type",
    },
    # --- Qualita' pixel (Livello A) ---
    "simulator.image.metrics": {
        "it": "nitidezza {sharp} · contrasto {contrast}% · colore {color} · luce {bright}%",
        "en": "sharpness {sharp} · contrast {contrast}% · color {color} · light {bright}%",
    },
    "simulator.image.blurry": {
        "it": "leggermente sfocata / poco nitida",
        "en": "slightly blurry / soft",
    },
    "simulator.image.very_blurry": {
        "it": "molto sfocata (probabile upscaling)",
        "en": "very blurry (likely upscaled)",
    },
    "simulator.image.too_dark": {
        "it": "troppo scura",
        "en": "too dark",
    },
    "simulator.image.washed_out": {
        "it": "slavata / sovraesposta",
        "en": "washed out / overexposed",
    },
    "simulator.image.low_contrast": {
        "it": "contrasto piatto",
        "en": "flat contrast",
    },
    "simulator.image.dull_color": {
        "it": "colori spenti",
        "en": "dull colors",
    },
    # --- Qualita' descrizione (Livello A) ---
    "simulator.text.stats": {
        "it": "{chars} caratteri · {words} parole · leggibilità {gulpease} · tag citati {coverage}%",
        "en": "{chars} chars · {words} words · readability {gulpease} · tags cited {coverage}%",
    },
    "simulator.text.ok": {
        "it": "descrizione tecnicamente solida",
        "en": "technically solid description",
    },
    "simulator.text.missing": {
        "it": "descrizione mancante",
        "en": "missing description",
    },
    "simulator.text.too_short": {
        "it": "troppo corta (meno di 120 caratteri)",
        "en": "too short (under 120 characters)",
    },
    "simulator.text.short": {
        "it": "corta: conviene ampliarla",
        "en": "short: consider expanding it",
    },
    "simulator.text.wall_of_text": {
        "it": "muro di testo: spezza in paragrafi/elenchi",
        "en": "wall of text: break into paragraphs/bullets",
    },
    "simulator.text.hard_read": {
        "it": "leggibilità difficile: frasi più brevi",
        "en": "hard to read: use shorter sentences",
    },
    "simulator.text.very_hard_read": {
        "it": "leggibilità molto difficile",
        "en": "very hard to read",
    },
    "simulator.text.low_tag_coverage": {
        "it": "i tag/generi non compaiono nel testo (scopribilità)",
        "en": "tags/genres absent from the text (discoverability)",
    },
    "simulator.text.fluffy": {
        "it": "troppi superlativi / marketing vuoto",
        "en": "too many superlatives / empty marketing",
    },
    "simulator.text.weak_hook": {
        "it": "la prima frase non dice cosa si fa nel gioco",
        "en": "the first sentence doesn't say what you do in the game",
    },
    # --- Raccolta dati "Raccogli ora" ---
    "collect.button": {
        "it": "🔄 Raccogli ora (dati + social)",
        "en": "🔄 Collect now (data + social)",
    },
    "collect.running": {
        "it": "Raccolta in corso...",
        "en": "Collecting...",
    },
    "collect.phase.discovery": {
        "it": "Scoperta nuovi giochi",
        "en": "Discovering new games",
    },
    "collect.phase.snapshots": {
        "it": "Aggiornamento snapshot",
        "en": "Updating snapshots",
    },
    "collect.phase.social": {
        "it": "Raccolta social (YouTube + Reddit API)",
        "en": "Collecting social (YouTube + Reddit API)",
    },
    "collect.phase.scraping": {
        "it": "Scraping social (TikTok, Instagram, X, Reddit)",
        "en": "Scraping social (TikTok, Instagram, X, Reddit)",
    },
    "collect.done": {"it": "Raccolta completata", "en": "Collection complete"},
    "collect.error": {
        "it": "Errore durante la raccolta: {message}",
        "en": "Error during collection: {message}",
    },
    "collect.include_social": {
        "it": "Includi social (TikTok, IG, X, YouTube, Reddit)",
        "en": "Include social (TikTok, IG, X, YouTube, Reddit)",
    },
}
