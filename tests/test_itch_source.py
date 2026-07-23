"""Test del client itch.io (parsing RSS + pagina gioco, nessuna rete)."""

from __future__ import annotations

from datetime import date

from core.sources.itch import parse_feed, parse_game_page, _price_from_text


SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"
     xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>New and Popular</title>
    <item>
      <title>Cool Indie Game</title>
      <link>https://dev1.itch.io/cool-indie-game</link>
      <dc:creator>Dev One</dc:creator>
      <pubDate>Mon, 20 Jul 2026 10:00:00 GMT</pubDate>
      <media:thumbnail url="https://img.itch.zone/thumb.png"/>
    </item>
    <item>
      <title>Another Game</title>
      <link>https://dev2.itch.io/another-game</link>
      <dc:creator>Dev Two</dc:creator>
      <pubDate>Sun, 19 Jul 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_parse_feed():
    items = parse_feed(SAMPLE_FEED)
    assert len(items) == 2
    first = items[0]
    assert first.title == "Cool Indie Game"
    assert first.url == "https://dev1.itch.io/cool-indie-game"
    assert first.author == "Dev One"
    assert first.thumbnail == "https://img.itch.zone/thumb.png"
    assert first.published is not None
    assert first.published.year == 2026


SAMPLE_GAME_PAGE = """<!DOCTYPE html>
<html><head>
  <meta property="og:title" content="Cool Indie Game" />
  <meta property="og:description" content="A cool game" />
  <meta property="og:image" content="https://img.itch.zone/header.png" />
  <script type="application/ld+json">
  {
    "@type": "VideoGame",
    "name": "Cool Indie Game",
    "author": {"@type": "Person", "name": "Dev One"},
    "datePublished": "2026-07-20",
    "offers": {"@type": "Offer", "price": "5.00", "priceCurrency": "USD"}
  }
  </script>
</head><body>
  <div class="game_info_panel_widget">
    <table>
      <tr><td>Genre</td><td><a>Platformer</a><a>Adventure</a></td></tr>
      <tr><td>Tags</td><td><a>pixel-art</a><a>retro</a></td></tr>
      <tr><td>Release date</td><td>2026-07-20</td></tr>
    </table>
  </div>
  <div class="buy_row"><div class="buy_btn">$5.00</div></div>
  <a href="https://twitter.com/dev1">Twitter</a>
  <a href="https://youtube.com/@dev1">YouTube</a>
  <div class="demo_button">Download Demo</div>
</body></html>
"""


def test_parse_game_page():
    data = parse_game_page(SAMPLE_GAME_PAGE, "https://dev1.itch.io/cool-indie-game")
    assert data.title == "Cool Indie Game"
    assert data.author == "Dev One"
    assert data.header_image == "https://img.itch.zone/header.png"
    assert data.price == 5.0
    assert data.is_free is False
    assert data.release_date == date(2026, 7, 20)
    assert data.genres == ["Platformer", "Adventure"]
    assert data.tags == ["pixel-art", "retro"]
    assert data.has_demo is True
    platforms = {link["platform"] for link in data.social_links}
    assert "twitter" in platforms
    assert "youtube" in platforms


def test_price_from_text():
    assert _price_from_text("$5.00") == (5.0, False)
    assert _price_from_text("Free") == (0.0, True)
    assert _price_from_text("Name your own price") == (0.0, True)
    assert _price_from_text("$0.00") == (0.0, True)
    assert _price_from_text(None) == (None, False)
