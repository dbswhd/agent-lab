# Room transcript

**Topic:** 새채팅수정테스트


## Human

새채팅수정테스트

## Cursor

주제 `새채팅수정테스트`면 지금은 **새 세션 첫 턴** 경로를 타는 게 맞아요. 레포 기준으로 새 대화 흐름은 이렇게 묶여 있습니다.

**상태 라우팅:** `App.tsx`의 `composerNew`가 true면 `RoomChat`에 `sessionId=null`이 넘어가고, `isNew` UI(제목 "3자 룸", plan 탭·컨텍스트 사이드바 숨김)가 켜집니다. 첫 전송은 `runRoom(..., { sessionId: undefined })` → 백엔드가 `sessions/2026-05-30-새채팅수정테스트/` 같은 폴더를 만들고 → `complete` 이벤트의 `session_id`로 `onSessionChange` → 그때부터 follow-up은 같은 `session_id`로 append됩니다.

**이번 테스트에서 볼 것 (순서대로):**
1. DevTools Network — 첫 POST `/api/run`에 `session_id` **없음**
2. SSE `complete`에 `session_id` **있음**
3. `sessions/2026-05-30-새채팅수정테스트/chat.jsonl` 생성 + L1 Human 한 줄
4. 왼쪽 목록에 세션 뜨고, 오른쪽 제목이 "3자 룸" → 주제명으로 바뀜
5. 두 번째 메시지 POST에 `session_id` **포함** (이어 말하기)

**수정 후보가 실제로 필요한 지점:** `startNew()`는 App 레벨(`selectedId`, `detail`, `composerNew`)만 리셋하고, `RoomChat` 인스턴스는 그대로라 `composeMode` / `turnProfile` / `contextOpen` / 진행 중 `running`이 남을 수 있어요. "새 대화 눌렀는데 이전 턴 설정·진행 상태가 남는다"가 재현되면, `RoomChat`에 `key={sessionId ?? "new"}` 한 줄이거나 `sessionId === null`일 때 로컬 상태 전부 초기화하는 `useEffect`가 가장 작은 diff입니다.

지금은 동료 발화가 없어서, 저는 **1→5 네트워크·파일 체크부터** 돌리고, 어느 단계에서 끊기는지 알려주면 그 구간 코드로 바로 패치 들어갈게요.
