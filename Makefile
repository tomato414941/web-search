VENV_BIN := .venv/bin

.PHONY: ci-frontend

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
