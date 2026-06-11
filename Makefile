.PHONY: install install-dev uninstall test report boarding lint ocr corpus-baseline hooks

# Enable versioned git hooks: lint on commit, lint+tests on push.
# Bypass per-invocation with --no-verify.
hooks:
	chmod +x .githooks/pre-commit .githooks/pre-push
	git config core.hooksPath .githooks
	@echo "OK → pre-commit (ruff) + pre-push (ruff + pytest)"

# Global install — isolated venv via pipx, wavi available everywhere
install:
	@command -v pipx >/dev/null 2>&1 || { echo "pipx not found. Run: brew install pipx && pipx ensurepath"; exit 1; }
	pipx install --editable .

# Compile the Apple Vision OCR helper to a native arm64 binary.
# ~6x less startup overhead than interpreting the script, and Vision runs
# natively instead of under Rosetta. vision.py picks it up automatically and
# falls back to `swift swift/ocr_vision.swift` if bin/ is missing or stale.
ocr:
	mkdir -p bin
	arch -arm64 swiftc -O swift/ocr_vision.swift -o bin/ocr_vision
	@echo "OK → bin/ocr_vision"

# Dev install — editable inside the project venv (changes take effect immediately)
install-dev:
	pip install -e ".[dev]"

uninstall:
	pipx uninstall wavi

# Run tests (conftest.py writes docs/reports/test_results.js automatically)
test:
	pytest

# Vision eval on the golden corpus (real OCR, macOS only, ~5-10s per case)
corpus: ocr
	WAVI_CORPUS=1 pytest tests/test_corpus.py -v

# Run tests and open boarding page to inspect results
report:
	pytest && wavi boarding

boarding:
	wavi boarding

lint:
	ruff check wavi/ tests/ scripts/
