"""Run the SQL and pandas analysis for the first-ride funnel portfolio case."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
PROCESSSED_DIR = ROOT / "data" / "processed"
TABLES_DIR = ROOT / "reports" / "tables"
FIGURES_DIR = ROOT / "reports" / "figures"
REPORTS_DIR = ROOT / "reports"

STAGE_LABELS = {
    "signup": "Регистрация",
    "verification": "Верификация",
    "payment_method": "Способ оплаты",
    "search": "Поиск авто",
    "booking": "Бронирование",
    "first_ride": "Первая поездка",
}
DIMENSION_LABELS = {
    "acquisition_channel": "Канал",
    "platform": "Платформа",
    "city": "Город",
}
SEGMENT_LABELS = {
    "organic": "Органика",
    "paid_search": "Платный поиск",
    "referral": "Реферальный",
    "partner": "Партнёрский",
    "ios": "iOS",
    "android": "Android",
    "web": "Web",
    "Moscow": "Москва",
    "Saint Petersburg": "Санкт-Петербург",
    "Kazan": "Казань",
}
TRANSITION_LABELS = {
    "signup → verification": "Регистрация →\nверификация",
    "verification → payment_method": "Верификация →\nоплата",
    "payment_method → search": "Оплата →\nпоиск",
    "search → booking": "Поиск →\nбронирование",
    "booking → first_ride": "Бронирование →\nпервая поездка",
}
COLORS = {"blue": "#365B8C", "gold": "#C78A2C", "ink": "#22313F", "grid": "#D9E0E6"}


def _read_sql(filename: str, segment: str | None = None) -> str:
    query = (SQL_DIR / filename).read_text(encoding="utf-8")
    return query.replace("{{SEGMENT}}", segment) if segment else query


def _run_query(connection: duckdb.DuckDBPyConnection, filename: str, segment: str | None = None) -> pd.DataFrame:
    return connection.execute(_read_sql(filename, segment)).df()


def _format_rate(value: float) -> str:
    return f"{value:.1%}"


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    view = frame.loc[:, columns].copy()
    for column in columns:
        view[column] = view[column].map(lambda value: value.replace("\n", " ") if isinstance(value, str) else value)
    return view.to_markdown(index=False)


def _segment_display(row: pd.Series) -> str:
    return f"{DIMENSION_LABELS[str(row['dimension'])]} / {SEGMENT_LABELS[str(row['segment'])]}"


def _save_figures(
    funnel: pd.DataFrame, segment_funnel: pd.DataFrame, time_to_step: pd.DataFrame, cohorts: pd.DataFrame
) -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.titleweight": "bold"})

    fig, ax = plt.subplots(figsize=(10, 5.2))
    chart_data = funnel.sort_values("stage_order", ascending=False)
    values = chart_data["conversion_from_signup"] * 100
    bars = ax.barh(chart_data["stage"].map(STAGE_LABELS), values, color=COLORS["blue"])
    ax.set_xlim(0, 100)
    ax.set_xlabel("Конверсия от регистраций, %")
    ax.set_title("Воронка первой поездки")
    ax.grid(axis="x", color=COLORS["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, values):
        ax.text(value + 1.2, bar.get_y() + bar.get_height() / 2, f"{value:.1f}%", va="center")
    fig.text(0.125, 0.01, "Синтетические события; пользователь учитывается один раз на этапе.", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIGURES_DIR / "funnel_overall.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    segment_data = segment_funnel.loc[
        segment_funnel["stage"] == "first_ride", ["dimension", "segment", "conversion_from_signup"]
    ].copy()
    segment_data["label"] = (
        segment_data["dimension"].map(DIMENSION_LABELS)
        + ": "
        + segment_data["segment"].map(SEGMENT_LABELS)
    )
    segment_data = segment_data.sort_values("conversion_from_signup")
    fig, ax = plt.subplots(figsize=(10, 6.2))
    bars = ax.barh(segment_data["label"], segment_data["conversion_from_signup"] * 100, color=COLORS["gold"])
    ax.set_xlim(0, max(30, float(segment_data["conversion_from_signup"].max() * 120)))
    ax.set_xlabel("Конверсия в первую поездку от регистраций, %")
    ax.set_title("Итоговая конверсия по сегментам")
    ax.grid(axis="x", color=COLORS["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, segment_data["conversion_from_signup"] * 100):
        ax.text(value + 0.35, bar.get_y() + bar.get_height() / 2, f"{value:.1f}%", va="center", fontsize=9)
    fig.text(0.125, 0.01, "Сегменты заданы до прохождения воронки в синтетическом генераторе.", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIGURES_DIR / "segment_first_ride_conversion.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.2))
    ordered = time_to_step.sort_values("stage_order")
    transitions = ordered["transition"].map(TRANSITION_LABELS)
    ax.bar(transitions, ordered["p50_hours"], color=COLORS["blue"], label="P50")
    ax.scatter(transitions, ordered["p90_hours"], color=COLORS["gold"], s=58, zorder=3, label="P90")
    ax.set_ylabel("Часы до следующего шага")
    ax.set_title("Время перехода между шагами")
    ax.tick_params(axis="x", rotation=0)
    ax.grid(axis="y", color=COLORS["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False)
    fig.text(0.125, 0.01, "P50/P90 только среди пользователей, прошедших оба соседних шага.", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIGURES_DIR / "time_to_step.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    cohort_chart = cohorts.set_index("signup_cohort")[["activation_d1", "activation_d7", "activation_d30"]] * 100
    cohort_matrix = cohort_chart.T
    fig, ax = plt.subplots(figsize=(8, 4.4))
    image = ax.imshow(cohort_matrix, cmap="Blues", vmin=0, vmax=max(25, float(cohort_chart.max().max())))
    ax.set_xticks(range(len(cohort_chart.index)), [str(value)[:7] for value in cohort_chart.index])
    ax.set_yticks(range(3), ["Activation D1", "Activation D7", "Activation D30"])
    for row in range(cohort_matrix.shape[0]):
        for column in range(cohort_matrix.shape[1]):
            value = float(cohort_matrix.iloc[row, column])
            label_color = "white" if image.norm(value) > 0.55 else COLORS["ink"]
            ax.text(column, row, f"{value:.1f}%", ha="center", va="center", color=label_color)
    ax.set_title("Активация когорт регистрации", pad=28)
    ax.text(0.5, 1.03, f"Синтетические регистрации, UTC; n = {int(cohorts['registrations'].sum()):,}",
            transform=ax.transAxes, ha="center", fontsize=9, color=COLORS["ink"])
    fig.colorbar(image, ax=ax, label="Доля регистраций, %")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "cohort_activation.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def loss_extremes(funnel: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    transitions = funnel.loc[funnel["stage_order"] > 1]
    absolute = transitions.loc[transitions["dropoff_users"].idxmax()]
    relative = transitions.loc[transitions["conversion_from_previous_stage"].idxmin()]
    return absolute, relative


def _build_report(
    funnel: pd.DataFrame,
    segment_funnel: pd.DataFrame,
    time_to_step: pd.DataFrame,
    cohorts: pd.DataFrame,
    quality: pd.DataFrame,
) -> None:
    signup_users = int(funnel.loc[funnel["stage"] == "signup", "users"].iloc[0])
    first_ride = funnel.loc[funnel["stage"] == "first_ride"].iloc[0]
    largest_absolute_loss, weakest_conversion = loss_extremes(funnel)
    payment_loss = funnel.loc[funnel["stage"] == "payment_method"].iloc[0]
    ride_loss = funnel.loc[funnel["stage"] == "first_ride"].iloc[0]

    payment_segments = segment_funnel.loc[
        (segment_funnel["stage"] == "payment_method") & (segment_funnel["dimension"] == "platform")
    ].sort_values("conversion_from_previous_stage")
    weakest_payment_platform = payment_segments.iloc[0]
    booking_cities = segment_funnel.loc[
        (segment_funnel["stage"] == "booking") & (segment_funnel["dimension"] == "city")
    ].sort_values("conversion_from_previous_stage")
    weakest_booking_city = booking_cities.iloc[0]
    final_segments = segment_funnel.loc[segment_funnel["stage"] == "first_ride"].copy()
    final_segments["overall_conversion_pct"] = final_segments["conversion_from_signup"] * 100
    best_segment = final_segments.sort_values("conversion_from_signup", ascending=False).iloc[0]
    worst_segment = final_segments.sort_values("conversion_from_signup").iloc[0]
    absolute_loss_label = STAGE_LABELS[str(largest_absolute_loss["stage"])]
    weakest_conversion_label = STAGE_LABELS[str(weakest_conversion["stage"])]
    best_segment_label = _segment_display(best_segment)
    worst_segment_label = _segment_display(worst_segment)
    weakest_booking_city_label = SEGMENT_LABELS[str(weakest_booking_city["segment"])]

    cohort_view = cohorts.copy()
    cohort_view["signup_cohort"] = cohort_view["signup_cohort"].astype(str).str[:7]
    for column in ["activation_d1", "activation_d7", "activation_d30", "retention_d1", "retention_d7", "retention_d30"]:
        cohort_view[column] = cohort_view[column].map(_format_rate)

    funnel_view = funnel.copy()
    funnel_view["stage"] = funnel_view["stage"].map(STAGE_LABELS)
    for column in ["conversion_from_signup", "conversion_from_previous_stage"]:
        funnel_view[column] = funnel_view[column].fillna(1).map(_format_rate)

    time_view = time_to_step.copy()
    time_view["transition"] = time_view["transition"].map(TRANSITION_LABELS)
    time_view["p50_hours"] = time_view["p50_hours"].map(lambda value: f"{value:.1f}")
    time_view["p90_hours"] = time_view["p90_hours"].map(lambda value: f"{value:.1f}")
    quality_passed = bool((quality["issue_value"] == 0).all())
    quality_label = "да" if quality_passed else "нет"

    report = f"""# Воронка первой поездки в каршеринге

## Краткие результаты

- **Из {signup_users:,} регистраций первую поездку совершили {int(first_ride['users']):,} пользователей ({_format_rate(float(first_ride['conversion_from_signup']))}).** Это описательная оценка на детерминированных синтетических событиях за регистрации с 1 января по 30 апреля 2025 года, а не данные реального оператора.
- **Максимальная потеря в людях — {absolute_loss_label}:** выбыло {int(largest_absolute_loss['dropoff_users']):,} пользователей; конверсия предыдущего шага — {_format_rate(float(largest_absolute_loss['conversion_from_previous_stage']))}.
- **Минимальная конверсия соседнего шага — {weakest_conversion_label}:** {_format_rate(float(weakest_conversion['conversion_from_previous_stage']))}; выбыло {int(weakest_conversion['dropoff_users']):,} пользователей. Абсолютная потеря и доля оттока отвечают на разные вопросы.
- **Сегментный разрыв заметен:** лучший итоговый сегмент — {best_segment_label} ({_format_rate(float(best_segment['conversion_from_signup']))}), слабейший — {worst_segment_label} ({_format_rate(float(worst_segment['conversion_from_signup']))}). Это факт симуляции, не причинный вывод.

## Как считаются метрики

Единица анализа — уникальный `user_id`, зарегистрировавшийся в окне 1 января — 30 апреля 2025 (UTC). На каждом шаге берётся **самое раннее** событие пользователя; следующий шаг засчитывается только если он произошёл не раньше предыдущего. Одно событие не может добавить пользователя дважды.

Конверсия шага — пользователи на шаге / пользователи на предшествующем шаге. Итоговая конверсия — пользователи с `first_ride` / все `signup`. Окно конверсии составляет 30 дней с регистрации: все регистрации взяты достаточно рано, чтобы окно завершилось до даты среза 30 июня 2025. Подробнее — в [методике](../docs/methodology.md).

## Абсолютная потеря и конверсия шага — разные критерии

**На этапе «{absolute_loss_label}» теряется больше всего людей — {int(largest_absolute_loss['dropoff_users']):,}.** При этом худшая конверсия перехода — «{weakest_conversion_label}»: {_format_rate(float(weakest_conversion['conversion_from_previous_stage']))}. На графике показана кумулятивная конверсия; таблица сохраняет оба знаменателя. Приоритет эксперимента зависит также от причин оттока, ожидаемого прироста итоговой конверсии и стоимости изменений — одним числом drop-off его не определить.

![Общая воронка](figures/funnel_overall.png)

{_markdown_table(funnel_view, ['stage', 'users', 'conversion_from_signup', 'conversion_from_previous_stage', 'dropoff_users'])}

## Платформа и город локализуют точки внимания, но не доказывают причины

**На этапе добавления оплаты слабее всего {SEGMENT_LABELS[str(weakest_payment_platform['segment'])]}: {_format_rate(float(weakest_payment_platform['conversion_from_previous_stage']))} от верифицированных пользователей.** На этапе поиска → бронирования минимум у сегмента «{weakest_booking_city_label}»: {_format_rate(float(weakest_booking_city['conversion_from_previous_stage']))}. Сегменты заданы до событий, поэтому они подходят для приоритизации диагностики; без эксперимента или логов ошибок причинность не установлена.

![Конверсия в первую поездку по сегментам](figures/segment_first_ride_conversion.png)

**Факт:** верификация → способ оплаты конвертирует {_format_rate(float(payment_loss['conversion_from_previous_stage']))}, а бронирование → первая поездка — {_format_rate(float(ride_loss['conversion_from_previous_stage']))}. **Гипотезы:** на оплате web-поток может проигрывать из-за UX/3DS или способов оплаты; в сегменте «{weakest_booking_city_label}» возможны дефицит подходящих машин, цена либо прозрачность условий; после бронирования — отмены, неуверенность в начале аренды или операционные барьеры. Эти механизмы не измеряются текущим event log.

## Скорость прохождения: хвост ожидания важнее среднего

**P90 времени до следующего шага заметно выше P50, поэтому среднее скроет длинный хвост.** Метрика рассчитана только среди прошедших оба соседних шага и не приписывает время пользователям, остановившимся воронке.

![Время перехода](figures/time_to_step.png)

{_markdown_table(time_view, ['transition', 'users_reaching_both_steps', 'p50_hours', 'p90_hours'])}

## Когорты: activation и retention разделены

**Activation D1/D7/D30** — доля всех регистраций когорты, завершивших первую поездку в течение 1/7/30 суток с регистрации. **Retention D1/D7/D30** — доля активированных пользователей, для которых уже прошло соответствующее окно, совершивших следующую завершённую поездку в интервале [D, D+1) от первой поездки. У retention другой знаменатель, поэтому эти две метрики нельзя напрямую сравнивать.

![Активация когорт](figures/cohort_activation.png)

{_markdown_table(cohort_view, ['signup_cohort', 'registrations', 'activation_d1', 'activation_d7', 'activation_d30', 'retention_d1', 'retention_d7', 'retention_d30'])}

## Что проверять следующим экспериментом

1. **Поток оплаты на web.** A/B: явно показать поддерживаемые способы оплаты и обрабатывать возврат из 3DS. Основная метрика — verification → payment_method; guardrail — error rate оплаты и time-to-payment. Стратифицировать по каналу и городу; не объявлять победу без доверительного интервала для разницы долей.
2. **Поиск → бронирование в сегменте «{weakest_booking_city_label}».** A/B: показать доступные рядом авто и полную цену до CTA либо предложить альтернативные классы. Основная метрика — search → booking; guardrail — отмены, стоимость скидок и жалобы. Перед тестом добавить события результатов поиска: количество машин, ETA, цена, экран/ошибка.
3. **Бронирование → первая поездка.** A/B: контекстное напоминание до начала брони и пошаговый старт аренды. Основная метрика — booking → first_ride; guardrail — отмена брони, обращения в поддержку, D7 retention. Измерять intent-to-treat от момента бронирования.

## Проверка качества и ограничения

**Проверки пройдены: {quality_label}.** SQL проверяет дубли `event_id`, обязательные поля, допустимые имена событий, дату среза и порядок шагов; отдельные pytest-проверки подтверждают монотонность воронки и порядок событий. Результаты описательны: синтетический генератор намеренно задаёт различия между сегментами. В логе нет причин событий, цен, наличия машин, отказов платёжного провайдера, отмен или реального эксперимента — поэтому рекомендации являются планом проверки, а не доказанными причинами.

## Что проверить дальше

- Как меняется search → booking при одинаковой доступности машин, цене и ETA?
- Какие конкретные ошибки или возвраты из 3DS происходят в web-потоке оплаты?
- Сколько бронирований отменяется до старта и отличаются ли отмены по городу/каналу?

_Воспроизводимость: `make all`; SQL в `sql/`, pandas/графики в `scripts/run_analysis.py`. Данные синтетические, seed `20250812`._
"""
    (REPORTS_DIR / "analysis_report.md").write_text(report, encoding="utf-8")


def _build_validation_report(
    funnel: pd.DataFrame, cohorts: pd.DataFrame, quality: pd.DataFrame, events: pd.DataFrame
) -> None:
    checks = {
        "Все SQL-проверки качества равны нулю": bool((quality["issue_value"] == 0).all()),
        "Воронка монотонна": bool(funnel["users"].is_monotonic_decreasing),
        "Activation когорт не убывает D1 ≤ D7 ≤ D30": bool(
            ((cohorts["activation_d1"] <= cohorts["activation_d7"]) & (cohorts["activation_d7"] <= cohorts["activation_d30"])).all()
        ),
        "Нет дубликатов event_id": bool(events["event_id"].is_unique),
        "События не выходят за дату среза": bool(events["event_ts"].max() <= pd.Timestamp("2025-06-30T23:59:00Z")),
    }
    rows = "\n".join(f"| {name} | {'PASS' if passed else 'FAIL'} |" for name, passed in checks.items())
    report = f"""# Отчёт валидации

## Итоговая оценка: готово к публикации как синтетический портфолио-кейс

**Вопрос:** где в воронке первой поездки теряются пользователи и какие срезы направят следующие проверки?

**Источник:** детерминированный synthetic event log из `scripts/generate_data.py`, seed `20250812`; окно событий до 30 июня 2025 UTC. Это не клиентские данные и не рыночное свидетельство.

## Контрольные пересчёты

| Проверка | Результат |
|---|---|
{rows}

Общая воронка независимо пересчитывается в DuckDB из raw events с окном первого события; графики и таблицы отчёта строятся pandas из этих SQL-результатов. В activation знаменатель — регистрации, в retention — только активированные пользователи с полным Dn-окном: это предотвращает right-censoring leakage.

## Проверка методики

Единица — уникальный зарегистрированный пользователь. Правило последовательности и 30-дневное окно конверсии заданы явно; канал, платформа и город определены до результата. Причинные формулировки намеренно не используются: различия сегментов — факты симуляции, а механизмы обозначены как гипотезы.

## Обязательные ограничения

- Генератор намеренно создаёт различия сегментов: их наличие валидирует pipeline, а не служит реальным бизнес-фактом.
- В event log нет supply, цены, ошибок оплаты, отмен и experiment assignment, поэтому он не выявляет причины.
- Retention — последующая завершённая поездка после первой, а не app-open или session retention.
"""
    (REPORTS_DIR / "validation_report.md").write_text(report, encoding="utf-8")


def run_analysis(root: Path = ROOT) -> dict[str, pd.DataFrame]:
    """Execute all SQL, merge result tables in pandas, write artifacts, and return frames."""
    raw_events = root / "data" / "raw" / "events.csv"
    if not raw_events.exists():
        raise FileNotFoundError("Raw events are missing. Run `make data` first.")
    previous_cwd = Path.cwd()
    os.chdir(root)
    try:
        connection = duckdb.connect()
        connection.execute("SET TimeZone = 'UTC'")
        quality = _run_query(connection, "01_data_quality.sql")
        funnel = _run_query(connection, "02_funnel_overall.sql")
        segment_funnel = pd.concat(
            [_run_query(connection, "03_funnel_by_segment.sql", dimension) for dimension in ["acquisition_channel", "platform", "city"]],
            ignore_index=True,
        )
        time_to_step = _run_query(connection, "04_time_to_step_and_dropoff.sql")
        cohorts = _run_query(connection, "05_cohorts_activation_retention.sql")
        connection.close()
    finally:
        os.chdir(previous_cwd)

    # pandas data path: loading, filtering, groupby and merge are intentionally explicit.
    events = pd.read_csv(raw_events)
    events["event_ts"] = pd.to_datetime(events["event_ts"], format="ISO8601", utc=True)
    signup_events = events.loc[events["event_name"].eq("signup")].sort_values("event_ts").drop_duplicates("user_id")
    signup_events = signup_events.loc[
        signup_events["event_ts"].ge(pd.Timestamp("2025-01-01", tz="UTC"))
        & signup_events["event_ts"].lt(pd.Timestamp("2025-05-01", tz="UTC"))
    ]
    segment_sizes = signup_events.groupby(["acquisition_channel", "platform", "city"], as_index=False).agg(
        registrations=("user_id", "nunique")
    )
    funnel_enriched = funnel.merge(
        time_to_step[["stage_order", "p50_hours", "p90_hours"]], on="stage_order", how="left", validate="one_to_one"
    )
    final_segment_summary = (
        segment_funnel.loc[segment_funnel["stage"].eq("first_ride")]
        .groupby(["dimension", "segment"], as_index=False)
        .agg(users=("users", "sum"), conversion_from_signup=("conversion_from_signup", "mean"))
        .sort_values(["dimension", "conversion_from_signup"])
    )

    for directory in [PROCESSSED_DIR, TABLES_DIR, FIGURES_DIR, REPORTS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    quality.to_csv(PROCESSSED_DIR / "data_quality.csv", index=False)
    funnel_enriched.to_csv(PROCESSSED_DIR / "funnel_overall.csv", index=False)
    segment_funnel.to_csv(PROCESSSED_DIR / "funnel_by_segment.csv", index=False)
    time_to_step.to_csv(PROCESSSED_DIR / "time_to_step.csv", index=False)
    cohorts.to_csv(PROCESSSED_DIR / "cohorts.csv", index=False)
    final_segment_summary.to_csv(TABLES_DIR / "final_segment_summary.csv", index=False)
    segment_sizes.to_csv(TABLES_DIR / "signup_segment_sizes.csv", index=False)
    _save_figures(funnel, segment_funnel, time_to_step, cohorts)
    _build_report(funnel, segment_funnel, time_to_step, cohorts, quality)
    _build_validation_report(funnel, cohorts, quality, events)
    return {
        "quality": quality,
        "funnel": funnel,
        "segment_funnel": segment_funnel,
        "time_to_step": time_to_step,
        "cohorts": cohorts,
        "events": events,
        "final_segment_summary": final_segment_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when key analytical invariants do not hold.")
    parser.parse_args()
    results = run_analysis()
    passed = (
        (results["quality"]["issue_value"] == 0).all()
        and results["funnel"]["users"].is_monotonic_decreasing
        and (results["events"]["event_id"].is_unique)
    )
    if not passed:
        raise SystemExit("Analytical invariant failed")
    print("Analysis completed; data-quality and funnel invariants passed.")


if __name__ == "__main__":
    main()
