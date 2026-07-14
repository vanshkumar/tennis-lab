# Slam entrant cold-start audit

## Definition

Prior history counts completed, non-walkover tour-level main-draw matches with a strictly earlier source tournament date. All matches sharing a tournament date are batched, so later rounds cannot leak into earlier-round predictions. The source does not provide actual match dates consistently; this conservative rule understates within-event experience but prevents same-date leakage.

The principal period is 1988–2025, with 1968–1987 available as warm-up history. Entry codes and pre-event rankings are source fields; blank entry means the source did not label a special entry route and is reported as `DIRECT_OR_MISSING`.

## Overall match exposure

| Tour | Matches | <1 prior | <5 prior | <10 prior | <20 prior | Missing ID |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ATP | 19177 | 1.43% | 5.80% | 10.30% | 17.88% | 0 |
| WTA | 19177 | 1.28% | 4.87% | 8.85% | 16.17% | 0 |

## Interpretation

The long-form audit contains 76,708 Slam match appearances and 0 appearances with missing source player IDs. Detailed tracked tables break the result down by Slam, tour, year/era, entry route, and unranked status. Cold starts should be judged from both their frequency and concentration among qualifiers, wild cards, and unranked entrants before deciding whether historically uneven lower-tier sources are warranted.

Files:

- `cold_start_by_tour.csv`
- `cold_start_by_slam_era.csv`
- `cold_start_by_year.csv`
- `cold_start_by_entry.csv`
