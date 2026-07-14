"""Historical betting-odds source acquisition and verification."""

from tennislab.odds.config import (
    OddsSourceConfig,
    OddsSourceSpec,
    load_odds_source_config,
)
from tennislab.odds.fetch import OddsSourceFetchError, fetch_odds_sources
from tennislab.odds.manifest import OddsLockError, verify_odds_lock
from tennislab.odds.benchmark import (
    BENCHMARK_VERSION,
    OddsBenchmarkError,
    build_market_benchmark,
    consensus_probability,
)

__all__ = [
    "OddsLockError",
    "OddsBenchmarkError",
    "OddsSourceConfig",
    "OddsSourceFetchError",
    "OddsSourceSpec",
    "BENCHMARK_VERSION",
    "build_market_benchmark",
    "consensus_probability",
    "fetch_odds_sources",
    "load_odds_source_config",
    "verify_odds_lock",
]
