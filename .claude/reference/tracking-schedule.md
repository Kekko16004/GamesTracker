# Schedule di tracking

Ogni gioco scoperto genera una serie di snapshot programmati rispetto alla sua `first_seen_at` (o `release_date` se più appropriato — da decidere per metrica).

## Snapshot canonici
| tipo | offset dalla scoperta | scopo |
|---|---|---|
| `discovery` | t0 | baseline al momento della scoperta |
| `h24` | +24 ore | crescita immediata |
| `h48` | +48 ore | crescita a 2 giorni |
| `w1` | +7 giorni | crescita a 1 settimana |
| `m1` | +30 giorni | crescita a 1 mese |

## Regole di backfill (importante)
L'utente ha chiesto esplicitamente: **se mancano gli snapshot precedenti, si registra comunque quello disponibile andando a ritroso**.
- Se il gioco è scoperto in ritardo (es. lo troviamo già 10 giorni dopo l'uscita): non abbiamo h24/h48, ma registriamo subito un `discovery` e pianifichiamo `w1`/`m1` a partire dalla release date reale.
- Non bloccare mai la raccolta perché manca uno step precedente. Ogni finestra è indipendente.
- Marcare gli snapshot mancanti come tali (assenza di riga) invece di inventare dati.

## Implementazione (collector)
- APScheduler con job store persistente su DB → i job sopravvivono al riavvio del collector.
- Alla scoperta di un gioco: schedula i 4 job futuri (h24, h48, w1, m1).
- Un job di `discovery` ricorrente (es. ogni N ore) scansiona le pagine nuove uscite Steam + itch.io.
- Un job ricorrente per gli snapshot social degli account collegati.
- Retry con backoff su errori di rete; loggare i fallimenti, non crashare.

## Frequenze consigliate (configurabili)
- Discovery nuove uscite: ogni 6-12h.
- Snapshot social ricorrenti: giornaliero.
- Rispettare quota API (YouTube 10k unità/giorno) → batch + cache.
