"""Default model IDs for 3-agent room (override via env)."""

DEFAULT_CURSOR_MODEL = "default"
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_CODEX_REASONING_EFFORT = "high"
DEFAULT_CODEX_ROOM_REASONING_EFFORT = "high"
DEFAULT_CODEX_ROOM_MAX_COMMANDS = 6
# Abandon a silently-hung room agent after this much inactivity (was 600s/10min,
# which felt like an infinite wait when Codex stalled on a usage limit).
DEFAULT_CODEX_ROOM_IDLE_TIMEOUT_SEC = 180
# Hard wall-clock cap for a single room turn. Without this, a rate-limited Codex
# that keeps emitting "retrying" events resets the idle timer and never stops.
DEFAULT_CODEX_ROOM_TIMEOUT_SEC = 300
DEFAULT_CLAUDE_MODEL = "opus"
DEFAULT_CLAUDE_REASONING_EFFORT = "high"
