"""Client itch.io — discovery via RSS + dettaglio gioco via OpenGraph/JSON-LD.

Discovery (metodo ufficiale e "gentile"): itch.io permette di appendere
``.xml`` a qualsiasi URL di browse per ottenere un feed RSS. Es.:
- ``https://itch.io/games/new-and-popular.xml``
- ``https://itch.io/games/tag-<tag>.xml``

Parsing feed con ``feedparser``. Il feed da' titolo, url, autore, thumbnail.

Dettaglio gioco: le pagine ``<autore>.itch.io/<gioco>`` espongono metadati
in OpenGraph e JSON-LD nel ``<head>`` (parsabili con BeautifulSoup):
titolo, immagine, descrizione, a volte prezzo. Tag/genere, presenza demo
e link social dell'autore si ricavano dal parsing dell'HTML.

robots.txt (verificato 2026-07-21): ``/games`` e i feed ``.xml`` NON sono
disallow; le pagine gioco sono su sottodomini autore, non bloccate. Blocchi
solo su ``/embed``, ``/search``, ``/checkout``, ``/game/download``, ecc.
Rispettiamo comunque rate limit gentile (1 req ogni ~2.5s) e User-Agent
identificabile.

I client ritornano dataclass normalizzate; non scrivono sul DB.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

import feedparser
import httpx
from bs4 import BeautifulSoup

from core.sources._http import Throttle, request_text

logger = logging.getLogger(__name__)

NEW_AND_POPULAR_FEED = "https://itch.io/games/new-and-popular.xml"

# Rate limit gentile per itch.io.
_throttle = Throttle(min_interval=2.5)

# Domini social riconosciuti per estrarre i link dell'autore.
_SOCIAL_DOMAINS = {
    "youtube.com": "youtube", "youtu.be": "youtube",
    "reddit.com": "reddit",
    "tiktok.com": "tiktok",
    "instagram.com": "instagram",
    "twitter.com": "twitter", "x.com": "twitter",
    "discord.gg": "discord", "discord.com": "discord",
}


@dataclass
class ItchFeedItem:
    """Voce del feed RSS itch (discovery)."""

    title: str
    url: str  # url della pagina gioco (usato come external_id/slug)
    author: Optional[str] = None
    thumbnail: Optional[str] = None
    published: Optional[datetime] = None


@dataclass
class ItchGameData:
    """Dati normalizzati di un gioco itch (da OpenGraph/JSON-LD + HTML)."""

    url: str
    title: str = ""
    author: Optional[str] = None
    description: Optional[str] = None
    header_image: Optional[str] = None
    price: Optional[float] = None
    is_free: bool = False
    release_date: Optional[date] = None
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    has_demo: bool = False
    social_links: list[dict[str, str]] = field(default_factory=list)


def parse_feed(feed_content: str | bytes) -> list[ItchFeedItem]:
    """Parsa un feed RSS itch (contenuto ``.xml``) in ItchFeedItem.

    Testabile senza rete: si passa direttamente il contenuto del feed.
    """
    parsed = feedparser.parse(feed_content)
    items: list[ItchFeedItem] = []
    for entry in parsed.entries:
        url = entry.get("link") or ""
        if not url:
            continue
        # Autore: itch mette spesso l'autore in dc:creator / author.
        author = entry.get("author") or None
        # Thumbnail: media_thumbnail o media_content.
        thumb = None
        media = entry.get("media_thumbnail") or entry.get("media_content")
        if media and isinstance(media, list) and media:
            thumb = media[0].get("url")
        # Data di pubblicazione.
        published = None
        if entry.get("published_parsed"):
            try:
                published = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                published = None
        items.append(
            ItchFeedItem(
                title=entry.get("title") or "",
                url=url,
                author=author,
                thumbnail=thumb,
                published=published,
            )
        )
    return items


def fetch_new_and_popular(
    feed_url: str = NEW_AND_POPULAR_FEED,
    *,
    client: Optional[httpx.Client] = None,
) -> list[ItchFeedItem]:
    """Scarica e parsa il feed RSS delle nuove/popolari uscite itch.

    Non solleva: logga e ritorna lista vuota su errore.
    """
    try:
        content = request_text(feed_url, client=client, throttle=_throttle)
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("fetch_new_and_popular (%s) fallito: %s", feed_url, exc)
        return []
    items = parse_feed(content)
    logger.info("itch feed %s: %d voci", feed_url, len(items))
    return items


def _price_from_text(text: Optional[str]) -> tuple[Optional[float], bool]:
    """Estrae ``(price, is_free)`` da una stringa di prezzo itch.

    Es. "$5.00" -> (5.0, False); "Free"/"$0.00" -> (0.0, True);
    "Name your own price" -> (0.0, True). Ritorna ``(None, False)`` se
    non deducibile.
    """
    if not text:
        return None, False
    low = text.strip().lower()
    if "free" in low or "name your own price" in low or "pay what you want" in low:
        return 0.0, True
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)", low.replace(",", "."))
    if not m:
        return None, False
    try:
        value = float(m.group(1))
    except ValueError:
        return None, False
    return value, value == 0.0


def _extract_jsonld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Estrae tutti i blocchi JSON-LD (``<script type=ld+json>``)."""
    blocks: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if isinstance(data, list):
            blocks.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            blocks.append(data)
    return blocks


def _og(soup: BeautifulSoup, prop: str) -> Optional[str]:
    """Legge il contenuto di un meta OpenGraph (``property=og:...``)."""
    tag = soup.find("meta", property=prop)
    if tag and tag.get("content"):
        return tag["content"]
    return None


def _parse_itch_date(raw: Optional[str]) -> Optional[date]:
    """Parsa una data ISO (JSON-LD ``datePublished``) in ``date``."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        # Formato solo-data.
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def parse_game_page(html: str, url: str) -> ItchGameData:
    """Parsa la pagina di un gioco itch (OpenGraph + JSON-LD + HTML).

    Funzione pura, testabile senza rete. Estrae titolo, autore, immagine,
    descrizione, prezzo, tag/genere, presenza demo, link social autore.
    Campi non trovati restano ai default.
    """
    soup = BeautifulSoup(html, "html.parser")
    data = ItchGameData(url=url)

    # --- OpenGraph (base affidabile) ---
    data.title = _og(soup, "og:title") or ""
    data.description = _og(soup, "og:description")
    data.header_image = _og(soup, "og:image")

    # --- JSON-LD (arricchimento: autore, prezzo, data) ---
    for block in _extract_jsonld(soup):
        if not data.title and block.get("name"):
            data.title = block["name"]
        author = block.get("author")
        if isinstance(author, dict) and author.get("name"):
            data.author = author["name"]
        elif isinstance(author, str):
            data.author = author
        offers = block.get("offers")
        if isinstance(offers, dict):
            price_val = offers.get("price")
            if price_val is not None:
                try:
                    data.price = float(price_val)
                    data.is_free = data.price == 0.0
                except (ValueError, TypeError):
                    pass
        if block.get("datePublished"):
            data.release_date = _parse_itch_date(block["datePublished"])

    # --- Tabella metadati itch (genere, tag, data pubblicazione) ---
    for row in soup.select("table tr, .game_info_panel_widget tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        label = cells[0].get_text(strip=True).lower()
        value_cell = cells[1]
        values = [a.get_text(strip=True) for a in value_cell.find_all("a")]
        if not values:
            values = [value_cell.get_text(strip=True)]
        if "genre" in label:
            data.genres = [v for v in values if v]
        elif "tags" in label:
            data.tags = [v for v in values if v]
        elif "release date" in label or "published" in label:
            if data.release_date is None and values:
                data.release_date = _parse_itch_date(values[0])

    # --- Prezzo dal buy-box se non trovato in JSON-LD ---
    if data.price is None:
        buy_row = soup.select_one(".buy_row .buy_btn, .price_value, .buy_btn")
        if buy_row:
            price, is_free = _price_from_text(buy_row.get_text(strip=True))
            if price is not None:
                data.price = price
                data.is_free = is_free

    # --- Presenza demo: euristica su testo/link ---
    page_text = html.lower()
    if "demo" in page_text and re.search(r"\bdemo\b", page_text):
        # Cerchiamo indizi forti (bottone/etichetta "Demo"), non la parola sparsa.
        if soup.find(string=re.compile(r"\bdemo\b", re.IGNORECASE)) and (
            soup.select_one(".demo_button, .demo") is not None
            or "download demo" in page_text
            or ">demo<" in page_text
        ):
            data.has_demo = True

    # --- Link social dell'autore ---
    seen_platforms: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        for domain, platform in _SOCIAL_DOMAINS.items():
            if domain in href and (platform, href) not in seen_platforms:
                seen_platforms.add((platform, href))  # type: ignore[arg-type]
                data.social_links.append({"platform": platform, "url": href})
                break

    return data


def fetch_game_page(
    url: str,
    *,
    client: Optional[httpx.Client] = None,
) -> Optional[ItchGameData]:
    """Scarica e parsa la pagina di un gioco itch.

    Non solleva: logga e ritorna ``None`` su errore.
    """
    try:
        html = request_text(url, client=client, throttle=_throttle)
    except Exception as exc:  # noqa: BLE001 - degradare, non crashare
        logger.warning("fetch_game_page (%s) fallito: %s", url, exc)
        return None
    return parse_game_page(html, url)
