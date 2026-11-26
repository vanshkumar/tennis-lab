"""Three concise charts from frozen study aggregates; no analysis is recomputed.

Run from the repository root:
    uv run --frozen python analyses/alcaraz_drop_shots/plot.py
"""

import csv
import hashlib
from html import escape
import json
from pathlib import Path
import re

from tennislab.publication.final_figure import Scene, render_png, render_svg


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'artifacts/alcaraz_drop_shots'
OUT = ROOT / 'artifacts/alcaraz_drop_shots_figures'
PAPER, INK, GREEN = '#F6F3EB', '#193C32', '#18785D'
MUTED, GRID, PALE = '#65716A', '#D8DDD5', '#A8BBB0'
CLAY = '#B65C3C'
WIDTH, HEIGHT = 1500, 1060


def text(scene, x, y, value, size=24, color=INK, bold=False, anchor='start'):
    scene.text(x, y, value, size=size, fill=color, weight='bold' if bold else 'regular', anchor=anchor)


def base(number, lines, subtitle):
    scene = Scene(WIDTH, HEIGHT)
    scene.rect(0, 0, WIDTH, HEIGHT, fill=PAPER)
    scene.rect(76, 52, 34, 5, fill=GREEN)
    text(scene, 126, 40, 'CARLOS ALCARAZ  /  THE DROP SHOT', 19, GREEN, True)
    text(scene, 1424, 40, f'{number:02d}', 19, MUTED, anchor='end')
    for i, line in enumerate(lines):
        text(scene, 76, 103 + i * 73, line, 61, bold=True)
    text(scene, 78, 278, subtitle, 23, MUTED)
    return scene


def footnotes(scene, lines):
    scene.line(76, 891, 1424, 891, stroke=GRID, width=1.5)
    for i, line in enumerate(lines):
        text(scene, 76, 916 + i * 25, line, 17, MUTED)
    text(scene, 76, 1013, 'SOURCE  Tennis Abstract / Jeff Sackmann & MCP contributors  ·  CC BY-NC-SA 4.0', 15, MUTED)
    text(scene, 1424, 1013, 'TENNIS LAB', 15, GREEN, True, 'end')


def primary_chart(row):
    scene = base(1, ['A little more drop shot', 'when the point matters.'],
                 'Adjusted drop attempts per 100 eligible baseline strokes')
    low, high = float(row['low_per_100']), float(row['high_per_100'])
    bottom, scale = 770, 74  # zero-based bar scale, common to both values
    for value, x, color, label in (
        (low, 265, PALE, 'Lower importance'),
        (high, 665, GREEN, 'Higher importance'),
    ):
        top = bottom - value * scale
        scene.rect(x, top, 218, bottom - top, fill=color)
        text(scene, x + 109, top - 89, f'{value:.2f}', 65, color=INK if color == PALE else GREEN, bold=True, anchor='middle')
        text(scene, x + 109, bottom + 25, label, 25, anchor='middle')
    scene.line(180, bottom, 960, bottom, stroke=INK, width=1.5)
    text(scene, 158, bottom - 10, '0', 18, MUTED, anchor='end')
    scene.line(1045, 390, 1045, 796, stroke=GRID, width=1.5)
    relative = 100 * (float(row['relative_rate']) - 1)
    text(scene, 1120, 446, f'+{relative:.0f}%', 100, GREEN, True)
    text(scene, 1126, 576, 'more often', 31, GREEN)
    text(scene, 1126, 632, 'in the primary comparison', 18, MUTED)
    footnotes(scene, [
        f'Within-match comparison: {row["matches"]} matches, {row["editions"]} editions. High importance = a modeled match-win probability swing of at least 10 pp.',
        f'Difference: +{float(row["difference_pp"]):.2f} percentage points (95% CI +{float(row["ci_low"]):.2f} to +{float(row["ci_high"]):.2f}). Equal-match weighting or removing the two finals yields intervals crossing zero.',
        'Charted matches, 2019–April 2026. Score importance uses an equal-player 65% serve model; this is an association, not a causal effect.',
    ])
    return scene


def situations_chart(rows):
    scene = base(2, ['Tiebreaks and deciding sets', 'show the clearest lift.'],
                 'Change in drop attempts per 100 eligible baseline strokes')
    selection = [('tiebreak', 'Tiebreaks'), ('deciding_set', 'Deciding sets'),
                 ('high_importance', 'High-importance points'),
                 ('break_point_against', 'Break points faced'),
                 ('break_point_for', 'Break points earned')]
    indexed = {r['comparison']: r for r in rows if r['variant'] == 'primary'}
    start, end, lo, hi = 610, 1260, -1.6, 3.2
    def x(value):
        return start + (value - lo) / (hi - lo) * (end - start)
    for tick in (-1, 0, 1, 2, 3):
        scene.line(x(tick), 382, x(tick), 802, stroke=PALE if tick == 0 else GRID, width=2 if tick == 0 else .7)
        text(scene, x(tick), 824, '0' if tick == 0 else f'{tick:+d}', 19, MUTED, anchor='middle')
    text(scene, x(0), 343, 'NO CHANGE', 15, MUTED, anchor='middle')
    for i, (key, label) in enumerate(selection):
        row = indexed[key]
        y = 418 + 86 * i
        color = GREEN if i < 3 else MUTED
        value, low, high = (float(row[k]) for k in ('difference_pp', 'ci_low', 'ci_high'))
        text(scene, 78, y - 17, label, 29, INK, i < 2)
        scene.line(x(low), y, x(high), y, stroke=color, width=3)
        scene.line(x(low), y - 6, x(low), y + 6, stroke=color, width=2)
        scene.line(x(high), y - 6, x(high), y + 6, stroke=color, width=2)
        scene.circle(x(value), y, 9 if i < 3 else 7, fill=color)
        text(scene, 1420, y - 25, f'{value:+.2f}', 36, color, True, 'end')
    footnotes(scene, [
        'Each situation is compared with other points in the same matches, adjusted for serving status and stroke order. Lines show 95% CIs.',
        'Selected contexts; the report includes all splits. Tiebreak/deciding-set results are exploratory. Both break-point intervals include zero.',
        'Sample sizes: ' + ' / '.join(indexed[key]['matches'] for key, label in selection)
        + ' matches, respectively. Intervals are not adjusted for multiple comparisons.',
    ])
    return scene


def finals_chart(rows):
    scene = base(3, ['His drop-shot rate peaked', 'in set five of both finals.'],
                 'Drop attempts per 100 eligible baseline strokes')
    matches = list(dict.fromkeys(row['match_id'] for row in rows))
    for panel, (mid, title, opponent, color) in enumerate(zip(
        matches, ('Wimbledon 2023', 'Roland Garros 2025'),
        ('vs Djokovic', 'vs Sinner'), (GREEN, CLAY),
    )):
        left = 114 + panel * 740
        text(scene, left, 352, title, 31, color, True)
        text(scene, left, 400, opponent, 21, MUTED)
        group = sorted((r for r in rows if r['match_id'] == mid), key=lambda r: int(r['set']))
        bottom, scale = 771, 36
        for tick in (0, 4, 8):
            y = bottom - tick * scale
            scene.line(left, y, left + 538, y, stroke=GRID, width=1)
            text(scene, left - 17, y - 12, str(tick), 17, MUTED, anchor='end')
        for i, row in enumerate(group):
            value = float(row['drops_per_100_strokes'])
            x = left + 17 + i * 106
            y = bottom - value * scale
            fill = color if i == 4 else '#C4D3C9' if panel == 0 else '#DFC5B6'
            scene.rect(x, y, 67, bottom - y, fill=fill)
            text(scene, x + 34, y - 47, f'{value:.1f}', 32, color if i == 4 else MUTED, i == 4, 'middle')
            text(scene, x + 34, 798, f'Set {i+1}', 22, color if i == 4 else MUTED, i == 4, 'middle')
    footnotes(scene, [
        'Descriptive case studies. Initiating baseline drops, including failed attempts; returns, net drops and re-drops excluded.',
        'Fifth-set attempts / eligible strokes: Wimbledon 5 / 74; Roland Garros 9 / 136. One unobservable Roland Garros point is excluded.',
        'The Wimbledon chart records 4 points won from 5 fifth-set drops, rather than the quoted 5 / 6. These finals alone do not establish a wider effect.',
    ])
    return scene


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with (SOURCE / 'comparisons.csv').open() as handle:
        comparisons = list(csv.DictReader(handle))
    with (SOURCE / 'finals_by_set.csv').open() as handle:
        finals = list(csv.DictReader(handle))
    primary = next(r for r in comparisons if r['variant'] == 'primary' and r['comparison'] == 'high_importance')
    charts = [
        ('01_primary', primary_chart(primary), 'A little more drop shot when the point matters.',
         'Adjusted attempts increase from 3.59 to 4.27 per 100 baseline strokes, about 19% relatively. Sensitivity checks remain inconclusive.'),
        ('02_situations', situations_chart(comparisons), 'Tiebreaks and deciding sets show the clearest lift.',
         'Within-match changes with 95% intervals: tiebreaks +1.62, deciding sets +0.86, high importance +0.68; break-point comparisons overlap zero.'),
        ('03_finals', finals_chart(finals), 'His drop-shot rate peaked in set five of both finals.',
         'Baseline drop attempts per 100 eligible strokes peak at 6.8 in Wimbledon 2023 set five and 6.6 in Roland Garros 2025 set five.'),
    ]
    for name, scene, title, description in charts:
        render_png(scene, OUT / f'{name}.png', scale=2)
        path = OUT / f'{name}.svg'
        render_svg(scene, path)
        # The existing renderer supplies Slam-specific accessibility text.
        svg = re.sub(r'<title id="title">.*?</title>', '<title id="title">' + escape(title) + '</title>', path.read_text())
        svg = re.sub(r'<desc id="desc">.*?</desc>', '<desc id="desc">' + escape(description) + '</desc>', svg)
        path.write_text(svg)
    metadata = {
        'inputs': {str(p.relative_to(ROOT)): digest(p) for p in [SOURCE / 'comparisons.csv', SOURCE / 'finals_by_set.csv']},
        'code_sha256': digest(Path(__file__)),
        'renderer_sha256': digest(ROOT / 'src/tennislab/publication/final_figure.py'),
        'outputs': {p.name: digest(p) for p in sorted(OUT.iterdir()) if p.suffix in ('.png', '.svg')},
    }
    (OUT / 'metadata.json').write_text(json.dumps(metadata, sort_keys=True, indent=2) + '\n')
    print(OUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
