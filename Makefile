.PHONY: install install-dev uninstall test report boarding lint

# Global install — isolated venv via pipx, wavi available everywhere
install:
	@command -v pipx >/dev/null 2>&1 || { echo "pipx not found. Run: brew install pipx && pipx ensurepath"; exit 1; }
	pipx install --editable .

# Dev install — editable inside the project venv (changes take effect immediately)
install-dev:
	pip install -e ".[dev]"

uninstall:
	pipx uninstall wavi

# Run tests (conftest.py writes docs/reports/test_results.js automatically)
test:
	pytest

# Run tests and open boarding page to inspect results
report:
	pytest && wavi boarding

boarding:
	wavi boarding

lint:
	@command -v ruff >/dev/null 2>&1 && ruff check wavi/ || true
