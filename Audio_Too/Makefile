
# Audio_Too Developer Makefile
# Run `make` to see available commands.

.PHONY: help setup start test full-test lint check clean install

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  setup    Create venv, install deps, init pre-commit"
	@echo "  install  Install/upgrade Python dependencies"
	@echo "  start    Launch the dashboard server (port 8080)"
	@echo "  test     Run tests (pytest)"
	@echo "  full-test Run crash-isolated release suite with reports"
	@echo "  lint     Run ruff linter"
	@echo "  check    Run repo hygiene + lint"
	@echo "  clean    Remove temp/artefacts (venv, cache, logs)"
	@echo "  freeze   Export pinned requirements.txt"

setup:
	python3 main.py setup

install:
	pip install -r requirements.txt

start:
	python3 main.py start

test:
	python -m pytest tests/ -x -v $(ARGS)

full-test:
	python3 main.py full-test $(ARGS)

lint:
	python -m ruff check business studio scripts tests thursday

check: lint
	python3 scripts/repo_hygiene.py check

clean:
	rm -rf .venv __pycache__ */__pycache__ .pytest_cache .ruff_cache
	rm -f tmp_*.log
	@echo "Cleaned."

freeze:
	pip freeze > requirements.txt
