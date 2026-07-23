# Decisioni di progetto (locked)

Queste decisioni sono state confermate dall'utente all'avvio. Non ridiscuterle senza motivo — sono la base dell'architettura.

## 1. Runtime — Collector + GUI separati
Il tracking temporale (24h/48h/1 settimana/1 mese) richiede un processo che gira in continuazione.
- Un **collector** (servizio in background con scheduler) raccoglie dati e scrive su DB anche a GUI chiusa.
- La **GUI PyQt6** legge dal DB. Non è responsabile della raccolta.
- Il collector deve poter girare come processo locale sempre attivo (avvio manuale/autostart). Design pronto per essere spostato su VPS in futuro.

## 1b. Steam — JSON endpoint (API), NON scraping HTML del gioco
Confermato dall'utente: per i dati del singolo gioco su Steam si usano i **JSON endpoint** pubblici
(`store.steampowered.com/api/appdetails`, `store.steampowered.com/appreviews/<appid>?json=1`),
NON lo scraping dell'HTML della pagina gioco. Motivo: ritornano dati già strutturati, sono più stabili,
evitano age-gate/cookie regione. Lo scraping HTML resta consentito SOLO per la **discovery** delle
nuove uscite (`explore/new/`) e per itch.io, dove non esiste un endpoint JSON equivalente.

## 2. Dati social — API ufficiali dove possibile, resto best-effort
- Usa **API ufficiali** dove esistono: YouTube Data API v3, Reddit API (PRAW).
- TikTok e Instagram non hanno API pubbliche affidabili → raccolta **best-effort** (endpoint pubblici / scraping leggero / import manuale di link).
- Priorità assoluta: **prendere esattamente i dati corretti e assicurarsi di poterli riutilizzare**. Meglio meno dati ma affidabili e persistiti bene, che tanti dati fragili.

### 2b. Reddit — DISABILITATO per ora (deciso 2026-07-21)
Reddit ha **chiuso l'accesso `.json` non autenticato il 28 maggio 2026**: lo scraping "facile" (append `.json`, librerie tipo YARS) non funziona più. Lo scraping HTML residuo viene silenziosamente strozzato (risposte parziali, reCAPTCHA) e richiederebbe proxy residenziali a pagamento per essere affidabile — contro il principio "dati corretti e riutilizzabili".
- **Decisione utente**: NON usare Reddit per ora. Le credenziali API (`REDDIT_*`) restano vuote in `config/.env`; l'utente configurerà l'app *script* ufficiale (reddit.com/prefs/apps, ~2 min, gratis, 100 req/min) con calma.
- Il client PRAW della Fase 3 resta pronto: con `require_reddit_credentials()` mancanti la sorgente resta `enabled=False` e degrada con log, senza bloccare il collector.
- Fonte: vedi ricerca in reference se serve riverificare quando l'utente riprende Reddit.

## 3. Metriche di crescita — traccia tutto ciò che è pubblico
Wishlist e vendite Steam NON sono pubbliche. Segnali tracciati (tutti):
- **N° recensioni Steam** nel tempo (proxy vendite più affidabile per indie).
- **Player count live** (Steam API / SteamCharts) — solo giochi già usciti.
- **Stime owner/vendite SteamSpy** (approssimative, utili per trend).
- **Crescita follower + volume menzioni/post** sulle piattaforme social.

## 4. Anti-trash — Quality Score 0-100
Ogni gioco riceve un punteggio 0-100 che combina qualità pagina, engagement social e crescita.
La soglia di cutoff è **configurabile dall'utente** nella GUI. Vedi `reference/quality-score.md`.

## 5. Lingua — Bilingue IT/EN
UI e report generati devono supportare Italiano e Inglese con switch nell'app. Predisporre i18n dall'inizio (no stringhe hardcoded sparse).

## 6. Priorità MVP (ordine di costruzione)
1. **Steam + itch.io**: raccolta nuove uscite + review tracking. Cuore del sistema.
2. **YouTube + Reddit**: API ufficiali, affidabili.
3. **TikTok + Instagram**: best-effort, per ultimo.
4. **Dashboard + report DENTRO l'app stessa**, fatti bene (grafici, dati scritti, report esportabili).

## 7. API keys — fornite dall'utente
L'utente fornirà key gratuite (Steam Web API, YouTube Data API, Reddit app).
L'app le legge da `config/.env` (mai committato). Prevedere `config/.env.example` con i nomi delle variabili.
