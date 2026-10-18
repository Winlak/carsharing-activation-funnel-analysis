from pathlib import Path

import duckdb
import pandas as pd
import pytest

SQL_DIR = Path(__file__).resolve().parents[1] / 'sql'
STAGES = ['signup', 'verification', 'payment_method', 'search', 'booking', 'first_ride']


@pytest.fixture
def query(tmp_path, monkeypatch):
    rows = []
    cases = [
        ('valid', '2025-01-01', 'normal'), ('old', '2024-12-31', 'normal'),
        ('late', '2025-05-01', 'normal'), ('missing', '2025-02-01', 'missing'),
        ('last_day', '2025-04-30', 'normal'), ('broken_order', '2025-02-01', 'broken'),
        ('outside_30d', '2025-02-01', 'outside'),
    ]
    for user, signup, mode in cases:
        for i, stage in enumerate(STAGES):
            if mode == 'missing' and i == 0:
                continue
            hours = -1 if mode == 'broken' and i == 1 else i
            if mode == 'outside' and i > 0:
                hours += 31 * 24
            rows.append(dict(event_id=f'{user}-{i}', user_id=user, event_name=stage,
                             event_ts=(pd.Timestamp(signup) + pd.Timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                             acquisition_channel='organic', platform='web', city='Moscow'))
    dest = tmp_path / 'data/raw'
    dest.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(dest / 'events.csv', index=False)
    monkeypatch.chdir(tmp_path)

    def execute(name, dimension=None):
        sql = (SQL_DIR / name).read_text()
        if dimension:
            sql = sql.replace('{{SEGMENT}}', dimension)
        with duckdb.connect() as con:
            return con.execute(sql).df()
    return execute


def test_overall_funnel_uses_signup_cohort_and_entire_valid_path(query):
    assert query('02_funnel_overall.sql')['users'].tolist() == [4, 2, 2, 2, 2, 2]


@pytest.mark.parametrize('dimension', ['platform', 'city', 'acquisition_channel'])
def test_segments_share_overall_cohort(query, dimension):
    assert query('03_funnel_by_segment.sql', dimension)['users'].tolist() == [4, 2, 2, 2, 2, 2]


def test_time_to_step_excludes_users_outside_cohort_or_with_broken_path(query):
    assert query('04_time_to_step_and_dropoff.sql')['users_reaching_both_steps'].tolist() == [2, 2, 2, 2, 2]


def test_cohorts_share_funnel_population_and_valid_activation(query):
    result = query('05_cohorts_activation_retention.sql')
    assert result['registrations'].sum() == 4
    assert result['signup_cohort'].dt.strftime('%Y-%m').tolist() == ['2025-01', '2025-02', '2025-04']
    assert (result['activation_d30'] * result['registrations']).sum() == 2


def test_quality_checks_flag_missing_signup_and_invalid_order(query):
    result = query('01_data_quality.sql').set_index('check_name')['issue_value']
    assert result['missing_signup'] == 1
    assert result['stage_order_violation'] >= 2
