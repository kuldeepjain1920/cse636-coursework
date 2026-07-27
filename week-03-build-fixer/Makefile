# Prefer the consolidated repo-root .venv if it exists; otherwise use a local one.
ROOT_VENV := ../../.venv
VENV := $(if $(wildcard $(ROOT_VENV)),$(ROOT_VENV),.venv)
BIN := $(VENV)/bin

.PHONY: setup test build-log agent demo clean

setup:                ## create a venv (reuses repo-root .venv if present) and install deps (pytest + anthropic + PyGithub)
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

test:                 ## run the pure log-parser tests (no AI / network needed)
	$(BIN)/pip install pytest >/dev/null 2>&1 || true
	$(BIN)/pytest -q tests/test_logparse.py

build-log:            ## run the buggy app tests and capture the red build (expected to fail)
	-$(BIN)/pytest -q --tb=short tests/test_calculator.py 2>&1 | tee build_log.txt

agent: build-log      ## dry-run the build-fixer agent on the log (needs ANTHROPIC_API_KEY)
	$(BIN)/python scripts/build_fixer_agent.py --dry-run

demo: agent           ## alias: produce the red build, then show the agent's proposed fix

clean:                ## remove caches and generated data (keeps the shared repo-root .venv)
	rm -rf .venv .pytest_cache __pycache__ */__pycache__ build_log.txt
