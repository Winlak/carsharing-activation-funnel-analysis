"""Create a deterministic synthetic event log for a car-sharing first-ride funnel.

The simulator deliberately injects plausible segment differences. It does not use,
approximate, or represent any operator's customer data.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20250812
UTC = timezone.utc
START_AT = datetime(2025, 1, 1, tzinfo=UTC)
SIGNUP_END_AT = datetime(2025, 4, 30, 23, 59, tzinfo=UTC)
ANALYSIS_END_AT = datetime(2025, 6, 30, 23, 59, tzinfo=UTC)
CANONICAL_STAGES = [
    "signup",
    "verification",
    "payment_method",
    "search",
    "booking",
    "first_ride",
]

CHANNELS = ["organic", "paid_search", "referral", "partner"]
PLATFORMS = ["ios", "android", "web"]
CITIES = ["Moscow", "Saint Petersburg", "Kazan"]


def _clip_probability(value: float) -> float:
    return float(np.clip(value, 0.02, 0.98))


def _event_id(user_id: str, event_name: str, event_at: datetime, ordinal: int) -> str:
    value = f"{user_id}|{event_name}|{event_at.isoformat()}|{ordinal}".encode()
    return hashlib.sha256(value).hexdigest()[:24]


def _ts(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _probability(stage: str, channel: str, platform: str, city: str) -> float:
    """Return stage-progression probability from explicit synthetic assumptions."""
    base = {
        "verification": 0.77,
        "payment_method": 0.76,
        "search": 0.93,
        "booking": 0.66,
        "first_ride": 0.78,
    }[stage]
    channel_effect = {
        "organic": 0.00,
        "paid_search": -0.055,
        "referral": 0.075,
        "partner": -0.020,
    }[channel]
    platform_effect = {
        "ios": 0.025,
        "android": 0.00,
        "web": -0.080,
    }[platform]
    city_effect = {"Moscow": 0.015, "Saint Petersburg": -0.035, "Kazan": 0.0}[city]
    stage_adjustment = 0.0
    if stage == "payment_method" and platform == "web":
        stage_adjustment -= 0.055
    if stage == "booking" and platform == "web":
        stage_adjustment -= 0.075
    if stage == "booking" and city == "Saint Petersburg":
        stage_adjustment -= 0.055
    if stage == "first_ride" and channel == "paid_search":
        stage_adjustment -= 0.025
    return _clip_probability(base + channel_effect + platform_effect + city_effect + stage_adjustment)


def _delay_hours(stage: str, generator: np.random.Generator) -> float:
    """Positive, bounded waiting time between a completed step and the next one."""
    distributions = {
        "verification": (2.2, 0.15, 48.0),
        "payment_method": (5.5, 0.20, 72.0),
        "search": (10.0, 0.10, 120.0),
        "booking": (17.0, 0.20, 168.0),
        "first_ride": (28.0, 0.50, 240.0),
    }
    mean, lower, upper = distributions[stage]
    return float(np.clip(generator.exponential(mean), lower, upper))


def generate_events(n_users: int = 12_000, seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate user and event tables at deterministic user and event grain."""
    if n_users < 1:
        raise ValueError("n_users must be positive")

    rng = np.random.default_rng(seed)
    span_seconds = int((SIGNUP_END_AT - START_AT).total_seconds())
    signup_offsets = rng.integers(0, span_seconds + 1, size=n_users)
    signup_times = sorted(START_AT + timedelta(seconds=int(value)) for value in signup_offsets)

    profile_rows: list[dict[str, str]] = []
    event_rows: list[dict[str, str]] = []
    for index, signup_at in enumerate(signup_times, start=1):
        user_id = f"u_{index:05d}"
        channel = str(rng.choice(CHANNELS, p=[0.36, 0.30, 0.19, 0.15]))
        platform = str(rng.choice(PLATFORMS, p=[0.36, 0.48, 0.16]))
        city = str(rng.choice(CITIES, p=[0.57, 0.29, 0.14]))
        profile_rows.append(
            {
                "user_id": user_id,
                "signup_ts": _ts(signup_at),
                "acquisition_channel": channel,
                "platform": platform,
                "city": city,
            }
        )

        ordinal = 1

        def append_event(event_name: str, event_at: datetime, session_suffix: str) -> None:
            nonlocal ordinal
            event_rows.append(
                {
                    "event_id": _event_id(user_id, event_name, event_at, ordinal),
                    "user_id": user_id,
                    "event_name": event_name,
                    "event_ts": _ts(event_at),
                    "session_id": f"s_{user_id}_{session_suffix}",
                    "acquisition_channel": channel,
                    "platform": platform,
                    "city": city,
                }
            )
            ordinal += 1

        append_event("signup", signup_at, "signup")
        current_at = signup_at
        first_ride_at: datetime | None = None
        for stage in CANONICAL_STAGES[1:]:
            if rng.random() > _probability(stage, channel, platform, city):
                break
            current_at += timedelta(hours=_delay_hours(stage, rng))
            append_event(stage, current_at, stage)
            if stage == "first_ride":
                first_ride_at = current_at

        if first_ride_at is not None:
            # Repeat-ride probabilities decrease with distance from the first ride.
            for day, probability in [(1, 0.37), (7, 0.28), (30, 0.19)]:
                if rng.random() <= probability:
                    repeat_at = first_ride_at + timedelta(
                        days=day, hours=float(rng.uniform(0.1, 20.0))
                    )
                    if repeat_at <= ANALYSIS_END_AT:
                        append_event("ride_completed", repeat_at, f"repeat_{day}")

    events = pd.DataFrame(event_rows).sort_values(["event_ts", "event_id"], kind="stable")
    users = pd.DataFrame(profile_rows).sort_values("user_id", kind="stable")
    return events.reset_index(drop=True), users.reset_index(drop=True)


def write_outputs(
    output: Path, users_output: Path, sample_output: Path, n_users: int, seed: int
) -> None:
    events, users = generate_events(n_users=n_users, seed=seed)
    for path in [output, users_output, sample_output]:
        path.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(output, index=False)
    users.to_csv(users_output, index=False)
    events.head(120).to_csv(sample_output, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--users-output", type=Path, required=True)
    parser.add_argument("--sample-output", type=Path, required=True)
    parser.add_argument("--n-users", type=int, default=12_000)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    write_outputs(args.output, args.users_output, args.sample_output, args.n_users, args.seed)
    print(f"Generated {args.n_users:,} users and event log at {args.output}")


if __name__ == "__main__":
    main()
