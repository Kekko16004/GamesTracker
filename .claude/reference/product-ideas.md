# Product Ideas — GamesTracker come riferimento per i dev indie

> Documento di prodotto (dominio marketing/prodotto). Obiettivo dichiarato dell'utente:
> "voglio vedere i migliori, soprattutto indie" e capire **come farsi pubblicità / cosa funziona ORA**.
> Ogni idea è vincolata ai dati che possiamo realmente avere: **niente wishlist/vendite** (proxy
> pubblici — recensioni, player, owner SteamSpy, menzioni/engagement social). Reddit off per ora,
> TikTok/IG best-effort/manuale, YouTube via API con quota. Regola d'oro: **correlazione, non causalità**.
>
> Ordine: per priorità (alta → media). Effort: basso/medio/alto.

---

## 1. Benchmark per genere a percentili ("dove sono nella mia categoria")
**Descrizione.** Per ogni metrica-proxy (recensioni a +24h/+48h/+1w/+1mo, % positive, player di picco, owner
SteamSpy, densità menzioni) calcoliamo la distribuzione per genere sul corpus e la esponiamo a percentili.
Il dev inserisce il proprio gioco (o un target) e legge subito: "le tue 120 recensioni a +48h sono nel 71°
percentile dei cozy usciti negli ultimi 90 giorni". Non un numero assoluto senza contesto, ma un ranking.

**Perché è preziosa.** Il singolo dato ("ho 120 recensioni") non dice nulla; il percentile dice tutto. È
l'unica cosa che trasforma i nostri proxy in un giudizio azionabile: "sto andando bene o male *per il mio
genere*?". Elimina il confronto ingiusto tra generi (un horror e un city-builder hanno scale diverse).

**Come si implementa coi nostri dati.** Puramente derivato da `game_snapshots` + `games.genres/tags`. Serie
già raccolte: raggruppiamo per genere, allineiamo per "giorni-da-release" (non per data assoluta), calcoliamo
percentili 5/25/50/75/95 con pandas. Nessuna nuova sorgente. **Limite onesto:** con poche decine di giochi per
genere i percentili sono rumorosi → dichiarare N del campione e disabilitare il benchmark sotto una N minima
(es. < 8 giochi). SteamSpy owner solo come trend, non valore assoluto.

**Priorità: alta · Effort: medio.**

---

## 2. Case study automatici dei giochi "esplosi" ("cosa hanno fatto quelli che ce l'hanno fatta")
**Descrizione.** Rilevatore di breakout: individua nel corpus i giochi con accelerazione di crescita
anomala (pendenza recensioni/player molto sopra il baseline del loro genere) e ne ricostruisce la timeline
già prevista dal playbook (demo→release, Next Fest, cadenza post, top-3 post per engagement, punti di svolta).
Output: una scheda "case study" narrata, bilingue, riutilizzabile.

**Perché è preziosa.** È esattamente la richiesta dell'utente: vedere i migliori e capire cosa hanno fatto.
Invece di consigli generici, il dev legge playbook reali estratti da vincitori veri e recenti del suo genere.
È il contenuto che rende il tool un "riferimento" e non un cruscotto qualsiasi.

**Come si implementa coi nostri dati.** Riusa `analysis/reports.py` (timeline, punti di svolta) + il rilevatore
di crescita. La selezione "esploso" = crescita nel top percentile del genere (idea #1). La narrativa esiste già
(§4.5 playbook). **Limite onesto:** senza dati social raccolti la timeline è solo store (recensioni/player);
diventa ricca solo quando YouTube/Reddit popolano `social_posts`. E resta correlazione: elencare le concause
(sconto, festival, video di terzi) come già impone il playbook §4.3. Campione singolo = aneddoto, non regola.

**Priorità: alta · Effort: medio** (basso se si riusa reports.py, medio per la selezione + narrativa dedicata).

---

## 3. Radar di crescita + alert sui giochi in rapida ascesa
**Descrizione.** Un job che, a ogni ciclo di snapshot, ricalcola la velocità di crescita di ogni gioco
rispetto al suo baseline e al genere, e segnala in GUI i "rising" (accelerazione forte) e i "breakout
candidate" (rising + sopra percentile). Pannello "In ascesa ora" ordinato per momentum, con badge per genere.

**Perché è preziosa.** Cattura le opportunità *mentre* accadono, non a posteriori. Il dev vede oggi quale gioco
del suo genere sta decollando, ci va a guardare la strategia, impara in tempo reale. È anche il gancio che fa
riaprire l'app ogni giorno (valore ricorrente).

**Come si implementa coi nostri dati.** Derivata seconda su `game_snapshots` (variazione di pendenza tra
finestre), confronto col baseline di genere (idea #1). Alert = riga in una tabella `alerts` o flag in GUI; nessuna
notifica di rete. **Limite onesto:** con snapshot a 24h/48h/1w/1mo la risoluzione temporale è bassa → un "rapido"
lo vediamo con lag di ore/giorni, non minuti. Onesto e sufficiente per il caso d'uso. Filtrare i falsi positivi
da review-bomb (usare `filter_offtopic_activity`) e da picchi di rumore su numeri piccoli (log-scala + soglia N).

**Priorità: alta · Effort: medio.**

---

## 4. "Il mio gioco vs i top del genere" — overlay comparativo normalizzato
**Descrizione.** Il dev aggiunge il proprio gioco (via appid Steam o import manuale se non ancora uscito) e ne
sovrappone la traiettoria a quella dei top-K del suo genere, **allineata per giorni-da-release** (curve
sovrapposte partendo da t=0). Vede a colpo d'occhio se è sopra o sotto la mediana e la banda dei migliori.

**Perché è preziosa.** Rende personale e concreto il benchmark: non "il genere fa X" ma "TU stai facendo X
rispetto ai migliori". È lo strumento che un dev userebbe la settimana del lancio e ogni giorno dopo, per capire
se la sua curva ha la forma giusta. Trasforma i dati altrui in una bussola per il proprio gioco.

**Come si implementa coi nostri dati.** Grafico pyqtgraph con più serie da `game_snapshots`, ri-origine su
`release_date` di ciascun gioco, banda percentile (5–95) come area. Riusa la normalizzazione dell'idea #1. Il
"mio gioco" è una entry `games` come le altre. **Limite onesto:** confrontiamo proxy (recensioni/player), non
wishlist/vendite; la "forma" della curva è indicativa, non predittiva del fatturato. Dichiararlo nel grafico.

**Priorità: alta · Effort: medio.**

---

## 5. Pattern di timing per genere (Next Fest, giorno/mese di lancio, gap demo→release)
**Descrizione.** Aggregatore che, sul corpus, estrae i pattern di timing che *co-occorrono* con crescita
migliore: gap demo→release ottimale, partecipazione a Next Fest, giorno della settimana e mese di release,
stagionalità. Output per genere: "gli horror con demo pubblicata 30–60 gg prima al Next Fest mostrano, sul
nostro campione (N=…), una crescita recensioni al lancio mediana superiore".

**Perché è preziosa.** Il timing è una delle poche leve che un dev controlla al 100% e a costo zero. Sapere
quando lanciare e quando far uscire la demo, con evidenza dal proprio genere, vale più di mille consigli generici.

**Come si implementa coi nostri dati.** Join tra `games` (demo/release date), calendario eventi in config
(§4.4 playbook, date Next Fest pubbliche) e crescita da `game_snapshots`. Statistica descrittiva con pandas,
segmentata per genere. **Limite onesto:** puro osservazionale, mai causale — chi va al Next Fest è già più curato
di media (bias di selezione). Dichiarare N e che è co-occorrenza. Serve un campione decente per genere per non
dare pattern-da-rumore.

**Priorità: alta · Effort: medio.**

---

## 6. Leaderboard "migliori indie per genere" + Genre Health (cosa tira ORA)
**Descrizione.** Due viste gemelle. **Leaderboard:** i top indie per genere ordinati per uno score comparabile
(momentum + qualità + reception), aggiornata a ogni ciclo. **Genre Health:** per ogni genere volume di nuove
uscite, crescita mediana, saturazione (quanti escono vs quanti crescono), tendenza nel tempo — un "cosa è caldo /
cosa è saturo adesso".

**Perché è preziosa.** Risponde direttamente a "voglio vedere i migliori, soprattutto indie" e a "quali generi
tirano ora". È utile a monte (decidere cosa sviluppare, leggere la saturazione) e per scoprire i giochi da studiare.
È anche il contenuto-vetrina che rende il tool un riferimento.

**Come si implementa coi nostri dati.** Query aggregate su `games` + `game_snapshots` + `quality_score`, raggruppate
per genere. La leaderboard riusa il momentum (#3) e il quality score esistente. **Limite onesto:** "indie" va
definito con euristica (assenza di grande publisher, prezzo, dimensione team come proxy incerti) — dichiarare i
criteri. La saturazione è misurata sul *nostro* corpus di uscite recenti, non su tutto Steam: è un campione, non il
censimento.

**Priorità: alta · Effort: medio.**

---

## 7. Audit della pagina store vs i top del genere (pre-lancio azionabile)
**Descrizione.** Estende il simulatore di quality score: analizza la pagina store del gioco del dev (trailer, n°
screenshot, lunghezza descrizione, tag/generi, header) e la confronta con la mediana dei top del suo genere,
producendo una gap-analysis concreta: "i top roguelike hanno in media 14 screenshot e un trailer < 90s; tu ne hai
6 e nessun trailer".

**Perché è preziosa.** È il consiglio più immediatamente eseguibile che possiamo dare: azioni di pre-lancio a
costo quasi zero, con impatto reale sulla conversione della pagina. Chiude il loop "analizzo gli altri → miglioro
il mio" prima ancora di spendere in marketing.

**Come si implementa coi nostri dati.** Riusa i campi già raccolti via Steam appdetails (screenshot, trailer,
descrizione, tag) che alimentano la componente "qualità pagina store" del quality score. Confronto con i benchmark
di genere (#1). **Limite onesto:** vale per Steam (pagina ispezionabile); itch non espone gli stessi campi → audit
degradato o assente per itch (coerente con `quality-score.md`). Misuriamo *presenza/quantità*, non qualità estetica
del contenuto.

**Priorità: alta · Effort: basso** (grosso riuso del quality score e del simulatore già esistenti).

---

## 8. Watchlist competitiva + digest dei cambiamenti
**Descrizione.** Il dev flagga i giochi che gli interessano (concorrenti diretti, ispirazioni, titoli del suo
genere) in una watchlist. Il tool produce una dashboard focalizzata solo su quelli e un "digest" periodico:
cosa è cambiato dall'ultima volta (nuova demo, salto di recensioni, nuovo video, cambio prezzo, punto di svolta).

**Perché è preziosa.** Riduce il rumore: invece di monitorare centinaia di uscite, il dev tiene d'occhio i 10–20
che contano per lui. Il digest è ciò che lo fa tornare (valore ricorrente) e gli dà intelligence competitiva
continua senza sforzo manuale.

**Come si implementa coi nostri dati.** Tabella `watchlist` (game_id + note), viste GUI filtrate, digest = diff
tra snapshot successivi già in `game_snapshots` + eventi da `games`/`social_posts`. Nessuna sorgente nuova.
**Limite onesto:** il digest ha la granularità degli snapshot (24h/48h/1w/1mo); i cambiamenti compaiono al
prossimo ciclo, non in tempo reale. Sufficiente per intelligence competitiva.

**Priorità: media · Effort: basso.**

---

## 9. Impatto streamer/press per genere ("a chi conviene mandare la key")
**Descrizione.** Sul corpus, incrocia i video YouTube di terzi (canali con molti iscritti che citano un gioco)
con i punti di svolta della crescita, aggregando per genere: quali canali/tipi di canale co-occorrono più spesso
con spike di crescita nei giochi di un genere. Output: una shortlist ragionata di canali potenzialmente rilevanti
per quel genere, con l'engagement osservato.

**Perché è preziosa.** L'outreach a streamer/press è una delle azioni ad alto impatto e alta incertezza per un
indie: sapere *chi* copre i giochi del tuo genere e la cui copertura ha coinciso con crescita è oro. Trasforma un
lavoro di ricerca manuale in una lista basata su dati.

**Come si implementa coi nostri dati.** YouTube `search.list`/`videos.list`/`channels.list` (già previsti) per i
video di terzi + `channels.subscriberCount`; correlazione col picco su `game_snapshots` (§1.7 playbook).
Aggregazione per genere. **Limite onesto:** dipende dalla quota YouTube (attivare solo sui giochi promettenti,
§8.2) e resta co-occorrenza forte ma non causale (poteva esserci sconto/festival in contemporanea). Non
raccomandare mai un canale come "garanzia": è "canali la cui copertura ha coinciso con crescita, sul campione".
Nessuna raccolta di dati personali oltre a metriche pubbliche del canale.

**Priorità: media · Effort: alto** (dipende dai dati social YouTube, ancora non popolati).

---

## 10. Report periodico condivisibile "State of Indie \<genere\>" (bilingue, esportabile)
**Descrizione.** Genera un report mensile/trimestrale per genere — "State of Indie Horror, luglio 2026" — che
sintetizza: top del periodo, generi in salita/discesa, pattern di timing osservati, 1–2 mini case study (idea #2),
benchmark chiave. Esportabile in PDF/Markdown bilingue IT/EN, pensato per essere letto e condiviso.

**Perché è preziosa.** È il pezzo che rende GamesTracker un *riferimento* riconosciuto e non solo un tool privato:
un artefatto che il dev può consultare, archiviare e condividere. Consolida tutte le altre feature in una narrazione
digeribile e ricorrente.

**Come si implementa coi nostri dati.** Composizione delle idee #1/#2/#5/#6 in un template di report; riusa
`analysis_reports` (chiave `genre`), l'i18n esistente (`report_i18n.py`) e l'export matplotlib già previsto per i
grafici statici. **Limite onesto:** ogni affermazione va etichettata come osservazione sul nostro corpus (N
dichiarato, co-occorrenza non causalità); la qualità del report scala con la copertura dei dati raccolti. Nessuna
pubblicazione automatica: l'export è locale, la condivisione la decide l'utente.

**Priorità: media · Effort: medio.**

---

## 11. Linter della descrizione store ("cosa non va nel testo della tua pagina")
**Descrizione.** Un analizzatore testuale della descrizione breve + lunga della pagina Steam che produce un
referto azionabile: lunghezza fuori scala rispetto ai top del genere, prime 2 righe (l'above-the-fold prima del
"Leggi tutto") vuote di gancio, muro di testo senza header/bullet, densità di aggettivi vuoti ("incredibile
esperienza unica"), assenza di parole-chiave di genere che i top usano, presenza/assenza di una riga-hook
iniziale. Output: checklist di correzioni concrete, non un voto opaco.

**Perché è preziosa.** La descrizione è testo che il dev può riscrivere stasera a costo zero, ed è la prima cosa
che un visitatore legge. Trasformiamo un'analisi soggettiva ("è scritta bene?") in gap misurabili rispetto a chi
nel suo genere sta crescendo. È l'azione più economica con effetto diretto sulla comprensione dell'offerta.

**Come si implementa coi nostri dati.** Su `detailed_description`/`short_description` da Steam appdetails (già
raccolti per il quality score) applichiamo metriche testuali con pandas/regex: conteggio parole, presenza di tag
HTML struttura (`<h2>`, liste), estrazione keyword vs il vocabolario dei top del genere (idea #1). **Limite
onesto:** misuriamo struttura e presenza di elementi, non la qualità retorica o l'accuratezza delle promesse; il
"gancio" lo rileviamo per euristica, non capiamo davvero se convince. Solo Steam (itch non espone campi
equivalenti in modo affidabile). Il vocabolario-top è correlazione col nostro corpus, non una formula vincente.

**Priorità: alta · Effort: basso.**

---

## 12. Autopsia dei tag e della scopribilità ("con questi tag chi ti trova?")
**Descrizione.** Confronta i tag/generi del gioco con quelli dei top e dei diretti concorrenti del suo cluster:
segnala tag mancanti che i vincitori del genere usano quasi tutti, tag troppo generici (alta competizione, poca
identità), tag di nicchia sotto-sfruttati, e incoerenze (tag che non co-occorrono mai con la crescita nel corpus).
Restituisce una lista ordinata di "tag da aggiungere / valutare / togliere" con la loro frequenza tra i top.

**Perché è preziosa.** Su Steam i tag guidano la scopribilità (code di raccomandazione, hub, "More like this").
Sono modificabili in pochi minuti e spesso trascurati. Dare al dev la mappa di quali tag usano quelli che il suo
pubblico già gioca è una leva di visibilità organica quasi gratuita.

**Come si implementa coi nostri dati.** Analisi di frequenza e co-occorrenza sui `tags/genres` in `games`,
segmentata per genere e incrociata col momentum (idea #3) per identificare i tag associati a crescita nel corpus.
**Limite onesto:** i tag Steam sono in parte assegnati dagli utenti e cambiano nel tempo; noi vediamo lo snapshot
al momento della raccolta. Correlazione tag↔crescita non implica che aggiungere il tag causerà crescita (il tag
riflette il contenuto, non lo crea). Non conosciamo l'algoritmo di raccomandazione di Steam: inferiamo, non sappiamo.

**Priorità: alta · Effort: basso.**

---

## 13. Rilevatore di red-flag della pagina ("le criticità che ti stanno costando visibilità")
**Descrizione.** Un motore di regole che scandaglia la pagina store e accende bandiere rosse concrete: nessun
trailer, meno di N screenshot, screenshot tutti di menu/UI e nessuno di gameplay leggibile (euristica su
risoluzione/aspetto), header capsule assente o testo illeggibile, descrizione sotto la soglia minima, nessuna
demo in un genere dove i top ce l'hanno, prezzo assente/incoerente, mancanza di localizzazione dichiarata nei
mercati che i concorrenti coprono. Ogni flag ha severità e "come si risolve".

**Perché è preziosa.** Il dev spesso non sa cosa manca perché guarda la sua pagina dall'interno. Una checklist di
criticità prioritizzate — "questi 3 problemi sono quelli che i top del tuo genere non hanno mai" — è esattamente
il "quali sono le CRITICITÀ" richiesto. È triage: prima spegni gli incendi, poi ottimizzi.

**Come si implementa coi nostri dati.** Regole deterministiche sui campi Steam appdetails già usati dal quality
score (screenshots, movies, description, price_overview, supported_languages, header_image) + soglie derivate dai
benchmark di genere (idea #1). **Limite onesto:** "screenshot di gameplay vs menu" è euristica fragile su
metadati d'immagine, da marcare come "possibile" non "certo". Solo Steam. Un flag è un'anomalia rispetto ai top,
non una prova che stia danneggiando le vendite (che non vediamo).

**Priorità: alta · Effort: basso.**

---

## 14. Checklist di lancio interattiva e datata ("cosa fare, e quando, prima del D-day")
**Descrizione.** Una checklist pre-lancio generata dalla release date del dev e retro-datata per genere: cosa
fare a -90/-60/-30/-14/-7/-1 giorni (pubblica demo, iscriviti al prossimo Next Fest utile, prepara press key,
apri il thread nei subreddit rilevanti, pianifica la cadenza post ottimale osservata). Ogni voce è spuntabile,
collegata al pattern di timing del genere (idea #5) e al calendario eventi Steam pubblico.

**Perché è preziosa.** Trasforma la strategia in un piano operativo con date reali. Il "cosa fare" astratto
diventa un task list che il dev può eseguire. Riduce l'errore più comune degli indie: arrivare al lancio senza
aver costruito nulla prima, o mancare la finestra del Next Fest.

**Come si implementa coi nostri dati.** Template di task parametrizzato sulla `release_date` del gioco in
watchlist (idea #8), con le finestre ottimali stimate dall'idea #5 e le date dei festival dal calendario in config.
Stato dei check in una tabella locale. **Limite onesto:** le finestre "ottimali" sono co-occorrenze osservate sul
corpus, non garanzie; le date dei festival futuri vanno mantenute a mano in config quando Valve le annuncia. La
checklist ricorda, non esegue: l'outreach e la pubblicazione restano azioni umane.

**Priorità: alta · Effort: medio.**

---

## 15. Anatomia delle capsule/screenshot dei top ("come sono fatte le immagini che convertono")
**Descrizione.** Analisi aggregata degli asset visivi dei top del genere: numero mediano di screenshot, presenza
e durata del trailer, uso di testo/GIF, rapporto screenshot-di-gameplay vs artwork. Ne deriva una scheda di best
practice per genere ("i cozy top hanno 8-12 screenshot molto colorati, trailer 45-70s, capsule con nome grande")
e confronta i tuoi asset con quel profilo.

**Perché è preziosa.** La capsule è il singolo asset che decide il click nella griglia di Steam, e gli screenshot
decidono lo scroll. Dare al dev il "profilo visivo" dei vincitori del suo genere orienta il lavoro
dell'artista/grafico verso ciò che il pubblico di quel genere si aspetta di vedere.

**Come si implementa coi nostri dati.** Metadati di `screenshots`/`movies` da Steam appdetails (conteggio, durata
video, dimensioni immagine) aggregati per genere; il confronto riusa i benchmark (idea #1). **Limite onesto:**
leggiamo quantità e metadati tecnici, NON l'estetica, la composizione o la leggibilità reale (non facciamo
computer vision). È un profilo strutturale, non un giudizio artistico. Le capsule variano per contesto (griglia,
wishlist, hub) e noi vediamo solo gli asset dichiarati nell'appdetails.

**Priorità: media · Effort: basso.**

---

## 16. Hype pre-esistente vs crescita organica da lancio ("sei partito da zero o da una base?")
**Descrizione.** Classifica ogni breakout del corpus in due profili: crescita "a razzo dal giorno 0" (segnali
già alti prima del lancio — molti follower/menzioni social pre-release, video di terzi precoci) vs crescita
"organica costruita nel tempo" (curva che accelera settimane dopo il lancio dal basso). Per il gioco del dev
mostra quale traiettoria realistica gli assomiglia di più e quali leve restano.

**Perché è preziosa.** Evita il consiglio-cargo-cult: copiare un gioco che è esploso perché aveva già 200k
follower non aiuta chi parte da zero. Separare "aveva già un pubblico" da "l'ha costruito dopo" dice al dev quali
case study sono davvero replicabili nella sua situazione e quali no. È onestà strategica.

**Come si implementa coi nostri dati.** Confronto tra il livello dei proxy nella finestra pre-release (menzioni
social, video di terzi, follower account ufficiale se raccolti) e la pendenza post-release su `game_snapshots`.
Etichetta a soglie relative al genere. **Limite onesto:** i dati social pre-release sono spesso incompleti o
assenti (Reddit off, TikTok/IG best-effort) → la classificazione può degradare a "ignoto". Il pre-esistente lo
stimiamo, non lo misuriamo con precisione. Etichette indicative, non un verdetto sul destino del gioco.

**Priorità: media · Effort: medio.**

---

## 17. Mappa dei concorrenti diretti ("chi gioca contro di te, non solo il genere")
**Descrizione.** Oltre al genere, trova i concorrenti *diretti* del gioco tramite similarità di tag, prezzo,
fascia di uscita e cluster tematico, e li presenta come una matrice: chi cresce di più, chi ha la pagina più
forte (dal linter/red-flag), chi ha una demo, dove ognuno è più forte/debole. Non "il genere horror" ma "questi
6 titoli sono quelli con cui competi per lo stesso click".

**Perché è preziosa.** Il benchmark di genere è ampio; la concorrenza reale è un pugno di titoli sovrapposti. Dare
al dev quel piccolo insieme, con i loro punti di forza/debolezza sulla pagina, rende il confronto competitivo
tangibile e gli mostra dove può differenziarsi concretamente.

**Come si implementa coi nostri dati.** Similarità coseno/Jaccard sui vettori di tag di `games`, filtrata per
fascia temporale e prezzo, poi arricchita con momentum (idea #3) e i referti pagina (idee #11/#13). **Limite
onesto:** la similarità di tag approssima la concorrenza percepita, ma due giochi con tag simili possono avere
pubblici diversi; noi non vediamo l'overlap reale di pubblico (nessun dato utente). È un cluster ragionato sul
nostro corpus di uscite recenti, non l'universo Steam completo.

**Priorità: media · Effort: medio.**

---

## 18. Sanità della cadenza social ("posti troppo poco, troppo, o tutto trailer?")
**Descrizione.** Analizza la timeline dei post dell'account ufficiale del dev (import manuale/YouTube) contro la
cadenza osservata nei top del genere: frequenza (post/settimana), regolarità (silenzi lunghi = red flag), mix di
formati, e distanza temporale dal lancio. Segnala anomalie: "silenzio di 40 giorni prima del lancio", "solo
annunci, nessun gameplay", "picco di post concentrati e poi nulla".

**Perché è preziosa.** La costanza di comunicazione è una leva 100% sotto controllo del dev, e gli errori (sparire,
postare solo il trailer, spammare al lancio e poi tacere) sono comuni e correggibili. Dargli uno specchio contro
la cadenza dei vincitori del genere rende concreto il "cosa migliorare nel marketing".

**Come si implementa coi nostri dati.** Serie temporale su `social_posts`/`social_accounts` del gioco vs
aggregato dei top di genere; metriche di frequenza e gap con pandas. **Limite onesto:** i dati social del dev sono
per lo più import manuale o best-effort (decisione locked §2b): se non li carica, l'analisi non parte. La cadenza
correla con l'attenzione ma non la causa; e YouTube (l'unica fonte via API) copre solo un canale. Non giudichiamo
la qualità creativa del singolo post, solo la struttura della cadenza.

**Priorità: media · Effort: medio.**

---

## 19. Rilevatore di trash/spam marketing ("stai facendo cose che ti penalizzano?")
**Descrizione.** Un set di segnali che scova pattern di marketing controproducenti nel corpus e li usa sia per
penalizzare il quality score sia per avvertire il dev sul proprio gioco: descrizione con keyword-stuffing di tag
irrilevanti, screenshot ingannevoli (asset store generici), promesse vaghe senza gameplay mostrato, sospetto di
recensioni gonfiate (spike anomalo di recensioni positive brevi in poche ore), auto-posting identico e ripetuto.

**Perché è preziosa.** Il "cosa NON fare" è prezioso quanto il "cosa fare". Molti indie affossano la propria
credibilità con tattiche che sembrano furbe (tag-spam, review inflation, hype vuoto) e che il pubblico e a volte
Steam penalizzano. Renderle visibili aiuta a evitarle e alimenta i pesi negativi del quality score.

**Come si implementa coi nostri dati.** Regole su `games` (tag vs contenuto), su `review_snapshots` (usare
`filter_offtopic_activity` e cercare burst anomali di recensioni brevi/positive), su `social_posts` (rilevare
testi duplicati). Alimenta i pesi negativi in `quality-score.md`. **Limite onesto:** non possiamo *provare* la
frode (nessun accesso ai dati privati di Steam); segnaliamo "pattern sospetti" con probabilità, mai accuse certe.
Rischio di falsi positivi su giochi legittimamente virali → soglie prudenti e sempre spiegabili.

**Priorità: media · Effort: medio.**

---

## 20. Segnale sentiment dalle recensioni ("cosa lodano e cosa criticano i giocatori")
**Descrizione.** Estrae dal testo delle recensioni Steam i temi ricorrenti positivi e negativi per gioco e per
genere: parole/bigrammi più frequenti nelle recensioni positive vs negative, evoluzione nel tempo (i bug citati
al lancio spariscono dopo una patch?), e confronto col genere ("nel tuo genere i top vengono lodati per X, tu
vieni criticato per Y"). Output: le 5 leve di miglioramento più citate.

**Perché è preziosa.** Le recensioni sono l'unica voce diretta del pubblico che possiamo leggere legalmente e in
volume. Aggregarle in temi azionabili dice al dev cosa correggere nel prodotto e cosa enfatizzare nella pagina —
un ponte tra marketing e product che gli altri strumenti non offrono.

**Come si implementa coi nostri dati.** NLP leggero (frequenze, n-grammi, eventualmente un lessico di sentiment)
sul testo di `review_snapshots` già raccolto, segmentato per voto e per periodo. Nessuna nuova sorgente. **Limite
onesto:** analisi lessicale, non comprensione profonda: sarcasmo, contesto e lingue diverse la confondono. Le
recensioni sono un campione auto-selezionato (chi scrive è più polarizzato). Descriviamo temi ricorrenti, non
"la verità" sul gioco. Solo Steam (itch raramente ha recensioni testuali comparabili).

**Priorità: media · Effort: medio.**

---

## 21. Punteggio di prontezza al lancio ("sei davvero pronto a uscire?")
**Descrizione.** Un indice sintetico 0-100 *pre-lancio* che aggrega i referti azionabili — completezza pagina
(linter #11, red-flag #13), qualità tag/scopribilità (#12), presenza demo e allineamento al timing (#14), cadenza
social (#18) — in un unico "readiness score" con il dettaglio di quali componenti ti stanno abbassando il punteggio
e cosa fare per alzarle. Diverso dal quality score (che valuta un gioco uscito): questo prepara al lancio.

**Perché è preziosa.** Dà al dev un unico numero-bussola prima del D-day e una to-do ordinata per impatto: "sei a
62/100, il buco più grosso è l'assenza di trailer e di demo". È il cruscotto di pre-lancio che riassume tutte le
idee di audit in una singola risposta a "sono pronto?".

**Come si implementa coi nostri dati.** Composizione pesata degli output delle idee #11/#12/#13/#14/#18, riusando
i campi Steam appdetails e i benchmark di genere (#1). Nessuna sorgente nuova, solo aggregazione. **Limite onesto:**
è un indice di *completezza e allineamento ai pattern del corpus*, NON una previsione di successo commerciale (che
dipende da vendite/wishlist invisibili e dalla qualità del gioco stesso). Un 90/100 dice "pagina e piano curati",
non "venderai". Va comunicato chiaramente per non illudere.

**Priorità: media · Effort: medio.**

---

## 22. Simulatore "e se..." per le azioni di pagina ("quanto sposta aggiungere un trailer?")
**Descrizione.** Un what-if interattivo: il dev spunta azioni ipotetiche (aggiungo trailer, porto gli screenshot
da 6 a 12, aggiungo 3 tag mancanti, pubblico una demo) e vede come cambierebbero il suo readiness score (#21) e la
sua posizione nei benchmark di genere. Non promette vendite: mostra di quanto si avvicinerebbe al profilo dei top.

**Perché è preziosa.** Rende il miglioramento un gioco di priorità: il dev vede subito quale azione lo avvicina di
più ai vincitori a parità di sforzo, e prioritizza. Trasforma l'audit statico in una leva decisionale ("faccio
prima il trailer o i tag?").

**Come si implementa coi nostri dati.** Ricalcolo locale del readiness score (#21) e del posizionamento a
percentili (#1) sostituendo i valori dei campi toccati dall'azione ipotetica. Puramente derivato, nessuna rete.
**Limite onesto:** simula solo l'effetto sui *nostri indici di completezza/allineamento*, non sulle conversioni o
vendite reali (invisibili). È "quanto ti avvicini al profilo dei top", non "quanto venderai in più". Il rischio è
che l'utente lo legga come predittivo: etichettare esplicitamente ogni numero come strutturale, non commerciale.

**Priorità: bassa · Effort: medio.**

---

## 23. Termometro della finestra di lancio ("chi altro esce nella tua settimana?")
**Descrizione.** Data una release date, mostra l'affollamento della finestra: quanti e quali giochi dello stesso
genere/tag escono a ±7 giorni, il loro momentum e forza-pagina, ed eventuali big release o eventi Steam che
oscurano quella settimana. Segnala "settimana rossa" (troppa concorrenza diretta) e suggerisce finestre vicine
meno sature sul nostro corpus.

**Perché è preziosa.** Scegliere la data di lancio è una leva gratuita e spesso decisa a caso. Sapere di uscire lo
stesso giorno di 4 concorrenti diretti — o durante un evento che monopolizza l'attenzione — permette di spostarsi
di una settimana e respirare. Concreto, azionabile, a costo zero.

**Come si implementa coi nostri dati.** Query su `games.release_date` filtrata per cluster di tag/genere (idea
#17) nella finestra ±N giorni, incrociata col calendario eventi in config. **Limite onesto:** vediamo solo le
uscite nel *nostro* corpus (uscite indie recenti raccolte), non tutto il calendario Steam: l'affollamento è
sottostimato e va dichiarato come "sul monitorato". Le release date future cambiano spesso (i rinvii sono comuni):
è una foto al momento, da riguardare. Nessun accesso al calendario ufficiale completo di Valve.

**Priorità: bassa · Effort: basso.**

---

## 24. Autopsia del post-lancio ("cosa succede dopo lo spike, e come tenerlo vivo")
**Descrizione.** Analizza la fase *dopo* il picco di lancio nel corpus: quanto velocemente decade la crescita di
recensioni/player per genere (half-life del lancio), quali giochi hanno avuto una "seconda vita" (update
maggiori, sconti, festival, uscita da Early Access) e cosa co-occorre con quei rimbalzi. Per il gioco del dev,
suggerisce le leve post-lancio osservate come più spesso associate a un secondo picco.

**Perché è preziosa.** Molti indie pianificano solo fino al D-day e poi non sanno cosa fare con la "coda". Sapere
quanto dura tipicamente lo slancio nel proprio genere e quali mosse hanno riacceso la crescita di altri (patch
1.0, sconto stagionale, evento) dà un piano post-lancio concreto invece del silenzio.

**Come si implementa coi nostri dati.** Analisi di decadimento sulle serie `game_snapshots` oltre il picco;
rilevazione di secondi picchi e loro co-occorrenza con eventi noti (sconti da `price_overview`, festival da
config, salto versione). **Limite onesto:** puro osservazionale — un update co-occorre con un rimbalzo ma poteva
coincidere con uno sconto o un video virale; non isoliamo la causa. Half-life stimata su proxy pubblici, non su
vendite. Campione per genere spesso piccolo per la fase lunga (1mo): dichiarare N.

**Priorità: bassa · Effort: alto.**

---

## 25. Score card esportabile della pagina ("il referto di una pagina in un colpo d'occhio")
**Descrizione.** Un artefatto compatto ed esportabile (PDF/Markdown, bilingue) che riassume l'intero audit di un
singolo gioco: readiness score (#21), red-flag prioritizzate (#13), gap sui tag (#12) e sugli asset (#15), note
del linter descrizione (#11), posizione a percentili nel genere (#1) e le 3 azioni a più alto impatto. Pensato per
essere salvato, condiviso col team/artista o riletto a distanza di settimane.

**Perché è preziosa.** Consolida tutte le analisi di pagina in un documento che il dev può passare a un
collaboratore ("ecco cosa sistemare sulla capsule") o usare come baseline da ricontrollare dopo le modifiche.
Rende l'audit tangibile e condivisibile, non solo una schermata effimera nell'app.

**Come si implementa coi nostri dati.** Composizione degli output delle idee di audit in un template che riusa
`analysis_reports`, l'i18n (`report_i18n.py`) e l'export matplotlib/Markdown già previsti (come l'idea #10, ma
focalizzato sul singolo gioco anziché sul genere). **Limite onesto:** vale principalmente per Steam (l'audit di
pagina è ricco lì); per itch il referto è ridotto. Fotografa lo stato al momento dell'export: va rigenerato dopo
le modifiche. Ogni voce eredita i limiti onesti delle idee sorgenti (strutturale, non predittivo di vendite).

**Priorità: bassa · Effort: basso.**

---

## Sintesi priorità/effort

| # | Idea | Priorità | Effort |
|---|---|---|---|
| 1 | Benchmark per genere a percentili | alta | medio |
| 2 | Case study automatici dei giochi esplosi | alta | medio |
| 3 | Radar di crescita + alert | alta | medio |
| 4 | Il mio gioco vs i top del genere | alta | medio |
| 5 | Pattern di timing per genere | alta | medio |
| 6 | Leaderboard + Genre Health | alta | medio |
| 7 | Audit pagina store vs top del genere | alta | basso |
| 8 | Watchlist + digest | media | basso |
| 9 | Impatto streamer/press per genere | media | alto |
| 10 | Report periodico condivisibile per genere | media | medio |
| 11 | Linter della descrizione store | alta | basso |
| 12 | Autopsia dei tag e della scopribilità | alta | basso |
| 13 | Rilevatore di red-flag della pagina | alta | basso |
| 14 | Checklist di lancio interattiva e datata | alta | medio |
| 15 | Anatomia delle capsule/screenshot dei top | media | basso |
| 16 | Hype pre-esistente vs crescita organica | media | medio |
| 17 | Mappa dei concorrenti diretti | media | medio |
| 18 | Sanità della cadenza social | media | medio |
| 19 | Rilevatore di trash/spam marketing | media | medio |
| 20 | Segnale sentiment dalle recensioni | media | medio |
| 21 | Punteggio di prontezza al lancio | media | medio |
| 22 | Simulatore "e se..." per le azioni di pagina | bassa | medio |
| 23 | Termometro della finestra di lancio | bassa | basso |
| 24 | Autopsia del post-lancio | bassa | alto |
| 25 | Score card esportabile della pagina | bassa | basso |

**Fondamenta trasversali (da fare prima):** l'idea #1 (benchmark a percentili normalizzati per genere e allineati
per giorni-da-release) è il mattone su cui poggiano #2, #3, #4, #6, #7, #10. Conviene implementarla per prima come
libreria di analisi riusabile in `analysis/`.


