import pandas as pd

from scripts.run_analysis import _markdown_table, loss_extremes


def test_absolute_loss_and_relative_dropoff_are_not_confused():
    funnel = pd.DataFrame({
        "stage_order": [1, 2, 3],
        "stage": ["signup", "verification", "booking"],
        "dropoff_users": [0, 3000, 2500],
        "conversion_from_previous_stage": [1.0, 0.75, 0.60],
    })
    absolute, relative = loss_extremes(funnel)
    assert absolute["stage"] == "verification"
    assert relative["stage"] == "booking"


def test_chart_line_breaks_do_not_split_markdown_table_rows():
    frame = pd.DataFrame({"transition": ["Поиск →\nбронирование"], "users": [100]})
    table = _markdown_table(frame, ["transition", "users"])
    assert len(table.splitlines()) == 3
    assert "Поиск → бронирование" in table
