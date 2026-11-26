from dataclasses import replace
import json

import pytest

from tennislab.analysis.drop_shot_charting import parse_shots, shot_counts
from tennislab.analysis.drop_shot_scoring import (
    Rules, State, advance, game_probability, match_probability, pressure,
    read_state, rules_for, set_probability, tb_probability, tb_server,
)
from tennislab.analysis.drop_shots import estimate, normalize, summarize, verify_sources


def row(first='6b38f3u1n@', second='', server=1, winner=1, **kwargs):
    return {'1st': first, '2nd': second, 'Svr': str(server), 'PtWinner': str(winner),
            'Set1': '0', 'Set2': '0', 'Gm1': '0', 'Gm2': '0', 'Pts': '0-0', 'Pt': '1',
            'source_file': 'fixture.csv', 'source_row': 1, **kwargs}


def metadata(**kwargs):
    return {'Date': '20230716', 'Tournament': 'Wimbledon', 'Best of': '5', 'Final TB?': 'T',
            'Player 1': 'Novak Djokovic', 'Player 2': 'Carlos Alcaraz', 'Round': 'F',
            'Surface': 'Grass', 'Charted by': 'fixture', 'source_row': 1, **kwargs}


def test_failed_drop_counts_and_player_orientation():
    shots = parse_shots(row())
    assert [(s.player, s.code) for s in shots] == [(2, 'b'), (1, 'f'), (2, 'u')]
    counts = shot_counts(shots, 2)
    assert counts['primary_drops'] == counts['opportunities'] == 1
    assert counts['choices'] == [(1, 1)]
    mirrored = parse_shots(row(server=2, winner=2))
    assert shot_counts(mirrored, 1) == counts


def test_second_serve_and_nonstandard_error_marker_order():
    shots = parse_shots(row('4+d', '6b38f3u1@d'))
    assert shot_counts(shots, 2)['primary_drops'] == 1
    assert parse_shots(row('4n', '5d', winner=2)) == []
    assert parse_shots(row('4^*', winner=1)) == []


def test_drop_categories_and_stop_at_first_drop():
    shots = parse_shots(row('4b28u1y2v3*'))
    assert shot_counts(shots, 1)['primary_drops'] == 1
    assert shot_counts(shots, 2)['primary_drops'] == 0
    assert shot_counts(shots, 2)['redrops'] == 1
    shots = parse_shots(row('4u1*', winner=2))
    assert shot_counts(shots, 2)['return_drops'] == 1
    assert shot_counts(shots, 2)['opportunities'] == 0
    shots = parse_shots(row('4+b28z^1f-2u-1*'))
    counts = shot_counts(shots, 1)
    assert counts['drop_volleys'] == counts['net_drops'] == counts['redrops'] == 1
    assert counts['primary_drops'] == 0


def test_approach_is_still_baseline_but_net_override_is_not():
    assert shot_counts(parse_shots(row('4b28u+1*')), 1)['primary_drops'] == 1
    assert shot_counts(parse_shots(row('4b28u-1*')), 1)['primary_drops'] == 0
    assert shot_counts(parse_shots(row('4b28u=1*')), 1)['primary_drops'] == 1


@pytest.mark.parametrize('first', ['R', 'S', '6q3n#', '6b28u1', '3b28u1*', '6b2df1*'])
def test_unknown_or_malformed_points_are_not_zero_drop(first):
    with pytest.raises(ValueError):
        parse_shots(row(first))


def test_known_penalties_and_winner_consistency():
    assert parse_shots(row('P', winner=2)) == []
    assert parse_shots(row('Q', winner=1)) == []
    with pytest.raises(ValueError, match='winner mismatch'):
        parse_shots(row('6b28u1*', winner=2))


def test_rules_override_obsolete_wimbledon_and_us_open_flags():
    rules, note = rules_for(metadata())
    assert rules == Rules(5, 6, 10)
    assert note
    assert rules_for(metadata(Date='20210830', Tournament='US Open', **{'Final TB?': 'A'}))[0] == Rules(5, 6, 7)
    assert rules_for(metadata(Date='20210530', Tournament='Roland Garros', **{'Final TB?': '0'}))[0] == Rules(5, None, 7)
    # Qualifying used ordinary tiebreaks, even when men's main draws did not.
    assert rules_for(metadata(Date='20200921', Tournament='Roland Garros', **{'Best of': '3', 'Final TB?': '1'}))[0] == Rules(3, 6, 7)


def test_server_first_scores_and_tiebreak_rotation():
    r = row(server=1, winner=2, Set1='2', Set2='2', Gm1='6', Gm2='6', Pts='0-3')
    state = read_state(r, Rules(5, 6, 10))
    assert (state.p1, state.p2) == (0, 3)
    state = advance(state, 2, Rules(5, 6, 10))
    assert state.server == 1
    state = advance(state, 2, Rules(5, 6, 10))
    assert state.server == 2
    assert read_state({**r, 'Pts': '5-0', 'Svr': '2'}, Rules(5, 6, 10)) == state
    assert [tb_server(1, n) for n in range(9)] == [1, 2, 2, 1, 1, 2, 2, 1, 1]


def test_normal_game_deuce_and_set_transitions():
    rules = Rules()
    s = State(0, 0, 5, 4, 3, 3, 1)
    assert advance(advance(s, 1, rules), 2, rules) == s
    end = advance(advance(s, 1, rules), 1, rules)
    assert end == State(1, 0, 0, 0, 0, 0, 2)
    flags = pressure(replace(s, p1=4), rules, 2)
    assert flags['set_point_against'] and not flags['match_point_against']


def test_seven_and_ten_point_tiebreaks_and_next_set_server():
    state = State(0, 0, 6, 6, 6, 5, 1)  # first TB server was player 1
    assert advance(state, 1, Rules()) == State(1, 0, 0, 0, 0, 0, 2)
    s = State(2, 2, 6, 6, 6, 5, 1)
    assert not pressure(s, Rules(5, 6, 10), 1)['match_point_for']
    assert advance(s, 1, Rules(5, 6, 10)).s1 == 2
    s = State(2, 2, 6, 6, 9, 8, 1)
    assert pressure(s, Rules(5, 6, 10), 1)['match_point_for']
    assert advance(s, 1, Rules(5, 6, 10)).s1 == 3


def test_analytic_probability_boundaries_and_extended_scores():
    p = .65
    deuce = p**2 / (p**2 + (1-p)**2)
    assert game_probability(3, 3, p) == pytest.approx(deuce)
    assert game_probability(4, 3, p) == pytest.approx(p + (1-p)*deuce)
    for first in (1, 2):
        for target in (7, 10):
            assert tb_probability(0, 0, first, target, p) == pytest.approx(.5)
            assert tb_probability(50, 50, first, target, p) == .5
        assert set_probability(0, 0, first, 6, 7, p) == pytest.approx(.5)
        assert match_probability(State(0, 0, 0, 0, 0, 0, first), Rules()) == pytest.approx(.5)
    assert set_probability(20, 20, 1, None, 7, p) == .5
    assert match_probability(State(2, 0, 0, 0, 0, 0, 1), Rules()) == 1


def test_pressure_is_prepoint_and_player_symmetric():
    rules = Rules(5, 6, 10)
    source = row(Set1='2', Set2='2', Gm1='5', Gm2='5', Pts='30-40')
    baseline = pressure(read_state(source, rules), rules, 1)
    # The point winner and rally (and any subsequent records) are not inputs.
    altered = {**source, 'PtWinner': '2', '1st': '6*'}
    assert pressure(read_state(altered, rules), rules, 1) == baseline
    state = read_state(source, rules)
    swapped = State(state.s2, state.s1, state.g2, state.g1, state.p2, state.p1, 3-state.server)
    assert match_probability(swapped, rules) == pytest.approx(1-match_probability(state, rules))
    assert pressure(swapped, rules, 2)['leverage'] == pytest.approx(baseline['leverage'])
    assert baseline['break_point_against']


def test_bad_score_excludes_match_without_deleting_shots():
    meta = {'match': metadata(**{'Best of': '3', 'Final TB?': '1', 'Tournament': 'Paris Masters'})}
    raw = {'match': [row(), row(Pt='2', Pts='0-15', source_row=2)]}  # first point was won by server
    detail, audit, coverage = normalize(meta, raw)
    assert len(detail) == 2
    assert all(r['shot_observed'] and not r['score_valid'] for r in detail)
    assert any(r['category'] == 'score_transition' for r in audit)
    assert not coverage[0]['score_valid']


def test_unobserved_points_are_excluded_from_usage_denominator():
    meta = {'match': metadata(**{'Best of': '3', 'Final TB?': '1', 'Tournament': 'Paris Masters'})}
    raw = {'match': [row(), row(first='S', Pt='2', Pts='15-0', source_row=2)]}
    detail, audit, coverage = normalize(meta, raw)
    total = summarize(detail)
    assert total['observed_points'] == total['primary_drops'] == 1
    assert total['drop_points_per_100'] == 100


def test_overlap_estimator_has_known_answer_and_drops_unpaired_strata():
    def record(mid, high, n, d):
        return dict(match_id=mid, edition=mid, serving=True, high_importance=high,
                    score_valid=True, shot_observed=True, opportunities=n,
                    n1=n, d1=d, n2=0, d2=0, n3=0, d3=0)
    # Overlap weights 5 and 15: standardized low=.175, high=.30.
    points = [record('A', False, 10, 1), record('A', True, 10, 3),
              record('B', False, 30, 6), record('B', True, 30, 9),
              record('unpaired', False, 100, 99)]
    result = estimate(points, 'high_importance', replicates=100)
    assert result['low_per_100'] == pytest.approx(17.5)
    assert result['high_per_100'] == pytest.approx(30)
    assert result['difference_pp'] == pytest.approx(12.5)
    assert result['matches'] == result['editions'] == 2
    assert result['excluded_strokes_no_overlap'] == pytest.approx(100)
    assert estimate(points, 'high_importance', replicates=100) == result


def test_single_edition_has_no_inferential_interval():
    points = [dict(match_id='a', edition='a', serving=True, high_importance=high,
                   score_valid=True, shot_observed=True, opportunities=10,
                   n1=10, d1=0, n2=0, d2=0, n3=0, d3=0) for high in (False, True)]
    result = estimate(points, 'high_importance')
    assert result['low_per_100'] == result['high_per_100'] == 0
    assert result['ci_low'] is None and result['relative_rate'] is None


def test_bad_source_bytes_are_rejected_not_overwritten(tmp_path):
    from tennislab.analysis.drop_shots import COMMIT, SOURCE_FILES
    import hashlib
    import urllib.parse

    raw = tmp_path / 'data/raw/charting'
    raw.mkdir(parents=True)
    files = []
    for name in SOURCE_FILES:
        (raw / name).write_bytes(b'good')
        files.append(dict(path=name, bytes=4, sha256=hashlib.sha256(b'good').hexdigest(),
                          url=f'https://raw.githubusercontent.com/JeffSackmann/tennis_MatchChartingProject/{COMMIT}/'+urllib.parse.quote(name)))
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/charting_sources.lock.json').write_text(json.dumps(dict(commit=COMMIT, files=files)))
    (raw / SOURCE_FILES[0]).write_bytes(b'bad!')
    with pytest.raises(ValueError, match='raw checksum mismatch'):
        verify_sources(tmp_path, fetch=True)
    assert (raw / SOURCE_FILES[0]).read_bytes() == b'bad!'
