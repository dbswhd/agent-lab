## 지금 실행

1. Score regression fixtures in CI
   - 무엇을: Add score fixture smoke to CI.
   - 어디서: `.github/workflows/ci.yml`, `./Makefile`
   - 검증: `tests/test_session_score_ci.py` via pytest -q

## 실행 순서 (이후)

1. Keep benchmark catalog offline
   - 무엇을: Document benchmark scenarios.
   - 어디서: `sessions/_benchmark/README.md`
   - 검증: `pytest tests/test_benchmark_catalog.py -q`
