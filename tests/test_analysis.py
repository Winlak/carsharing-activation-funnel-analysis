from __future__ import annotations

from pathlib import Path

from scripts.generate_data import write_outputs
from scripts.run_analysis import run_analysis


def test_analysis_recomputes_monotonic_funnel_and_complete_cohorts() -> None:
    root = Path(__file__).resolve().parents[1]
    write_outputs(
        root / "data" / "raw" / "events.csv",
        root / "data" / "raw" / "users.csv",
        root / "data" / "sample" / "events_sample.csv",
        n_users=1_500,
        seed=101,
    )
    results = run_analysis(root)
    assert (results["quality"]["issue_value"] == 0).all()
    assert results["funnel"]["users"].is_monotonic_decreasing
    cohorts = results["cohorts"]
    assert (cohorts["activation_d1"] <= cohorts["activation_d7"]).all()
    assert (cohorts["activation_d7"] <= cohorts["activation_d30"]).all()
