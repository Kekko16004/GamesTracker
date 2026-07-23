# Marketing Playbook — come si analizza una strategia indie

> Documento di dominio del `social-marketing-analyst`. Guida `data-analyst` (report, quality score) e gli engineer social (cosa raccogliere e in quali tabelle).
> Regola d'oro trasversale: **noi osserviamo correlazioni, non causalità**. Un picco di crescita *dopo* un post NON prova che il post l'abbia causato. Il nostro lavoro è rendere visibili le co-occorrenze temporali e formulare ipotesi etichettate come tali, mai come fatti.
> Vincolo dati: wishlist e vendite Steam NON sono pubbliche. Tutto ciò che segue usa **proxy pubblici** (recensioni, player count, follower, volume/engagement post). Vedi `decisions.md` §3.

---

## 0. Premessa sui proxy (leggere prima di tutto)

Non possiamo misurare l'obiettivo reale del marketing (wishlist, vendite). Misuriamo segnali osservabili correlati:

| Vogliamo sapere | Non è pubblico | Proxy pubblico che usiamo | Tabella |
|---|---|---|---|
| Vendite / wishlist | ❌ | N° recensioni Steam nel tempo (regola empirica di settore: recensioni ≈ 1/30–1/50 delle copie, ma il **rapporto NON va assunto** — usare solo la *traiettoria*) | `game_snapshots.total_reviews` |
| Interesse pre-release | ❌ | Menzioni/post social, follower, iscritti Discord | `social_snapshots`, `social_posts` |
| Popolarità live | parziale | Player count concorrente | `game_snapshots.current_players` |
| Diffusione stimata | ❌ | Fasce owner SteamSpy (trend relativo, non assoluto) | `game_snapshots.steamspy_owners` |

Ogni conclusione del report deve dichiarare quale proxy sta usando e il suo limite.

---

## 1. Segnali di viralità / campagna vincente

Per ogni segnale: **cosa misurare** (metrica osservabile) e **mapping sui nostri dati** (da dove esce). I segnali sono ordinati per affidabilità/valore.

### 1.1 Timing demo → release
Le campagne efficaci usano la demo come strumento di accumulo interesse: la demo esce, genera menzioni e recensioni-anticipate, la release la converte.
- **Cosa misurare**:
  - Δ giorni tra `demo_release_date` e `release_date` (finestra tipica efficace: la demo resta disponibile settimane/mesi prima, non ore).
  - La demo è stata rilasciata *in concomitanza* con un festival (Next Fest)? (co-occorrenza con eventi noti).
  - Crescita di menzioni/recensioni nella finestra demo vs post-release.
- **Mapping dati**: `games.has_demo`, `games.demo_release_date`, `games.release_date`; crescita da `game_snapshots` (recensioni/player) segmentata sulle due date.
- **Interpretazione**: demo pubblicata mesi prima + spike di menzioni durante = strategia di "wishlist farming". Demo pubblicata il giorno stesso della release = strategia debole/assente (segnale negativo lieve).

### 1.2 Partecipazione a Steam Next Fest / festival
Il Next Fest (evento Steam trimestrale di demo) è il singolo evento a più alto ROI per un indie. Altri: festival tematici Steam, Wishlist events, Day of the Devs, itch bundle/jam.
- **Cosa misurare**: presenza della demo in una finestra Next Fest nota (le date dei Next Fest sono pubbliche e vanno mantenute in una tabella/config di eventi — vedi §4.4); spike di recensioni/player/menzioni coincidente con la finestra festival.
- **Mapping dati**: `demo_release_date` confrontata con calendario eventi; spike su `game_snapshots` e `social_posts.posted_at` dentro la finestra.
- **Nota**: la partecipazione in sé non è osservabile via API in modo diretto; la deduciamo dalla co-occorrenza demo/festival + eventuale menzione esplicita nei post ("live at Next Fest").

### 1.3 Cadenza e formato dei post
Una campagna curata ha ritmo regolare, non silenzio seguito da uno sbotto. Il segnale è la **regolarità**, non solo il volume.
- **Cosa misurare**:
  - Frequenza di pubblicazione (post/settimana) per canale nelle settimane attorno a demo/release.
  - Regolarità (deviazione standard degli intervalli tra post — bassa = cadenza pianificata).
  - Mix di formato: annunci, dietro-le-quinte/devlog, clip di gameplay, meme/community.
- **Mapping dati**: conteggio e distribuzione temporale di `social_posts.posted_at` per `platform`; `social_snapshots.total_posts` per l'andamento aggregato.
- **Interpretazione**: cadenza regolare che *accelera* verso la release = campagna pianificata. Un unico burst isolato = tentativo spot (meno efficace, spesso).

### 1.4 Short-form video (TikTok / Reels / YouTube Shorts)
Nel 2024–2026 lo short-form è il principale motore di scoperta indie. Un singolo short virale può spostare le wishlist più di mesi di post.
- **Cosa misurare**: n° di short pubblicati, e soprattutto la **distribuzione dell'engagement** (un video con views/like ordini di grandezza sopra la mediana del canale = "hit"); rapporto views/follower (un video che supera di molto il numero di follower indica diffusione fuori dalla fanbase, cioè viralità reale).
- **Mapping dati**: `social_posts` (platform=`tiktok`|`youtube`|`instagram`, `views`, `likes`, `comments`, `shares`); il baseline del canale da `social_snapshots.followers`.
- **Segnale forte di viralità**: `views` >> `followers` del canale e >> mediana dei post del gioco stesso.

### 1.5 Thread Reddit ad alto engagement
Reddit è dove gli indie ottengono i primi wishlist "veri". Un thread che sfonda in un subreddit grande (r/Games, r/gaming) è raro e ad alto impatto.
- **Cosa misurare**: upvote, commenti, subreddit di pubblicazione (peso maggiore ai subreddit grandi/generalisti), rapporto upvote/commenti (discussione vs semplice like), timing rispetto a demo/release.
- **Mapping dati**: `social_posts` (platform=`reddit`, `subreddit`, `likes`=upvote, `comments`). Reddit API dà questi dati in modo affidabile.
- **Interpretazione**: post in r/IndieGaming con engagement medio = routine sana. Post che sfonda in r/Games con migliaia di upvote = evento potenzialmente svolta (§4).

### 1.6 Devlog itch / update Steam
I devlog segnalano un progetto vivo e curano una community. Cadenza costante di devlog correla con progetti seri (non asset-flip).
- **Cosa misurare**: presenza e frequenza dei devlog itch (`.../devlog`); frequenza degli update/annunci Steam.
- **Mapping dati**: `social_posts` con platform dedicata o `discovered_via='devlog'`; in alternativa un conteggio in `social_snapshots.extra`. La frequenza alimenta anche i "segnali di cura" del quality score.

### 1.7 Collaborazioni con streamer / press
Copertura da streamer/YouTuber o testate porta picchi improvvisi e "esogeni".
- **Cosa misurare**: comparsa di video YouTube da canali con molti iscritti che citano il gioco (subscriberCount alto via `channels.list`); spike di player/recensioni coincidente con l'uscita di quel video.
- **Mapping dati**: `social_posts` (youtube) + `social_accounts`/`social_snapshots` per la dimensione del canale; correlazione col picco su `game_snapshots`.
- **Attenzione causalità**: un picco dopo un video di un grande streamer è una co-occorrenza forte, ma potrebbe esserci stato anche un update/sconto in contemporanea. Segnalare le concause.

### 1.8 Wishlist spike (proxy)
Non misurabile direttamente. Proxy combinato:
- **Cosa misurare**: accelerazione simultanea di (a) crescita recensioni post-release, (b) volume menzioni social, (c) player count al lancio. Quando tutti e tre salgono nella stessa finestra pre/post release, è l'evidenza più forte che abbiamo di una campagna riuscita.
- **Mapping dati**: derivata di `game_snapshots.total_reviews` e `current_players` + densità di `social_posts.posted_at`.

---

## 2. Piattaforma per piattaforma — cosa raccogliere

Legenda affidabilità: 🟢 API ufficiale affidabile · 🟡 best-effort/fragile · 🔴 solo import manuale realistico.
Mapping fisso valido per tutte: il **profilo** → `social_accounts`, la **metrica del profilo nel tempo** (follower, n° post) → `social_snapshots`, il **singolo post/menzione** → `social_posts`.

### 2.1 YouTube 🟢 (API ufficiale, ma quota stretta)
- **Cosa serve per ricostruire la strategia**: canale ufficiale del gioco/dev; video di terzi (streamer/press) che lo citano; tipo di contenuto (trailer, dev diary, Shorts); timing dei trailer rispetto a demo/release; dimensione dei canali che ne parlano.
- **Come raccogliere** (vedi `data-sources.md`): 1 `search.list` per gioco (100 unità — usare con parsimonia) per scoprire i `videoId` rilevanti; poi tracking economico con `videos.list` (1 unità, batch 50) per `viewCount`/`likeCount`/`commentCount`; `channels.list` per `subscriberCount` del canale.
- **Mapping tabelle**:
  - `social_accounts`: canale ufficiale (platform=`youtube`, handle, url, `discovered_via`).
  - `social_snapshots`: `followers`=subscriberCount, `total_posts`=videoCount; `extra`={viewCount canale}.
  - `social_posts`: un record per video rilevante — `posted_at`=publishedAt, `title`, `views`, `likes`, `comments`. Per i video di terzi, salvare comunque in `social_posts` con nota in nessun account collegato o con `discovered_via`.
- **Realistico**: 🟢 ottimo. Limite reale = quota (max ~100 `search.list`/giorno): cache-are gli ID, aggiornare solo le statistiche.

### 2.2 Reddit 🟢 (API ufficiale, affidabile)
- **Cosa serve**: subreddit dove il gioco è stato postato; upvote/commenti; timing rispetto a demo/release; se il dev ha postato in prima persona (self-promotion) vs menzioni organiche.
- **Come raccogliere**: PRAW, ricerca per titolo/URL Steam-itch del gioco e nei subreddit target (§3.1). 100 QPM OAuth, gestito da PRAW.
- **Mapping tabelle**:
  - `social_accounts`: eventuale profilo Reddit del dev (spesso assente/non rilevante).
  - `social_posts`: **tabella principale per Reddit** — `subreddit`, `posted_at`, `title`, `likes`=score/upvote, `comments`=num_comments, `post_url`.
  - `social_snapshots`: poco rilevante per Reddit (nessun "follower" del gioco); usare al più per il karma di un subreddit dedicato se esiste.
- **Realistico**: 🟢 ottimo per menzioni ed engagement datati.

### 2.3 TikTok 🟡 (best-effort)
- **Cosa serve**: account ufficiale del gioco/dev; hashtag usati; n° video e loro engagement; presenza di clip virali (views >> follower); timing rispetto alla release.
- **Come raccogliere** (vedi `existing-solutions.md`): libreria non ufficiale `TikTokApi` (fragile, richiede Playwright + ms_token, rischio blocco) **oppure** import manuale. Preferire import manuale per stabilità e ToS.
- **Mapping tabelle**:
  - `social_accounts`: account ufficiale (platform=`tiktok`).
  - `social_snapshots`: `followers`, `total_posts`, `extra`={likes totali profilo}.
  - `social_posts`: per video raccolto — `views`, `likes`, `comments`, `shares`, `posted_at`.
- **Realistico**: 🟡/🔴 — dati puntuali affidabili solo via import manuale dell'utente; raccolta automatica opportunistica e da trattare come "best-effort, può mancare".

### 2.4 Instagram 🔴 (best-effort, molto fragile)
- **Cosa serve**: profilo ufficiale; Reels (short-form, l'unico formato che conta per scoperta); hashtag; cadenza post.
- **Come raccogliere**: `instaloader` è molto fragile nel 2025/2026 (login-wall, 401/429, rischio ban account). **Import manuale è l'opzione realistica.**
- **Mapping tabelle**: identico a TikTok — `social_accounts` (platform=`instagram`), `social_snapshots` (followers, post count), `social_posts` (Reels: views/likes/comments, `posted_at`).
- **Realistico**: 🔴 — trattare come opzionale/manuale. Non bloccare mai un'analisi sull'assenza di dati IG.

### 2.5 Regola comune sui dati mancanti
Ogni piattaforma può avere dati parziali. Il data-analyst e il quality score devono **degradare con grazia**: assenza di dati TikTok/IG ≠ segnale negativo (potrebbe essere solo un limite di raccolta). Distinguere sempre "assente perché non c'è" da "assente perché non l'abbiamo potuto raccogliere". Se possibile marcare la differenza in `social_snapshots.extra` (es. `{"collection":"manual"|"api"|"unavailable"}`).

---

## 3. Liste di partenza — subreddit, hashtag, keyword

Liste riutilizzabili dalla ricerca automatica. Mantenerle in config così l'utente/agente le aggiorna senza toccare codice.

### 3.1 Subreddit
**Generalisti / discovery (alto valore, alta soglia di rumore):**
- `r/IndieGaming` — hub principale scoperta indie.
- `r/indiegames` — variante attiva, molto usata dai dev.
- `r/IndieDev` — lato sviluppatori, spesso dietro-le-quinte.
- `r/gamedev` — sviluppo; utile per devlog e feedback tecnico, meno per hype.
- `r/Games` — grande, generalista, curato; sfondare qui = evento raro e forte.
- `r/gaming` — enorme e rumoroso; menzioni qui pesano solo se ad altissimo engagement.
- `r/pcgaming` — PC-centrico, buon segnale per uscite Steam.

**Vetrine / feedback dedicate:**
- `r/playmygame` — dev che chiedono prova/feedback.
- `r/DestroyMyGame` — feedback critico su trailer/gameplay.
- `r/IMadeThis`, `r/SideProject` — occasionali, bassa priorità.
- `r/WishlistWednesday`, `r/IndieGaming` thread promo — per wishlist push.

**Per genere (aggiungere in base a `games.genres`/`tags`):**
- Horror: `r/HorrorGaming`, `r/survivalhorror`.
- Roguelike/roguelite: `r/roguelikes`, `r/roguelites`.
- Metroidvania: `r/metroidvania`.
- RPG: `r/rpg_gamers`, `r/JRPG` (se JRPG), `r/CRPG` (se CRPG).
- Strategia/gestionali: `r/BaseBuildingGames`, `r/citybuilders`, `r/RealTimeStrategy`, `r/4Xgaming`.
- Puzzle/platform: `r/PuzzleVideoGames`, `r/platformers`.
- Sim/cozy: `r/CozyGamers`, `r/simulationgaming`, `r/farmingsimulator` (se pertinente).
- Survival/crafting: `r/survivalgaming`, `r/survivalcrafting`.
- Pixel art / retro: `r/PixelArt`, `r/retrogaming` (per estetica, non genere).
- VR: `r/virtualreality`, `r/OculusQuest` (se VR).
- Deck-builder: `r/deckbuilders`, `r/slaythespire`-like community.

**Regola**: pesare l'engagement per dimensione del subreddit (500 upvote in r/roguelikes valgono più di 500 in r/gaming). Mantenere una mappa `subreddit → genere → size_tier`.

### 3.2 Hashtag TikTok / Instagram
**Marketing indie / dev (evergreen):**
`#indiegame` `#indiedev` `#gamedev` `#indiegamedev` `#madewithunity` `#unrealengine` `#godot` `#gamedevelopment` `#indiegames` `#screenshotsaturday` `#wishlistnow` `#steamgame` `#pcgaming` `#gaming` `#devlog` `#pixelart` `#solodev` `#gamedevlife`

**Per genere (combinare con quelli sopra):**
- Horror: `#horrorgame` `#indiehorror` `#horrorgaming`
- Cozy: `#cozygame` `#cozygaming` `#wholesomegames`
- Roguelike: `#roguelike` `#roguelite`
- Pixel/retro: `#pixelart` `#retrogame` `#2dgame`
- RPG: `#indierpg` `#rpg` `#jrpg`
- Puzzle/platform: `#puzzlegame` `#platformer`

**Nota**: gli hashtag servono a (a) scoprire il contenuto del gioco quando raccogliamo, (b) analizzare quali tag il dev ha scelto. `#screenshotsaturday` e `#wishlistnow` sono forti indicatori di una strategia di marketing attiva e consapevole.

### 3.3 Keyword di ricerca YouTube
Usare `search.list` con parsimonia (100 unità). Query per gioco:
- `"<titolo esatto>"` (match preciso, prima scelta).
- `<titolo> gameplay`, `<titolo> demo`, `<titolo> trailer`, `<titolo> review`, `<titolo> first look`, `<titolo> demo next fest`.
- Per scoperta di genere (rara, costosa): `indie <genere> <anno>`, `best indie <genere> demo`.
- Filtri `search.list`: `type=video`, `order=relevance` (o `date` per novità), `publishedAfter` = ~data demo per ridurre rumore.
- **Ottimizzazione quota**: 1 sola `search.list` per gioco al momento della scoperta, salvare i `videoId`, poi solo `videos.list`.

### 3.4 Steam / itch — tag di genere per la discovery mirata
Per la discovery via feed RSS itch e per filtrare le nuove uscite Steam per genere, usare i tag di genere principali: `roguelike`, `metroidvania`, `horror`, `rpg`, `strategy`, `simulation`, `puzzle`, `platformer`, `deckbuilder`, `survival`, `cozy`, `visual-novel`, `pixel-art`, `souls-like`, `city-builder`, `farming`. Allinearli ai `games.tags`/`genres`.

---

## 4. Ricostruire e interpretare la "timeline strategia"

### 4.1 Cos'è la timeline
Merge ordinato per data di tutti gli eventi di un gioco (come da `data-model.md` §Note):
- `games.demo_release_date`, `games.release_date` (eventi ancora).
- `social_posts.posted_at` (ogni post/menzione).
- Eventi esterni noti (finestre Next Fest/festival — tabella eventi in config).
- **Punti di svolta della crescita**: cambi di pendenza nelle serie `game_snapshots.total_reviews` e `current_players`.

### 4.2 Cosa rende un post "il punto di svolta"
Un post è candidato "punto di svolta" quando soddisfa **entrambe** le condizioni:
1. **È un outlier di engagement**: le sue metriche (views/upvote/like) superano di molto la mediana dei post dello stesso gioco/canale (regola pratica: ≥ 5× la mediana, oppure `views > followers` del canale = uscito dalla fanbase).
2. **Precede un cambio di traiettoria** in una metrica di crescita entro una finestra plausibile (es. 1–14 giorni), cioè la pendenza di `total_reviews`/`current_players` aumenta in modo marcato *dopo* il post.

Se entrambe valgono, è un **candidato** punto di svolta — mai una certezza. Un post outlier senza cambio di crescita a valle è "engagement senza conversione". Un cambio di crescita senza alcun post/evento vicino è "crescita inspiegata" (probabile causa esterna non catturata: sconto, review di un grande streamer non raccolta, algoritmo).

### 4.3 Correlazione ≠ causalità — regole operative
Il data-analyst DEVE rispettare questi criteri quando scrive il report:
- Usare sempre linguaggio di co-occorrenza: "il picco di recensioni **coincide con / segue** il thread Reddit del 12/03", MAI "il thread Reddit ha causato il picco".
- **Elencare le concause** possibili in ogni finestra di picco: sconto/saldo (visibile in `game_snapshots.price`), festival in corso, release/demo, video di terzi, review-bomb (usare `filter_offtopic_activity`). Se in una finestra ci sono più eventi, dichiarare che non si può attribuire l'effetto a uno solo.
- **Baseline e controfattuale**: confrontare la crescita nella finestra dell'evento con la crescita "normale" nelle settimane precedenti dello stesso gioco. Un picco va giudicato rispetto al trend di base, non in assoluto.
- **Lag plausibile**: definire una finestra temporale (default 1–14 giorni) entro cui un effetto è credibile. Effetti "prima" del post non sono attribuibili al post.
- **Confondere volume e causa**: molti post nello stesso giorno di un picco possono essere *conseguenza* del picco (il gioco è di tendenza, quindi se ne parla), non causa. Segnalare questa possibile inversione.
- **Campione singolo**: un pattern osservato su UN gioco è aneddoto. Le raccomandazioni di strategia richiedono il pattern ripetuto su più giochi (analisi per-genere, `analysis_reports.genre`).

### 4.4 Calendario eventi
Mantenere in config una tabella di eventi noti con finestre di date: Steam Next Fest (trimestrale), festival Steam tematici, grandi bundle itch, eventi di annuncio (Summer Game Fest, ecc.). Serve a etichettare automaticamente le finestre di picco come "durante evento X".

### 4.5 Cosa deve produrre il data-analyst nel report
Per report **per-gioco** (`analysis_reports` con `game_id`):
- **Narrativa `summary`** (IT/EN): sequenza cronologica degli eventi chiave, con date esplicite, che descrive la strategia osservata (es. "demo pubblicata 45 gg prima al Next Fest → cadenza settimanale di Reels → thread r/IndieGaming ad alto engagement 3 gg prima della release → al lancio recensioni salite da X a Y in 48h"). Ogni nesso causale-apparente etichettato come co-occorrenza + concause.
- **Date da evidenziare**: demo, release, festival, top-3 post per engagement, punti di svolta della crescita.
- **Grafici richiesti** (dati strutturati in `analysis_reports.data`):
  1. Serie temporale recensioni (`total_reviews`) con marker verticali per demo/release/festival/post-svolta.
  2. Serie temporale player count con gli stessi marker.
  3. Timeline/gantt dei post social per piattaforma (densità e cadenza).
  4. Barre di engagement dei top post (per identificare gli outlier).
  5. (Opzionale) overlay crescita follower social vs recensioni.
- **Sezione limiti**: dichiarare quali dati mancano (es. TikTok non raccolto), quali proxy sono usati, dove la causalità non è stabilibile.

Per report **per-genere** (`analysis_reports` con `genre`): aggregare i pattern ricorrenti tra i giochi del genere (es. "nel genere horror, i giochi con demo al Next Fest mostrano in media una crescita recensioni al lancio superiore" — sempre come correlazione osservata sul campione, con N dichiarato).

---

## 5. Componente "Engagement social" del quality score (peso 20%)

Riferimento: `quality-score.md`. La componente è un sottopunteggio **normalizzato 0–1** (poi pesato 20% e ×100). Obiettivo: premiare presenza social reale e viva, penalizzare lo spam/trash. NON deve premiare i grandi budget (un gioco valido di un piccolo dev non deve essere punito per assenza di TikTok).

### 5.1 Segnali che alimentano il sottopunteggio
Comporre da 4 sotto-segnali, ciascuno normalizzato 0–1, poi media pesata:

| Sotto-segnale | Peso interno | Come calcolarlo | Fonte |
|---|---|---|---|
| **Presenza account attivi** | 0.25 | esiste almeno 1 account ufficiale con attività recente (post negli ultimi ~90 gg). 0/0.5/1 secondo n° piattaforme attive (cap a 2-3). | `social_accounts` + `social_posts.posted_at` |
| **Menzioni Reddit/YouTube** | 0.35 | volume di menzioni datate ponderate per engagement e size del subreddit/canale. **Log-scalare** (come le recensioni) per non far esplodere gli outlier. | `social_posts` (reddit, youtube) |
| **Volume post** | 0.20 | cadenza di pubblicazione normalizzata; premia regolarità, non solo quantità (vedi §1.3). Log-scalare. | `social_posts`, `social_snapshots.total_posts` |
| **Traiettoria follower** | 0.20 | crescita follower tra snapshot (positiva = premio); se un solo snapshot, neutro (0.5). | `social_snapshots.followers` |

### 5.2 Normalizzazione — regole
- **Log-scala** su tutti i conteggi (menzioni, post, follower) prima di normalizzare: `norm = log(1+x) / log(1+x_ref)` con `x_ref` = valore di riferimento configurabile (es. percentile alto del dataset o costante tarabile). Evita che un solo gioco virale schiacci tutti gli altri a ~0.
- **Normalizzazione relativa al dataset**: preferire percentili sul corpus dei giochi raccolti (min-max robusto tra 5° e 95° percentile) rispetto a soglie assolute, così lo score si adatta al catalogo reale. Il data-analyst deve tarare `x_ref` sui dati veri.
- **Dati mancanti = neutro, non zero**: se una piattaforma non è stata raccolta (best-effort TikTok/IG), NON contarla come 0 (sarebbe una penalità ingiusta). Ridistribuire i pesi sui segnali disponibili. Distinguere "assente perché non c'è" da "non raccolto" via `social_snapshots.extra.collection` (§2.5).
- **Recency**: pesare di più l'attività recente; menzioni/post molto vecchi contano meno (decay temporale opzionale, tarabile).

### 5.3 Penalità — pattern di marketing spam/trash
Riducono il sotto-punteggio social (e concorrono ai flag trash di `quality-score.md`):
- **Engagement piatto sospetto**: molti follower ma engagement quasi nullo sui post (`likes`/`comments` ≈ 0 rispetto ai `followers`) → indizio di follower comprati/bot. Penalità.
- **Rapporti innaturali**: like/commenti in rapporti fissi e innaturali tra post diversi, spike di follower istantanei senza post → segnale di gonfiaggio artificiale.
- **Spam cross-posting**: stesso identico titolo/link postato in molti subreddit in poche ore (pattern di self-promo aggressiva) → non premiare il volume, penalizzare.
- **Hashtag stuffing**: post con decine di hashtag irrilevanti / clickbait puro senza contenuto di gioco → segnale trash.
- **Menzioni solo da account del dev, zero organiche**: tutto il "buzz" è auto-generato, nessuna discussione di terzi → engagement social reale ≈ basso.
- **Zero social + zero recensioni + prezzo 0**: già un flag trash forte in `quality-score.md` §Penalità — la componente social conferma (contributo ~0, non negativo di per sé, ma concorre al discard combinato).

### 5.4 Cosa NON penalizzare
- Assenza di TikTok/Instagram in sé (limite di raccolta, non di qualità).
- Numeri assoluti bassi di un dev piccolo ma con engagement genuino (rapporti sani vale più del volume).
- Progetto pre-release con pochi dati: usare valori neutri, non penalizzanti.

### 5.5 Da validare sul campo (per il data-analyst)
Come da `quality-score.md`: tarare pesi interni, `x_ref` e soglie di penalità contro un set di giochi reali noti (indie validi vs asset-flip/trash) e aggiustare. Tutti i parametri di questa sezione vanno in config, non hardcoded.

---

## 6. Sintesi operativa (cheat-sheet)
- Proxy, non verità: recensioni/player/menzioni sostituiscono wishlist/vendite non pubbliche.
- Segnali forti di campagna: demo anticipata al Next Fest, cadenza social regolare in crescita, short-form con `views > followers`, thread Reddit che sfonda in subreddit grandi.
- Raccolta: YouTube/Reddit affidabili (API); TikTok/IG best-effort/manuale, mai bloccanti.
- Timeline = merge di demo/release + post + eventi + punti di svolta della crescita; "svolta" = post outlier + cambio pendenza a valle.
- Sempre correlazione, mai causalità: elencare concause, usare baseline, richiedere ripetizione su più giochi prima di raccomandare una strategia.
- Quality score social: presenza + menzioni pesate + cadenza + trend follower, log-scalati; mancante = neutro; penalizzare bot/spam/cross-post.

---

## 7. Analisi pre-lancio: hype pre-esistente vs crescita da lancio

> Motivazione (utente): un gioco può uscire da pochi giorni ma arrivare al lancio già famoso
> perché in beta/early-access/pre-order da mesi (es. **Palworld**: release recente, ma anni di
> hype accumulato). Confondere "cresciuto grazie al marketing di lancio" con "già famoso da
> prima" falsa ogni conclusione. Dobbiamo distinguere i due casi. Wishlist/vendite/pre-order
> NON sono pubblici: usiamo proxy.

### 7.1 Segnali osservabili (proxy pubblici)
- **Attività social datata prima vs dopo la release**: contare `social_posts.posted_at`
  precedenti a `games.release_date` (`n_pre`) contro i successivi (`n_post`). Molti post/video
  *prima* dell'uscita = interesse pre-esistente.
- **Early Access / Coming Soon**: tag/genere "Early Access" in `games.tags`/`genres` = il gioco
  era giocabile/noto ben prima della "release" nominale.
- **Gap demo → release lungo**: `release_date - demo_release_date ≥ ~30 gg` = demo usata per
  accumulare interesse nel tempo (wishlist farming), non lancio a freddo.
- **Scoperta molto anteriore alla release**: `release_date - first_seen_at ≥ ~30 gg` (proxy
  debole: `first_seen_at` è la scoperta del collector, non l'annuncio reale — dichiararlo).
- **Densità video pre-release**: molti video YouTube datati prima della release (richiede
  `capture_pre_launch=True`, che rimuove il filtro `publishedAfter=demo_date`).

### 7.2 Metrica e verdetto
`analysis/reports.py::_prelaunch_analysis(game, posts)` (funzione pura) produce:
`n_pre`, `n_post`, `signals` (lista), `preexisting_hype` (bool), `verdict` ∈
`{preexisting, launch_driven, insufficient}`. Regola: verdict `preexisting` se ci sono segnali
di maturità e l'attività pre-release ≥ post-release; `launch_driven` se l'attività si concentra
dopo; `insufficient` senza release date o dati. Soglie iniziali (≥30gg, ≥3 video pre) **da
tarare** sui dati reali.

### 7.3 Cosa scrivere nel report (IT/EN)
Sezione dedicata "Interesse pre-lancio" (chiavi `report_i18n.py::prelaunch_*`). Sempre
linguaggio di **co-occorrenza + disclaimer**: l'hype pre-esistente può derivare da
beta/EA/pre-order non misurabili. Nel payload `data["prelaunch"]` per i grafici (marker
"Early Access / hype pre-esistente" sulla timeline, da aggiungere lato GUI).

---

## 8. Ricerca per developer/publisher e track record del team

> Motivazione (utente): cercando **nome developer + nome editore + nome gioco** le ricerche
> sono più accurate — si scopre se il team ha già fatto altri giochi andati bene e si trovano i
> canali ufficiali.

### 8.1 Query
Oltre a `"<titolo>"` + suffissi (§3.3), quando si cerca il track record aggiungere alla query
YouTube i nomi `developer`/`publisher` (`GameQuery.developer/.publisher`, ora popolati). Es.:
`"Palworld" | "Palworld" gameplay | ... | "Pocketpair" game`. Escludere nomi vuoti/`unknown`;
dedup dev==publisher. La `cache_key` deve includere i termini team (altrimenti falso cache-hit).

### 8.2 Gating quota (deciso con l'utente)
La ricerca allargata (dev/publisher + video pre-lancio) costa più quota YouTube. Attivarla
**solo per i giochi promettenti** (`quality_score >= soglia`, non `discarded`) — vedi
`collector/jobs/social.py::run_social_collection`, flag `include_team`/`capture_pre_launch`.
Condividere UNA sola `QuotaTracker` per rispettare il budget 10k/giorno.

### 8.3 Track record → quality score
Il segnale "developer con altri giochi" alimenta la componente **segnali di cura (10%)**
(`quality_score.build_game_data` legge `care["developer_other_games"]` da
`game_snapshots.extra`). Stima proxy: altri video/canali dello stesso studio o altri titoli
sotto lo stesso publisher emersi dalla ricerca. **Limite dichiarato**: non abbiamo un catalogo
completo del dev → è un proxy incerto, mai una certezza; co-occorrenza, non causalità.
