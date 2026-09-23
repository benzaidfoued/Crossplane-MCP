.PHONY: setup test lint check build chart
setup:
	uv sync --frozen
lint:
	uv run ruff check .
	uv run ruff format --check .
test:
	uv run pytest --cov --cov-fail-under=85
check: lint test
	uv run python scripts/check_versions.py
build:
	uv build
chart:
	mkdir -p dist
	helm lint charts/crossplane-compass --strict
	helm package charts/crossplane-compass --destination dist
