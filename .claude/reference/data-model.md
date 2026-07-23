# Modello dati (bozza schema)

Principio guida: **append-only per le serie storiche**. I dati anagrafici del gioco stanno in `games`; ogni misura nel tempo è uno snapshot separato. Mai sovrascrivere metriche.

## Tabelle

### `games` — anagrafica gioco (una riga per gioco)
| campo | tipo | note |
|---|---|---|
| id | PK | interno |
| platform | enum | `steam` \| `itch` |
| external_id | str | appid Steam / slug-url itch (UNIQUE con platform) |
| title | str | |
| developer | str | |
| publisher | str | nullable |
| genres | json/str[] | generi |
| tags | json/str[] | tag utente/store |
| release_date | date | nullable se non ancora uscito |
| has_demo | bool | se rilasciata una demo |
| demo_release_date | date | nullable |
| price | float | prezzo di lancio |
| is_free | bool | |
| store_url | str | |
| header_image | str | url |
| first_seen_at | datetime | quando il collector l'ha scoperto |
| quality_score | float | ultimo score calcolato (0-100) |
| discarded | bool | sotto soglia trash |

### `game_snapshots` — metriche del gioco nel tempo (append-only)
| campo | tipo | note |
|---|---|---|
| id | PK | |
| game_id | FK → games | |
| captured_at | datetime | timestamp snapshot |
| snapshot_type | enum | `discovery` \| `h24` \| `h48` \| `w1` \| `m1` \| `manual` |
| total_reviews | int | Steam |
| total_positive | int | Steam |
| total_negative | int | Steam |
| review_score_desc | str | es. "Very Positive" |
| current_players | int | Steam player count live |
| steamspy_owners | str | range stimato |
| steamspy_estimate | int | stima puntuale se disponibile |
| price | float | prezzo al momento (per tracciare sconti/lancio) |
| extra | json | campi specifici piattaforma |

### `social_accounts` — profili social collegati a un gioco
| campo | tipo | note |
|---|---|---|
| id | PK | |
| game_id | FK → games | |
| platform | enum | `youtube` \| `reddit` \| `tiktok` \| `instagram` \| `twitter/x` \| `discord` |
| handle | str | |
| url | str | |
| discovered_via | str | come è stato trovato (link store, ricerca) |

### `social_snapshots` — metriche social nel tempo (append-only)
| campo | tipo | note |
|---|---|---|
| id | PK | |
| social_account_id | FK → social_accounts | |
| captured_at | datetime | |
| followers | int | nullable |
| total_posts | int | nullable |
| extra | json | metriche specifiche piattaforma |

### `social_posts` — singoli post/menzioni rilevanti (timeline marketing)
| campo | tipo | note |
|---|---|---|
| id | PK | |
| game_id | FK → games | |
| platform | enum | |
| post_url | str | |
| subreddit | str | nullable (Reddit) |
| posted_at | datetime | **data del post** — chiave per la timeline |
| title | str | |
| views | int | nullable |
| likes | int | nullable |
| comments | int | nullable |
| shares | int | nullable |
| captured_at | datetime | quando l'abbiamo raccolto |

### `analysis_reports` — report generati
| campo | tipo | note |
|---|---|---|
| id | PK | |
| game_id | FK → games | nullable (report per-gioco vs per-genere) |
| genre | str | nullable |
| lang | enum | `it` \| `en` |
| generated_at | datetime | |
| summary | text | strategia spiegata |
| data | json | dati strutturati a supporto dei grafici |

## Note
- Implementazione ORM: `core/models.py` (SQLAlchemy 2.x, typed). Gli enum sono salvati come VARCHAR (`native_enum=False`) per portabilità Postgres. Valori: platform=`steam|itch`; social platform=`youtube|reddit|tiktok|instagram|twitter|discord` (il "twitter/x" della bozza è normalizzato a `twitter`); snapshot_type=`discovery|h24|h48|w1|m1|manual`; lang=`it|en`. Le FK usano `ondelete=CASCADE`. Indici aggiunti su game_id, captured_at, platform, posted_at, genre.
- `snapshot_type` permette di sapere se uno snapshot è quello canonico +24h/+48h/ecc. o un backfill.
- La timeline marketing di un gioco = merge di `demo_release_date`, `release_date`, `social_posts.posted_at`, e i punti di svolta nella crescita (`game_snapshots`).
- Schema pensato per SQLite ma portabile a Postgres (evitare feature SQLite-only).
