# Agent Lab — 사용 워크플로 (메신저 UI)

> **Legacy doc (Tier 4)** — early messenger metaphor. **Canonical:** [USER-GUIDE.md](./USER-GUIDE.md) · [README.md](./README.md)

> UI 레퍼런스: **iMessage** (말풍선·전송), **Instagram DM** (대화 목록·프리뷰), **Telegram** (그룹 발신자 라벨·고정 메시지)

---

## 1. 화면 구조 (한눈에)

```
┌──────────────────┬────────────────────────────────────────┐
│  Agent Lab       │  [채팅 헤더] 주제 / 역할                 │
│  [새 대화]       │  ─────────────────────────────────────   │
│  backend 상태    │  말풍선 스크롤 (나 → Planner → …)        │
│  ─────────────   │  ─────────────────────────────────────   │
│  DM 목록         │  [입력창] 메시지 + 백엔드 + ↑ 전송        │
│  · 세션 A        │                                        │
│  · 세션 B        │                                        │
└──────────────────┴────────────────────────────────────────┘
     Telegram/IG          iMessage 대화창
```

---

## 2. 일상 워크플로 (단계별)

### ① 앱 켜기

```bash
cd ~/Projects/agent-lab
source .venv/bin/activate
make dev
# 브라우저 http://127.0.0.1:5173
```

왼쪽 상단에 **백엔드 상태** (예: `Claude opus (high) · Codex gpt-5.5 (medium) · Cursor default`)가 보이면 API 연결 OK.

| 백엔드 | 언제 쓰나 |
|--------|-----------|
| **codex** | ChatGPT Plus (`codex login`) — API quota 없을 때 |
| **openai** | Platform API 결제·크레딧 있을 때 |
| **anthropic** | Claude API 키 있을 때 |

`.env`에서 `AGENT_LAB_PROVIDER=codex` 권장.

---

### ② 새 주제 보내기 (iMessage “새 메시지”)

1. 왼쪽 **「새 대화」** 클릭  
2. 아래 입력창에 **주제** 입력 (한 줄~몇 줄)  
3. (선택) 백엔드 드롭다운  
4. **↑** 또는 **Enter** 전송  

**화면에서 일어나는 일**

| 순서 | UI | 실제 동작 |
|------|-----|-----------|
| 1 | **파란 말풍선**(오른쪽) = 내 주제 | `topic` 저장 예정 |
| 2 | **회색 말풍선** + 이름 Planner + **…입력 중** | `invoke_role(Planner)` |
| 3 | Planner 완료 말풍선 | bullet 가설 생성 |
| 4 | Critic **…입력 중** → 완료 | 맹점·리스크 |
| 5 | Scribe **…입력 중** → 완료 | `plan.md` 초안 |
| 6 | 가운데 **「세션 저장됨」** pill | `sessions/<date>-<slug>/` 생성 |
| 7 | 자동으로 **대화 목록**에서 해당 세션 열림 | 전체 transcript 로드 |

한 번 실행 ≈ **LLM 3회** (비용·시간 감안).

---

### ③ 지난 대화 열기 (Instagram DM 목록)

1. 왼쪽 목록에서 세션 탭  
2. 오른쪽 **대화** 탭:  
   - 내 주제 (파란색)  
   - Planner / Critic / Scribe (회색, **이름 라벨** = Telegram 그룹 채팅)  
3. **plan.md** 탭: Scribe 최종안 전문 (Telegram **고정 메시지** 느낌)

목록에는 **제목(topic)** · **모델** · **날짜/시간** 프리뷰.

---

### ④ pipeline으로 넘기기 (Human 단계)

Agent Lab은 **실행 안 함** — 산출물만 넘깁니다.

```text
sessions/2026-05-26-my-topic/plan.md
        │
        ▼  (본인 + Cursor Conductor 검토)
quant-pipeline/tasks/TASK-NNN-*.md
```

앱에서 **plan.md** 탭 → 복사 → pipeline repo에 TASK 초안 작성.

---

## 3. CLI vs 앱

| | 앱 (`make dev`) | CLI |
|---|-----------------|-----|
| 입력 | 메신저 입력창 | `python -m agent_lab run "주제"` |
| 진행 | 말풍선·입력 중 | 터미널 로그 |
| 결과 | UI + `sessions/` | `sessions/` 동일 |

같은 폴더·같은 파일 형식 → **앱과 CLI 혼용 가능**.

---

## 4. 세션 폴더 (디스크)

주제 1개 = 폴더 1개:

```text
sessions/2026-05-26-c45-overlay/
├── topic.txt
├── transcript.md    # UI 「대화」탭 소스
├── plan.md            # UI 「plan.md」탭
└── meta.json          # 모델·시간
```

앱을 껐다 켜도 목록은 **폴더 스캔**으로 복구.

---

## 5. 자주 막히는 지점

| 증상 | 원인 | 조치 |
|------|------|------|
| OpenAI `insufficient_quota` | Plus ≠ API | 백엔드 **codex** 또는 Anthropic |
| Codex 멈춤 | stdin 대기 등 | `codex login`, 터미널에서 `codex doctor` |
| 목록 비어 있음 | 아직 실행 안 함 | 새 대화 1회 |
| 말풍선에 본문 짧음 | 실행 중에는 요약만 | 완료 후 세션 **대화** 탭에서 전문 |

---

## 6. 디자인 외주 시 (Figma/Stitch)

레퍼런스를 **메신저 3종**으로 고정했습니다. 자세한 스펙:

→ [docs/02-ui-ux-handoff.md](./02-ui-ux-handoff.md)

코드 핸드오프:

| 요소 | 파일 |
|------|------|
| 말풍선 | `web/src/components/ChatBubble.tsx` |
| DM 목록 | `web/src/components/SessionList.tsx` |
| 색·radius | `web/src/styles/tokens.css` |

---

## 7. 다음 단계 (선택)

- **Tauri `.app`** — quant-control처럼 맥에 설치 (진행 중이면 `make tauri-dev`)  
- **실시간 스트리밍** — 실행 중 Planner 본문이 말풍선에 조금씩 채워지기 (API 확장)  
- **TASK export** — plan.md → `TASK-draft.md` 버튼

관련: [docs/APP.md](./APP.md) · [README.md](../README.md)
