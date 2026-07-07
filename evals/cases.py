from __future__ import annotations

import json
from pathlib import Path

from evals.schema import EvalCase, parse_eval_case


def load_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        loaded: object = json.loads(line)
        case = parse_eval_case(loaded)
        if case is not None:
            cases.append(case)
    return cases
