from __future__ import annotations

import pandas as pd

from scripts.generate_data import CANONICAL_STAGES, generate_events


def test_event_ids_are_unique_and_required_fields_are_present() -> None:
    events, users = generate_events(n_users=1_200, seed=123)
    assert events["event_id"].is_unique
    assert events[["event_id", "user_id", "event_name", "event_ts"]].notna().all().all()
    assert users["user_id"].is_unique
    assert set(events["event_name"]).issubset(set(CANONICAL_STAGES) | {"ride_completed"})


def test_stage_order_and_dependencies_hold() -> None:
    events, _ = generate_events(n_users=1_200, seed=456)
    events["event_ts"] = pd.to_datetime(events["event_ts"], format="ISO8601", utc=True)
    first_events = (
        events.loc[events["event_name"].isin(CANONICAL_STAGES)]
        .groupby(["user_id", "event_name"], as_index=False)["event_ts"]
        .min()
        .pivot(index="user_id", columns="event_name", values="event_ts")
    )
    for previous_stage, next_stage in zip(CANONICAL_STAGES, CANONICAL_STAGES[1:]):
        reached_next = first_events[next_stage].notna()
        assert first_events.loc[reached_next, previous_stage].notna().all()
        assert (first_events.loc[reached_next, next_stage] >= first_events.loc[reached_next, previous_stage]).all()


def test_generation_is_deterministic() -> None:
    first_events, first_users = generate_events(n_users=300, seed=789)
    second_events, second_users = generate_events(n_users=300, seed=789)
    pd.testing.assert_frame_equal(first_events, second_events)
    pd.testing.assert_frame_equal(first_users, second_users)
