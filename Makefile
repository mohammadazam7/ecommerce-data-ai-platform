.PHONY: install lock lint format typecheck test audit check data clean

install:
	pip install -r requirements-dev.lock
	pip install -e . --no-deps

lock:
	uv pip compile pyproject.toml --extra dev --python-version 3.11 --universal -o requirements-dev.lock

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

typecheck:
	mypy src

test:
	pytest

audit:
	pip-audit --skip-editable

data:
	commerce download
	commerce bronze

check: lint typecheck test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
