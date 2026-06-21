# Nifty100 Financial Intelligence Platform

.PHONY: help setup load ratios test report dashboard api clean

help:
	@echo "======================================"
	@echo " Nifty100 Financial Intelligence Platform"
	@echo "======================================"
	@echo ""
	@echo "Available Commands:"
	@echo "  setup      Install project dependencies"
	@echo "  load       Run ETL pipeline"
	@echo "  ratios     Run Financial Ratio Engine"
	@echo "  test       Run pytest suite"
	@echo "  report     Generate reports"
	@echo "  dashboard  Launch dashboard"
	@echo "  api        Launch API"
	@echo "  clean      Remove cache files"
	@echo ""

setup:
	pip install -r requirements.txt

load:
	python src/etl/loader.py

ratios:
	@echo "Ratio Engine not implemented yet"

test:
	pytest tests/ -v

report:
	@echo "Reporting module not implemented yet"

dashboard:
	@echo "Dashboard module not implemented yet"

api:
	@echo "API module not implemented yet"

clean:
	python -c "import shutil; shutil.rmtree('.pytest_cache', ignore_errors=True)"