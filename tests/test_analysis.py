from __future__ import annotations

from pathlib import Path

from scripts import run_analysis as analysis_module
from scripts.generate_data import write_outputs
from scripts.run_analysis import run_analysis


def test_analysis_recomputes_monotonic_funnel_and_complete_cohorts(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    for name, location in {"PROCESSSED_DIR": "data/processed", "TABLES_DIR": "reports/tables",
                           "FIGURES_DIR": "reports/figures", "REPORTS_DIR": "reports"}.items():
        monkeypatch.setattr(analysis_module, name, root / location)
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
    signups = results["events"].loc[results["events"]["event_name"] == "signup"]
    expected_counts = signups["event_ts"].dt.strftime("%Y-%m").value_counts().to_dict()
    actual_counts = dict(zip(cohorts["signup_cohort"].astype(str).str[:7], cohorts["registrations"]))
    assert actual_counts == expected_counts
