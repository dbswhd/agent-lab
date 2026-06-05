"""Room notification taxonomy contract (frontend mapper + docs)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_notification_taxonomy_doc_exists():
    doc = _read("docs", "NOTIFICATION-TAXONOMY.md")
    assert "P0 blocker" in doc
    assert "dispatchNotification" in doc or "pushAppNotification" in doc


def test_notification_store_module():
    store = _read("web", "src", "utils", "notificationStore.ts")
    assert "pushAppNotification" in store
    assert "NotificationTier" in store


def test_dispatch_notification_wires_mac_and_activity():
    push = _read("web", "src", "utils", "pushNotification.ts")
    room = _read("web", "src", "components", "RoomChat.tsx")
    assert "dispatchNotification" in push
    assert "dispatchNotification" in room
    assert "NotificationCenter" in _read("web", "src", "components", "NotificationCenter.tsx")
