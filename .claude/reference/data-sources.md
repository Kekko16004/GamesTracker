# Sorgenti dati — endpoint, auth, rate limit

> Aggiornato dal `research-scout` il 2026-07-21 con verifica online.
> Legenda: ✅ = verificato su fonte ufficiale/autorevole; ⚠️ = parzialmente verificato o soggetto a cambiamento; ❓ = NON verificato, da confermare in fase di implementazione.
> Tutti gli endpoint "store" e "appreviews" sono API **interne non ufficiali** di Steam: stabili da anni ma senza garanzie né SLA. Le fonti sono citate in fondo.

---

## Steam

### Pagine di discovery (nuove uscite)
- ⚠️ New & popular (HTML): `https://store.steampowered.com/explore/new/` — pagina web, richiede scraping HTML. Non è un'API JSON.
- ⚠️ In alternativa allo scraping della pagina explore, per scoprire nuovi appid conviene fare diffing periodico di `GetAppList` (vedi sotto) e poi arricchire con `appdetails`. La pagina explore resta utile per capire cosa Steam mette in evidenza ("popular").
- ❓ Non esiste un endpoint JSON ufficiale "solo nuove uscite indie": va costruito lato nostro (filtro per release_date recente + generi/tag).

### Steam Store API — dettaglio app (non ufficiale ma stabile) ✅
- Endpoint: `https://store.steampowered.com/api/appdetails?appids=<APPID>&l=english`
  - Parametri utili: `appids` (uno o più separati da virgola — ma con più appid la risposta può essere parziale/limitata; consigliato 1 alla volta), `l` (lingua), `cc` (country code per prezzo/valuta), `filters` (es. `price_overview,basic`).
  - Ritorna JSON con chiave `<appid> -> { success, data }`. `data` contiene: `name`, `type`, `is_free`, `genres`, `categories`, `release_date`, `price_overview`, `screenshots`, `movies` (trailer), `developers`, `publishers`, `short_description`, `header_image`, ecc.
  - ⚠️ Rate limit non documentato ufficialmente. Empiricamente segnalato intorno a ~200 richieste ogni 5 minuti per IP (≈1 ogni 1.5s) prima di rischiare HTTP 429; usare backoff. Non richiede API key.

### Steam Store API — review summary / review tracking ✅ (cuore del sistema)
- Endpoint: `https://store.steampowered.com/appreviews/<APPID>?json=1`
- Documentazione ufficiale (stessa API, lato Steamworks): "User Reviews - Get List".
- Parametri (tutti stringa; i default tra parentesi):
  - `filter`: `recent` (per data creazione) | `updated` (per data update) | `all` (default, per helpfulness con finestra `day_range`).
  - `language`: codice lingua API oppure `all`.
  - `day_range`: giorni indietro per review "helpful"; solo con `filter=all`; max 365.
  - `cursor`: token di paginazione. Prima chiamata `*`, poi il valore `cursor` restituito. Va URL-encodato.
  - `review_type`: `all` (default) | `positive` | `negative`.
  - `purchase_type`: `all` | `non_steam_purchase` | `steam` (default). **Per il conteggio pubblico usare `purchase_type=all`.**
  - `num_per_page`: default 20, max 100.
  - `filter_offtopic_activity`: `0` per includere i review-bomb (di default esclusi).
- Risposta — top level: `success`, `cursor`, `query_summary`, `reviews[]`.
  - `query_summary` (presente solo sulla PRIMA chiamata): `num_reviews`, `review_score`, `review_score_desc`, `total_positive`, `total_negative`, `total_reviews`. **Questi sono i campi chiave per il review tracking nel tempo.**
  - ⚠️ **Trappola nota**: se `review_type` è `positive`/`negative`, il campo `total_reviews` viene sovrascritto con `total_positive`/`total_negative`. Per il totale reale usare `review_type=all` oppure sommare `total_positive + total_negative`.
  - Ogni review contiene: `recommendationid`, `author` (`steamid`, `num_games_owned`, `num_reviews`, `playtime_forever`, `playtime_at_review`, ...), `language`, `review`, `timestamp_created`, `timestamp_updated`, `voted_up`, `votes_up`, `votes_funny`, `weighted_vote_score`, `comment_count`, `steam_purchase`, `received_for_free`, `written_during_early_access`, `primarily_steam_deck`.
- ⚠️ Rate limit: la doc ufficiale non dichiara limiti. Empiricamente ~10 review/secondo sostenibili (vedi libreria `steamreviews`). Reviews restituite a batch di 20 se non si alza `num_per_page`.
- 💡 **Per il solo tracking dei conteggi** basta 1 chiamata con `num_per_page=0` o `1` e leggere `query_summary` — molto economico. Non serve scaricare tutte le review.
- ⚠️ Endpoint correlato non documentato: histogram delle review nel tempo `https://store.steampowered.com/appreviewhistogram/<APPID>?l=english` (utile per ricostruire la serie storica di recensioni senza dover fare snapshot dal giorno 1). Da verificare in implementazione.

### Steam Store API — lista completa app ✅
- Endpoint: `https://api.steampowered.com/ISteamApps/GetAppList/v2/`
  - Ritorna `{ applist: { apps: [ { appid, name }, ... ] } }` — TUTTI gli appid (lista enorme, centinaia di migliaia). Non richiede key.
  - Uso previsto: snapshot periodico + diff per individuare nuovi appid. Non filtra per data/tipo: il filtraggio è a carico nostro.

### Steam Web API — richiede key gratuita ✅
- Key: `https://steamcommunity.com/dev/apikey` — variabile `STEAM_WEB_API_KEY`. Gratuita, richiede account Steam con acquisto ≥ 5$.
- Player count live: `https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid=<APPID>`
  - ⚠️ Nota: molte fonti indicano che `GetNumberOfCurrentPlayers` funziona **anche senza key**. La key è comunque consigliata per gli endpoint Web API che la richiedono.
  - Ritorna `{ response: { player_count, result } }`. Solo per giochi già usciti.
- ✅ Rate limit Steam Web API (con key): quota "soft" di ~100.000 chiamate/giorno per key (da ToS). In pratica esiste anche un limite di burst per IP che restituisce HTTP 429 su raffiche brevi → serve throttling/backoff anche stando sotto la quota giornaliera.

### SteamSpy (stime owner/vendite) ✅
- Endpoint base: `https://steamspy.com/api.php`
  - `?request=appdetails&appid=<APPID>` — dettaglio singolo gioco (owners stimati in fasce, ccu, prezzo, tag, ecc.).
  - `?request=all&page=<N>` — 1000 giochi per pagina ordinati per owner (page parte da 0).
  - Altri: `genre`, `tag`, `top100in2weeks`, `top100forever`, `top100owned`.
- ✅ Rate limit reale (dalla doc di `steamspypi`):
  - `appdetails` e simili: **1 richiesta al secondo**.
  - `all`: **1 richiesta al minuto** (fortemente limitato).
- Stime approssimative → usare per trend relativi, non valori assoluti. La fascia owners è ampia (es. "20,000 .. 50,000").

### SteamCharts (player count storico) ⚠️
- `https://steamcharts.com/app/<APPID>` — pagina HTML, nessuna API JSON ufficiale. I dati storici (grafico) sono resi lato client; lo scraping è fragile e non documentato.
- ⚠️ **SteamCharts NON offre API pubblica.** Opzioni:
  1. Ricostruire noi la serie storica facendo snapshot periodici di `GetNumberOfCurrentPlayers` (approccio consigliato, coerente col principio "ogni raccolta è uno snapshot"). SteamCharts stessa fa così (query oraria del player count via Steam Web API).
  2. SteamDB (`https://steamdb.info/app/<APPID>/charts/`) ha dati storici migliori ma vieta lo scraping (Cloudflare + ToS restrittivi) → **sconsigliato**.
- 💡 Raccomandazione: NON dipendere da SteamCharts/SteamDB. Costruire la serie storica del player count internamente via snapshot di `GetNumberOfCurrentPlayers`. Per il passato già trascorso si può tentare `appreviewhistogram` (per le recensioni) come proxy.

---

## itch.io

### Discovery via RSS ✅ (metodo migliore, ufficialmente supportato)
- itch.io permette di appendere `.xml` a QUALSIASI URL di browse per ottenere un feed RSS:
  - New & popular: `https://itch.io/games/new-and-popular.xml`
  - Per tag/genere: `https://itch.io/games/tag-<tag>.xml`, `https://itch.io/games/genre-<genre>.xml`
  - Gratis: `https://itch.io/games/price-free.xml`
- Feed globale: `https://itch.io/feed` (attività). Featured: `https://itch.io/featured-games-feed`.
- ✅ Questo è il modo ufficiale e "gentile" per la discovery: niente scraping HTML aggressivo. Il feed dà titolo, URL, autore, thumbnail.

### Dettaglio di un gioco ⚠️
- Le pagine gioco (`https://<autore>.itch.io/<gioco>`) espongono metadati in **OpenGraph** e **JSON-LD** nel `<head>` (parsabili con BeautifulSoup) → titolo, immagine, descrizione, a volte prezzo.
- ⚠️ Tag/genere, presenza demo, link social dell'autore e devlog si ricavano dal parsing dell'HTML della pagina gioco / pagina autore. Non c'è un endpoint JSON pubblico che li dia tutti insieme. Da confermare quali campi sono affidabilmente presenti in JSON-LD.
- I devlog (`.../devlog`) danno timeline degli aggiornamenti → utili per ricostruire la strategia.

### Server-side API ⚠️ (NON adatta alla discovery pubblica)
- `https://api.itch.io` (doc: `https://itch.io/docs/api/serverside`, OAuth: `https://itch.io/docs/api/oauth`).
- ⚠️ **Limite chiave**: la server-side API è pensata per far interrogare a uno sviluppatore i **propri** giochi/account tramite API key. NON permette di navigare il catalogo pubblico o le nuove uscite altrui. Confermato anche dallo staff itch: "The api is meant for developers. Not for users or data scrapers."
- Conclusione: per GamesTracker la server-side API NON serve (non abbiamo i giochi sul nostro account). Usare RSS + parsing pagine pubbliche.

### robots.txt / ToS ✅ (verificato 2026-07-21 dal data-collector-engineer)
- ✅ `https://itch.io/robots.txt` letto in fase di implementazione. Per `User-agent: *` i path bloccati sono: `/embed/`, `/embed-upload/`, `/search`, `/checkout/`, `/game/download/`, `/bundle/download/`, `/register-for-purchase/`, `/email-feedback/`. **Ne' `/games` ne' i feed `.xml` sono disallow**; le pagine gioco (sottodomini `<autore>.itch.io`) non sono bloccate. La sitemap `https://itch.io/sitemap.xml` e' esplicitamente indicata.
- itch incoraggia l'uso degli RSS per il consumo automatico dei listing. Regola operativa applicata nel client `core/sources/itch.py`: preferire RSS, User-Agent identificabile (da `HTTP_USER_AGENT`), rate limit gentile (Throttle a 1 req ogni 2.5s), niente parallelismo aggressivo.

---

## YouTube Data API v3 (key gratuita) ✅
- Key: Google Cloud Console → variabile `YOUTUBE_API_KEY`.
- Endpoint principali e **costo in unità** (verificato su doc ufficiale Google):
  - `search.list` → **100 unità** per chiamata. Cerca video per keyword/titolo gioco. È l'endpoint costoso.
  - `videos.list` → **1 unità** (part `statistics`: viewCount, likeCount, commentCount).
  - `channels.list` → **1 unità** (statistiche canale, subscriberCount).
  - `playlistItems.list` → **1 unità**.
- ✅ Quota giornaliera di default: **10.000 unità/giorno** per progetto.
  - ⚠️ Con `search.list` a 100 unità → **max ~100 ricerche/giorno**. Va usato con parsimonia: cache-are i risultati, preferire recuperare gli `videoId` una volta e poi aggiornare le statistiche con `videos.list` (1 unità, batch fino a 50 id per chiamata).
- Strategia consigliata: 1 `search.list` per gioco per scoprire i video rilevanti, poi tracking continuo delle statistiche via `videos.list` batch (economico).

---

## Reddit API (PRAW, key gratuita) ✅
- App: `https://www.reddit.com/prefs/apps` → variabili `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`.
- ✅ Auth: OAuth obbligatorio. Client non autenticati vengono throttlati/bloccati.
- ✅ Rate limit (tier free non commerciale): **100 query al minuto (QPM) per client OAuth** (10 QPM senza OAuth). PRAW gestisce automaticamente il rispetto dei limiti e attende quando serve.
- Uso commerciale a pagamento ($0.24 / 1000 chiamate) — **non ci riguarda** finché restiamo non commerciali e sotto i 100 QPM.
- Uso previsto: cercare menzioni del gioco, subreddit (r/IndieGaming, r/gamedev, r/Games, ...), upvote, commenti, data post, timing rispetto a demo/release.

---

## TikTok / Instagram (best-effort, NO API pubblica affidabile) ⚠️
Nessuna API ufficiale gratuita utile per raccogliere metriche di post pubblici altrui. Dettaglio opzioni, trade-off e librerie in `existing-solutions.md`. In sintesi:
- **TikTok**: libreria non ufficiale `TikTokApi` (davidteather) — mantenuta ma fragile, richiede browser (Playwright) e `ms_token`; rischio blocco.
- **Instagram**: `instaloader` — mantenuta, ma nel 2025/2026 Instagram ha stretto molto: login-wall al secondo profilo, HTTP 401/429 frequenti, rischio ban dell'account usato. Molto fragile.
- **Import manuale**: opzione più affidabile e ToS-safe → l'utente incolla link/metriche nella GUI, il sistema li persiste come snapshot.
- Da fare per ultimo (coerente con priorità MVP).

---

## Variabili d'ambiente (config/.env.example)
```
STEAM_WEB_API_KEY=
YOUTUBE_API_KEY=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=GamesTracker/0.1 by <username>
# opzionali/futuri:
# TIKTOK_MS_TOKEN=
# INSTAGRAM_SESSION=   # sessione instaloader se si sceglie login
```

---

## Cosa NON è stato possibile verificare (da confermare in implementazione)
- Rate limit esatti degli endpoint non ufficiali Steam (`appdetails`, `appreviews`): solo stime empiriche, non documentati da Valve.
- Esistenza/stabilità di `appreviewhistogram` per ricostruire la storia recensioni.
- Contenuto reale di `https://itch.io/robots.txt` e quali path sono `Disallow`.
- Quali campi (tag, demo, social autore) sono affidabilmente presenti nel JSON-LD/OpenGraph delle pagine itch vs. richiedono parsing HTML.
- Se `GetNumberOfCurrentPlayers` richieda davvero la key (fonti discordanti; testare senza e con key).

## Fonti (URL)
- Steam Get List (ufficiale Steamworks): https://partner.steamgames.com/doc/store/getreviews
- Internal Steam Web API wiki (appreviews, histogram): https://github.com/Revadike/InternalSteamWebAPI/wiki/Get-App-Reviews
- Steam Web API ToS / rate limit: https://steamcommunity.com/dev/apiterms — https://steamapi.xpaw.me/
- SteamSpy API + rate limit: https://github.com/woctezuma/steamspypi — https://gist.github.com/woctezuma/a8a9cbde6b03868b8631d2f436bbcfab
- SteamCharts about (metodo di raccolta): https://steamcharts.com/about — SteamDB: https://steamdb.info/
- itch.io RSS feeds: https://itch.io/docs/api/overview — https://itch.io/updates/rss-feeds-for-browsing-games
- itch.io server-side API: https://itch.io/docs/api/serverside — https://itch.io/t/4748289/itchio-api-for-game-metadata
- YouTube quota cost (ufficiale): https://developers.google.com/youtube/v3/determine_quota_cost
- Reddit API rate limit: https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki — https://praw.readthedocs.io/en/stable/getting_started/ratelimits.html
</content>
</invoke>
