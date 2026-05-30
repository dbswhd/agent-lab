.PHONY: install dev api web cli tauri-dev tauri-build

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

api:
	.venv/bin/uvicorn app.server.main:app --reload --host 127.0.0.1 --port 8765 \
		--reload-dir app --reload-dir src --reload-dir tests

web:
	cd web && npm run dev

cli:
	.venv/bin/python -m agent_lab run "$(TOPIC)"

tauri-dev:
	cd web && npm run tauri dev

tauri-build:
	cd web && npm run tauri build
