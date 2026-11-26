"""Score-only point importance for the Alcaraz study (equal serve strengths).

The 0.65 serve probability is an assumption, not a fitted player forecast.
Future sets start at 50/50 under this symmetric model. Deuce and extended
tiebreak tails are solved analytically rather than truncated.
"""

from dataclasses import dataclass, replace
from functools import lru_cache


@dataclass(frozen=True)
class Rules:
    best_of: int = 3
    final_tb_at: int | None = 6
    final_tb_target: int = 7

    def tiebreak(self, s1: int, s2: int) -> tuple[int | None, int]:
        if s1 == s2 == self.best_of // 2:
            return self.final_tb_at, self.final_tb_target
        return 6, 7


def rules_for(meta: dict) -> tuple[Rules, str]:
    """Edition rules take precedence over obsolete spreadsheet format codes."""
    year = int(meta['Date'][:4])
    event = meta['Tournament'].strip()
    code = meta['Final TB?']
    formats = {'1': (6, 7), '0': (None, 7), 'A': (6, 10), 'T': (12, 7)}
    if code not in formats or meta['Best of'] not in ('3', '5'):
        raise ValueError(f'unsupported scoring format: {meta["Best of"]}/{code}')
    at, target = formats[code]
    documented = (at, target)
    if event in ('Australian Open', 'Roland Garros', 'Wimbledon', 'US Open') and (meta['Best of'] == '5' or year >= 2022 or event == 'Australian Open'):
        if year >= 2022 or event == 'Australian Open' and year >= 2019:
            at, target = 6, 10
        elif event == 'Roland Garros':
            at, target = None, 7
        elif event == 'Wimbledon' and year >= 2019:
            at, target = 12, 7
        else:
            at, target = 6, 7
    note = '' if documented == (at, target) else f'{code} -> tiebreak at {at}, target {target}'
    return Rules(int(meta['Best of']), at, target), note


@dataclass(frozen=True)
class State:
    s1: int
    s2: int
    g1: int
    g2: int
    p1: int
    p2: int
    server: int

    def is_tb(self, rules: Rules) -> bool:
        at, _ = rules.tiebreak(self.s1, self.s2)
        return at is not None and self.g1 == self.g2 == at


def read_state(row: dict, rules: Rules) -> State:
    s1, s2, g1, g2, server = (int(row[k]) for k in ('Set1', 'Set2', 'Gm1', 'Gm2', 'Svr'))
    if server not in (1, 2) or min(s1, s2, g1, g2) < 0 or max(s1, s2) > rules.best_of // 2:
        raise ValueError('invalid score/server')
    at, _ = rules.tiebreak(s1, s2)
    tb = at is not None and g1 == g2 == at
    a, b = row['Pts'].split('-')
    lookup = {'0': 0, '15': 1, '30': 2, '40': 3, 'AD': 4}
    a, b = (int(a), int(b)) if tb else (lookup[a], lookup[b])
    if min(a, b) < 0 or (not tb and max(a, b) == 4 and min(a, b) != 3):
        raise ValueError('invalid point score')
    p1, p2 = (a, b) if server == 1 else (b, a)
    state = State(s1, s2, g1, g2, p1, p2, server)
    if max(g1, g2) >= 6 and abs(g1 - g2) >= 2:
        raise ValueError('set already finished')
    if at is not None and max(g1, g2) > at:
        raise ValueError('games exceed tiebreak boundary')
    if tb and max(a, b) >= rules.tiebreak(s1, s2)[1] and abs(a - b) >= 2:
        raise ValueError('tiebreak already finished')
    return state


def tb_server(first: int, points_played: int) -> int:
    return 3 - first if ((points_played + 1) // 2) % 2 else first


def point_ends_game(state: State, winner: int) -> bool:
    a, b = state.p1 + (winner == 1), state.p2 + (winner == 2)
    return max(a, b) >= 4 and abs(a - b) >= 2


def advance(state: State, winner: int, rules: Rules) -> State:
    if winner not in (1, 2):
        raise ValueError('invalid point winner')
    a, b = state.p1 + (winner == 1), state.p2 + (winner == 2)
    tb = state.is_tb(rules)
    target = rules.tiebreak(state.s1, state.s2)[1] if tb else 4
    ends = max(a, b) >= target and abs(a - b) >= 2
    if tb:
        first = tb_server(state.server, state.p1 + state.p2)  # inversion is identical
        next_server = tb_server(first, a + b)
    else:
        next_server = state.server
    if not ends:
        if not tb and min(a, b) >= 3:
            a, b = a - min(a, b) + 3, b - min(a, b) + 3
        return replace(state, p1=a, p2=b, server=next_server)
    g1, g2 = state.g1 + (winner == 1), state.g2 + (winner == 2)
    next_server = 3 - first if tb else 3 - state.server
    if tb or max(g1, g2) >= 6 and abs(g1 - g2) >= 2:
        return State(state.s1 + (winner == 1), state.s2 + (winner == 2), 0, 0, 0, 0, next_server)
    return State(state.s1, state.s2, g1, g2, 0, 0, next_server)


@lru_cache(maxsize=None)
def game_probability(a: int, b: int, p: float) -> float:
    if max(a, b) >= 4 and abs(a - b) >= 2:
        return float(a > b)
    if min(a, b) >= 3:
        deuce = p * p / (p * p + (1 - p) ** 2)
        return deuce if a == b else p + (1 - p) * deuce if a > b else p * deuce
    return p * game_probability(a + 1, b, p) + (1 - p) * game_probability(a, b + 1, p)


@lru_cache(maxsize=None)
def tb_probability(a: int, b: int, first: int, target: int, serve_p: float) -> float:
    if max(a, b) >= target and abs(a - b) >= 2:
        return float(a > b)
    p = serve_p if tb_server(first, a + b) == 1 else 1 - serve_p
    if min(a, b) >= target - 1:
        # From a tied extended breaker each player serves once in the next pair.
        return 0.5 if a == b else p + (1 - p) * 0.5 if a > b else p * 0.5
    return p * tb_probability(a + 1, b, first, target, serve_p) + (1 - p) * tb_probability(a, b + 1, first, target, serve_p)


@lru_cache(maxsize=None)
def set_probability(g1: int, g2: int, server: int, tb_at: int | None, target: int, serve_p: float) -> float:
    if max(g1, g2) >= 6 and abs(g1 - g2) >= 2:
        return float(g1 > g2)
    if tb_at is not None and g1 == g2 == tb_at:
        return 0.5
    p = game_probability(0, 0, serve_p if server == 1 else 1 - serve_p)
    if tb_at is None and min(g1, g2) >= 5:
        return 0.5 if g1 == g2 else p + (1 - p) * 0.5 if g1 > g2 else p * 0.5
    return p * set_probability(g1 + 1, g2, 3 - server, tb_at, target, serve_p) + (1 - p) * set_probability(g1, g2 + 1, 3 - server, tb_at, target, serve_p)


@lru_cache(maxsize=None)
def remaining_match(s1: int, s2: int, needed: int) -> float:
    if max(s1, s2) == needed:
        return float(s1 == needed)
    return 0.5 * (remaining_match(s1 + 1, s2, needed) + remaining_match(s1, s2 + 1, needed))


def match_probability(state: State, rules: Rules, serve_p: float = 0.65) -> float:
    needed = rules.best_of // 2 + 1
    if max(state.s1, state.s2) == needed:
        return float(state.s1 == needed)
    at, target = rules.tiebreak(state.s1, state.s2)
    if state.is_tb(rules):
        first = tb_server(state.server, state.p1 + state.p2)
        set_p = tb_probability(state.p1, state.p2, first, target, serve_p)
    else:
        p = serve_p if state.server == 1 else 1 - serve_p
        game_p = game_probability(state.p1, state.p2, p)
        set_p = game_p * set_probability(state.g1 + 1, state.g2, 3 - state.server, at, target, serve_p)
        set_p += (1 - game_p) * set_probability(state.g1, state.g2 + 1, 3 - state.server, at, target, serve_p)
    return set_p * remaining_match(state.s1 + 1, state.s2, needed) + (1 - set_p) * remaining_match(state.s1, state.s2 + 1, needed)


def pressure(state: State, rules: Rules, player: int, serve_p: float = 0.65) -> dict:
    after = {w: advance(state, w, rules) for w in (1, 2)}
    importance = match_probability(after[1], rules, serve_p) - match_probability(after[2], rules, serve_p)
    tb = state.is_tb(rules)
    flags = {'leverage': importance, 'high_importance': importance >= 0.10,
             'tiebreak': tb, 'deciding_set': state.s1 == state.s2 == rules.best_of // 2}
    for suffix, w in [('for', player), ('against', 3 - player)]:
        flags['break_point_' + suffix] = not tb and w != state.server and point_ends_game(state, w)
        flags['set_point_' + suffix] = after[w].s1 + after[w].s2 > state.s1 + state.s2
        flags['match_point_' + suffix] = max(after[w].s1, after[w].s2) == rules.best_of // 2 + 1
    return flags
