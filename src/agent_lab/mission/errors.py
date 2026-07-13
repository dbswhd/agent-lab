from __future__ import annotations


class MissionTransitionError(Exception):
    def __init__(self, command: str, state: str, reason: str) -> None:
        self.command = command
        self.state = state
        self.reason = reason
        super().__init__(command, state, reason)

    def __str__(self) -> str:
        return f"{self.command} rejected in {self.state}: {self.reason}"
