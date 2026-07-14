# Tennis match data coverage and quality audit

## Scope and provenance

This audit covers the pinned 1968–2025 ATP and WTA tour-level main-draw singles files recorded in `config/sources.lock.json`. Raw source rows are retained; audit signals do not delete or repair matches. Jeff Sackmann's source data is attributed under CC BY-NC-SA 4.0.

The original Sackmann commit SHAs are retained; named GitHub fork-network routes provide the same commit objects while the original repository URLs are unavailable.

Detailed groupings are in `coverage.csv`, round-level Slam counts are in `slam_match_counts.csv`, and row/event-level findings are in `issues.csv`.

## 1988–2025 primary comparison period

**Ready for the Elo milestone.** No blocking primary-period coverage, essential-field, round, duplicate, surface, or severe count signals were detected. Review warnings before modeling.

| Blocking signal | Count |
| --- | --- |
| Missing expected Slam events | 0 |
| Duplicate canonical Slam rows | 0 |
| Probable duplicate Slam groups | 0 |
| Historical surface mismatches | 0 |
| Severe 128-draw count shortfalls | 0 |
| Unmapped Grand Slam rows | 0 |
| Rows missing essential fields | 0 |
| Rows with unexpected rounds | 0 |

The primary-period test expects all four Slams for both tours except cancelled Wimbledon 2020. A standard 128-player draw's 127 matches and per-round counts are validation signals, not hard filtering assumptions.

## Dataset coverage

| Tour | Matches |
| --- | --- |
| ATP | 197940 |
| WTA | 160887 |

### Annual match counts

| Tour | Year | Matches |
| --- | --- | --- |
| ATP | 1968 | 4377 |
| ATP | 1969 | 3165 |
| ATP | 1970 | 3287 |
| ATP | 1971 | 3640 |
| ATP | 1972 | 3617 |
| ATP | 1973 | 4327 |
| ATP | 1974 | 4200 |
| ATP | 1975 | 4164 |
| ATP | 1976 | 3979 |
| ATP | 1977 | 4140 |
| ATP | 1978 | 3852 |
| ATP | 1979 | 3959 |
| ATP | 1980 | 4013 |
| ATP | 1981 | 3910 |
| ATP | 1982 | 4070 |
| ATP | 1983 | 3489 |
| ATP | 1984 | 3248 |
| ATP | 1985 | 3392 |
| ATP | 1986 | 3249 |
| ATP | 1987 | 3546 |
| ATP | 1988 | 3733 |
| ATP | 1989 | 3583 |
| ATP | 1990 | 3681 |
| ATP | 1991 | 3727 |
| ATP | 1992 | 3792 |
| ATP | 1993 | 3890 |
| ATP | 1994 | 3938 |
| ATP | 1995 | 3800 |
| ATP | 1996 | 3774 |
| ATP | 1997 | 3623 |
| ATP | 1998 | 3591 |
| ATP | 1999 | 3334 |
| ATP | 2000 | 3378 |
| ATP | 2001 | 3307 |
| ATP | 2002 | 3213 |
| ATP | 2003 | 3218 |
| ATP | 2004 | 3288 |
| ATP | 2005 | 3264 |
| ATP | 2006 | 3267 |
| ATP | 2007 | 3192 |
| ATP | 2008 | 3123 |
| ATP | 2009 | 3085 |
| ATP | 2010 | 3030 |
| ATP | 2011 | 3015 |
| ATP | 2012 | 3009 |
| ATP | 2013 | 2944 |
| ATP | 2014 | 2901 |
| ATP | 2015 | 2943 |
| ATP | 2016 | 2941 |
| ATP | 2017 | 2911 |
| ATP | 2018 | 2897 |
| ATP | 2019 | 2806 |
| ATP | 2020 | 1462 |
| ATP | 2021 | 2733 |
| ATP | 2022 | 2917 |
| ATP | 2023 | 2986 |
| ATP | 2024 | 3076 |
| ATP | 2025 | 2944 |
| WTA | 1968 | 3068 |
| WTA | 1969 | 3024 |
| WTA | 1970 | 3047 |
| WTA | 1971 | 2580 |
| WTA | 1972 | 2996 |
| WTA | 1973 | 2977 |
| WTA | 1974 | 2825 |
| WTA | 1975 | 2703 |
| WTA | 1976 | 2242 |
| WTA | 1977 | 2347 |
| WTA | 1978 | 2765 |
| WTA | 1979 | 2273 |
| WTA | 1980 | 4032 |
| WTA | 1981 | 3479 |
| WTA | 1982 | 2975 |
| WTA | 1983 | 2469 |
| WTA | 1984 | 2355 |
| WTA | 1985 | 2705 |
| WTA | 1986 | 2550 |
| WTA | 1987 | 2735 |
| WTA | 1988 | 2862 |
| WTA | 1989 | 2831 |
| WTA | 1990 | 2728 |
| WTA | 1991 | 2752 |
| WTA | 1992 | 2685 |
| WTA | 1993 | 2847 |
| WTA | 1994 | 2615 |
| WTA | 1995 | 2529 |
| WTA | 1996 | 2733 |
| WTA | 1997 | 2996 |
| WTA | 1998 | 2870 |
| WTA | 1999 | 2873 |
| WTA | 2000 | 2893 |
| WTA | 2001 | 3098 |
| WTA | 2002 | 3140 |
| WTA | 2003 | 2933 |
| WTA | 2004 | 2805 |
| WTA | 2005 | 2843 |
| WTA | 2006 | 2787 |
| WTA | 2007 | 2778 |
| WTA | 2008 | 2791 |
| WTA | 2009 | 2722 |
| WTA | 2010 | 2781 |
| WTA | 2011 | 2804 |
| WTA | 2012 | 2849 |
| WTA | 2013 | 2714 |
| WTA | 2014 | 2785 |
| WTA | 2015 | 2651 |
| WTA | 2016 | 2923 |
| WTA | 2017 | 2862 |
| WTA | 2018 | 2756 |
| WTA | 2019 | 2743 |
| WTA | 2020 | 1276 |
| WTA | 2021 | 2597 |
| WTA | 2022 | 2594 |
| WTA | 2023 | 2810 |
| WTA | 2024 | 2689 |
| WTA | 2025 | 2795 |

### Tournament level

| Tour | Level | Matches |
| --- | --- | --- |
| ATP | A | 129087 |
| ATP | D | 15042 |
| ATP | F | 624 |
| ATP | G | 28045 |
| ATP | M | 25078 |
| ATP | O | 64 |
| WTA | 35+H | 31 |
| WTA | 50+H | 184 |
| WTA | CC | 1913 |
| WTA | D | 12224 |
| WTA | E | 282 |
| WTA | F | 533 |
| WTA | G | 25753 |
| WTA | I | 15521 |
| WTA | J | 6 |
| WTA | O | 672 |
| WTA | P | 10965 |
| WTA | PM | 5133 |
| WTA | T1 | 4778 |
| WTA | T2 | 4329 |
| WTA | T3 | 4562 |
| WTA | T4 | 2912 |
| WTA | T5 | 968 |
| WTA | W | 70121 |

### Surface

| Tour | Surface | Matches |
| --- | --- | --- |
| ATP | Carpet | 20900 |
| ATP | Clay | 70238 |
| ATP | Grass | 23698 |
| ATP | Hard | 80114 |
| ATP | (missing) | 2990 |
| WTA | Carpet | 14128 |
| WTA | Clay | 50489 |
| WTA | Grass | 23560 |
| WTA | Hard | 67835 |
| WTA | (missing) | 4875 |

## Slam coverage

| Tour | Slam | Matches |
| --- | --- | --- |
| ATP | Australian Open | 6174 |
| ATP | Roland Garros | 7318 |
| ATP | US Open | 7314 |
| ATP | Wimbledon | 7239 |
| WTA | Australian Open | 5781 |
| WTA | Roland Garros | 6494 |
| WTA | US Open | 6719 |
| WTA | Wimbledon | 6759 |

Historical surface validation uses Australian Open grass through 1987 and hard from 1988; US Open grass through 1974, clay from 1975–1977, and hard from 1978; Roland Garros clay; and Wimbledon grass. Australian Open 1986 was not held. Wimbledon 2020 was cancelled.

## Missing canonical fields

| Field | Missing rows |
| --- | --- |
| loser_rank | 99533 |
| loser_rank_points | 144194 |
| score | 4 |
| surface | 7865 |
| winner_rank | 87415 |
| winner_rank_points | 139983 |

Missing fields remain null in the canonical table and are reported rather than causing row drops. Rankings are historically sparse and should not be interpreted as match-coverage gaps on their own.

## Normalization observations

| Field | Observation | Rows |
| --- | --- | --- |
| tourney_date | tournament date year differs from source-file season year | 2843 |
| draw_size | invalid integer retained as null | 1 |

The canonical `year` is the yearly source-file season. Some tournaments begin in late December or finish in early January, so a one-year difference between that season and `tourney_date` is retained and audited rather than rewritten.

## Match endings and duplicates

| Tour | Walkovers | Retirements |
| --- | --- | --- |
| ATP | 1295 | 3980 |
| WTA | 1256 | 2911 |

Duplicate checks found 0 canonical-ID groups and 121 probable duplicate groups across the full dataset.

## Suspicious years and tournaments

| Tour | Year | Event/value | Signal | Detail |
| --- | --- | --- | --- | --- |
| ATP | 1970 | US Open | slam_match_count_signal | 128-player draw validation signal is 127 matches; this is not a deletion rule |
| ATP | 1975 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| ATP | 2020 | 1462 | low_annual_coverage | annual match count is below 65% of the ATP 1988-2025 non-2020 median (3213) |
| WTA | 1968 | Australian Championships | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1969 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1970 | Roland Garros | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1970 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1971 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1972 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1972 | Roland Garros | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1973 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1974 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1975 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1976 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1977 | Australian Open 2 | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1977 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1977 | US Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1978 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1979 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1980 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1980 | US Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1981 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 1982 | Australian Open | unexpected_slam_draw_size | historical Slam draw size is outside the common 64/96/128 signals |
| WTA | 2020 | 1276 | low_annual_coverage | annual match count is below 65% of the WTA 1988-2025 non-2020 median (2791) |

Annual coverage is flagged below 65% of the tour's 1988–2025 non-2020 median. The 2020 season is expected to be low because of the COVID-19 disruption. The table is capped at 100 rows; `issues.csv` is complete.

## Issue summary

| Severity | Category | Rows/groups |
| --- | --- | --- |
| warning | normalization | 2844 |
| warning | probable_duplicate_match | 121 |
| warning | slam_match_count_signal | 1 |
| warning | slam_round_count_signal | 1 |
| info | known_cancelled_event | 4 |
| info | low_annual_coverage | 2 |
| info | missing_value | 478994 |
| info | unexpected_slam_draw_size | 21 |

## Interpretation limits

Draw sizes and expected round counts are diagnostic signals. Historical draws, byes, source gaps, and event-format changes can legitimately differ, so no anomaly is deleted automatically. Probable duplicates use tour, date, tournament name, round, and the unordered player pair; they require review rather than automatic deduplication. Player identity uses source IDs when present and never performs fuzzy name matching.
