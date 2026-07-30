MANAGER_HOST ?= 0.0.0.0
MANAGER_PORT ?= 8001
PORT         ?= 5174
BACKEND_PORT ?= $(MANAGER_PORT)

.PHONY: help install install-frontend run run-reload frontend build-frontend dev test test-verbose lint clean

help:          ## Diese Hilfe anzeigen
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Abhängigkeiten ────────────────────────────────────────────────────────────

install:       ## Python-Abhängigkeiten installieren (inkl. dev)
	uv sync --group dev

install-frontend: ## Node-Abhängigkeiten im frontend/-Verzeichnis installieren
	cd frontend && npm install

# ── Backend ───────────────────────────────────────────────────────────────────

run:           ## Backend starten (MANAGER_HOST/MANAGER_PORT konfigurierbar)
	MANAGER_HOST=$(MANAGER_HOST) MANAGER_PORT=$(MANAGER_PORT) \
	  uv run python -m app.main

run-reload:    ## Backend mit Auto-Reload starten (Entwicklung)
	MANAGER_HOST=$(MANAGER_HOST) MANAGER_PORT=$(MANAGER_PORT) \
	  uv run uvicorn app.main:app --reload --host $(MANAGER_HOST) --port $(MANAGER_PORT)

# ── Frontend ──────────────────────────────────────────────────────────────────

frontend:      ## Frontend-Dev-Server starten (PORT/BACKEND_PORT konfigurierbar)
	cd frontend && PORT=$(PORT) BACKEND_PORT=$(BACKEND_PORT) npm run dev

build-frontend: ## Frontend für Produktion bauen
	cd frontend && npm run build

# ── Kombiniert ────────────────────────────────────────────────────────────────

dev:           ## Backend (reload) + Frontend parallel starten
	$(MAKE) -j2 run-reload frontend

# ── Tests & Qualität ──────────────────────────────────────────────────────────

test:          ## Pytest ausführen
	uv run pytest

test-verbose:  ## Pytest mit ausführlicher Ausgabe
	uv run pytest -v

# ── Aufräumen ─────────────────────────────────────────────────────────────────

clean:         ## Build-Artefakte und temporäre Dateien entfernen
	rm -rf frontend/dist frontend/node_modules/.vite
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -f mcp_servers.db
