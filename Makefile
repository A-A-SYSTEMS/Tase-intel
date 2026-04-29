# ============================================================
# tase-intel — Makefile
# ============================================================
# Phase 1 / Batch 2: Alembic scaffolding wired up.
#
# Quick reference:
#   make help         show this help
#   make up           start Postgres + TimescaleDB
#   make down         stop containers (data persists)
#   make clean        stop AND wipe volume (DESTRUCTIVE)
#   make psql         open psql shell to local DB
#   make health       check DB is reachable + extensions present
#   make migrate-init sanity-check Alembic setup
#   make migrate      run Alembic migrations (upgrade head)
#   make rollback     roll back last migration
#   make smoke-test   run schema integrity tests     [Batch 4+]
#   make lint         run forbidden-pattern checks   [Batch 5+]
# ============================================================

# Load .env if present. Safe if missing (vars come from environment).
ifneq (,$(wildcard ./.env))
    include .env
    export
endif

# Defaults (overridable via .env)
POSTGRES_USER     ?= tase_intel
POSTGRES_PASSWORD ?= changeme
POSTGRES_DB       ?= tase_intel
POSTGRES_HOST     ?= localhost
POSTGRES_PORT     ?= 5432

# Compose command (handle both legacy and v2)
COMPOSE := $(shell command -v docker-compose 2>/dev/null || echo "docker compose")

# Alembic via venv (if active) or system
ALEMBIC := alembic -c alembic.ini

.DEFAULT_GOAL := help
.PHONY: help up down clean psql health migrate-init migrate rollback smoke-test lint check-env stub

# ---------- Help ----------

help: ## Show this help
	@echo "tase-intel — available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Spec docs: docs/spec/  (read IMPLEMENTATION_GUARDRAILS_V1.0.1.md before coding)"

# ---------- Environment guards ----------

check-env: ## Verify .env exists and required vars are set
	@if [ ! -f .env ]; then \
		echo "ERROR: .env not found. Run: cp .env.example .env  (then edit)"; \
		exit 1; \
	fi
	@if [ "$(POSTGRES_PASSWORD)" = "changeme" ]; then \
		echo "ERROR: POSTGRES_PASSWORD is still 'changeme'. Set a real value in .env"; \
		exit 1; \
	fi

# ---------- Docker lifecycle ----------

up: check-env ## Start Postgres + TimescaleDB containers
	$(COMPOSE) up -d
	@echo ""
	@echo "Waiting for DB to be healthy..."
	@for i in $$(seq 1 30); do \
		if $(COMPOSE) exec -T db pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB) >/dev/null 2>&1; then \
			echo "DB ready."; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "ERROR: DB did not become healthy in 30s"; \
	$(COMPOSE) logs db; \
	exit 1

down: ## Stop containers (volume persists)
	$(COMPOSE) down

clean: ## Stop containers AND delete volume (DESTRUCTIVE)
	@echo "WARNING: this will permanently delete all data in the local DB."
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		$(COMPOSE) down -v; \
		echo "Volume removed."; \
	else \
		echo "Aborted."; \
		exit 1; \
	fi

# ---------- DB shells / health ----------

psql: check-env ## Open psql shell to local DB
	$(COMPOSE) exec db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

health: check-env ## Verify DB is up, TimescaleDB loaded, show schema + Alembic state
	@echo "Checking DB connection..."
	@$(COMPOSE) exec -T db pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB)
	@echo ""
	@echo "Checking TimescaleDB availability..."
	@$(COMPOSE) exec -T db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c \
		"SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name = 'timescaledb';"
	@echo ""
	@echo "Server timezone:"
	@$(COMPOSE) exec -T db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -tAc "SHOW timezone;"
	@echo ""
	@echo "Public-schema tables:"
	@$(COMPOSE) exec -T db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "\dt public.*" || true
	@echo ""
	@echo "Public-schema functions:"
	@$(COMPOSE) exec -T db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "\df public.*" || true
	@echo ""
	@echo "Alembic current revision:"
	@$(ALEMBIC) current || echo "(alembic not available or not initialized)"

# ---------- Alembic migrations ----------

migrate-init: check-env ## Sanity-check Alembic setup (idempotent)
	@echo "Verifying Alembic configuration..."
	@$(ALEMBIC) heads
	@echo ""
	@echo "Current state:"
	@$(ALEMBIC) current || echo "(no current revision)"
	@echo ""
	@echo "Alembic is configured. Use 'make migrate' to apply."

migrate: check-env ## Run Alembic migrations (upgrade head)
	$(ALEMBIC) upgrade head

rollback: check-env ## Roll back the last Alembic migration
	$(ALEMBIC) downgrade -1

# ---------- Stubs for future batches ----------

stub:
	@echo "ERROR: $(STUB_TARGET) is not implemented yet."
	@echo "       It will be enabled in $(STUB_BATCH)."
	@echo "       See: docs/spec/IMPLEMENTATION_GUARDRAILS_V1.0.1.md"
	@exit 1

smoke-test: check-env ## Run schema integrity smoke tests
	python -m pytest tests/smoke/ -v

lint: ## [Batch 5+] Run forbidden-pattern static checks
	@$(MAKE) stub STUB_TARGET=lint STUB_BATCH="Batch 5 (Lint tests)"
