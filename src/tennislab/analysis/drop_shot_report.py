"""Compact report and two PNG charts, using the repo's existing Pillow dependency."""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def number(value, digits=2):
    return 'NA' if value is None else f'{value:.{digits}f}'


def canvas(width, height):
    image = Image.new('RGB', (width, height), '#faf9f5')
    draw = ImageDraw.Draw(image)
    def text(x, y, content, size=20, color='#26352f'):
        draw.text((x, y), content, font=ImageFont.load_default(size=size), fill=color)
    return image, draw, text


def comparison_chart(out: Path, comparisons: list[dict]):
    from tennislab.analysis.drop_shots import LABELS

    rows = comparisons[:9]
    image, draw, text = canvas(1500, 980)
    text(60, 35, 'Does Alcaraz choose more drop shots under pressure?', 36)
    text(60, 90, 'Adjusted change in initiating drop attempts per 100 baseline strokes', 24)
    text(60, 130, 'Within-match comparisons; dots are estimates, lines are 95% tournament-edition bootstrap intervals.', 18, '#657168')
    lo = math.floor(min(-1, *(r['ci_low'] for r in rows if r['ci_low'] is not None)))
    hi = math.ceil(max(1, *(r['ci_high'] for r in rows if r['ci_high'] is not None)))
    def x(v):
        return 410 + (v - lo) / (hi - lo) * 600
    text(60, 188, 'Situation', 21)
    text(1070, 188, 'Other -> situation', 21)
    text(1305, 188, 'Change (pp)', 21)
    for tick in range(lo, hi + 1):
        if tick % max(1, math.ceil((hi - lo) / 10)) and tick != 0:
            continue
        draw.line((x(tick), 230, x(tick), 850), fill='#bcc9c0' if tick == 0 else '#e4e7e2', width=3 if tick == 0 else 1)
        text(x(tick) - 12, 865, f'{tick:+d}', 18, '#657168')
    for i, (row, label) in enumerate(zip(rows, LABELS)):
        y = 265 + 67 * i
        text(60, y - 16, label, 23)
        text(60, y + 14, f'{row["matches"]} matches / {row["editions"]} editions', 15, '#657168')
        if row['difference_pp'] is not None:
            if row['ci_low'] is not None:
                draw.line((x(row['ci_low']), y, x(row['ci_high']), y), fill='#398074', width=4)
            xx = x(row['difference_pp'])
            draw.ellipse((xx - 7, y - 7, xx + 7, y + 7), fill='#17695a')
        text(1070, y - 13, f'{number(row["low_per_100"])} -> {number(row["high_per_100"])}', 21)
        text(1310, y - 13, f'{row["difference_pp"]:+.2f}' if row['difference_pp'] is not None else 'NA', 21)
    text(60, 923, 'Positive = more drop choices in that situation. High importance: >=10 pp match-win swing, equal-player 65% serve model.', 18)
    image.save(out / 'pressure_comparisons.png')


def finals_chart(out: Path, finals: list[dict]):
    image, draw, text = canvas(1500, 700)
    text(60, 30, 'Two finals, set by set', 36)
    text(60, 85, 'Initiating baseline drop-shot points per 100 observable points', 24)
    text(60, 125, 'Labels show attempts; parentheses show points eventually won. Net drops and re-drops are separate.', 19, '#657168')
    upper = max(15, 5 * math.ceil(max(r['drop_points_per_100'] for r in finals) / 5))
    for panel, title in enumerate(('Wimbledon 2023 vs Djokovic', 'Roland Garros 2025 vs Sinner')):
        left = 80 + panel * 740
        text(left, 185, title, 26)
        for tick in range(0, upper + 1, 5):
            yy = 550 - tick / upper * 260
            draw.line((left, yy, left + 590, yy), fill='#dde3dc')
            text(left - 35, yy - 11, str(tick), 17)
        for i, row in enumerate(finals[panel * 5:(panel + 1) * 5]):
            xx = left + 38 + i * 115
            yy = 550 - row['drop_points_per_100'] / upper * 260
            draw.rectangle((xx, yy, xx + 65, 550), fill='#17695a' if i == 4 else '#81aaa0')
            text(xx - 5, yy - 34, f'{row["primary_drops"]} ({row["drop_points_won"]})', 21)
            text(xx + 4, 570, f'Set {i + 1}', 20)
            text(xx - 8, 610, f'{row["observed_points"]} pts', 17, '#657168')
    image.save(out / 'finals_by_set.png')


def write_report(out, comparisons, summaries, finals, meta, audit, points):
    from tennislab.analysis.drop_shots import COMMIT, FINALS, FLAGS, LABELS

    primary = comparisons[0]
    lookup = {(r['dimension'], r['group']): r for r in summaries}
    low, high = [lookup['high_importance', str(b)] for b in (False, True)]
    if primary['ci_low'] is not None and primary['ci_low'] > 0:
        conclusion = 'Tentative support: Alcaraz chooses somewhat more drop shots at high-importance scores in this charted sample.'
    elif primary['ci_high'] is not None and primary['ci_high'] < 0:
        conclusion = 'The charted sample points toward lower drop-shot selection at high-importance scores.'
    else:
        conclusion = 'The charted sample does not establish that Alcaraz chooses drop shots more often at high-importance scores.'
    lines = ['# Alcaraz drop shots under pressure', '', conclusion, '',
             f'The primary within-match estimate is **{number(primary["difference_pp"])} percentage points** '
             f'(95% interval **{number(primary["ci_low"])} to {number(primary["ci_high"])}**): '
             f'{number(primary["low_per_100"])} initiating drops per 100 eligible baseline strokes at lower importance, '
             f'versus {number(primary["high_per_100"])} at high importance. Relative rate: {number(primary["relative_rate"])}.', '',
             'The result is sensitive to weighting and sample choice: the equal-match and without-the-two-finals '
             'checks below retain positive estimates but their intervals include no change. Tiebreaks and deciding sets '
             'show increases; the two break-point comparisons are inconclusive. This is not evidence of a uniform response to every kind of pressure.', '',
             f'The raw point-level frequencies are {number(low["drop_points_per_100"])} versus '
             f'{number(high["drop_points_per_100"])} drop-containing points per 100 observable points. '
             'Those rates are descriptive and also reflect how many baseline-shot opportunities occur. '
             f'Eventual point success after a drop is {number(low["drop_success_pct"])}% versus '
             f'{number(high["drop_success_pct"])}%; success is a separate question from usage.', '',
             '![Pressure comparisons](pressure_comparisons.png)', '',
             '## Familiar pressure situations', '',
             'Each row compares that situation with its complement, using its own within-match overlap sample. '
             'Positive changes mean more drop choices. These secondary comparisons overlap and are exploratory; '
             'their intervals are not adjusted for multiple comparisons.', '',
             '| Situation | Other / 100 strokes | Situation / 100 | Change, pp (95% interval) | Drops / strokes, situation | Matches |',
             '|---|---:|---:|---:|---:|---:|']
    for label, row in zip(LABELS, comparisons):
        lines.append(f'| {label} | {number(row["low_per_100"])} | {number(row["high_per_100"])} | '
                     f'{number(row["difference_pp"])} [{number(row["ci_low"])}, {number(row["ci_high"])}] | '
                     f'{row["high_drops"]} / {row["high_strokes"]} | {row["matches"]} |')
    lines += ['', '## The two examples', '', '![Finals by set](finals_by_set.png)', '',
              '| Final | Set | Initiating drops | Points won after drop | Drops / 100 observable points | All u/y drop attempts |',
              '|---|---:|---:|---:|---:|---:|']
    for row in finals:
        label = 'Wimbledon 2023' if row['match_id'] == FINALS[0] else 'Roland Garros 2025'
        lines.append(f'| {label} | {row["set"]} | {row["primary_drops"]} | {row["drop_points_won"]} | '
                     f'{number(row["drop_points_per_100"])} | {row["all_drop_attempts"]} |')
    w5 = finals[4]
    tiebreak_point = next(r for r in points if r['match_id'] == FINALS[1] and r['point'] == 377)
    lines += ['', f'The Wimbledon fifth set contains **{w5["all_drop_attempts"]} coded groundstroke drop attempts, '
              f'with {w5["all_drop_points_won"]} points won**, rather than the screenshot’s 5/6. '
              'The chart therefore does not reproduce that exact claim. Drop volleys use different codes; '
              'the detailed source rows are retained for manual/video checking. Earlier sets also contain drop attempts.', '',
              'The Roland Garros example is confirmed: source point **377**, Alcaraz leading **3–0** '
              'in the deciding tiebreak, includes his forehand drop (`u`) and ends with him winning the point. '
              f'Its modeled match-win swing is **{100 * tiebreak_point["leverage"]:.2f} percentage points**. '
              'Being in a deciding tiebreak and having a high-leverage score are different definitions of pressure.', '',
              '## Sensitivity checks', '',
              '| Primary score-importance comparison | Change, pp | 95% interval | Matches |',
              '|---|---:|---:|---:|']
    for row in [comparisons[0], *comparisons[9:]]:
        lines.append(f'| {row["variant"]} | {number(row["difference_pp"])} | '
                     f'[{number(row["ci_low"])}, {number(row["ci_high"])}] | {row["matches"]} |')
    bad = sorted({r['match_id'] for r in audit if r['category'] == 'pressure_exclusion'})
    lines += ['', '## Data and exclusions', '',
              f'- Snapshot: {meta["metadata_matches"]} listed Alcaraz matches, {meta["point_matches"]} with points; '
              f'**{meta["source_points"]:,} source points**, April 2, 2019–April 12, 2026. This is the downloaded snapshot, not all charts currently on the website.',
              f'- {meta["score_valid_matches"]} matches / {meta["score_valid_points"]:,} points pass scoring validation. '
              f'{meta["primary_eligible_points"]:,} points also have fully observable shot sequences.',
              f'- The primary contrast uses {primary["matches"]} matches and {primary["editions"]} tournament editions. '
              f'{primary["excluded_strokes_no_overlap"]:,} of {primary["eligible_strokes"]:,} eligible strokes lack high/low overlap '
              'within their match, serving status, and stroke-order stratum.',
              f'- Existing match-history links: {meta["canonical_links"]}. An unresolved canonical link does not exclude charted points.',
              '- Pressure-excluded matches: ' + '; '.join(f'`{mid}`' for mid in bad) + '.',
              '- One metadata-only Madrid 2023 record has no corresponding points. Missing or malformed shots are unobservable, not zero-drop points.',
              '- Finished prefixes of retirements are retained; a completed-match sensitivity is shown above. Exhibition charts are retained in the all-charted primary sample and excluded in a sensitivity.', '',
              'Full reasons and source row numbers: [audit](audit.csv), [coverage](coverage.csv), '
              '[match links](match_crosswalk.csv). Counts and secondary splits: [descriptive data](descriptive.csv). '
              'Full comparison denominators: [comparisons](comparisons.csv).', '',
              '## Method and limits', '',
              'A primary attempt is an initiating baseline forehand/backhand drop (`u`/`y`), including errors. '
              'Eligible strokes are nonreturn baseline drives, slices, lobs, and drops; net position follows the '
              'source’s shot-type defaults and `-`/`=` modifiers. The risk set stops at the first drop or drop volley '
              'by either player. Return drops, re-drops, net drops, and drop volleys are reported separately; those descriptive categories can overlap. '
              'No tracking data establish whether a drop was physically feasible on each eligible stroke.', '',
              'Pressure uses only the score before the point: P(match win after winning the next point) minus '
              'P(match win after losing it). Both players have a fixed 65% serve-point win probability. '
              'High importance means a swing of at least 10 percentage points. This is an equal-strength '
              'score benchmark, not an Alcaraz win forecast or a measurement of his emotional state. '
              'Future sets begin at 50/50 in this symmetric model; deuce and extended-tiebreak tails are analytic.', '',
              'For each match × serving/returning status × own eligible-stroke ordinal (1, 2, 3+), '
              'calculate low/high attempt rates and weight both by n_low × n_high / (n_low + n_high). '
              'Strata without both groups are excluded from that comparison. Retain zero-drop strata. '
              'Bootstrap whole tournament editions 2,000 times with seed 20261125; report percentile 95% intervals. '
              'The equal-match sensitivity normalizes weights within each contributing match. '
              'Final rally length and future outcomes are never explanatory variables.', '',
              'Chart selection is not random. Within-match comparisons account for stable match differences, '
              'but fatigue, ball difficulty, and opponent positioning remain possible explanations. '
              'Unknown shot types exclude the entire point from shot denominators. Scoring inconsistencies exclude '
              'the entire match from pressure comparisons while preserving its observable shot records. '
              'This is an observational, personal analysis; a wide interval means the data are inconclusive.', '',
              '## Reproduce and sources', '',
              '```bash', 'uv run --frozen tennislab analyze-drop-shots --fetch',
              'uv run --frozen tennislab analyze-drop-shots', '```', '',
              'Detailed records are in `data/processed/alcaraz_drop_shots/points.csv` (gitignored). '
              'The source lock, code hashes, assumptions and output hashes are recorded in [metadata](metadata.json). '
              'The existing Slam-upset results and source locks are unchanged.', '',
              f'- [Tennis Abstract Match Charting Project snapshot](https://github.com/JeffSackmann/tennis_MatchChartingProject/tree/{COMMIT}), '
              'Jeff Sackmann and volunteer chart contributors; CC BY-NC-SA 4.0. The pinned workbook’s Instructions sheet defines the notation.',
              '- [Drop-shot definition and distinction from point success](https://www.tennisabstract.com/blog/2024/03/21/effects-and-after-effects-of-the-carlos-alcaraz-drop-shot/).',
              '- [Grand Slam deciding-tiebreak rule change](https://ausopen.com/articles/news/grand-slams-jointly-adopt-10-point-final-set-tiebreak).',
              '- [Wimbledon 2023 chart](https://www.tennisabstract.com/charting/' + FINALS[0] + '.html) and '
              '[Roland Garros 2025 chart](https://www.tennisabstract.com/charting/' + FINALS[1] + '.html), both charted by Edo.', '']
    (out / 'results.md').write_text('\n'.join(lines), encoding='utf-8')
    comparison_chart(out, comparisons)
    finals_chart(out, finals)
