# Quality Score (0-100) — spec anti-trash

Obiettivo: separare i giochi "validi" dal trash (Steam è pieno di asset-flip e giochi di bassissima qualità). Ogni gioco riceve un punteggio 0-100. La **soglia di cutoff è configurabile** nella GUI (slider). Sotto soglia → `discarded = true` (non cancellato, solo filtrato dalle viste di default).

## Composizione (pesi indicativi, da tarare)
Il punteggio è una somma pesata di sottopunteggi normalizzati 0-1, poi ×100.

| Componente | Peso | Segnali |
|---|---|---|
| **Qualità pagina store** | 25% | presenza trailer, n° screenshot, lunghezza descrizione, presenza tag/generi sensati, header image |
| **Reception recensioni** | 30% | % recensioni positive, n° recensioni (log-scalato), review_score_desc |
| **Engagement social** | 20% | presenza account social attivi, menzioni Reddit/YouTube, volume post |
| **Crescita** | 15% | delta recensioni/player tra snapshot (traiettoria positiva) |
| **Segnali di cura** | 10% | ha demo, developer con altri giochi, prezzo non sospetto, sito ufficiale |

## Penalità (flag trash)
Riducono forte il punteggio o forzano discard:
- Nessuno screenshot / nessun trailer.
- Descrizione vuota o placeholder.
- Tag di asset-flip noti / pattern di publisher spam (lista mantenuta dal research-scout).
- Prezzo 0 + zero contenuti social + zero recensioni (probabile shovelware).

## Note implementative
- Il calcolo vive in `analysis/quality_score.py`, pura funzione su dati DB → testabile.
- Ricalcolare a ogni nuovo snapshot (il punteggio evolve nel tempo).
- Salvare l'ultimo score in `games.quality_score` e la storia negli snapshot se serve.
- I pesi vanno in config così l'utente può ritararli senza toccare il codice.
- **Da validare sul campo**: il data-analyst deve verificare i pesi contro giochi reali noti (buoni vs trash) e aggiustare.

## Taratura sul corpus reale (2026-07-21, sessione 3)
Prima calibrazione su dati veri (76 giochi: 40 Steam + 36 itch, uscite recenti):
- **`REF_REVIEWS` 2000 → 24000** (~p95 del corpus Steam). Il valore 2000 era vicino al p75
  reale (2101) e faceva **saturare** il segnale volume: un gioco mediano (~880 recensioni)
  otteneva già ~0.9, schiacciando tutti in alto. Ora il volume differenzia davvero.
- **`REF_MENTIONS_ENGAGEMENT` e `REF_POST_COUNT` restano provvisori**: nessun dato social
  ancora raccolto (componente social neutra 0.5 per tutti). Ritarare sui percentili social
  quando il job YouTube avrà popolato `social_posts`.
- **Fix penalità per pagine non ispezionabili (itch):** le penalità `no_screenshots`/
  `no_trailer`/`empty_description`/`hard_trash` si applicano SOLO quando la pagina è stata
  effettivamente ispezionata per quei campi (`store_inspected=True`, vero per Steam via
  appdetails; falso per itch che non li espone). Distinguere "pagina vuota" da "dato non
  raccoglibile" evita di penalizzare gli itch per dati inesistenti (allineato a
  marketing-playbook §2.5). Prima del fix gli itch erano tutti ~10; dopo 58-62.
- Distribuzione osservata post-taratura: Steam 54-72, itch 58-62, Palworld 70.1. Compressione
  **onesta**: con social+growth neutri (0.5) la differenziazione viene solo da store+reviews;
  gli score si allargheranno con i dati social e le serie storiche multiple. Soglia discard: 40.
