ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VENV_BIN := $(ROOT_DIR)/.venv/bin
PYTEST := $(if $(wildcard $(VENV_BIN)/pytest),$(VENV_BIN)/pytest,pytest)
RUFF := $(if $(wildcard $(VENV_BIN)/ruff),$(VENV_BIN)/ruff,ruff)
WATCH_REF ?= HEAD
STG_REF ?= main
PRD_REF ?= production
STG_FRONTEND_URL ?= https://web-search-staging.5.223.74.201.sslip.io
STG_INDEXER_URL ?= http://indexer:8000
SMOKE_TEST_URL ?= https://example.com
VERIFY_ADMIN_MAX_SECONDS ?= 2.0

.PHONY: ci ci-lint ci-frontend ci-shared ci-crawler ci-indexer ci-mcp
.PHONY: watch-ci verify-stg verify-prd verify-admin-stg verify-admin-prd
.PHONY: release-check-stg release-check-prd

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

watch-ci:
	cd $(ROOT_DIR) && ./scripts/ops/watch_latest_ci.sh $(WATCH_REF)

verify-stg:
	cd $(ROOT_DIR) && ./scripts/ops/verify_coolify_deploy.sh stg $(STG_REF)
	cd $(ROOT_DIR) && ./scripts/ops/run_coolify_staging_smoke_via_frontend.sh \
		"$(STG_FRONTEND_URL)" \
		"$(STG_INDEXER_URL)" \
		"$(SMOKE_TEST_URL)"

verify-prd:
	cd $(ROOT_DIR) && ./scripts/ops/verify_coolify_deploy.sh prd $(PRD_REF)

verify-admin-stg:
	cd $(ROOT_DIR) && ./scripts/ops/verify_admin_pages.sh stg $(VERIFY_ADMIN_MAX_SECONDS)

verify-admin-prd:
	cd $(ROOT_DIR) && ./scripts/ops/verify_admin_pages.sh prd $(VERIFY_ADMIN_MAX_SECONDS)

release-check-stg:
	$(MAKE) watch-ci WATCH_REF=$(STG_REF)
	$(MAKE) verify-stg STG_REF=$(STG_REF)
	$(MAKE) verify-admin-stg VERIFY_ADMIN_MAX_SECONDS=$(VERIFY_ADMIN_MAX_SECONDS)

release-check-prd:
	$(MAKE) watch-ci WATCH_REF=$(PRD_REF)
	$(MAKE) verify-prd PRD_REF=$(PRD_REF)
	$(MAKE) verify-admin-prd VERIFY_ADMIN_MAX_SECONDS=$(VERIFY_ADMIN_MAX_SECONDS)
