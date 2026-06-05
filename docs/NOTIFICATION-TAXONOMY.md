# Notification Taxonomy

## Tier

| Tier | 예시 | Surfaces |
|------|------|----------|
| P0 blocker | consensus BLOCK, execute 409 | MacAlert + Activity badge + desktop |
| P1 action | dry-run ready, plan sync | toast (7s) + Activity |
| P2 info | agent done, artifact saved | Activity only |
| P3 debug | context trim, SSE parse | dev console only |

## Dedup

- Key: `{sessionId}:{kind}:{entityId}` — 동일 key 30s 내 1회
- P0는 dedup 없음

## Frontend routing

```
pushNotification({ tier, title, body, sessionId, kind, entityId?, actions? })
  → P0/P1: MacNotificationHost + optional notifyDesktop
  → all: NotificationCenter.append (Inspector Activity)
```

## SSE mapping (frontend)

| SSE type | Tier | kind |
|----------|------|------|
| consensus_plan_synced | P1 | plan_sync |
| consensus_plan_sync_failed | P0 | plan_sync_fail |
| consensus_dry_run_proposal | P1 | dry_run |
| turn_failed | P0 | turn_fail |
| turn_partial | P1 | turn_partial |
| complete | P2 | turn_complete |

Frontend routing uses `dispatchNotification()` and `pushAppNotification()`.
