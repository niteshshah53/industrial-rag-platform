# ============================================================
# Industrial RAG Platform — Makefile
# ============================================================
# Usage: make <target>
# Run `make help` to list all available targets.
#
# Prerequisites:
#   - Docker Desktop (or Docker Engine + Docker Compose)
#   - Python 3.12+ with uv installed (for local test-unit and lint)
#     Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# ============================================================

.PHONY: help dev build stop logs test test-unit test-integration \
        lint format install-dev eval demo pull-models init-collection clean

# Default target
.DEFAULT_GOAL := help

# ── Help ─────────────────────────────────────────────────────────────────────
help: ## Show this help message
	@echo ""
	@echo "Industrial RAG Platform"
	@echo "========================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Development ───────────────────────────────────────────────────────────────
dev: ## Build images and start all services with hot reload
	docker compose up -d --build
	@echo ""
	@echo "\033[32mServices starting...\033[0m"
	@echo "  API (with docs):  http://localhost:8000/docs"
	@echo "  Qdrant Web UI:    http://localhost:6333/dashboard"
	@echo "  Ollama API:       http://localhost:11434"
	@echo ""
	@echo "NOTE: Ollama downloads models on first run (~2.3 GB total)."
	@echo "      This can take several minutes on a slow connection."
	@echo "      Monitor progress with: make logs-ollama"
	@echo ""
	@echo "Run \033[36mmake logs\033[0m to tail application logs."

build: ## Build Docker images without starting services
	docker compose build

stop: ## Stop all running services (preserves volumes)
	docker compose stop

logs: ## Tail application logs
	docker compose logs -f app

logs-ollama: ## Tail Ollama logs (useful to monitor model downloads)
	docker compose logs -f ollama

status: ## Show service health status
	docker compose ps

# ── Testing ───────────────────────────────────────────────────────────────────
test: ## Run full test suite inside the app container (requires running services)
	docker compose exec app pytest tests/ -v --tb=short

test-unit: ## Run unit tests locally without Docker (fast — no external services needed)
	pytest tests/unit/ -v --tb=short

test-integration: ## Run integration tests (requires running Docker services)
	pytest tests/integration/ -v --tb=short

test-cov: ## Run tests with coverage report
	pytest tests/ --cov=app --cov-report=term-missing --cov-report=html

# ── Code Quality ─────────────────────────────────────────────────────────────
lint: ## Check code style with ruff and black
	ruff check app/ tests/
	black --check app/ tests/
	@echo "\033[32mLint passed.\033[0m"

format: ## Auto-fix code style with ruff and black
	ruff check --fix app/ tests/
	black app/ tests/
	@echo "\033[32mFormatting complete.\033[0m"

# ── Local Development Setup ───────────────────────────────────────────────────
install-dev: ## Install project and dev dependencies locally (for lint and unit tests)
	uv pip install -e ".[dev]" --system

# ── Ollama Model Management ───────────────────────────────────────────────────
pull-models: ## Manually pull Ollama models (normally handled automatically on first start)
	docker compose exec ollama ollama pull llama3.2:3b
	docker compose exec ollama ollama pull nomic-embed-text

list-models: ## List models available in the running Ollama instance
	docker compose exec ollama ollama list

# ── Database ──────────────────────────────────────────────────────────────────
init-collection: ## Create the Qdrant vector collection (idempotent — safe to run multiple times)
	docker compose exec app python scripts/init_collection.py

# ── Evaluation ────────────────────────────────────────────────────────────────
eval: ## Run the RAGAS evaluation pipeline against the benchmark dataset (Phase 4+)
	@echo "Running RAGAS evaluation..."
	docker compose exec app python evaluation/run_ragas.py

# ── Demo ─────────────────────────────────────────────────────────────────────
demo: ## Seed demo documents and run example queries (Phase 4+)
	@echo "Seeding demo documents..."
	docker compose exec app python scripts/seed_demo_data.py
	@echo "\033[32mDemo data loaded. Visit http://localhost:8000/docs to try queries.\033[0m"

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean: ## Stop services and remove containers, networks, and volumes (DESTRUCTIVE)
	@echo "\033[33mThis will delete all Docker volumes including Qdrant data and downloaded models.\033[0m"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	docker compose down -v --remove-orphans
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@echo "\033[32mClean complete.\033[0m"

clean-soft: ## Stop services and remove containers but KEEP volumes (data preserved)
	docker compose down --remove-orphans
