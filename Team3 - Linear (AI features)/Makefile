.PHONY: setup doctor dev seed demo-reset lint typecheck unit integration test eval live-check build check demo package clean

UV_CACHE_DIR ?= .uv-cache
RUN = UV_CACHE_DIR=$(UV_CACHE_DIR) uv run
VENV_STAMP = .venv/.warrant-path
ZIP ?= ../warrant-submission.zip

# A virtualenv is not relocatable: console-script shebangs hard-code an absolute path.
# Moving or unzipping the project elsewhere breaks them, so every target invokes tools
# as `python -m <tool>`, and setup recreates a venv that was built for another path.

setup:
	@if [ -d .venv ] && [ "$$(cat "$(VENV_STAMP)" 2>/dev/null)" != "$(CURDIR)" ]; then \
	  echo "-> .venv was built for a different path; recreating"; rm -rf .venv; \
	fi
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv sync --extra dev
	@printf '%s\n' "$(CURDIR)" > "$(VENV_STAMP)"

doctor:
	@echo "project : $(CURDIR)"
	@if [ ! -d .venv ]; then echo "venv    : MISSING -> make setup"; \
	elif [ "$$(cat "$(VENV_STAMP)" 2>/dev/null)" != "$(CURDIR)" ]; then \
	  echo "venv    : STALE (built for another path) -> rm -rf .venv && make setup"; \
	else echo "venv    : matches this directory"; fi
	@$(RUN) python -c "import warrant, uvicorn; print('imports : ok')" 2>/dev/null \
	  || echo "imports : FAILED -> rm -rf .venv && make setup"

seed demo-reset:
	$(RUN) python -m warrant.seed

dev:
	@test -f data/warrant.db || $(MAKE) seed
	$(RUN) python -m uvicorn warrant.main:app --reload --host 127.0.0.1 --port 8000

demo:
	$(MAKE) demo-reset
	$(RUN) python -m uvicorn warrant.main:app --host 127.0.0.1 --port 8000

test:
	$(RUN) python -m pytest

unit:
	$(RUN) python -m pytest tests/unit

integration:
	$(RUN) python -m pytest tests/integration tests/security tests/e2e

eval:
	$(RUN) python -m warrant.evaluation

live-check:
	$(RUN) python -m warrant.live_check

lint:
	$(RUN) python -m ruff check src tests

typecheck:
	$(RUN) python -m mypy src/warrant

build:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv build

# Required order: static checks first, then progressively wider runtime evidence.
check: lint typecheck unit integration eval build

# Submission archive. Excludes virtualenvs, caches, build output and databases, which
# the assignment forbids, then fails loudly if a key-shaped string slipped through.
package:
	@rm -f "$(ZIP)"
	zip -rq "$(ZIP)" . \
	  -x '.venv/*' '.uv-cache/*' '.mypy_cache/*' '.pytest_cache/*' '.ruff_cache/*' \
	     'dist/*' 'build/*' '*__pycache__*' '*.pyc' '.git/*' '.DS_Store' \
	     'data/*.db' 'data/*.db-shm' 'data/*.db-wal' '.env'
	@if unzip -l "$(ZIP)" | grep -Eq '(\.venv/|\.uv-cache/|/dist/|__pycache__|\.env$$)'; then \
	  echo "REFUSING: excluded path present in $(ZIP)"; exit 1; fi
	@if grep -rEl '(sk|ghp|lin_api)_[A-Za-z0-9_-]{12,}' --exclude-dir=.venv --exclude-dir=.uv-cache \
	     --exclude-dir=.git . 2>/dev/null | grep -v 'security.py' | grep -q .; then \
	  echo "REFUSING: key-shaped string found; inspect before shipping"; exit 1; fi
	@echo "wrote $(ZIP)"

clean:
	find src tests -type d -name __pycache__ -prune -exec rm -r {} +
