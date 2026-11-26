"""Small MCP notation reader for this study, not a general charting framework.

Notation authority: Instructions sheet, pinned MatchChart 0.3.2.xlsm.
Unknown or malformed sequences are retained in the audit, never counted as
observed non-drop points. Court position follows shot type and -/= overrides.
"""

from dataclasses import dataclass
import re


SHOT_CODES = 'fbrsvzopuylmhijktq'
BASELINE = set('fbrsuylm')
NET = set('vzophijk')


@dataclass(frozen=True)
class Shot:
    code: str
    modifiers: str
    player: int
    number: int  # serve = 1, return = 2

    @property
    def at_net(self) -> bool:
        return False if '=' in self.modifiers else '-' in self.modifiers or self.code in NET

    @property
    def drop(self) -> bool:
        return self.code in 'uy'

    @property
    def drop_volley(self) -> bool:
        return self.code in 'vzhijk' and '^' in self.modifiers


def parse_shots(row: dict) -> list[Shot]:
    """Parse the live serve/rally and cross-check its winner when observable."""
    server, winner = int(row['Svr']), int(row['PtWinner'])
    if server not in (1, 2) or winner not in (1, 2):
        raise ValueError('invalid server/winner')
    first, second = row['1st'].strip(), row['2nd'].strip()
    if second and not re.fullmatch(r'(?:c*[0456][+;^]*[ndwxge]|[Ve])', first):
        raise ValueError('second serve without a recognizable first-serve fault')
    sequence = second or first
    if sequence in ('R', 'S'):
        raise ValueError('unobserved point')
    if sequence in ('P', 'Q'):
        expected = 3 - server if sequence == 'P' else server
        if winner != expected:
            raise ValueError('penalty winner mismatch')
        return []
    serve = re.match(r'c*[0456][+;^]*', sequence)
    if not serve:
        raise ValueError('unrecognized serve sequence')
    tail = sequence[serve.end():]
    if not tail:
        raise ValueError('missing point ending')
    if re.fullmatch('[ndwxge]', tail):
        if not second:
            raise ValueError('first fault without second serve')
        if winner != 3 - server:
            raise ValueError('double-fault winner mismatch')
        return []
    if tail in ('*', '#', 'C'):
        if tail != 'C' and winner != server:
            raise ValueError('serve winner mismatch')
        return []
    tokens = list(re.finditer('[' + SHOT_CODES + ']', tail))
    if not tokens or tokens[0].start() != 0:
        raise ValueError('unrecognized rally prefix')
    shots = []
    for index, token in enumerate(tokens):
        end = tokens[index + 1].start() if index + 1 < len(tokens) else len(tail)
        modifiers = tail[token.end():end]
        if token.group() == 'q':
            raise ValueError('unknown shot type')
        if not re.fullmatch(r'[0-9+\-=;^!ndwxe@#*C]*', modifiers):
            raise ValueError('unrecognized shot modifiers')
        if index + 1 < len(tokens) and re.search(r'[@#*Cndwxe]', modifiers):
            raise ValueError('point ending before last stroke')
        shots.append(Shot(token.group(), modifiers, 3 - server if index % 2 == 0 else server, index + 2))
    endings = re.findall(r'[*@#C]', shots[-1].modifiers)
    if len(endings) != 1:
        raise ValueError('missing point ending')
    ending = endings[0]
    expected = shots[-1].player if ending == '*' else 3 - shots[-1].player
    if ending != 'C' and winner != expected:
        raise ValueError('shot/point winner mismatch')
    return shots


def shot_counts(shots: list[Shot], player: int) -> dict:
    """Return eligible choices by ordinal and distinct descriptive categories."""
    counts = dict(opportunities=0, primary_drops=0, all_drops=0, return_drops=0,
                  redrops=0, net_drops=0, drop_volleys=0)
    # Pair (own eligible-stroke ordinal capped at 3, drop event).
    choices = []
    prior_drop = False
    for shot in shots:
        if shot.player == player:
            if shot.drop:
                counts['all_drops'] += 1
                counts['return_drops'] += shot.number == 2
                counts['redrops'] += prior_drop
                counts['net_drops'] += shot.at_net
            counts['drop_volleys'] += shot.drop_volley
            if not prior_drop and shot.number > 2 and shot.code in BASELINE and not shot.at_net:
                counts['opportunities'] += 1
                counts['primary_drops'] += shot.drop
                choices.append((min(counts['opportunities'], 3), int(shot.drop)))
        prior_drop |= shot.drop or shot.drop_volley
    return {**counts, 'choices': choices}
