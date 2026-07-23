# Soluzioni esistenti — librerie, progetti GitHub, codice locale riusabile

> Creato dal `research-scout` il 2026-07-21. Obiettivo: NON reinventare la ruota.
> Legenda manutenzione: 🟢 attivo (release/commit recenti) · 🟡 datato ma usabile · 🔴 fermo/rischioso.
> Preferenza: licenze permissive (MIT/Apache/BSD) e progetti mantenuti.

---

## (a) Librerie / progetti GitHub raccomandati

### Steam — store, reviews, SteamSpy

| Nome | URL | Licenza | Manutenzione | Cosa risolve | Come usarlo |
|---|---|---|---|---|---|
| **steamreviews** | https://github.com/woctezuma/download-steam-reviews | MIT | 🟢 v0.9.6.1, feb 2026 (Py 3.11+) | Scarica review via endpoint `appreviews`, gestisce cursor/paginazione/rate limit (~10 review/s), espone `query_summary` (total_positive/negative). | **Dipendenza** (`pip install steamreviews`). Perfetta per il review tracking. Attenzione: richiede Py 3.11+, noi siamo su 3.10.11 → verificare compatibilità o incapsulare la sola logica appreviews. |
| **steamspypi** | https://github.com/woctezuma/steamspypi | MIT | 🟡 v1.1.1, 2021 | Wrapper SteamSpy: `appdetails`, `all` (paginato), `top100*`. Rispetta i rate limit (1 `all`/min). | **Dipendenza** (`pip install steamspypi`). Piccola e stabile; l'API SteamSpy cambia raramente. |
| **ValvePython/steam** | https://github.com/valvepython/steam | MIT | 🟡 ultimo commit mag 2023 | Pacchetto ampio per Steam (WebAPI, CM, auth). Grande e con molte feature che NON ci servono. | **Solo studiare** il modulo `WebAPI` come riferimento. Troppo pesante come dipendenza per il nostro uso (ci basta httpx + endpoint noti). |
| **steam.py (Gobot1234)** | https://github.com/Gobot1234/steam.py | MIT | 🟢 attivo | Wrapper async stile discord.py, orientato a bot/client (login, trading, chat). | **Non usare**: fuori scope (è per client/bot utente, non per data collection di store/reviews). |

> Nota chiave: per **appdetails** dello Store e per **GetNumberOfCurrentPlayers** NON serve una libreria: sono singole GET con parametri noti (vedi `data-sources.md`). Meglio un piccolo client `httpx` nostro con retry/backoff che una dipendenza pesante. Le librerie sopra convengono solo per reviews (steamreviews) e SteamSpy (steamspypi).

### Progetti Steam da studiare (pattern, non dipendenze)

| Nome | URL | Licenza | Manutenzione | Perché studiarlo |
|---|---|---|---|---|
| **FronkonGames/Steam-Games-Scraper** | https://github.com/FronkonGames/Steam-Games-Scraper | (verificare) | 🟢 | Estrae tutti i giochi via Web API + arricchisce con SteamSpy, salva JSON. Ottimo pattern di discovery + dedup + gestione rate limit su larga scala. |
| **altskop/steam-scraper** | https://github.com/altskop/steam-scraper | (verificare) | 🟡 | Scraper configurabile che salva in **SQLite** — pattern vicino al nostro (DB locale, raccolta automatica). |
| **coder202/trendx-steam** | https://github.com/coder202/trendx-steam | (verificare) | 🟡 | "Tag & Release Momentum": traccia momentum di tag/review nel tempo con snapshot e diff CSV. Concettualmente vicinissimo al nostro tracking di crescita. |
| **hhm970/c10-games-tracker-project** | https://github.com/hhm970/c10-games-tracker-project | (verificare) | 🟡 | Pipeline che traccia nuove uscite su più piattaforme + dashboard con metriche/grafici. Pattern architetturale simile al nostro. |

### itch.io

| Nome | URL | Licenza | Manutenzione | Cosa risolve | Come usarlo |
|---|---|---|---|---|---|
| **itchio-lib (Tch1b0)** | https://github.com/Tch1b0/itchio-lib | MIT | 🟡 v1.1.3, apr 2024 | Wrapper della server-side API (Session/GameCollection/UserCollection). | **Non adatto** alla discovery: copre solo dati del PROPRIO account via API key. Non naviga il catalogo pubblico. |
| **DragoonAethis/itch-dl** | https://github.com/DragoonAethis/itch-dl | GPL-ish (verificare) | 🟢 | Downloader itch con supporto a game jam/collection/library; contiene logica di parsing pagine itch. | **Solo studiare** i selettori/parsing HTML delle pagine itch. Attenzione licenza (probabile GPL → non incorporare codice). |

> **Raccomandazione itch.io**: non esiste una libreria pronta per la discovery pubblica. Approccio migliore = **feed RSS ufficiali** (`.xml` su qualsiasi URL di browse) con `feedparser` + parsing OpenGraph/JSON-LD delle pagine gioco con `BeautifulSoup`. Vedi `data-sources.md`.

### Social — YouTube, Reddit

| Nome | URL | Licenza | Manutenzione | Cosa risolve | Come usarlo |
|---|---|---|---|---|---|
| **google-api-python-client** | https://github.com/googleapis/google-api-python-client | Apache-2.0 | 🟢 | Client ufficiale Google per YouTube Data API v3 (`search.list`, `videos.list`). | **Dipendenza** (già previsto nell'architettura). Standard. |
| **PRAW** | https://github.com/praw-dev/praw | BSD-2 | 🟢 | Wrapper ufficioso ma de-facto standard per Reddit API; gestisce OAuth e rate limit (100 QPM). | **Dipendenza** (già previsto). |

### Social — TikTok / Instagram (fragili, vedi sezione (b))

| Nome | URL | Licenza | Manutenzione | Note |
|---|---|---|---|---|
| **TikTok-Api (davidteather)** | https://github.com/davidteather/TikTok-Api | MIT | 🟢 v7.3.3, apr 2026 | Solo dati pubblici (trending, hashtag, utenti, sound). Richiede Playwright + `ms_token`. Fragile, rischio blocco. |
| **instaloader** | https://github.com/instaloader/instaloader | MIT | 🟢 | Scarica post/metadati IG. Nel 2025/26 IG ha stretto molto: 401/429, login-wall, rischio ban account. |

### GUI PyQt6 + grafici (pattern/template)

| Nome | URL | Licenza | Manutenzione | Cosa offre |
|---|---|---|---|---|
| **pyqtgraph** | https://github.com/pyqtgraph/pyqtgraph | MIT | 🟢 (supporta PyQt6) | Grafici veloci; l'`examples browser` incluso (`python -m pyqtgraph.examples`) è una cookbook di pattern (plot real-time, ROI, parameter tree). **Dipendenza + fonte di esempi.** |
| **ixjlyons/embed-pyqtgraph-tutorial** | https://github.com/ixjlyons/embed-pyqtgraph-tutorial | MIT | 🟡 | Come incorporare plot pyqtgraph in una UI Qt Designer. Pattern utile per la dashboard. |
| **nthuepl/Realtime-Plot-Template** | https://github.com/nthuepl/Realtime-Plot-Template | (verificare) | 🟡 | Template plotting real-time PyQt + pyqtgraph. |
| **pyqt/examples** | https://github.com/pyqt/examples | (verificare) | 🟡 | Raccolta di esempi desktop PyQt (widget, layout). Buono per onboarding. |

---

## (b) TikTok / Instagram — opzioni e trade-off

Nessuna API ufficiale gratuita per raccogliere metriche di post pubblici altrui. Opzioni realistiche:

| Opzione | Fragilità | Costo | Legalità / ToS | Rischio ban | Verdetto |
|---|---|---|---|---|---|
| **TikTokApi (davidteather)** — scraping non ufficiale | Alta (dipende da `ms_token`, cambi anti-bot) | Gratis (+ Playwright) | Contro i ToS TikTok | Medio-alto (IP/token) | Best-effort, non su percorso critico. Isolare dietro interfaccia sostituibile. |
| **instaloader** — scraping IG | Molto alta (401/429, login-wall) | Gratis | Contro i ToS IG | **Alto** se si usa login di un account reale | Sconsigliato con account personale; anonimo è quasi inutilizzabile nel 2026. |
| **Servizi terzi a pagamento** (Apify, HasData, Bright Data, ecc.) | Bassa (gestiscono loro il blocco) | A pagamento (per chiamata/mese) | Zona grigia, ma rischio spostato sul fornitore | Basso lato nostro | Valida SE l'utente accetta il costo. Astrarre dietro la stessa interfaccia. |
| **Import manuale nella GUI** | Nulla | Gratis | Pienamente conforme | Nullo | **Raccomandato come base**: campo in GUI dove incollare link + metriche visibili, persistite come snapshot. |

Raccomandazione: partire da **import manuale** (affidabile e ToS-safe), predisporre un'interfaccia `SocialCollector` astratta così da poter innestare in futuro TikTokApi o un servizio a pagamento senza toccare il resto. Coerente con la decisione locked "meglio meno dati ma affidabili".

---

## (c) Codice locale riusabile (cartelle in `C:\Users\FRANCY\Desktop\Dev Things\`)

> Nulla è stato copiato. Solo inventario di cosa esiste e dove.

| Cartella / file | Linguaggio / librerie | Cosa contiene | Riuso per GamesTracker |
|---|---|---|---|
| `SteamAchievement\steam.py` | Python, `requests`, `ThreadPoolExecutor` | Chiamate a Steam Web API (`GetOwnedGames`, `GetBadges`) con pattern params + `key`. ⚠️ Contiene una **Steam Web API key hardcoded in chiaro** (`API_KEY`) e uno SteamID: da NON riusare così, spostare in `.env`. | Pattern di base per chiamate Steam Web API con `requests` + threading. Utile come riferimento minimale. |
| `Instagram Tools\Not Following Back\check-follow-back.py` | Python, **PyQt6** (`QMainWindow`, `QTableWidget`, `QFileDialog`, `QMessageBox`) | App desktop PyQt6 completa e pulita: selezione file, tabella risultati, load JSON. | **Molto utile**: template PyQt6 già funzionante (finestra + tabella + dialog) da cui partire per la GUI. È già lo stack target. |
| `YoutubeVisualBot\YoutubeBotVisual.py` | Python, `selenium`, `webdriver_manager`, `tkinter`, `threading` | Bot di visualizzazioni YouTube via Selenium + GUI Tkinter. | Poco utile (Tkinter, non PyQt; è un viewbot). Solo pattern threading GUI. |
| `TikTokBot\tiktodv4.py` | Python, `selenium`, `undetected_chromedriver`, `selenium_stealth`, `chromedriver_autoinstaller` | Automazione TikTok via Zefoy (viewbot/heartbot). | Utile solo come riferimento **anti-detection Selenium** (undetected_chromedriver + stealth) se un giorno servisse scraping browser. Non logica dati. |
| `IG Unfollower\ig.py` | Python, `selenium`, `WebDriverWait`, `webdriver_manager` + grosso blob JS iniettato | Automazione Instagram via Selenium: login manuale + esecuzione JS in console. | Riferimento per **login manuale semi-automatico IG** (attende login utente, poi opera). Fragile, ma pattern di auth interattiva. |
| `Subito-Bot\subito-searcher.py` | Python, `requests`, `bs4` (BeautifulSoup), `argparse`, notifiche Telegram/Windows | **Tracker/poller completo**: salva query su file JSON, modalità `--daemon` con loop e `delay`, dedup dei risultati, fasce orarie attive/pausa, notifiche. | **Molto utile come pattern architetturale**: è esattamente un collector che fa polling periodico, dedup e persistenza. Ottimo riferimento per la logica dello scheduler/discovery (concetti, non codice). |
| `Twitch\twitch.py` | Python, `selenium`, `re`, `pyperclip`, `winsound` | Legge chat Twitch via Selenium, estrae codici con regex. | Poco utile (Selenium su chat). Solo pattern regex/estrazione. |
| `Github\` (repo di terzi clonati) | vari (Moriarty, SpiderFoot, GhostTrack, phomber...) | Tool OSINT di terzi. SpiderFoot ha molti moduli `sfp_*.py` con pattern di client HTTP verso API. | Marginale. SpiderFoot come **riferimento di architettura a moduli/plugin** per client di sorgenti diverse, se utile. |

Sintesi codice locale: i due asset più preziosi sono **(1)** `Instagram Tools\...\check-follow-back.py` come template PyQt6 già nel nostro stack, e **(2)** `Subito-Bot\subito-searcher.py` come esempio concreto di collector con polling/dedup/persistenza/notifiche. `SteamAchievement\steam.py` mostra il pattern Steam Web API ma con una API key esposta da bonificare.

---

## (d) Raccomandazione finale di stack per sorgente

| Sorgente | Stack consigliato | Dipendenza vs. codice nostro |
|---|---|---|
| **Steam appdetails** | Client `httpx` nostro + retry/backoff, endpoint noto. | Codice nostro (no libreria). |
| **Steam reviews (tracking)** | `steamreviews` se compatibile con Py 3.10, altrimenti client `httpx` nostro su `appreviews` leggendo solo `query_summary`. | Dipendenza (con fallback nostro). |
| **Steam player count** | Client `httpx` su `GetNumberOfCurrentPlayers`, snapshot periodici. | Codice nostro. |
| **Steam app list (discovery)** | `httpx` su `GetAppList` + diff periodico. | Codice nostro. |
| **SteamSpy** | `steamspypi`. | Dipendenza. |
| **SteamCharts** | NON dipendere: ricostruire serie storica con snapshot di `GetNumberOfCurrentPlayers`. | Codice nostro. |
| **itch.io discovery** | `feedparser` sui feed RSS (`.xml`) ufficiali. | Codice nostro. |
| **itch.io dettaglio gioco** | `httpx` + `BeautifulSoup` per OpenGraph/JSON-LD; rate limit gentile, User-Agent identificabile. | Codice nostro. |
| **YouTube** | `google-api-python-client`; 1 `search.list` per scoperta + `videos.list` batch per tracking (attenti a 10k unità/giorno). | Dipendenza ufficiale. |
| **Reddit** | `PRAW` (OAuth, 100 QPM). | Dipendenza. |
| **TikTok** | Import manuale in GUI (base). Interfaccia astratta per innestare `TikTokApi` o servizio a pagamento in futuro. | Codice nostro + eventuale dipendenza opzionale. |
| **Instagram** | Import manuale in GUI (base). Sconsigliato `instaloader` con account reale. | Codice nostro. |
| **GUI** | PyQt6 + pyqtgraph (grafici in-app) + matplotlib (export report). Partire dal template locale `check-follow-back.py`, studiare esempi pyqtgraph. | Dipendenze + template locale. |

---

## Fonti (URL)
- steamreviews: https://github.com/woctezuma/download-steam-reviews · https://pypi.org/project/steamreviews
- steamspypi: https://github.com/woctezuma/steamspypi
- ValvePython/steam: https://github.com/valvepython/steam · steam.py: https://github.com/Gobot1234/steam.py
- Progetti Steam: https://github.com/FronkonGames/Steam-Games-Scraper · https://github.com/altskop/steam-scraper · https://github.com/coder202/trendx-steam · https://github.com/hhm970/c10-games-tracker-project
- itchio-lib: https://github.com/Tch1b0/itchio-lib · itch-dl: https://github.com/DragoonAethis/itch-dl
- google-api-python-client: https://github.com/googleapis/google-api-python-client
- PRAW: https://github.com/praw-dev/praw
- TikTok-Api: https://github.com/davidteather/TikTok-Api · instaloader: https://github.com/instaloader/instaloader
- pyqtgraph: https://github.com/pyqtgraph/pyqtgraph · embed tutorial: https://github.com/ixjlyons/embed-pyqtgraph-tutorial · Realtime-Plot-Template: https://github.com/nthuepl/Realtime-Plot-Template · pyqt/examples: https://github.com/pyqt/examples
</content>
</invoke>
