# 3자 룸 — Cursor · Codex · Claude

> 통제 워크플로: [01-CONTROLLED-WORKFLOW-SYSTEM.md](./01-CONTROLLED-WORKFLOW-SYSTEM.md)  
> UI: Figma **Mac & iOS UI Kit** (Messages / system colors)

---

## 1. 무엇이 달라졌나

| | 클래식 | **3자 룸** (기본) |
|---|--------|------------------|
| 흐름 | Planner → Critic → Scribe (순차) | **Cursor + Codex + Claude 병렬** → plan 합성 |
| 백엔드 | codex / openai / anthropic 중 1개 | **에이전트 3명 각자** |
| 저장 | transcript.md | **chat.jsonl** + run.json + plan.md |

---

## 2. 에이전트 설정

| 에이전트 | 필요 조건 | 역할 |
|----------|-----------|------|
| **Codex** | `codex login`, `CODEX_BIN` (앱은 PATH 보강) | 분해·가설·실행 순서 |
| **Claude** | `ANTHROPIC_API_KEY` | 맹점·검증·범위 |
| **Cursor** | `CURSOR_API_KEY` + `pip install -e ".[cursor]"` | 구현·IDE·다음 편집 |

`.env` 예:

```env
AGENT_LAB_PROVIDER=codex
CODEX_BIN=/Users/you/.nvm/versions/node/v24.13.1/bin/codex
ANTHROPIC_API_KEY=sk-ant-...
CURSOR_API_KEY=...
```

---

## 3. 사용 워크플로 (앱)

1. **새 대화** → 상단 **3자 룸** 선택  
2. 참여 칩: Cursor / Codex / Claude (준비된 것만 켜기)  
3. 주제 입력 → **↑** 전송  
4. 세 에이전트가 **동시에** 말풍선 (입력 중 … → 본문)  
5. 끝나면 **plan.md** 합성 + 왼쪽 목록에 세션 생성  
6. 세션 열기 → **대화** / **plan.md** 탭

CLI:

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from agent_lab.room import run_room
folder, msgs, plan = run_room('주제 테스트')
print(folder, len(msgs), len(plan))
"
```

API: `POST /api/room/runs` (SSE) — `agent_start`, `agent_done`+`content`, `scribe_*`, `complete`

---

## 4. 통제 워크플로 (현재 구현 범위)

| 원칙 | 구현 |
|------|------|
| 명시적 입력 | `topic` + chat.jsonl |
| 최소 권한 | 텍스트만, 도구 없음 (`T0`) |
| 산출물 중심 | plan.md + run.json |
| 재현성 | chat.jsonl, transcript, meta |
| 병렬 상한 | 최대 3 에이전트 / 1 라운드 |

**다음 단계** (01 문서 Phase 2+): Clarifier gate, human approval, follow-up 메시지, YAML 워크플로 엔진.

---

## 5. Figma (Mac / iOS Kit)

| 화면 | Kit 참고 |
|------|----------|
| 말풍선 | iOS **Messages** — sent blue `#0A84FF`, received gray |
| 목록 | **Messages** sidebar / IG DM row height |
| 칩 | iOS **segmented** / capsule buttons |
| 에이전트 색 | Cursor `#7C5CFF`, Codex `#10A37F`, Claude `#D97757` (tokens.css) |

Community에서 **Apple iOS 18 UI Kit** 또는 **macOS Sonoma** Duplicate → `tokens.css` Variables 동기화.

---

## 6. 파일

| 경로 | 내용 |
|------|------|
| `src/agent_lab/room.py` | 병렬 오케스트레이션 |
| `src/agent_lab/agents/` | cursor / codex / claude |
| `workflows/room.parallel.yaml` | 워크플로 계약 (설정) |
| `sessions/.../chat.jsonl` | 메시지 로그 |
