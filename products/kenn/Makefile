PYTHON ?= python3
BACKEND_PYTHONPATH := apps/backend/src

.PHONY: demo-cache backend-test backend-dev frontend-install frontend-test frontend-build frontend-dev

demo-cache:
	$(PYTHON) tooling/scripts/create_demo_slo_cache.py

backend-test:
	PYTHONPATH=$(BACKEND_PYTHONPATH) $(PYTHON) -m pytest -q \
		apps/backend/src/kenn/tests/test_slo_classification_adapter.py \
		apps/backend/src/kenn/tests/test_slo_classification_routes.py

backend-dev:
	PYTHONPATH=$(BACKEND_PYTHONPATH) $(PYTHON) run_ux_backend.py

frontend-install:
	cd apps/frontend && npm ci

frontend-test:
	cd apps/frontend && npm test

frontend-build:
	cd apps/frontend && npm run build

frontend-dev:
	cd apps/frontend && npm run dev
