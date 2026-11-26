"""Focused, offline-reproducible Alcaraz drop-shot study. No fitted models.

Run: uv run --frozen tennislab analyze-drop-shots [--fetch]
Full point detail stays in data/processed; compact evidence is in artifacts.
"""

from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import urllib.request

from tennislab.analysis.drop_shot_charting import parse_shots, shot_counts
from tennislab.analysis.drop_shot_scoring import advance, pressure, read_state, rules_for


COMMIT = '1813a1309b7ed7ebf1c7e884b32bf675d00e4edf'
PLAYER = 'Carlos Alcaraz'
FINALS = (
    '20230716-M-Wimbledon-F-Novak_Djokovic-Carlos_Alcaraz',
    '20250608-M-Roland_Garros-F-Jannik_Sinner-Carlos_Alcaraz',
)
FLAGS = ('high_importance', 'break_point_for', 'break_point_against',
         'set_point_for', 'set_point_against', 'match_point_for',
         'match_point_against', 'tiebreak', 'deciding_set')
LABELS = ('High score importance', 'Break point for', 'Break point against',
          'Set point for', 'Set point against', 'Match point for',
          'Match point against', 'Tiebreak', 'Deciding set')
SEED, REPLICATES = 20261125, 2000
SOURCE_FILES = ('charting-m-matches.csv', 'charting-m-points-2010s.csv',
                'charting-m-points-2020s.csv', 'MatchChart 0.3.2.xlsm')


def sha256(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def verify_sources(root: Path, fetch: bool) -> dict:
    lock = json.loads((root / 'config/charting_sources.lock.json').read_text())
    if lock['commit'] != COMMIT or sorted(f['path'] for f in lock['files']) != sorted(SOURCE_FILES):
        raise ValueError('unexpected charting source lock')
    raw = root / 'data/raw/charting'
    raw.mkdir(parents=True, exist_ok=True)
    if raw.is_symlink():
        raise ValueError('raw source directory is a symlink')
    for item in lock['files']:
        path = raw / item['path']
        if path.is_symlink():
            raise ValueError(f'symlink source: {path.name}')
        expected_url = f'https://raw.githubusercontent.com/JeffSackmann/tennis_MatchChartingProject/{COMMIT}/' + urllib.parse.quote(item['path'])
        if item['url'] != expected_url:
            raise ValueError('source URL does not match pinned repository/commit')
        if not path.exists():
            if not fetch:
                raise FileNotFoundError(f'{path}: rerun with --fetch')
            data = urllib.request.urlopen(item['url'], timeout=120).read()
            if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError(f'download checksum mismatch: {path.name}')
            with path.open('xb') as handle:
                handle.write(data)
        if path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
            raise ValueError(f'raw checksum mismatch: {path.name}; never overwrite it')
    return lock


def load_points(root: Path) -> tuple[dict, dict]:
    raw = root / 'data/raw/charting'
    metadata = {}
    with (raw / SOURCE_FILES[0]).open(encoding='utf-8-sig', newline='') as handle:
        for source_row, row in enumerate(csv.DictReader(handle), 1):
            if PLAYER not in (row['Player 1'], row['Player 2']):
                continue
            if row['match_id'] in metadata:
                raise ValueError('duplicate chart match ID')
            metadata[row['match_id']] = {**row, 'source_row': source_row}
    points = defaultdict(list)
    for name in SOURCE_FILES[1:3]:
        with (raw / name).open(encoding='utf-8-sig', newline='') as handle:
            for source_row, row in enumerate(csv.DictReader(handle), 1):
                if row['match_id'] in metadata:
                    points[row['match_id']].append({**row, 'source_file': name, 'source_row': source_row})
                elif 'Carlos_Alcaraz' in row['match_id']:
                    raise ValueError(f'point record without player metadata: {row["match_id"]}')
    return metadata, points


def crosswalk(root: Path, metadata: dict) -> tuple[list[dict], str]:
    """Optional exact contextual link; this is not an eligibility requirement."""
    import duckdb

    database = root / 'data/processed/tennislab.duckdb'
    records = []
    if database.exists():
        with duckdb.connect(str(database), read_only=True) as connection:
            cursor = connection.execute('''SELECT match_id, tourney_name, tourney_date,
                round, surface, winner_name, loser_name, source_file, source_row_number
                FROM matches WHERE tour = 'ATP' AND (winner_id = 207989 OR loser_id = 207989)
                ORDER BY match_id, source_file, source_row_number''')
            records = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
    digest = hashlib.sha256(json.dumps(records, default=str, sort_keys=True).encode()).hexdigest()
    # Explicit spelling/event aliases only; no similarity scoring.
    events = {'queens club': "queen's club", 'olympics': 'paris olympics',
              'atp rio de janeiro': 'rio de janeiro'}
    def event(name):
        name = name.strip().casefold()
        return events.get(name, name)
    result = []
    for mid, meta in sorted(metadata.items()):
        date = datetime.strptime(meta['Date'], '%Y%m%d').date()
        players = {meta['Player 1'].casefold(), meta['Player 2'].casefold()}
        matches = [r for r in records if players == {r['winner_name'].casefold(), r['loser_name'].casefold()}
                   and event(meta['Tournament']) == event(r['tourney_name'])
                   and meta['Round'] == r['round'] and meta['Surface'] == r['surface']
                   and 0 <= (date - r['tourney_date']).days <= 21]
        result.append(dict(match_id=mid, source_metadata_row=meta['source_row'],
                           status='exact' if len(matches) == 1 else 'ambiguous' if matches else 'unmatched',
                           canonical_match_id=matches[0]['match_id'] if len(matches) == 1 else '',
                           canonical_candidates=';'.join(r['match_id'] for r in matches)))
    return result, digest


def normalize(metadata: dict, raw_points: dict) -> tuple[list[dict], list[dict], list[dict]]:
    detail, audit, coverage = [], [], []
    for mid, meta in sorted(metadata.items()):
        raw = sorted(raw_points.get(mid, []), key=lambda r: int(r['Pt']))
        player = 1 if meta['Player 1'] == PLAYER else 2
        context = dict(match_id=mid, date=meta['Date'], year=int(meta['Date'][:4]),
                       tournament=meta['Tournament'].strip(), surface=meta['Surface'], round=meta['Round'],
                       opponent=meta['Player 2'] if player == 1 else meta['Player 1'],
                       edition=meta['Date'][:4] + ':' + meta['Tournament'].strip(), charted_by=meta['Charted by'])
        def issue(category, reason, row=None):
            audit.append(dict(match_id=mid, point=row['Pt'] if row else '', category=category,
                              reason=reason, source_file=row['source_file'] if row else SOURCE_FILES[0],
                              source_row=row['source_row'] if row else meta['source_row']))
        if not raw:
            issue('missing_points', 'metadata match has no points in either source file')
            coverage.append({**context, 'points': 0, 'observable_points': 0, 'score_valid': False, 'complete': False})
            continue
        rules, override = rules_for(meta)
        if override:
            issue('scoring_override', override)
        ordinals = [int(r['Pt']) for r in raw]
        valid_sequence = ordinals == list(range(1, len(raw) + 1))
        if not valid_sequence:
            issue('point_sequence', 'duplicate, missing, or noninitial point number')
        states, expected = [], None
        score_valid = valid_sequence
        for row in raw:
            try:
                state = read_state(row, rules)
                if expected is not None and state != expected:
                    issue('score_transition', f'expected {expected}; observed {state}', row)
                    score_valid = False
                if int(row['Pt']) == 1 and (state.s1, state.s2, state.g1, state.g2, state.p1, state.p2) != (0, 0, 0, 0, 0, 0):
                    issue('score_start', 'nonzero initial score', row)
                    score_valid = False
                expected = advance(state, int(row['PtWinner']), rules)
                states.append(state)
            except (ValueError, KeyError) as error:
                issue('invalid_score', str(error), row)
                score_valid = False
                expected = None
                states.append(None)
        if not score_valid:
            issue('pressure_exclusion', 'entire match excluded from pressure comparisons; shot observations retained')
        complete = bool(score_valid and expected and max(expected.s1, expected.s2) == rules.best_of // 2 + 1)
        if not complete and score_valid:
            issue('incomplete_match', 'recorded match ends before match point; retain observed prefix (possible retirement)')
        observable = 0
        for row, state in zip(raw, states):
            item = {**context, 'point': int(row['Pt']), 'source_file': row['source_file'], 'source_row': row['source_row'],
                    'set': int(row['Set1']) + int(row['Set2']) + 1, 'games_p1': row['Gm1'], 'games_p2': row['Gm2'],
                    'server': int(row['Svr']), 'point_score_server_first': row['Pts'],
                    'serving': int(row['Svr']) == player, 'point_won': int(row['PtWinner']) == player,
                    'score_valid': score_valid, 'complete_match': complete,
                    'shot_observed': False, 'shot_exclusion': '',
                    'leverage': None, **{flag: None for flag in FLAGS}}
            if score_valid:
                item.update(pressure(state, rules, player))
            try:
                shots = parse_shots(row)
                counts = shot_counts(shots, player)
                choices = counts.pop('choices')
                item.update(counts)
                for ordinal in (1, 2, 3):
                    item[f'n{ordinal}'] = sum(o == ordinal for o, d in choices)
                    item[f'd{ordinal}'] = sum(d for o, d in choices if o == ordinal)
                item['shot_observed'] = valid_sequence
                observable += valid_sequence
            except (ValueError, KeyError) as error:
                item['shot_exclusion'] = str(error)
                issue('unobservable_shots', str(error), row)
            detail.append(item)
        coverage.append({**context, 'points': len(raw), 'observable_points': observable,
                         'score_valid': score_valid, 'complete': complete})
    return detail, audit, coverage


def percentile(values: list[float], q: float) -> float:
    values = sorted(values)
    position = (len(values) - 1) * q
    lower = int(position)
    return values[lower] + (position - lower) * (values[min(lower + 1, len(values) - 1)] - values[lower])


def estimate(points: list[dict], flag: str, *, equal_match: bool = False, replicates: int = REPLICATES) -> dict:
    """Within-match, serve-status and prior-stroke-bin overlap standardization."""
    strata = defaultdict(lambda: [0, 0, 0, 0])  # nLow,dLow,nHigh,dHigh
    eligible_points = [r for r in points if r['score_valid'] and r['shot_observed']]
    edition_for = {r['match_id']: r['edition'] for r in eligible_points}
    for row in eligible_points:
        high = int(row[flag])
        for ordinal in (1, 2, 3):
            s = strata[(row['match_id'], row['serving'], ordinal)]
            s[2 * high] += row[f'n{ordinal}']
            s[2 * high + 1] += row[f'd{ordinal}']
    by_match = defaultdict(lambda: [0., 0., 0.])  # weight, weighted low, weighted high
    matched = set()
    n_low = n_high = d_low = d_high = 0
    for key, (nl, dl, nh, dh) in sorted(strata.items()):
        if not nl or not nh:
            continue
        matched.add(key)
        w = nl * nh / (nl + nh)
        m = by_match[key[0]]
        m[0] += w
        m[1] += w * dl / nl
        m[2] += w * dh / nh
        n_low += nl
        n_high += nh
        d_low += dl
        d_high += dh
    editions = defaultdict(lambda: [0., 0., 0.])
    for mid, (w, low, high) in sorted(by_match.items()):
        if equal_match:
            w, low, high = 1., low / w, high / w
        e = editions[edition_for[mid]]
        for i, value in enumerate((w, low, high)):
            e[i] += value
    values = [editions[k] for k in sorted(editions)]
    totals = [sum(v[i] for v in values) for i in range(3)]
    low = 100 * totals[1] / totals[0] if totals[0] else None
    high = 100 * totals[2] / totals[0] if totals[0] else None
    diffs = []
    if len(values) >= 2 and replicates:
        rng = random.Random(SEED)
        for _ in range(replicates):
            sample = rng.choices(values, k=len(values))
            w = sum(v[0] for v in sample)
            diffs.append(100 * sum(v[2] - v[1] for v in sample) / w)
    total_strokes = sum(r['opportunities'] for r in eligible_points)
    matched_points = sum(any((r['match_id'], r['serving'], o) in matched and r[f'n{o}'] for o in (1, 2, 3)) for r in eligible_points)
    return dict(comparison=flag, low_per_100=low, high_per_100=high,
                difference_pp=high - low if high is not None else None,
                relative_rate=high / low if low else None,
                ci_low=percentile(diffs, .025) if diffs else None,
                ci_high=percentile(diffs, .975) if diffs else None,
                matches=len(by_match), editions=len(values), overlap_strata=len(matched),
                eligible_points=len(eligible_points), overlap_points=matched_points,
                eligible_strokes=total_strokes, excluded_strokes_no_overlap=total_strokes - n_low - n_high,
                low_strokes=n_low, low_drops=d_low, high_strokes=n_high, high_drops=d_high,
                bootstrap_replicates=len(diffs), bootstrap_seed=SEED)


def summarize(rows: list[dict]) -> dict:
    observed = [r for r in rows if r['shot_observed']]
    opportunities = sum(r['opportunities'] for r in observed)
    drops = sum(r['primary_drops'] for r in observed)
    drop_points = sum(r['primary_drops'] > 0 for r in observed)
    won = sum(r['point_won'] for r in observed if r['primary_drops'])
    all_drop_points = sum(r['all_drops'] > 0 for r in observed)
    all_won = sum(r['point_won'] for r in observed if r['all_drops'])
    return dict(points=len(rows), observed_points=len(observed), unknown_shot_points=len(rows) - len(observed),
                eligible_strokes=opportunities, primary_drops=drops, primary_drop_points=drop_points,
                drops_per_100_strokes=100 * drops / opportunities if opportunities else None,
                drop_points_per_100=100 * drop_points / len(observed) if observed else None,
                drop_points_won=won, drop_success_pct=100 * won / drop_points if drop_points else None,
                all_drop_attempts=sum(r['all_drops'] for r in observed), all_drop_points=all_drop_points,
                all_drop_points_won=all_won, drop_volleys=sum(r['drop_volleys'] for r in observed),
                return_drops=sum(r['return_drops'] for r in observed), redrops=sum(r['redrops'] for r in observed),
                net_drops=sum(r['net_drops'] for r in observed))


def descriptive_tables(points: list[dict]) -> tuple[list[dict], list[dict]]:
    valid = [r for r in points if r['score_valid']]
    groups = [('overall', 'all', valid)]
    for flag in FLAGS:
        groups.extend((flag, str(value), [r for r in valid if r[flag] == value]) for value in (False, True))
    for dimension in ('year', 'surface'):
        groups.extend((dimension, str(value), [r for r in valid if r[dimension] == value]) for value in sorted({r[dimension] for r in valid}))
    edges = [0, .025, .05, .10, .20, 1.000001]
    for lo, hi in zip(edges, edges[1:]):
        groups.append(('leverage_bin', f'{lo:g}-{min(hi, 1):g}', [r for r in valid if lo <= r['leverage'] < hi]))
    summary = [dict(dimension=dimension, group=group, **summarize(rows)) for dimension, group, rows in groups]
    finals = [dict(match_id=mid, set=set_no, **summarize([r for r in points if r['match_id'] == mid and r['set'] == set_no]))
              for mid in FINALS for set_no in range(1, 6)]
    return summary, finals


def build(root: Path = Path('.'), *, fetch: bool = False) -> dict:
    lock = verify_sources(root, fetch)
    metadata, raw = load_points(root)
    points, audit, coverage = normalize(metadata, raw)
    links, canonical_digest = crosswalk(root, metadata)
    canonical_ids = {r['match_id']: r['canonical_match_id'] for r in links}
    for point in points:
        point['canonical_match_id'] = canonical_ids[point['match_id']]
    comparisons = [dict(variant='primary', **estimate(points, flag)) for flag in FLAGS]
    comparisons += [dict(variant='equal_match', **estimate(points, 'high_importance', equal_match=True)),
                    dict(variant='without_two_finals', **estimate([r for r in points if r['match_id'] not in FINALS], 'high_importance')),
                    dict(variant='completed_matches', **estimate([r for r in points if r['complete_match']], 'high_importance')),
                    dict(variant='without_exhibitions', **estimate([r for r in points if r['tournament'] != 'Six Kings Slam'], 'high_importance'))]
    summaries, finals = descriptive_tables(points)
    out = root / 'artifacts/alcaraz_drop_shots'
    detail = root / 'data/processed/alcaraz_drop_shots'
    fields = list(dict.fromkeys(k for row in points for k in row))
    write_csv(detail / 'points.csv', points, fields)
    write_csv(out / 'comparisons.csv', comparisons)
    write_csv(out / 'descriptive.csv', summaries)
    write_csv(out / 'finals_by_set.csv', finals)
    write_csv(out / 'coverage.csv', coverage)
    write_csv(out / 'audit.csv', audit)
    write_csv(out / 'match_crosswalk.csv', links)
    modules = ('drop_shots.py', 'drop_shot_charting.py', 'drop_shot_scoring.py', 'drop_shot_report.py')
    metadata_out = dict(source_commit=COMMIT, source_lock_sha256=sha256(root / 'config/charting_sources.lock.json'),
                        source_files=lock['files'], analysis_date='2026-11-25',
                        code_sha256={n: sha256(Path(__file__).with_name(n)) for n in modules},
                        canonical_alcaraz_rows_sha256=canonical_digest,
                        serve_point_probability=.65, high_leverage_threshold=.10,
                        bootstrap_seed=SEED, bootstrap_replicates=REPLICATES,
                        metadata_matches=len(metadata), point_matches=len(raw), source_points=len(points),
                        first_date=min(m['Date'] for m in metadata.values()), last_date=max(m['Date'] for m in metadata.values()),
                        score_valid_matches=sum(c['score_valid'] for c in coverage),
                        score_valid_points=sum(r['score_valid'] for r in points),
                        fully_observable_points=sum(r['shot_observed'] for r in points),
                        primary_eligible_points=sum(r['score_valid'] and r['shot_observed'] for r in points),
                        canonical_links=dict(Counter(r['status'] for r in links)),
                        audit_counts=dict(sorted(Counter(r['category'] for r in audit).items())))
    from tennislab.analysis.drop_shot_report import write_report
    write_report(out, comparisons, summaries, finals, metadata_out, audit, points)
    metadata_out['output_sha256'] = {p.name: sha256(p) for p in sorted(out.iterdir()) if p.name != 'metadata.json'}
    metadata_out['detail_sha256'] = sha256(detail / 'points.csv')
    (out / 'metadata.json').write_text(json.dumps(metadata_out, sort_keys=True, indent=2) + '\n')
    return dict(report=str(out / 'results.md'), primary=comparisons[0], coverage=metadata_out['audit_counts'])
