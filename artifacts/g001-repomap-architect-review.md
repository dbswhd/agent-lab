# Architect Review — ultragoal G001 (P1): Symbol-Graph Repo-Map

> NOTE: role-agent subagent dispatch down all session. Conducted INLINE by the ultragoal leader, source-verified. Disclosed.

## Verdict
- architectureStatus: CLEAR
- productStatus: CLEAR
- codeStatus: CLEAR
- recommendation: APPROVE
- blocking count: 0

## Scope reviewed
src/agent_lab/repo_map.py (new), src/agent_lab/context_bundle.py (the build_repo_tree_block call-site swap), src/agent_lab/runtime_flags.py (AGENT_LAB_REPO_MAP + AGENT_LAB_REPO_MAP_TOKENS), .env.example, tests/test_repo_map.py, tests/test_integration_registry.py (budget).

## Findings (against plan + constraints)
1. CORRECT LEVER: the single build_repo_tree_block call site (context_bundle.py) is swapped behind a flag guard; flag-off calls the original unchanged and never imports repo_map (import lives inside the `if _env_bool("AGENT_LAB_REPO_MAP"):` branch). CLEAR.
2. OFF-PARITY (PRIMARY): flag-off path is byte-identical (original build_repo_tree_block); AC5 asserts the import is guarded (not module-top) and repo_map_enabled() False by default; full default-off suite (1583 passed) unchanged. CLEAR.
3. ZERO DEPENDENCY: repo_map imports only stdlib (ast/os/collections/pathlib) + repo_tree_context seed/root helpers + context_layers toggle; AC8 parses the module AST and asserts no tree_sitter/networkx and no room/mission/plan_execute/runtime lane imports. CLEAR.
4. ARCHITECT HIGH (from ralplan, AC10) RESOLVED: build_repo_map_block returns "" when _workspace_root is None (unbound) OR repo_tree_layer_enabled is False; the file walk prunes dotdirs + EXCLUDE_DIRS in os.walk and caps at MAX_FILES (restricting to seed dirs when exceeded); unparseable files return None and are skipped (never raise). AC10 + AC6 tests cover all three. CLEAR.
5. SEED REUSE: ranking seeds resolve _plan_path_hints + _plan_action_path_hints against the workspace root, tolerate missing hints, and fall back to deterministic global reference-frequency when no seed resolves (AC2/AC7). CLEAR.
6. DETERMINISM + BUDGET: ranking + render sort by (-score, path) / (lineno) with deterministic tie-breaks; render accumulates within AGENT_LAB_REPO_MAP_TOKENS*4 chars and drops lowest-ranked first (AC4 + Critic N2 length bound). CLEAR.
7. REPLACE-NOT-DUPLICATE: flag-on emits exactly one [Repo map] block in place of [Repo tree] (AC6). No on-disk persistence (per-turn compute). CLEAR.

## Verification observed (leader-run, real)
- ruff check + format --check: clean.
- mypy ratchet: 243/243 (delta 0).
- make test-fast: 1583 passed, 1 skipped, 0 failed.
- focused: 37 passed (artifacts/g001-repomap-qa.txt) covering AC1-AC10 + Critic N1 (excluded/.venv fixture never parsed) + N2 (rendered length within budget).
