.PHONY: install dev prod api web cli tauri-dev prepare-bundled-runtime tauri-build test smoke smoke-e2e validate-quant verify-release

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[cursor]"
	cd web && npm install

icons:
	.venv/bin/pip install -q pillow
	.venv/bin/python scripts/generate_app_icon.py
	.venv/bin/python scripts/generate_agent_icons.py

dev:
	chmod +x scripts/dev.sh
	./scripts/dev.sh

prod:
	cd web && npm run build
	.venv/bin/uvicorn app.server.main:app --host 127.0.0.1 --port 8765

api:
	.venv/bin/uvicorn app.server.main:app --reload --host 127.0.0.1 --port 8765 \
		--reload-dir app --reload-dir src --reload-dir tests

web:
	cd web && npm run dev

cli:
	.venv/bin/python -m agent_lab run "$(TOPIC)"

tauri-dev:
	@test -x .venv/bin/python || (echo "Run: make install" && exit 1)
	cd web && npm run tauri dev

prepare-bundled-runtime:
	chmod +x scripts/prepare_bundled_runtime.sh
	./scripts/prepare_bundled_runtime.sh

tauri-build: prepare-bundled-runtime
	cd web && npm run tauri build

test:
	.venv/bin/pytest tests/ -q

smoke:
	.venv/bin/python scripts/smoke_room.py

smoke-e2e:
	AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/smoke_room_e2e.py

validate-quant:
	.venv/bin/python scripts/validate_quant_utility.py

verify-release:
	chmod +x scripts/verify_release.sh
	./scripts/verify_release.sh
