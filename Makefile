ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VENV_BIN := $(ROOT_DIR)/.venv/bin
PYTHON := $(if $(wildcard $(VENV_BIN)/python3),$(VENV_BIN)/python3,python3)
PYTEST := $(if $(wildcard $(VENV_BIN)/pytest),$(VENV_BIN)/pytest,pytest)
RUFF := $(if $(wildcard $(VENV_BIN)/ruff),$(VENV_BIN)/ruff,ruff)
UV := $(if $(wildcard $(VENV_BIN)/uv),$(VENV_BIN)/uv,uv)
WATCH_REF ?= HEAD
PRD_REF ?= main
SEARCH_EVAL_BASE_URL ?= https://palebluesearch.com

.PHONY: ci ci-lint ci-legacy-paths ci-frontend ci-packages ci-crawler ci-indexer ci-mcp
.PHONY: watch-ci verify-prd
.PHONY: release-check-prd evaluate-search
.PHONY: validate-search-eval
.PHONY: collect-query-candidates
.PHONY: enqueue-url-prd
.PHONY: deploy-prd rebuild-projection-prd
.PHONY: verify-compose-prd
.PHONY: sync sync-packages sync-frontend sync-indexer sync-crawler sync-mcp

ci: ci-lint ci-packages ci-frontend ci-crawler ci-indexer ci-mcp

ci-lint:
	$(MAKE) ci-legacy-paths
	$(RUFF) check apps/frontend/src/ packages/contracts/src/ packages/core/src/ packages/postgres/src/ packages/web-model/src/ packages/kernel/src/ packages/opensearch/src/ packages/indexing/src/ packages/search-config/src/ apps/crawler/src/ apps/indexer/src/ apps/mcp/src/
	$(RUFF) format --check apps/frontend/src/ packages/contracts/src/ packages/core/src/ packages/postgres/src/ packages/web-model/src/ packages/kernel/src/ packages/opensearch/src/ packages/indexing/src/ packages/search-config/src/ apps/crawler/src/ apps/indexer/src/ apps/mcp/src/

ci-legacy-paths:
	cd $(ROOT_DIR) && $(PYTHON) scripts/ci/check_no_legacy_paths.py

ci-frontend:
	$(RUFF) check apps/frontend/src/
	$(RUFF) format --check apps/frontend/src/
	cd $(ROOT_DIR) && \
		INDEXER_API_KEY="$${INDEXER_API_KEY:-test}" \
		$(UV) run --package web-search-frontend pytest apps/frontend/tests -v --tb=short --cov=web_search_frontend --cov-report=term-missing

ci-packages:
	cd $(ROOT_DIR) && \
		$(UV) run --all-packages pytest packages/core/tests packages/search-config/tests packages/postgres/tests packages/web-model/tests packages/kernel/tests packages/opensearch/tests packages/indexing/tests -v --tb=short --cov=web_search_core --cov=web_search_search_config --cov=web_search_postgres --cov=web_search_web_model --cov=web_search_kernel --cov=web_search_opensearch --cov=web_search_indexing --cov-report=term-missing

ci-crawler:
	cd $(ROOT_DIR) && \
		INDEXER_API_KEY="$${INDEXER_API_KEY:-test}" \
		$(UV) run --package web-search-crawler pytest apps/crawler/tests -v --tb=short --cov=web_search_crawler --cov-report=term-missing

ci-indexer:
	cd $(ROOT_DIR) && \
		INDEXER_API_KEY="$${INDEXER_API_KEY:-test}" \
		$(UV) run --package web-search-indexer pytest apps/indexer/tests -v --tb=short --cov=web_search_indexer --cov-report=term-missing

ci-mcp:
	cd $(ROOT_DIR) && \
		$(UV) run --package paleblue-search-mcp pytest apps/mcp/tests -v --tb=short

sync:
	$(UV) sync --all-packages --group dev

sync-packages:
	$(UV) sync --all-packages --group dev

sync-frontend:
	$(UV) sync --only-group dev
	$(UV) sync --package web-search-frontend --inexact

sync-indexer:
	$(UV) sync --only-group dev
	$(UV) sync --package web-search-indexer --inexact

sync-crawler:
	$(UV) sync --only-group dev
	$(UV) sync --package web-search-crawler --inexact

sync-mcp:
	$(UV) sync --only-group dev
	$(UV) sync --package paleblue-search-mcp --inexact

watch-ci:
	cd $(ROOT_DIR) && ./scripts/ops/watch_latest_ci.sh $(WATCH_REF)

verify-prd:
	cd $(ROOT_DIR) && ./scripts/ops/verify_compose_deploy.sh prd $(PRD_REF)

deploy-prd:
	test "$(CONFIRM_PRD_DEPLOY)" = "1"
	cd $(ROOT_DIR) && ./scripts/ops/deploy_compose.sh prd $(PRD_REF)

rebuild-projection-prd:
	cd $(ROOT_DIR) && ./scripts/ops/rebuild_search_projection_segments.sh prd $(PRD_REBUILD_ARGS)

verify-compose-prd:
	cd $(ROOT_DIR) && ./scripts/ops/verify_compose_deploy.sh prd $(PRD_REF)

release-check-prd:
	$(MAKE) watch-ci WATCH_REF=$(PRD_REF)
	$(MAKE) verify-prd PRD_REF=$(PRD_REF)

evaluate-search:
	cd $(ROOT_DIR) && uv run --package web-search-search-config web-search-evaluate-search --base-url "$(SEARCH_EVAL_BASE_URL)"

validate-search-eval:
	cd $(ROOT_DIR) && uv run --package web-search-search-config web-search-validate-search-eval-config

collect-query-candidates:
	cd $(ROOT_DIR) && uv run --package web-search-search-config web-search-collect-query-candidates $(QUERY_CANDIDATE_ARGS)

enqueue-url-prd:
	cd $(ROOT_DIR) && uv run --package web-search-crawler web-search-enqueue-url prd $(ENQUEUE_ARGS)
