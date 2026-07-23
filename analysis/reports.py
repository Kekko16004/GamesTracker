"""Generazione report per-gioco e per-genere (IT/EN) per GamesTracker.

Ogni report produce:
- un ``summary`` testuale nella lingua richiesta che ricostruisce la
  strategia osservata (date demo/release, date/canali dei post, timeline,
  correlazione con la crescita) SEGUENDO le regole correlazione != causalita'
  del marketing-playbook §4.3;
- un dict ``data`` strutturato e json-serializzabile a supporto dei 5
  grafici indicati nel playbook §4.5.

Il report puo' essere salvato su ``analysis_reports`` (game_id o genre,
lang, summary, data, generated_at) tramite ``save_report``.

Le stringhe testuali stanno tutte in ``report_i18n.py`` (nessun testo
hardcoded in una sola lingua). Le funzioni che costruiscono i dati sono
pure dove possibile; l'accesso al DB e' isolato nelle ``*_from_db``.

Export: ``export_html`` produce un HTML autoconsistente. ``export_pdf`` e'
un hook opzionale: usa una lib PDF se presente, altrimenti ritorna None
senza rompere.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional, Sequence

from analysis.growth import (
    compute_growth_metrics,
    find_turning_points,
)
from analysis.report_i18n import t
from analysis import post_launch as post_launch_mod
from analysis import trends as trends_mod


def _iso(d: Any) -> Optional[str]:
    """Serializza date/datetime in ISO string; passa attraverso il resto."""
    if isinstance(d, (date, datetime)):
        return d.isoformat()
    return d


def _json_safe(obj: Any) -> Any:
    """Rende un oggetto ricorsivamente json-serializzabile.

    Converte date/datetime in stringhe ISO; lascia intatti i tipi base.
    Usato per garantire che ``data`` sia sempre serializzabile prima di
    salvarlo su ``analysis_reports.data`` (colonna JSON).
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def _fmt_date(d: Any, lang: str) -> str:
    """Formatta una data in modo compatto e leggibile."""
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    return t("not_available", lang)


def _engagement(post: dict[str, Any]) -> int:
    """Engagement cumulato di un post (like+commenti+views+share)."""
    return (
        (post.get("likes") or 0)
        + (post.get("comments") or 0)
        + (post.get("views") or 0)
        + (post.get("shares") or 0)
    )


# ==========================================================================
# REPORT PER-GIOCO
# ==========================================================================


def _to_date(d: Any) -> Optional[date]:
    """Normalizza a ``date`` (accetta date/datetime/ISO string)."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        try:
            return datetime.fromisoformat(d.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _prelaunch_analysis(
    game: dict[str, Any],
    posts: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Distingue 'hype pre-esistente' da 'crescita da lancio' (FUNZIONE PURA).

    Confronta l'attivita' social datata PRIMA della release con quella DOPO,
    e raccoglie segnali di maturita' pre-lancio (early access, gap demo-release
    lungo, scoperta molto anteriore alla release, molti video pre-release).

    Ritorna un dict con ``n_pre``, ``n_post``, ``preexisting_hype`` (bool),
    ``signals`` (lista di chiavi i18n) e ``verdict`` in
    {"preexisting", "launch_driven", "insufficient"}. Tutto proxy pubblici,
    mai wishlist/vendite (non pubbliche); co-occorrenza, non causalita'.
    """
    release = _to_date(game.get("release_date"))
    n_pre = n_post = 0
    if release is not None:
        for p in posts:
            pd = _to_date(p.get("posted_at"))
            if pd is None:
                continue
            if pd < release:
                n_pre += 1
            else:
                n_post += 1

    # Segnali di maturita' pre-lancio (indipendenti dai post).
    signals: list[str] = []
    tags_genres = [
        str(x).lower() for x in
        (list(game.get("genres") or []) + list(game.get("tags") or []))
    ]
    if any("early access" in x for x in tags_genres):
        signals.append("prelaunch_signal_early_access")

    demo = _to_date(game.get("demo_release_date"))
    if demo and release and (release - demo).days >= 30:
        signals.append("prelaunch_signal_long_demo_gap")

    first_seen = _to_date(game.get("first_seen_at"))
    if first_seen and release and (release - first_seen).days >= 30:
        signals.append("prelaunch_signal_early_discovery")

    if n_pre >= 3 and n_pre >= n_post:
        signals.append("prelaunch_signal_pre_videos")

    # Verdetto: hype pre-esistente se ci sono segnali forti o molta attivita'
    # pre-release rispetto alla post-release.
    if release is None or (n_pre + n_post == 0 and not signals):
        verdict = "insufficient"
        preexisting = False
    elif signals and (n_pre >= n_post or (n_pre + n_post) == 0):
        verdict = "preexisting"
        preexisting = True
    elif n_post > n_pre:
        verdict = "launch_driven"
        preexisting = False
    else:
        # attivita' bilanciata ma con qualche segnale: prudenza -> pre-esistente
        verdict = "preexisting" if signals else "launch_driven"
        preexisting = bool(signals)

    return {
        "n_pre": n_pre,
        "n_post": n_post,
        "preexisting_hype": preexisting,
        "signals": signals,
        "verdict": verdict,
    }


def build_game_report(
    game: dict[str, Any],
    snapshots: Sequence[dict[str, Any]],
    posts: Sequence[dict[str, Any]],
    lang: str = "it",
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Costruisce summary + data per un report per-gioco (FUNZIONE PURA).

    Parametri
    ---------
    game:
        Dati anagrafici: ``title, developer, genres, tags, release_date,
        demo_release_date, quality_score, discarded``.
    snapshots:
        Lista di dict con ``captured_at, total_reviews, current_players``.
    posts:
        Lista di dict con ``platform, subreddit, posted_at, title, likes,
        comments, views, shares``.
    lang:
        ``"it"`` o ``"en"``.

    Ritorna ``{"summary": str, "data": dict}`` con ``data`` json-serializzabile.
    """
    lang = lang if lang in ("it", "en") else "it"
    lines: list[str] = []

    # --- Overview ---
    lines.append(t("game_report_title", lang, title=game.get("title", "?")))
    lines.append("")
    lines.append("## " + t("section_overview", lang))
    if game.get("developer"):
        lines.append(t("overview_developer", lang, developer=game["developer"]))
    genres = ", ".join((game.get("genres") or []) + (game.get("tags") or [])) \
        or t("not_available", lang)
    lines.append(t("overview_genres", lang, genres=genres))
    if game.get("quality_score") is not None:
        suffix = t("discarded_suffix", lang) if game.get("discarded") else ""
        lines.append(
            t("overview_quality", lang,
              score=round(game["quality_score"], 1), discarded=suffix)
        )
    else:
        lines.append(t("no_quality", lang))

    # --- Timeline ---
    timeline = _build_timeline(game, snapshots, posts, lang)
    lines.append("")
    lines.append("## " + t("section_timeline", lang))
    if timeline["events"]:
        for ev in timeline["events"]:
            lines.append("- " + ev["text"])
    else:
        lines.append(t("no_events", lang))

    # --- Top post per engagement ---
    top_posts = timeline["top_posts"]
    if top_posts:
        lines.append("")
        lines.append(t("top_posts_header", lang))
        for p in top_posts:
            sub = f" (r/{p['subreddit']})" if p.get("subreddit") else ""
            lines.append(
                "- " + t("event_post", lang,
                         date=_fmt_date(p.get("posted_at"), lang),
                         platform=p.get("platform", "?"),
                         subreddit=sub,
                         title=(p.get("title") or "")[:80],
                         engagement=_engagement(p))
            )

    # --- Crescita ---
    growth = compute_growth_metrics(list(snapshots), now=now)
    lines.append("")
    lines.append("## " + t("section_growth", lang))
    lines.extend(_growth_lines(snapshots, growth, lang))

    # --- Pre-lancio: hype pre-esistente vs crescita da lancio ---
    prelaunch = _prelaunch_analysis(game, posts)
    lines.append("")
    lines.append("## " + t("section_prelaunch", lang))
    if prelaunch["verdict"] == "insufficient":
        lines.append(t("prelaunch_insufficient", lang))
    else:
        signals_txt = ", ".join(
            t(s, lang) for s in prelaunch["signals"]
        ) or t("not_available", lang)
        key = ("prelaunch_preexisting" if prelaunch["verdict"] == "preexisting"
               else "prelaunch_launch_driven")
        lines.append(
            t(key, lang, n_pre=prelaunch["n_pre"],
              n_post=prelaunch["n_post"], signals=signals_txt)
        )

    # --- Social ---
    lines.append("")
    lines.append("## " + t("section_social", lang))
    if posts:
        n_platforms = len({p.get("platform") for p in posts})
        lines.append(
            t("social_summary", lang, n_posts=len(posts), n_platforms=n_platforms)
        )
    else:
        lines.append(t("social_none", lang))

    # --- Autopsia post-lancio (complemento della sezione pre-lancio) ---
    post_launch = post_launch_mod.analyze_post_launch(game, snapshots, posts)
    lines.append("")
    lines.append("## " + t("section_post_launch", lang))
    lines.extend(_post_launch_lines(post_launch, lang))

    # --- Limiti / disclaimer (SEMPRE) ---
    lines.append("")
    lines.append("## " + t("section_limits", lang))
    lines.append(t("corr_disclaimer", lang))
    lines.append(t("proxy_disclaimer", lang))
    lines.append(t("single_sample_disclaimer", lang))

    summary = "\n".join(lines)
    data = _json_safe(
        _build_game_data_payload(game, snapshots, posts, growth, timeline, prelaunch)
    )
    data["post_launch"] = post_launch
    return {"summary": summary, "data": data}


def _build_timeline(
    game: dict[str, Any],
    snapshots: Sequence[dict[str, Any]],
    posts: Sequence[dict[str, Any]],
    lang: str,
) -> dict[str, Any]:
    """Merge cronologico di demo/release/post + punti di svolta crescita."""
    events: list[dict[str, Any]] = []

    demo = game.get("demo_release_date")
    release = game.get("release_date")
    if demo:
        events.append({"date": _iso(demo),
                       "text": t("event_demo", lang, date=_fmt_date(demo, lang)),
                       "kind": "demo"})
    if release:
        events.append({"date": _iso(release),
                       "text": t("event_release", lang, date=_fmt_date(release, lang)),
                       "kind": "release"})
    if demo and release and isinstance(demo, date) and isinstance(release, date):
        days = (release - demo).days
        if days >= 7:
            events.append({"date": _iso(demo),
                           "text": t("event_demo_to_release", lang, days=days),
                           "kind": "note"})
        elif 0 <= days < 2:
            events.append({"date": _iso(demo),
                           "text": t("event_demo_same_day", lang),
                           "kind": "note"})

    # Post: ordina per data.
    sorted_posts = sorted(
        [p for p in posts if p.get("posted_at")],
        key=lambda p: p["posted_at"],
    )
    for p in sorted_posts:
        sub = f" (r/{p['subreddit']})" if p.get("subreddit") else ""
        events.append({
            "date": _iso(p.get("posted_at")),
            "text": t("event_post", lang,
                      date=_fmt_date(p.get("posted_at"), lang),
                      platform=p.get("platform", "?"),
                      subreddit=sub,
                      title=(p.get("title") or "")[:80],
                      engagement=_engagement(p)),
            "kind": "post",
        })

    # Punti di svolta della crescita (recensioni).
    turns = find_turning_points(list(snapshots), metric="total_reviews")
    for tp in turns:
        events.append({
            "date": _iso(tp["at"]),
            "text": t("event_turning_point", lang,
                      date=_fmt_date(tp["at"], lang), metric="total_reviews"),
            "kind": "turning_point",
        })

    # Ordina tutti gli eventi per data (string ISO ordina cronologicamente).
    events.sort(key=lambda e: e["date"] or "")

    # Top 3 post per engagement.
    top_posts = sorted(posts, key=_engagement, reverse=True)[:3]
    top_posts = [p for p in top_posts if _engagement(p) > 0]

    return {"events": events, "top_posts": top_posts, "turning_points": turns}


def _growth_lines(
    snapshots: Sequence[dict[str, Any]],
    growth: dict[str, Any],
    lang: str,
) -> list[str]:
    """Righe testuali che descrivono la crescita osservata."""
    lines: list[str] = []
    reviews = [s for s in snapshots if s.get("total_reviews") is not None]
    players = [s for s in snapshots if s.get("current_players") is not None]

    if len(reviews) >= 2:
        ordered = sorted(reviews, key=lambda s: s["captured_at"])
        v0 = float(ordered[0]["total_reviews"])
        v1 = float(ordered[-1]["total_reviews"])
        lines.append(t("growth_reviews", lang, delta=v1 - v0, v0=v0, v1=v1))
        # Dettaglio per finestra (solo quelle calcolabili).
        for name, w in (growth.get("reviews_windows") or {}).items():
            if w and w.get("rate") is not None:
                lines.append(t("growth_window", lang, window=name, rate=w["rate"]))
    if players:
        peak = max(float(s["current_players"]) for s in players)
        lines.append(t("growth_players", lang, peak=peak))
    if not lines:
        lines.append(t("growth_none", lang))
    return lines


_LEVER_LABEL_KEYS = {
    "discount": "lever_discount",
    "ea_exit": "lever_ea_exit",
    "festival": "lever_festival",
    "social_surge": "lever_social_surge",
}


def _post_launch_lines(post_launch: dict[str, Any], lang: str) -> list[str]:
    """Righe testuali per la sezione 'Autopsia post-lancio' (co-occorrenza)."""
    lines: list[str] = []

    if post_launch.get("status") != "ok":
        lines.append(
            t("post_launch_insufficient", lang,
              needed=post_launch_mod.MIN_SNAPSHOTS,
              n=post_launch.get("n_snapshots", 0))
        )
        return lines

    # Picco.
    peak = post_launch.get("peak") or {}
    if peak.get("at") is not None:
        lines.append(
            t("post_launch_peak", lang,
              metric=post_launch.get("metric", "total_reviews"),
              date=_fmt_date(_to_date(peak.get("at")), lang),
              value=float(peak.get("value") or 0.0))
        )

    # Half-life.
    half = post_launch.get("half_life") or {}
    if half.get("half_life_days") is not None:
        lines.append(
            t("post_launch_half_life", lang,
              half_life=float(half["half_life_days"]), n=half.get("n", 0))
        )
    elif half.get("reason") == "no_decay":
        lines.append(t("post_launch_no_decay", lang, n=half.get("n", 0)))
    else:
        lines.append(
            t("post_launch_half_life_none", lang,
              reason=str(half.get("reason") or "n/d"), n=half.get("n", 0))
        )

    # Seconde vite + co-occorrenze.
    winds = post_launch.get("second_winds") or []
    if winds:
        lines.append(t("post_launch_second_winds_header", lang))
        for w in winds:
            evs = w.get("events") or []
            if evs:
                labels = ", ".join(
                    t(_LEVER_LABEL_KEYS.get(e.get("type"), e.get("type", "?")), lang)
                    for e in evs
                )
            else:
                labels = t("post_launch_no_events", lang)
            lines.append(
                t("post_launch_second_wind", lang,
                  date=_fmt_date(_to_date(w.get("at")), lang), events=labels)
            )
        lines.append(t("post_launch_cooccurrence_note", lang))
    else:
        lines.append(t("post_launch_no_second_winds", lang))

    return lines


def _build_game_data_payload(
    game: dict[str, Any],
    snapshots: Sequence[dict[str, Any]],
    posts: Sequence[dict[str, Any]],
    growth: dict[str, Any],
    timeline: dict[str, Any],
    prelaunch: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Dati strutturati per i 5 grafici del playbook §4.5 (json-serializzabile).

    1. Serie temporale recensioni con marker.
    2. Serie temporale player count con marker.
    3. Timeline/densita' post per piattaforma.
    4. Barre di engagement dei top post.
    5. Overlay follower vs recensioni (dati grezzi disponibili).
    """
    ordered = sorted(
        [s for s in snapshots if s.get("captured_at") is not None],
        key=lambda s: s["captured_at"],
    )
    reviews_series = [
        {"t": _iso(s["captured_at"]), "value": s.get("total_reviews")}
        for s in ordered
    ]
    players_series = [
        {"t": _iso(s["captured_at"]), "value": s.get("current_players")}
        for s in ordered
    ]

    # Marker verticali comuni ai grafici 1 e 2.
    markers: list[dict[str, Any]] = []
    if game.get("demo_release_date"):
        markers.append({"t": _iso(game["demo_release_date"]), "kind": "demo"})
    if game.get("release_date"):
        markers.append({"t": _iso(game["release_date"]), "kind": "release"})
    for tp in timeline.get("turning_points", []):
        markers.append({"t": _iso(tp["at"]), "kind": "turning_point"})

    # Grafico 3: post per piattaforma (data + engagement).
    posts_by_platform: dict[str, list[dict[str, Any]]] = {}
    for p in posts:
        plat = str(p.get("platform", "unknown"))
        posts_by_platform.setdefault(plat, []).append(
            {
                "t": _iso(p.get("posted_at")),
                "engagement": _engagement(p),
                "title": p.get("title"),
                "subreddit": p.get("subreddit"),
            }
        )

    # Grafico 4: barre engagement top post.
    top_posts_bars = [
        {
            "label": (p.get("title") or p.get("platform") or "?")[:40],
            "platform": p.get("platform"),
            "engagement": _engagement(p),
            "t": _iso(p.get("posted_at")),
        }
        for p in timeline.get("top_posts", [])
    ]

    return {
        "kind": "game",
        "game": {
            "title": game.get("title"),
            "developer": game.get("developer"),
            "genres": game.get("genres") or [],
            "tags": game.get("tags") or [],
            "quality_score": game.get("quality_score"),
            "discarded": game.get("discarded"),
            "release_date": _iso(game.get("release_date")),
            "demo_release_date": _iso(game.get("demo_release_date")),
        },
        "charts": {
            "reviews_timeseries": {"series": reviews_series, "markers": markers},
            "players_timeseries": {"series": players_series, "markers": markers},
            "posts_by_platform": posts_by_platform,
            "top_posts_engagement": top_posts_bars,
            "growth_windows": growth,
        },
        "prelaunch": prelaunch or {},
        "events": timeline.get("events", []),
    }


# ==========================================================================
# REPORT PER-GENERE
# ==========================================================================


def build_genre_report(
    genre: str,
    genre_row: Optional[dict[str, Any]],
    timing_row: Optional[dict[str, Any]],
    n_games: int,
    lang: str = "it",
    small_sample_threshold: int = 5,
) -> dict[str, Any]:
    """Costruisce summary + data per un report per-genere (FUNZIONE PURA).

    ``genre_row`` proviene da ``trends.growth_by_genre`` (una riga),
    ``timing_row`` da ``trends.timing_by_genre``. Ritorna
    ``{"summary": str, "data": dict}``.
    """
    lang = lang if lang in ("it", "en") else "it"
    na = t("not_available", lang)
    lines: list[str] = []

    lines.append(t("genre_report_title", lang, genre=genre))
    lines.append("")
    lines.append(t("genre_sample", lang, n=n_games, genre=genre))

    gr = genre_row or {}
    lines.append(
        t("genre_avg_growth", lang,
          reviews=_pct(gr.get("avg_reviews_growth"), na),
          players=_pct(gr.get("avg_players_growth"), na),
          score=_num(gr.get("avg_quality_score"), na))
    )

    tr = timing_row or {}
    lines.append(
        t("genre_timing", lang,
          d2r=_num(tr.get("median_demo_to_release"), na),
          r2p=_num(tr.get("median_release_to_peak"), na))
    )

    if n_games < small_sample_threshold:
        lines.append("")
        lines.append(t("genre_small_sample", lang, n=n_games))

    # Disclaimer sempre presenti.
    lines.append("")
    lines.append("## " + t("section_limits", lang))
    lines.append(t("corr_disclaimer", lang))
    lines.append(t("proxy_disclaimer", lang))

    summary = "\n".join(lines)
    data = _json_safe({
        "kind": "genre",
        "genre": genre,
        "n_games": n_games,
        "growth": gr,
        "timing": tr,
    })
    return {"summary": summary, "data": data}


def _pct(value: Optional[float], na: str) -> str:
    """Formatta una frazione come percentuale, o n/d."""
    if value is None:
        return na
    return f"{value:+.1%}"


def _num(value: Optional[float], na: str) -> str:
    """Formatta un numero con 1 decimale, o n/d."""
    if value is None:
        return na
    return f"{value:.1f}"


# ==========================================================================
# ACCESSO AL DB
# ==========================================================================


def generate_game_report(session, game_id: int, lang: str = "it",
                         persist: bool = True) -> dict[str, Any]:
    """Carica un gioco dal DB, genera il report e (opz.) lo salva.

    Ritorna ``{"summary", "data"}``. Se ``persist``, salva anche su
    ``analysis_reports`` e ritorna ``report_id`` nel dict.
    """
    from sqlalchemy import select

    from core.models import Game, GameSnapshot, SocialPost

    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game id={game_id} non trovato")

    snaps = list(
        session.scalars(
            select(GameSnapshot)
            .where(GameSnapshot.game_id == game_id)
            .order_by(GameSnapshot.captured_at)
        )
    )
    posts = list(
        session.scalars(
            select(SocialPost).where(SocialPost.game_id == game_id)
        )
    )

    game_dict = {
        "title": game.title,
        "developer": game.developer,
        "publisher": game.publisher,
        "genres": game.genres or [],
        "tags": game.tags or [],
        "release_date": game.release_date,
        "demo_release_date": game.demo_release_date,
        "first_seen_at": game.first_seen_at,
        "quality_score": game.quality_score,
        "discarded": game.discarded,
    }
    snap_dicts = [
        {
            "captured_at": s.captured_at,
            "total_reviews": s.total_reviews,
            "current_players": s.current_players,
            "price": s.price,
            "extra": s.extra,
        }
        for s in snaps
    ]
    post_dicts = [
        {
            "platform": p.platform.value if hasattr(p.platform, "value") else p.platform,
            "subreddit": p.subreddit,
            "posted_at": p.posted_at,
            "title": p.title,
            "likes": p.likes,
            "comments": p.comments,
            "views": p.views,
            "shares": p.shares,
        }
        for p in posts
    ]

    report = build_game_report(game_dict, snap_dicts, post_dicts, lang=lang)
    if persist:
        report_id = save_report(session, report, lang=lang, game_id=game_id)
        report["report_id"] = report_id
    return report


def generate_genre_report(session, genre: str, lang: str = "it",
                          persist: bool = True) -> dict[str, Any]:
    """Genera un report aggregato per genere leggendo dal DB."""
    records = trends_mod.collect_trend_input(session)
    df = trends_mod.build_games_frame(records)

    genre_rows = {r["genre"]: r for r in trends_mod.growth_by_genre(df)}
    timing_rows = {r["genre"]: r for r in trends_mod.timing_by_genre(df)}

    n_games = int(genre_rows.get(genre, {}).get("n_games", 0)) or \
        int(timing_rows.get(genre, {}).get("n_games", 0))

    report = build_genre_report(
        genre, genre_rows.get(genre), timing_rows.get(genre), n_games, lang=lang
    )
    if persist:
        report_id = save_report(session, report, lang=lang, genre=genre)
        report["report_id"] = report_id
    return report


def save_report(session, report: dict[str, Any], lang: str,
                game_id: Optional[int] = None,
                genre: Optional[str] = None) -> int:
    """Salva un report su ``analysis_reports`` e ritorna l'id.

    ``report`` e' il dict ``{"summary", "data"}`` prodotto dai builder.
    """
    from core.models import AnalysisReport, Lang

    row = AnalysisReport(
        game_id=game_id,
        genre=genre,
        lang=Lang(lang) if not isinstance(lang, Lang) else lang,
        summary=report.get("summary"),
        data=report.get("data"),
        generated_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return row.id


# ==========================================================================
# EXPORT (HTML sempre; PDF hook opzionale)
# ==========================================================================


def export_html(report: dict[str, Any], title: Optional[str] = None) -> str:
    """Genera un HTML autoconsistente dal report.

    Il ``summary`` (markdown-lite) viene reso in paragrafi/heading semplici;
    i dati grezzi sono inclusi in un blocco ``<pre>`` per riferimento.
    """
    import html
    import json

    summary = report.get("summary", "") or ""
    doc_title = title or summary.splitlines()[0] if summary else "Report"

    body_parts: list[str] = []
    for raw in summary.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("## "):
            body_parts.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            body_parts.append(f"<li>{html.escape(line[2:])}</li>")
        else:
            body_parts.append(f"<p>{html.escape(line)}</p>")

    data_json = html.escape(json.dumps(report.get("data", {}), indent=2,
                                       ensure_ascii=False, default=str))

    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        f"<title>{html.escape(doc_title)}</title>"
        "<style>body{font-family:sans-serif;max-width:820px;margin:2em auto;"
        "line-height:1.5;padding:0 1em}h2{border-bottom:1px solid #ccc;"
        "padding-bottom:.2em;margin-top:1.5em}pre{background:#f5f5f5;"
        "padding:1em;overflow:auto;font-size:.85em}</style></head><body>"
        + "\n".join(body_parts)
        + "<h2>data</h2><pre>" + data_json + "</pre>"
        + "</body></html>"
    )


def export_pdf(report: dict[str, Any], out_path: str,
               title: Optional[str] = None) -> Optional[str]:
    """Hook opzionale per l'export PDF.

    Prova ad usare una libreria PDF se disponibile (senza dipendenze
    pesanti obbligatorie). Se nessuna e' installata, ritorna ``None`` senza
    sollevare: la GUI puo' ripiegare sull'HTML.

    Ritorna il path del PDF generato oppure ``None``.
    """
    html_str = export_html(report, title=title)
    # Tentativo 1: weasyprint (se presente nell'ambiente).
    try:
        from weasyprint import HTML  # type: ignore

        HTML(string=html_str).write_pdf(out_path)
        return out_path
    except Exception:
        pass
    # Nessuna lib PDF disponibile: hook lasciato aperto.
    return None
