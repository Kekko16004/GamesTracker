"""Stringhe bilingue (IT/EN) per i report generati.

Separa completamente il testo dalla logica di ``reports.py`` cosi' che
nessuna stringa di report sia hardcoded in una sola lingua. Le funzioni
di ``reports.py`` scelgono il dizionario in base a ``lang`` e formattano
con ``.format(**kwargs)``.

Regola trasversale (marketing-playbook §4.3): il linguaggio e' sempre di
CO-OCCORRENZA, mai di causalita'. Le frasi qui riflettono questo vincolo.
"""

from __future__ import annotations

from typing import Any

# Dizionario: chiave -> {"it": ..., "en": ...}. Le stringhe usano
# placeholder in stile str.format.
STRINGS: dict[str, dict[str, str]] = {
    # --- Intestazioni report per-gioco ---
    "game_report_title": {
        "it": "Report strategia — {title}",
        "en": "Strategy report — {title}",
    },
    "section_overview": {
        "it": "Panoramica",
        "en": "Overview",
    },
    "section_timeline": {
        "it": "Timeline della strategia",
        "en": "Strategy timeline",
    },
    "section_growth": {
        "it": "Crescita osservata",
        "en": "Observed growth",
    },
    "section_social": {
        "it": "Attivita' social",
        "en": "Social activity",
    },
    "section_limits": {
        "it": "Limiti e avvertenze",
        "en": "Limitations and caveats",
    },
    # --- Pre-lancio (hype pre-esistente vs crescita da lancio) ---
    "section_prelaunch": {
        "it": "Interesse pre-lancio",
        "en": "Pre-launch interest",
    },
    "prelaunch_preexisting": {
        "it": "Questo gioco sembra arrivare al lancio con interesse gia' "
              "accumulato: {n_pre} post/video datati PRIMA della release, "
              "contro {n_post} dopo. Segnali di maturita' pre-lancio: {signals}. "
              "Co-occorrenza, non causalita': l'hype pre-esistente puo' derivare "
              "da beta/early-access/pre-order non misurabili direttamente.",
        "en": "This game appears to reach launch with interest already "
              "accumulated: {n_pre} posts/videos dated BEFORE release, versus "
              "{n_post} after. Pre-launch maturity signals: {signals}. "
              "Co-occurrence, not causation: pre-existing hype may stem from "
              "beta/early-access/pre-orders we cannot measure directly.",
    },
    "prelaunch_launch_driven": {
        "it": "L'attivita' osservata si concentra DOPO la release ({n_post} "
              "post/video dopo contro {n_pre} prima): crescita apparentemente "
              "guidata dal lancio, non da hype pre-esistente. Sempre come "
              "co-occorrenza osservata sui proxy pubblici.",
        "en": "Observed activity is concentrated AFTER release ({n_post} "
              "posts/videos after versus {n_pre} before): growth appears "
              "launch-driven rather than from pre-existing hype. Always as "
              "co-occurrence observed on public proxies.",
    },
    "prelaunch_insufficient": {
        "it": "Dati insufficienti per valutare l'interesse pre-lancio "
              "(servono post datati e una data di release).",
        "en": "Insufficient data to assess pre-launch interest "
              "(dated posts and a release date are required).",
    },
    "prelaunch_signal_early_access": {
        "it": "early access",
        "en": "early access",
    },
    "prelaunch_signal_long_demo_gap": {
        "it": "demo pubblicata molto prima della release",
        "en": "demo released well before launch",
    },
    "prelaunch_signal_early_discovery": {
        "it": "gioco noto da tempo prima della release",
        "en": "game known well before release",
    },
    "prelaunch_signal_pre_videos": {
        "it": "molti video/menzioni pre-release",
        "en": "many pre-release videos/mentions",
    },
    # --- Overview ---
    "overview_developer": {
        "it": "Sviluppatore: {developer}.",
        "en": "Developer: {developer}.",
    },
    "overview_genres": {
        "it": "Generi/tag: {genres}.",
        "en": "Genres/tags: {genres}.",
    },
    "overview_release_date": {
        "it": "**Data di uscita:** {date}",
        "en": "**Release date:** {date}",
    },
    "overview_quality": {
        "it": "Quality score attuale: {score}/100{discarded}.",
        "en": "Current quality score: {score}/100{discarded}.",
    },
    "discarded_suffix": {
        "it": " (sotto soglia, filtrato)",
        "en": " (below threshold, filtered)",
    },
    "no_quality": {
        "it": "Quality score non ancora calcolato.",
        "en": "Quality score not computed yet.",
    },
    # --- Timeline eventi ---
    "event_demo": {
        "it": "{date}: pubblicazione della demo.",
        "en": "{date}: demo released.",
    },
    "event_release": {
        "it": "{date}: uscita ufficiale (release).",
        "en": "{date}: official release.",
    },
    "event_demo_to_release": {
        "it": "La demo e' uscita {days} giorni prima della release "
              "(finestra di accumulo interesse).",
        "en": "The demo was released {days} days before launch "
              "(interest-building window).",
    },
    "event_demo_same_day": {
        "it": "Demo e release molto ravvicinate: strategia di accumulo "
              "interesse debole o assente (segnale negativo lieve).",
        "en": "Demo and release very close together: weak or absent "
              "interest-building strategy (mild negative signal).",
    },
    "event_post": {
        "it": "{date}: post su {platform}{subreddit} - \"{title}\" "
              "(engagement: {engagement}).",
        "en": "{date}: post on {platform}{subreddit} - \"{title}\" "
              "(engagement: {engagement}).",
    },
    "event_turning_point": {
        "it": "{date}: punto di svolta nella crescita di {metric} "
              "(la pendenza accelera dopo questa data).",
        "en": "{date}: turning point in {metric} growth "
              "(slope accelerates after this date).",
    },
    "top_posts_header": {
        "it": "Post a maggiore engagement:",
        "en": "Top posts by engagement:",
    },
    # --- Crescita ---
    "growth_reviews": {
        "it": "Recensioni: {delta:+.0f} nell'intervallo osservato "
              "(da {v0:.0f} a {v1:.0f}).",
        "en": "Reviews: {delta:+.0f} over the observed span "
              "(from {v0:.0f} to {v1:.0f}).",
    },
    "growth_players": {
        "it": "Player count: picco osservato di {peak:.0f} giocatori.",
        "en": "Player count: observed peak of {peak:.0f} players.",
    },
    "growth_none": {
        "it": "Dati di crescita insufficienti (servono piu' snapshot).",
        "en": "Insufficient growth data (more snapshots needed).",
    },
    "growth_window": {
        "it": "  - {window}: {rate:+.1%} recensioni.",
        "en": "  - {window}: {rate:+.1%} reviews.",
    },
    # --- Social ---
    "social_summary": {
        "it": "{n_posts} post/menzioni raccolti su {n_platforms} piattaforme.",
        "en": "{n_posts} posts/mentions collected across {n_platforms} platforms.",
    },
    "social_none": {
        "it": "Nessun dato social raccolto per questo gioco.",
        "en": "No social data collected for this game.",
    },
    # --- Correlazione / causalita' (SEMPRE presente) ---
    "corr_disclaimer": {
        "it": "Nota metodologica: osserviamo CO-OCCORRENZE temporali, non "
              "rapporti di causa-effetto. Un picco di crescita che segue un "
              "post NON prova che il post l'abbia causato. Nelle finestre di "
              "picco possono coesistere piu' cause (sconti, festival, video "
              "di terzi, release).",
        "en": "Methodological note: we observe temporal CO-OCCURRENCES, not "
              "cause-effect relationships. A growth spike following a post "
              "does NOT prove the post caused it. Multiple causes may coexist "
              "in a spike window (discounts, festivals, third-party videos, "
              "release).",
    },
    "proxy_disclaimer": {
        "it": "Le vendite e le wishlist Steam non sono pubbliche: usiamo "
              "proxy (n. recensioni, player count, follower). Le stime "
              "SteamSpy sono approssimative e vanno lette come trend, non "
              "come valori assoluti.",
        "en": "Steam sales and wishlists are not public: we use proxies "
              "(review count, player count, followers). SteamSpy estimates "
              "are approximate and should be read as trends, not absolute "
              "values.",
    },
    "single_sample_disclaimer": {
        "it": "Questo report riguarda un singolo gioco: i pattern osservati "
              "sono aneddotici, non generalizzabili.",
        "en": "This report covers a single game: observed patterns are "
              "anecdotal, not generalizable.",
    },
    "no_events": {
        "it": "Nessun evento di timeline registrato (demo/release/post).",
        "en": "No timeline events recorded (demo/release/posts).",
    },
    # --- Report per-genere ---
    "genre_report_title": {
        "it": "Report di genere — {genre}",
        "en": "Genre report — {genre}",
    },
    "genre_sample": {
        "it": "Campione: {n} giochi del genere \"{genre}\".",
        "en": "Sample: {n} games in the \"{genre}\" genre.",
    },
    "genre_avg_growth": {
        "it": "Crescita media recensioni: {reviews}. Crescita media player: "
              "{players}. Quality score medio: {score}.",
        "en": "Average review growth: {reviews}. Average player growth: "
              "{players}. Average quality score: {score}.",
    },
    "genre_timing": {
        "it": "Timing tipico (mediana): demo->release {d2r} giorni, "
              "release->picco {r2p} giorni.",
        "en": "Typical timing (median): demo->release {d2r} days, "
              "release->peak {r2p} days.",
    },
    "genre_small_sample": {
        "it": "ATTENZIONE: campione piccolo (N={n}). Le medie non sono "
              "statisticamente robuste.",
        "en": "WARNING: small sample (N={n}). Averages are not "
              "statistically robust.",
    },
    "not_available": {
        "it": "n/d",
        "en": "n/a",
    },
    # --- Autopsia post-lancio ---
    "section_post_launch": {
        "it": "Autopsia post-lancio",
        "en": "Post-launch autopsy",
    },
    "post_launch_insufficient": {
        "it": "Dati insufficienti per l'autopsia post-lancio: servono almeno "
              "{needed} snapshot oltre il picco per stimare il decadimento "
              "(disponibili: N={n}). Con piu' snapshot nel tempo questa "
              "sezione diventera' quantitativa.",
        "en": "Insufficient data for the post-launch autopsy: at least "
              "{needed} snapshots past the peak are required to estimate "
              "decay (available: N={n}). This section becomes quantitative "
              "as more snapshots accumulate over time.",
    },
    "post_launch_peak": {
        "it": "Picco di lancio ({metric}) osservato intorno al {date} "
              "(valore {value:.0f}).",
        "en": "Launch peak ({metric}) observed around {date} "
              "(value {value:.0f}).",
    },
    "post_launch_half_life": {
        "it": "Emivita dello slancio post-picco: ~{half_life:.1f} giorni "
              "(tempo stimato perche' il ritmo di crescita si dimezzi; "
              "fit su N={n} punti). Stima approssimata.",
        "en": "Post-peak momentum half-life: ~{half_life:.1f} days "
              "(estimated time for the growth rate to halve; fit on N={n} "
              "points). Rough estimate.",
    },
    "post_launch_half_life_none": {
        "it": "Emivita del decadimento non stimabile (motivo: {reason}; "
              "N={n} punti oltre il picco). Servono piu' snapshot dopo il "
              "picco.",
        "en": "Decay half-life not estimable (reason: {reason}; N={n} points "
              "past the peak). More post-peak snapshots are needed.",
    },
    "post_launch_no_decay": {
        "it": "Nessun decadimento dello slancio rilevato dopo il picco "
              "(N={n}): il ritmo si mantiene o cresce ancora.",
        "en": "No momentum decay detected after the peak (N={n}): the pace "
              "is holding or still rising.",
    },
    "post_launch_second_winds_header": {
        "it": "Seconde vite (nuovi rialzi dello slancio dopo il lancio):",
        "en": "Second winds (renewed momentum after launch):",
    },
    "post_launch_second_wind": {
        "it": "- {date}: rimbalzo della crescita. Eventi che CO-OCCORRONO "
              "nella finestra: {events}.",
        "en": "- {date}: growth rebound. Events CO-OCCURRING in the window: "
              "{events}.",
    },
    "post_launch_no_second_winds": {
        "it": "Nessuna seconda vita rilevata dopo il picco: lo slancio non "
              "e' piu' ripartito nei dati osservati.",
        "en": "No second wind detected after the peak: momentum did not "
              "restart in the observed data.",
    },
    "post_launch_no_events": {
        "it": "nessun evento osservabile",
        "en": "no observable event",
    },
    "post_launch_cooccurrence_note": {
        "it": "Nota: gli eventi elencati COINCIDONO temporalmente con i "
              "rimbalzi, non ne sono la causa dimostrata (vedi Limiti).",
        "en": "Note: the listed events COINCIDE in time with the rebounds; "
              "they are not a proven cause (see Limitations).",
    },
    # Etichette leggibili per i tipi di evento/leva.
    "lever_discount": {
        "it": "sconto sul prezzo",
        "en": "price discount",
    },
    "lever_ea_exit": {
        "it": "uscita da Early Access / salto di versione",
        "en": "Early Access exit / version jump",
    },
    "lever_festival": {
        "it": "festival Steam",
        "en": "Steam festival",
    },
    "lever_social_surge": {
        "it": "impennata di post social",
        "en": "surge of social posts",
    },
}


def t(key: str, lang: str, **kwargs: Any) -> str:
    """Restituisce la stringa localizzata per ``key`` in ``lang``.

    Ripiega su IT se la lingua non e' disponibile e sulla chiave stessa se
    la chiave non esiste (fail-safe, non solleva).
    """
    entry = STRINGS.get(key)
    if entry is None:
        return key
    template = entry.get(lang) or entry.get("it") or next(iter(entry.values()))
    try:
        return template.format(**kwargs) if kwargs else template
    except (KeyError, IndexError, ValueError):
        return template
