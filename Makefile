VENV_BIN := .venv/bin

.PHONY: ci ci-lint ci-frontend ci-shared ci-crawler ci-indexer ci-mcp

ci: ci-lint ci-shared ci-frontend ci-crawler ci-indexer ci-mcp

ci-lint:
	$(VENV_BIN)/ruff check frontend/src/ shared/src/ crawler/src/ indexer/src/ mcp/src/
	$(VENV_BIN)/ruff format --check frontend/src/ shared/src/ crawler/src/ indexer/src/ mcp/src/

ci-frontend:
	$(VENV_BIN)/ruff check frontend/src/
	$(VENV_BIN)/ruff format --check frontend/src/
	cd frontend && \
		PYTHONPATH=src \
		ADMIN_USERNAME="$${ADMIN_USERNAME:-test}" \
		ADMIN_PASSWORD="$${ADMIN_PASSWORD:-test}" \
		ADMIN_SESSION_SECRET="$${ADMIN_SESSION_SECRET:-test}" \
		INDEXER_API_KEY="$${INDEXER_API_KEY:-test}" \
		../$(VENV_BIN)/pytest tests/ -v --tb=short --cov=frontend --cov-report=term-missing

ci-shared:
	cd shared && \
		PYTHONPATH=src \
		../$(VENV_BIN)/pytest tests/ -v --tb=short --cov=shared --cov-report=term-missing

ci-crawler:
	cd crawler && \
		PYTHONPATH=src \
		INDEXER_API_KEY="$${INDEXER_API_KEY:-test}" \
		../$(VENV_BIN)/pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

ci-indexer:
	cd indexer && \
		PYTHONPATH=src \
		INDEXER_API_KEY="$${INDEXER_API_KEY:-test}" \
		../$(VENV_BIN)/pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

ci-mcp:
	cd mcp && \
		PYTHONPATH=src \
		../$(VENV_BIN)/pytest tests/ -v --tb=short
