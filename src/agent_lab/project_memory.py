"""Bootstrap workspace `.agent-lab/PROJECT.md` (LazyCodex /init-deep pattern)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PROJECT_MD_CAP = 2000
PROJECT_MD_INJECT_CAP = 1500


def project_md_path(workspace: Path) -> Path:
    return workspace.resolve() / ".agent-lab" / "PROJECT.md"


def bootstrap_project_md(
    workspace: Path,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> str:
    """Create or refresh PROJECT.md from filesystem heuristics. Returns written text."""
    root = workspace.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"workspace not found: {root}")
    target = project_md_path(root)
    if target.is_file() and not overwrite:
        return target.read_text(encoding="utf-8")

    text = _render_project_md(root)
    if len(text) > PROJECT_MD_CAP:
        text = text[: PROJECT_MD_CAP - 1] + "…"

    if dry_run:
        return text

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return text


def _render_project_md(root: Path) -> str:
    name = _project_name(root)
    blurb = _architecture_blurb(root)
    modules = _module_lines(root)
    build = _build_lines(root)
    notes = _agent_notes(root)

    lines = [
        f"# 프로젝트 메모리 — {name}",
        "",
        "## 아키텍처 한 줄",
        blurb or f"{name} workspace",
        "",
        "## 핵심 모듈",
        *modules,
        "",
        "## 빌드 & 실행",
        *build,
        "",
        "## 에이전트 주의사항",
        *notes,
        "",
        "## 현재 작업 맥락",
        "(Human이 채움 — 진행 중 작업·최근 결정)",
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def _project_name(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            proj = data.get("project") or {}
            if isinstance(proj, dict) and proj.get("name"):
                return str(proj["name"])
        except (OSError, tomllib.TOMLDecodeError):
            pass
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            import json

            data = json.loads(pkg.read_text(encoding="utf-8"))
            if data.get("name"):
                return str(data["name"])
        except (OSError, json.JSONDecodeError):
            pass
    return root.name


def _architecture_blurb(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            desc = (data.get("project") or {}).get("description")
            if isinstance(desc, str) and desc.strip():
                return desc.strip()
        except (OSError, tomllib.TOMLDecodeError):
            pass
    readme = root / "README.md"
    if readme.is_file():
        try:
            return _first_readme_paragraph(readme.read_text(encoding="utf-8"))
        except OSError:
            pass
    return ""


def _first_readme_paragraph(text: str) -> str:
    lines = text.splitlines()
    body: list[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not started:
            if stripped.startswith("#"):
                continue
            if not stripped or stripped.startswith(">"):
                continue
            started = True
        if started:
            if not stripped:
                break
            if stripped.startswith("#") or stripped == "---":
                break
            body.append(stripped)
    paragraph = " ".join(body).strip()
    return paragraph[:280]


def _module_lines(root: Path) -> list[str]:
    hints: list[tuple[str, str, str]] = [
        ("src/agent_lab", "src/agent_lab/", "Python Room·execute 코어"),
        ("app/server", "app/server/", "FastAPI 서버"),
        ("web/src", "web/src/", "React/Vite UI"),
        ("tests", "tests/", "pytest 회귀"),
        ("scripts", "scripts/", "스모크·운영 스크립트"),
        ("docs", "docs/", "설계·런북 문서"),
        ("src", "src/", "소스 트리"),
        ("app", "app/", "앱/서버 코드"),
        ("web", "web/", "웹 프론트"),
    ]
    seen: set[str] = set()
    lines: list[str] = []
    for _key, rel, role in hints:
        path = root / rel.rstrip("/")
        if not path.exists() or rel in seen:
            continue
        seen.add(rel)
        lines.append(f"- `{rel.rstrip('/')}` — {role}")
        if len(lines) >= 6:
            break
    if not lines:
        lines.append("- (핵심 경로를 Human이 추가)")
    return lines


def _build_lines(root: Path) -> list[str]:
    makefile = root / "Makefile"
    if not makefile.is_file():
        return ["- (빌드 명령을 Human이 추가)"]
    try:
        content = makefile.read_text(encoding="utf-8")
    except OSError:
        return ["- (빌드 명령을 Human이 추가)"]
    targets = ("dev", "test", "ci", "install", "build")
    lines: list[str] = []
    for target in targets:
        if re.search(rf"^{re.escape(target)}:", content, re.MULTILINE):
            lines.append(f"- `make {target}`")
    if not lines:
        lines.append("- `make help` 또는 README 참고")
    return lines[:5]


def _agent_notes(root: Path) -> list[str]:
    notes = [
        "- `.agent-lab/PROJECT.md`는 Agent Lab `session_guidance`가 workspace-bound 세션에 주입 (1500자 cap).",
        "- init-project-memory로 생성됨 — Human 검토·보강 필수.",
    ]
    if (root / "CLAUDE.md").is_file():
        notes.append("- 개발 규칙: 루트 `CLAUDE.md` 및 `.claude/rules/` 참고.")
    if (root / ".env.example").is_file():
        notes.append("- secrets는 `.env`만; child subprocess에 env 전체 상속 금지.")
    return notes
