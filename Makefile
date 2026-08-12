.PHONY: all data analysis test lint check clean

all: data analysis

data:
	python scripts/generate_data.py --output data/raw/events.csv --users-output data/raw/users.csv --sample-output data/sample/events_sample.csv

analysis:
	python scripts/run_analysis.py

test:
	pytest -q

lint:
	ruff check scripts tests

check: lint test all

clean:
	rm -f data/raw/*.csv data/processed/*.csv reports/tables/*.csv reports/figures/*.png reports/analysis_report.md reports/validation_report.md
