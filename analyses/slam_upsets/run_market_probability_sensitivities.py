"""Convenience entry point for the prespecified market probability reparse."""

from pathlib import Path

from tennislab.analysis.market_probability import (
    build_market_probability_sensitivities,
)


if __name__ == "__main__":
    print(
        build_market_probability_sensitivities(
            sensitivity_config_path=Path(
                "config/market_probability_sensitivities.json"
            ),
            predictions_path=Path("data/processed/predictions.parquet"),
            market_predictions_path=Path(
                "data/processed/market_predictions.parquet"
            ),
            market_observations_path=Path(
                "data/processed/market_benchmark_observations.csv"
            ),
            odds_config_path=Path("config/odds_sources.toml"),
            odds_lock_path=Path("config/odds_sources.lock.json"),
            aliases_path=Path("config/odds_aliases.csv"),
            raw_dir=Path("data/raw/odds/tennis-data"),
            output_dir=Path("artifacts/robustness"),
            observation_detail_path=Path(
                "data/processed/market_probability_sensitivity_observations.csv"
            ),
            pair_detail_path=Path(
                "data/processed/market_probability_pair_audit.csv"
            ),
        )
    )
