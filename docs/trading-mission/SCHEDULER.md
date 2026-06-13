# Trading Mission — 스케줄·이벤트 (P2)

장전 premarket 자동 실행과 장중 delta mission 트리거 설정.

## 환경 변수

```bash
export QUANT_PIPELINE_ROOT=/Users/yoonjong/Desktop/pipeline
export AGENTIC_TRADING_DB=~/Documents/New\ project/data/agentic_trading/control_plane.sqlite3
export AGENTIC_USE_NATIVE_INGEST=1              # RiskEngine ingest via quant_pipeline (권장)
export AGENTIC_QUANT_PIPELINE_SRC=~/Documents/New\ project/src  # optional override
export AGENT_LAB_TRADING_SCHEDULE=0730          # KST 장전 시각
export AGENT_LAB_TRADING_WATCHER_COOLDOWN_SEC=1800
```

## 1. 장전 스케줄러 (premarket)

수동 1회 (테스트):

```bash
cd ~/Projects/agent-lab
QUANT_PIPELINE_ROOT=/Users/yoonjong/Desktop/pipeline \
  .venv/bin/python scripts/run_trading_mission_scheduler.py --force --ingest
```

평일 07:30 이후 due 판정:

```bash
.venv/bin/python scripts/run_trading_mission_scheduler.py --ingest
```

상태 파일: `~/.agent-lab/trading_mission_scheduler_state.json` (당일 중복 실행 방지)

### macOS launchd (예시)

`~/Library/LaunchAgents/com.agentlab.trading-premarket.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.agentlab.trading-premarket</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/yoonjong/Projects/agent-lab/.venv/bin/python</string>
    <string>/Users/yoonjong/Projects/agent-lab/scripts/run_trading_mission_scheduler.py</string>
    <string>--ingest</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>QUANT_PIPELINE_ROOT</key>
    <string>/Users/yoonjong/Desktop/pipeline</string>
    <key>AGENTIC_TRADING_DB</key>
    <string>/Users/yoonjong/Documents/New project/data/agentic_trading/control_plane.sqlite3</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>7</integer>
    <key>Minute</key>
    <integer>35</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/yoonjong/.agent-lab/logs/trading-premarket.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/yoonjong/.agent-lab/logs/trading-premarket.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.agentlab.trading-premarket.plist
```

또는 경로 치환 포함 일괄 설치:

```bash
cd ~/Projects/agent-lab
make install-mission-triggers
```

템플릿: `scripts/deploy/com.agentlab.trading-{premarket,watcher,delta}.plist`

## 2. Watcher (delta enqueue)

5~15분 cron:

```bash
.venv/bin/python scripts/run_trading_mission_watcher.py
```

큐: `~/.agent-lab/trading_mission_queue.jsonl`

트리거:
- `ACTION_REQUIRED.flag` 신규
- `freshness.blocking` 전환
- `kill_switch` 활성화

## 3. Delta mission 처리

큐에서 1건 처리:

```bash
.venv/bin/python scripts/process_trading_mission_queue.py --skip-discuss --ingest
```

수동 delta:

```bash
.venv/bin/python scripts/run_trading_mission_delta.py \
  --trigger ACTION_REQUIRED.flag --skip-discuss
```

산출물: `artifacts/proposal_delta.json`, `playbook_patch.md`

## 4. cron 예시 (Linux/macOS)

```cron
# 장전 07:35 KST (시스템 TZ 확인)
35 7 * * 1-5 cd ~/Projects/agent-lab && .venv/bin/python scripts/run_trading_mission_scheduler.py --ingest

# 장중 watcher 10분
*/10 9-15 * * 1-5 cd ~/Projects/agent-lab && .venv/bin/python scripts/run_trading_mission_watcher.py

# delta 큐 처리 (watcher 직후)
*/10 9-15 * * 1-5 cd ~/Projects/agent-lab && .venv/bin/python scripts/process_trading_mission_queue.py --ingest
```
