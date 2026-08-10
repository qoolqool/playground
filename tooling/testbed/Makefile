.PHONY: all check test demo validate clean

# ─── Paths ──────────────────────────────────────────────────────────
PROJECT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
PYTHONPATH  := $(PROJECT_DIR)

# ─── Commands ───────────────────────────────────────────────────────
PYTHON  := python3
TESTBED := PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m testbed.cli

# ─── Default ───────────────────────────────────────────────────────
all: check

# ─── Check environment ──────────────────────────────────────────────
check:
	@echo "🔍 Checking testbed environment..."
	@$(PYTHON) -c "import pydantic; print(f'  ✅ pydantic v{pydantic.__version__}')" 2>/dev/null || echo "  ❌ pydantic not installed"
	@$(PYTHON) -c "import testbed; print(f'  ✅ testbed package found at {testbed.__file__}')" 2>/dev/null || echo "  ❌ testbed package not found (set PYTHONPATH=$(PYTHONPATH))"
	@echo "  ✅ PYTHONPATH=$(PYTHONPATH)"
	@echo ""
	@echo "Usage:"
	@echo "  make test       — Run all tests"
	@echo "  make demo       — Run the demo script"
	@echo "  make validate   — Validate the QUIC edge spec"
	@echo "  make check      — This check"

# ─── Tests ─────────────────────────────────────────────────────────
test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/ -v

# ─── Demo ───────────────────────────────────────────────────────────
demo:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) examples/demo.py

# ─── Validate QUIC edge spec ───────────────────────────────────────
validate:
	$(TESTBED) validate /workspace/quic-edge-spec.json

# ─── Gate 2: Code Validator ─────────────────────────────────────────
gate2:
	$(TESTBED) gate2 --spec /workspace/quic-edge-v2-spec.json --workspace /workspace

# ─── Gate 3: Security & Policy Guardrails ────────────────────────────
gate3:
	$(TESTBED) gate3 --spec /workspace/quic-edge-v2-spec.json --workspace /workspace

# ─── Gate 4: Runtime & Integration Verification ───────────────────────
gate4:
	$(TESTBED) gate4 --workspace /workspace

gate4-skip-up:
	$(TESTBED) gate4 --workspace /workspace --skip-up

# ─── Clean ─────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -rf .pytest_cache
