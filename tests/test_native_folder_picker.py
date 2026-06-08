from __future__ import annotations

from agent_lab import native_folder_picker as nfp


def test_pick_folder_native_non_macos(monkeypatch):
    monkeypatch.setattr(nfp.platform, "system", lambda: "Linux")
    available, path = nfp.pick_folder_native()
    assert available is False
    assert path is None


def test_pick_folder_macos_cancelled(monkeypatch):
    def fake_run(*_args, **_kwargs):
        class R:
            returncode = 1
            stdout = ""
            stderr = "User canceled."

        return R()

    monkeypatch.setattr(nfp.subprocess, "run", fake_run)
    assert nfp.pick_folder_macos() is None


def test_pick_folder_macos_returns_path(monkeypatch):
    captured: list[str] = []

    def fake_run(cmd, **_kwargs):
        captured.extend(cmd)

        class R:
            returncode = 0
            stdout = "/Users/me/project\n"
            stderr = ""

        return R()

    monkeypatch.setattr(nfp.subprocess, "run", fake_run)
    path = nfp.pick_folder_macos(default_path="/Users/me")
    assert path == "/Users/me/project"
    assert captured[0] == "osascript"
    assert "/Users/me" in captured[2]
