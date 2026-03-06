ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VENV_BIN := $(ROOT_DIR)/.venv/bin
PYTEST := $(if $(wildcard $(VENV_BIN)/pytest),$(VENV_BIN)/pytest,pytest)
RUFF := $(if $(wildcard $(VENV_BIN)/ruff),$(VENV_BIN)/ruff,ruff)

.PHONY: ci ci-lint ci-frontend ci-shared ci-crawler ci-indexer ci-mcp

ci: ci-lint ci-shared ci-frontend ci-crawler ci-indexer ci-mcp

ci-lint:
	$(RUFF) check frontend/src/ shared/src/ crawler/src/ indexer/src/ mcp/src/
	$(RUFF) format --check frontend/src/ shared/src/ crawler/src/ indexer/src/ mcp/src/

ci-frontend:
	$(RUFF) check frontend/src/
	$(RUFF) format --check frontend/src/
	cd $(ROOT_DIR)/frontend && \
		PYTHONPATH=src \
		ADMIN_USERNAME="$${ADMIN_USERNAME:-test}" \
		ADMIN_PASSWORD="$${ADMIN_PASSWORD:-test}" \
		ADMIN_SESSION_SECRET="$${ADMIN_SESSION_SECRET:-test}" \
		INDEXER_API_KEY="$${INDEXER_API_KEY:-test}" \
		$(PYTEST) tests/ -v --tb=short --cov=frontend --cov-report=term-missing

ci-shared:
	cd $(ROOT_DIR)/shared && \
		PYTHONPATH=src \
		$(PYTEST) tests/ -v --tb=short --cov=shared --cov-report=term-missing

ci-crawler:
	cd $(ROOT_DIR)/crawler && \
		PYTHONPATH=src \
		INDEXER_API_KEY="$${INDEXER_API_KEY:-test}" \
		$(PYTEST) tests/ -v --tb=short --cov=app --cov-report=term-missing

ci-indexer:
	cd $(ROOT_DIR)/indexer && \
		PYTHONPATH=src \
		INDEXER_API_KEY="$${INDEXER_API_KEY:-test}" \
		$(PYTEST) tests/ -v --tb=short --cov=app --cov-report=term-missing

ci-mcp:
	cd $(ROOT_DIR)/mcp && \
		PYTHONPATH=src \
		$(PYTEST) tests/ -v --tb=short
