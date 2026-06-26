.PHONY: install dev prod api web cli tauri-dev prepare-bundled-runtime tauri-build test test-fast test-integration test-bridge test-duration-report lint typecheck ci ci-full check-worktrees smoke smoke-e2e smoke-web-ui smoke-tauri-ui validate-quant verify-quant-workspace verify-trading-v1 verify-mcp-contract build-research-cards offline-lane thin-runtime-status verify-release verify-ops verify-ops-quick verify-ops-live verify-ops-live-merge score-session score-weekly score-regression-fixtures live-worktree-dry-run live-telegram-merge-soak init-project-memory verify-hooks measure-communicate-baseline mission-dogfood-report mission-dogfood-weekly list-flags emergence-bench dogfood-suite-mock dogfood-suite-checklist dogfood-suite-aggregate verify-ops verify-ops-quick verify-ops-live verify-ops-live-merge score-session score-weekly score-regression-fixtures live-worktree-dry-run live-telegram-merge-soak init-project-memory verify-hooks measure-communicate-baseline mission-dogfood-report mission-dogfood-weekly list-flags emergence-bench dogfood-suite-mock dogfood-suite-checklist dogfood-suite-aggregate dogfood-feedback-mock feedback-report

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

web-lint:
	cd web && npm run lint

web-format-check:
	cd web && npm run format:check

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

test: check-worktrees
	.venv/bin/pytest tests/ -q -m "not live"

test-fast: check-worktrees
	@if .venv/bin/python -c "import xdist" 2>/dev/null; then \
		.venv/bin/python scripts/run_verification_lane.py --lane fast --marker-expression "not live and not integration and not bridge" -- .venv/bin/pytest tests/ -q -m "not live and not integration and not bridge" -n $${TEST_FAST_WORKERS:-auto}; \
	else \
		.venv/bin/python scripts/run_verification_lane.py --lane fast --marker-expression "not live and not integration and not bridge" -- .venv/bin/pytest tests/ -q -m "not live and not integration and not bridge"; \
	fi

test-integration: check-worktrees
	.venv/bin/python scripts/run_verification_lane.py --lane integration --marker-expression "integration and not live and not bridge" -- .venv/bin/pytest tests/ -q -m "integration and not live and not bridge"

test-bridge: check-worktrees
	.venv/bin/python scripts/run_verification_lane.py --lane bridge --marker-expression "bridge and not live" -- .venv/bin/pytest tests/ -q -m "bridge and not live"

test-duration-report: check-worktrees
	.venv/bin/pytest tests/ -q -m "not live and not integration and not bridge" --durations=20

verify-hooks:
	.venv/bin/pytest tests/test_room_hooks.py tests/test_pre_execute_hooks.py tests/test_hook_router.py tests/test_reply_policy.py tests/test_gate_snapshot.py tests/test_hook_communicate_patches.py tests/test_hook_communicate_remaining.py tests/test_communicate_kpis.py tests/test_measure_communicate_baseline.py -q

measure-communicate-baseline:
	.venv/bin/python scripts/measure_communicate_baseline.py --sessions sessions/_benchmark --out tests/fixtures/communicate-baseline-benchmark.json
	.venv/bin/python scripts/measure_communicate_baseline.py --sessions sessions/_regression --out sessions/_regression/_reports/communicate-baseline-$$(date -u +%Y%m%d).json

mission-dogfood-report:
	@test -n "$(SESSION)" || SESSION=sessions/_regression/mission_loop_dogfood_ok; \
	.venv/bin/python scripts/mission_dogfood_report.py $$SESSION

mission-dogfood-run:
	AGENT_LAB_MOCK_AGENTS=1 AGENT_LAB_MISSION_LOOP=1 .venv/bin/python scripts/mission_dogfood_run.py

pipeline-dogfood-run:
	AGENT_LAB_MOCK_AGENTS=1 AGENT_LAB_MISSION_LOOP=1 AGENT_LAB_PIPELINE=1 .venv/bin/python scripts/pipeline_dogfood_run.py

mission-dogfood-weekly:
	AGENT_LAB_MOCK_AGENTS=1 AGENT_LAB_MISSION_LOOP=1 .venv/bin/python scripts/mission_dogfood_weekly.py --days $${DAYS:-7} $(if $(SKIP_MOCK),--skip-mock,) $(if $(INCLUDE_FIXTURES),--include-fixtures,)

test-live:
	@test "$$AGENT_LAB_RUN_LIVE" = "1" || (echo "Set AGENT_LAB_RUN_LIVE=1 for live Cursor spike tests" && exit 1)
	.venv/bin/python scripts/run_verification_lane.py --lane live --marker-expression "live" -- .venv/bin/pytest tests/ -q -m live

loop-model-eval-mock:
	AGENT_LAB_MOCK_AGENTS=1 AGENT_LAB_MOCK_STRUCTURED_ENVELOPE=1 AGENT_LAB_LOOP_PROBE=0 \
		.venv/bin/python scripts/run_loop_model_eval.py --mock

loop-model-eval-live:
	@test "$$AGENT_LAB_RUN_LIVE" = "1" || (echo "Set AGENT_LAB_RUN_LIVE=1 for live loop eval" && exit 1)
	.venv/bin/python scripts/run_loop_model_eval.py --live

lint:
	.venv/bin/ruff check src/ app/ tests/ scripts/

format:
	.venv/bin/ruff format src/ app/ tests/ scripts/ examples/

format-check:
	.venv/bin/ruff format --check src/ app/ tests/ scripts/ examples/

typecheck:
	.venv/bin/mypy

typecheck-ratchet:
	.venv/bin/python scripts/mypy_ratchet.py --check

ci: lint format-check typecheck-ratchet test-fast smoke

ci-full: check-worktrees
	.venv/bin/python scripts/run_verification_lane.py --lane ci_full -- sh -c 'make lint format-check typecheck-ratchet test-fast test-integration test-bridge smoke score-regression-fixtures'

init-project-memory:
	@test -n "$(WORKSPACE)" || WORKSPACE=.; \
	.venv/bin/python scripts/init_project_memory.py "$(WORKSPACE)" $(if $(OVERWRITE),--overwrite,)

verify-quant-workspace:
	@test -n "$(QUANT_PIPELINE_ROOT)" || true; \
	.venv/bin/python scripts/verify_quant_workspace_setup.py

verify-trading-v1:
	.venv/bin/python scripts/verify_trading_mission_v1.py --synthetic --pilot

verify-mcp-contract:
	PYTHONPATH=$${PYTHONPATH:-$(HOME)/Projects/quant-agentic-trading/src} \
	.venv/bin/python scripts/verify_mcp_contract.py
	PYTHONPATH=$${PYTHONPATH:-$(HOME)/Projects/quant-agentic-trading/src} \
	.venv/bin/python -m pytest tests/test_mcp_tool_contract.py -q

build-research-cards:
	QUANT_PIPELINE_ROOT=$${QUANT_PIPELINE_ROOT:-$(HOME)/Desktop/pipeline} \
	.venv/bin/python scripts/build_research_artifact_cards.py --pipeline "$$QUANT_PIPELINE_ROOT"

artifact-cards: build-research-cards

offline-lane:
	QUANT_PIPELINE_ROOT=$${QUANT_PIPELINE_ROOT:-$(HOME)/Desktop/pipeline} \
	.venv/bin/python scripts/run_trading_mission_offline.py --force

thin-runtime-status:
	@test -n "$(SESSION)" || (echo "Usage: make thin-runtime-status SESSION=sessions/<id>" && exit 1)
	AGENT_LAB_SESSION_FOLDER="$(abspath $(SESSION))" \
	AGENTIC_TRADING_DB=$${AGENTIC_TRADING_DB:-$(HOME)/Projects/quant-agentic-trading/data/agentic_trading/control_plane.sqlite3} \
	.venv/bin/python -m agent_lab.trading_mission.thin_runtime --session "$(abspath $(SESSION))" --db "$$AGENTIC_TRADING_DB"

install-mission-triggers:
	chmod +x scripts/install_mission_triggers.sh
	QUANT_PIPELINE_ROOT=$${QUANT_PIPELINE_ROOT:-$(HOME)/Desktop/pipeline} \
	AGENTIC_TRADING_DB=$${AGENTIC_TRADING_DB:-$(HOME)/Projects/quant-agentic-trading/data/agentic_trading/control_plane.sqlite3} \
	AGENTIC_QUANT_PIPELINE_SRC=$${AGENTIC_QUANT_PIPELINE_SRC:-$(HOME)/Projects/quant-agentic-trading/src} \
	AGENT_LAB_FRESHNESS_PYTHON=$${AGENT_LAB_FRESHNESS_PYTHON:-$(HOME)/Desktop/pipeline/.venv/bin/python} \
	./scripts/install_mission_triggers.sh

install-serve-daemon:
	chmod +x scripts/install_serve_daemon.sh
	./scripts/install_serve_daemon.sh

token-log-summary:
	QUANT_PIPELINE_ROOT=$${QUANT_PIPELINE_ROOT:-$(HOME)/Desktop/pipeline} \
	.venv/bin/python scripts/summarize_token_log.py --lines $${LINES:-20}

refresh-freshness:
	@test -x $${QUANT_PIPELINE_ROOT:-$(HOME)/Desktop/pipeline}/.venv/bin/python || (echo "pipeline .venv missing" && exit 1)
	PRICE_BACKFILL_DAYS=$${PRICE_BACKFILL_DAYS:-15} \
	$${QUANT_PIPELINE_ROOT:-$(HOME)/Desktop/pipeline}/.venv/bin/python \
		$${QUANT_PIPELINE_ROOT:-$(HOME)/Desktop/pipeline}/scripts/spec91/spec91_daily_data_refresh.py \
		--kind kr-daily
	$${QUANT_PIPELINE_ROOT:-$(HOME)/Desktop/pipeline}/.venv/bin/python \
		$${QUANT_PIPELINE_ROOT:-$(HOME)/Desktop/pipeline}/scripts/spec91/spec91_daily_data_refresh.py \
		--kind us --skip-notebook
	AGENT_LAB_FRESHNESS_PYTHON=$${AGENT_LAB_FRESHNESS_PYTHON:-$(HOME)/Desktop/pipeline/.venv/bin/python} \
	QUANT_PIPELINE_ROOT=$${QUANT_PIPELINE_ROOT:-$(HOME)/Desktop/pipeline} \
	.venv/bin/python -c "from agent_lab.pipeline_market_read import run_data_freshness; import json; r=run_data_freshness(); print(json.dumps({'ok':r.get('ok'),'blocking':r.get('blocking'),'message':r.get('message')}, ensure_ascii=False)); raise SystemExit(0 if r.get('ok') else 1)"

check-worktrees:
	.venv/bin/python scripts/check_worktree_orphans.py

list-flags:
	.venv/bin/python scripts/list_flags.py

score-session:
	@test -n "$(SESSION)" || (echo "Usage: make score-session SESSION=sessions/<id>" && exit 1)
	.venv/bin/python scripts/score_session.py "$(SESSION)"

score-weekly:
	@if [ "$${REPORT:-1}" = "0" ]; then \
		.venv/bin/python scripts/score_sessions_weekly.py --days $${DAYS:-7} $(if $(INCLUDE_FIXTURES),--include-fixtures,) $(if $(STRICT),--strict,); \
	else \
		REPORT_DIR="$${AGENT_LAB_WEEKLY_REPORT_DIR:-sessions/_reports}"; \
		.venv/bin/python scripts/score_sessions_weekly.py --days $${DAYS:-7} $(if $(INCLUDE_FIXTURES),--include-fixtures,) $(if $(STRICT),--strict,) --write-artifacts "$$REPORT_DIR"; \
	fi

verify-ops:
	$(MAKE) ci-full
	.venv/bin/python scripts/check_worktree_orphans.py
	.venv/bin/python scripts/check_bridge_processes.py
	@if [ "$${REPORT:-1}" = "0" ]; then \
		echo "Ops report: skipped (REPORT=0)"; \
	else \
		REPORT_DIR="$${AGENT_LAB_WEEKLY_REPORT_DIR:-sessions/_reports}"; \
		AGENT_LAB_WEEKLY_REPORT_DIR="$$REPORT_DIR" $(MAKE) score-weekly DAYS=$${DAYS:-7} REPORT=1 $(if $(INCLUDE_FIXTURES),INCLUDE_FIXTURES=1,) $(if $(STRICT),STRICT=1,); \
		status="$$?"; \
		END_DATE="$$(date -u +%F)"; \
		echo "Ops report: $$REPORT_DIR/weekly-$$END_DATE.md"; \
		exit "$$status"; \
	fi

verify-ops-quick:
	$(MAKE) smoke
	.venv/bin/python scripts/check_worktree_orphans.py
	REPORT=0 $(MAKE) score-weekly DAYS=$${DAYS:-7} INCLUDE_FIXTURES=1

verify-ops-live:
	@if [ "$${SKIP_PREFLIGHT:-0}" != "1" ]; then \
		$(MAKE) verify-ops REPORT=0; \
	fi
	@test "$$AGENT_LAB_RUN_LIVE" = "1" || (echo "Set AGENT_LAB_RUN_LIVE=1 before verify-ops-live" && exit 1)
	@REPORT_DIR="$${AGENT_LAB_WEEKLY_REPORT_DIR:-sessions/_reports}"; \
	REPORT_PATH="$$REPORT_DIR/live-worktree-$$(date -u +%F).json"; \
	AGENT_LAB_RUN_LIVE=1 .venv/bin/python scripts/live_cursor_worktree_dry_run.py --write "$$REPORT_PATH"; \
	status="$$?"; \
	verdict="NO_GO"; \
	if [ "$$status" = "0" ]; then verdict="GO"; elif [ "$$status" = "3" ]; then verdict="SKIPPED"; fi; \
	echo "Live ops report: $$REPORT_PATH ($$verdict)"; \
	exit "$$status"

verify-ops-live-merge:
	@if [ "$${SKIP_PREFLIGHT:-0}" != "1" ]; then \
		$(MAKE) verify-ops REPORT=0; \
	fi
	@test "$$AGENT_LAB_RUN_LIVE" = "1" || (echo "Set AGENT_LAB_RUN_LIVE=1 before verify-ops-live-merge" && exit 1)
	@REPORT_DIR="$${AGENT_LAB_WEEKLY_REPORT_DIR:-sessions/_reports}"; \
	REPORT_PATH="$$REPORT_DIR/live-merge-$$(date -u +%F).json"; \
	AGENT_LAB_RUN_LIVE=1 .venv/bin/python scripts/live_cursor_worktree_merge_run.py --write "$$REPORT_PATH"; \
	status="$$?"; \
	verdict="NO_GO"; \
	if [ "$$status" = "0" ]; then verdict="GO"; elif [ "$$status" = "3" ]; then verdict="SKIPPED"; fi; \
	echo "Live merge ops report: $$REPORT_PATH ($$verdict)"; \
	exit "$$status"

verify-ops-live-telegram-merge:
	@if [ "$${SKIP_PREFLIGHT:-0}" != "1" ]; then \
		$(MAKE) verify-ops REPORT=0; \
	fi
	@test "$$AGENT_LAB_RUN_LIVE" = "1" || (echo "Set AGENT_LAB_RUN_LIVE=1 before verify-ops-live-telegram-merge" && exit 1)
	@REPORT_DIR="$${AGENT_LAB_WEEKLY_REPORT_DIR:-sessions/_reports}"; \
	REPORT_PATH="$$REPORT_DIR/live-telegram-merge-$$(date -u +%F).json"; \
	AGENT_LAB_RUN_LIVE=1 .venv/bin/python scripts/live_telegram_merge_ingress_soak.py --write "$$REPORT_PATH"; \
	status="$$?"; \
	verdict="NO_GO"; \
	if [ "$$status" = "0" ]; then verdict="GO"; elif [ "$$status" = "3" ]; then verdict="SKIPPED"; fi; \
	echo "Live Telegram merge ingress report: $$REPORT_PATH ($$verdict)"; \
	exit "$$status"

live-telegram-merge-soak:
	@test "$$AGENT_LAB_RUN_LIVE" = "1" || (echo "Set AGENT_LAB_RUN_LIVE=1 before live Telegram merge soak" && exit 1)
	.venv/bin/python scripts/live_telegram_merge_ingress_soak.py

verify-ops-live-tunnel-launchd:
	@if [ "$${SKIP_PREFLIGHT:-0}" != "1" ]; then \
		$(MAKE) verify-ops REPORT=0; \
	fi
	@test "$$AGENT_LAB_RUN_LIVE" = "1" || (echo "Set AGENT_LAB_RUN_LIVE=1 before verify-ops-live-tunnel-launchd" && exit 1)
	@REPORT_DIR="$${AGENT_LAB_WEEKLY_REPORT_DIR:-sessions/_reports}"; \
	REPORT_PATH="$$REPORT_DIR/live-tunnel-launchd-$$(date -u +%F).json"; \
	AGENT_LAB_RUN_LIVE=1 .venv/bin/python scripts/live_tunnel_launchd_soak.py --write "$$REPORT_PATH"; \
	status="$$?"; \
	verdict="NO_GO"; \
	if [ "$$status" = "0" ]; then verdict="GO"; elif [ "$$status" = "3" ]; then verdict="SKIPPED"; fi; \
	echo "Live tunnel+launchd report: $$REPORT_PATH ($$verdict)"; \
	exit "$$status"

live-tunnel-launchd-soak:
	@test "$$AGENT_LAB_RUN_LIVE" = "1" || (echo "Set AGENT_LAB_RUN_LIVE=1 before live tunnel+launchd soak" && exit 1)
	.venv/bin/python scripts/live_tunnel_launchd_soak.py

live-worktree-dry-run:
	@test "$$AGENT_LAB_RUN_LIVE" = "1" || (echo "Set AGENT_LAB_RUN_LIVE=1 before live Cursor spike" && exit 1)
	.venv/bin/python scripts/live_cursor_worktree_dry_run.py

score-regression-fixtures:
	.venv/bin/python scripts/score_session.py --json sessions/_regression/worktree_merge_ok
	.venv/bin/python scripts/score_session.py --json sessions/_regression/objection_blocks_execute
	.venv/bin/python scripts/score_session.py --json sessions/_regression/emergence_hybrid_plan
	.venv/bin/python scripts/score_session.py --json sessions/_regression/discuss_challenge_resolved
	.venv/bin/python scripts/score_session.py --json sessions/_regression/recombination_synthesis

emergence-bench:
	.venv/bin/python scripts/emergence_bench.py

dogfood-suite-mock:
	AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/run_dogfood_suite.py --mode mock \
	  $(if $(TIER),--tier $(TIER),) $(if $(ONLY),--only $(ONLY),)

dogfood-suite-checklist:
	.venv/bin/python scripts/run_dogfood_suite.py --mode checklist \
	  $(if $(TIER),--tier $(TIER),) $(if $(ONLY),--only $(ONLY),)

dogfood-suite-aggregate:
	@test -n "$(LOG)" || (echo "Usage: make dogfood-suite-aggregate LOG=suite-log.json" && exit 1)
	.venv/bin/python scripts/run_dogfood_suite.py --mode aggregate --log "$(LOG)" \
	  $(if $(TIER),--tier $(TIER),) $(if $(ONLY),--only $(ONLY),)

dogfood-feedback-mock:
	AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/run_dogfood_suite.py --mode mock --feedback \
	  --repeat $${REPEAT:-4} $(if $(TIER),--tier $(TIER),) $(if $(ONLY),--only $(ONLY),)

feedback-report:
	.venv/bin/python scripts/feedback_report.py $(if $(ROOT),--root $(ROOT),) $(if $(JSON),--json,)

smoke:
	.venv/bin/python scripts/smoke_room.py

smoke-e2e:
	AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/smoke_room_e2e.py

smoke-web-ui:
	chmod +x scripts/smoke_web_ui.sh
	./scripts/smoke_web_ui.sh

smoke-tauri-ui:
	chmod +x scripts/smoke_tauri_ui.sh
	./scripts/smoke_tauri_ui.sh

validate-quant:
	.venv/bin/python scripts/validate_quant_utility.py

verify-release:
	chmod +x scripts/verify_release.sh
	./scripts/verify_release.sh
