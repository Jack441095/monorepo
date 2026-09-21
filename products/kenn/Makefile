PYTHON ?= python3
BACKEND_PYTHONPATH := apps/backend/src

NATIVE_BUILD_DIR ?= /tmp/kenn-dsp-native-build
NATIVE_PYTHON ?= $(PYTHON)
AUTOMIX_KERNEL_BUILD_DIR ?= /tmp/kenn-automix-kernels
CMAKE ?= $(if $(wildcard /opt/homebrew/bin/cmake),/opt/homebrew/bin/cmake,cmake)

.PHONY: demo-cache backend-test backend-dev native-build native-wheel automix-kernel-build frontend-install frontend-test frontend-build frontend-dev

demo-cache:
	$(PYTHON) tooling/scripts/create_demo_slo_cache.py

backend-test:
	PYTHONPATH=$(BACKEND_PYTHONPATH) $(PYTHON) -m pytest -q \
		apps/backend/src/kenn/tests/test_slo_classification_adapter.py \
		apps/backend/src/kenn/tests/test_slo_classification_routes.py

backend-dev:
	PYTHONPATH=$(BACKEND_PYTHONPATH) $(PYTHON) run_ux_backend.py

native-build:
	$(CMAKE) -S tooling/native/dsp_core -B $(NATIVE_BUILD_DIR) -DCMAKE_BUILD_TYPE=Release -DPython_EXECUTABLE=$(NATIVE_PYTHON)
	$(CMAKE) --build $(NATIVE_BUILD_DIR) --parallel 2

native-wheel:
	# Use the selected interpreter's nanobind/scikit-build-core/CMake toolchain;
	# isolated pip builds can accidentally select an incompatible host CMake.
	CMAKE_EXECUTABLE="$(CMAKE)" $(NATIVE_PYTHON) -m pip wheel tooling/native/dsp_core --no-build-isolation --no-deps --wheel-dir $(NATIVE_BUILD_DIR)/wheel

automix-kernel-build:
	$(CMAKE) -S ../../audio-technology/audio-analysis/audio_analysis/dsp_engine/native -B $(AUTOMIX_KERNEL_BUILD_DIR) -DCMAKE_BUILD_TYPE=Release
	$(CMAKE) --build $(AUTOMIX_KERNEL_BUILD_DIR) --config Release --parallel 2

frontend-install:
	cd apps/frontend && npm ci

frontend-test:
	cd apps/frontend && npm test

frontend-build:
	cd apps/frontend && npm run build

frontend-dev:
	cd apps/frontend && npm run dev
