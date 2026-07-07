from __future__ import annotations

from agent_lab.clarity import clarity_short_circuit, detect_concrete_anchors


def test_clarity_short_circuit_korean_suffix_after_extension() -> None:
    topic = "room.py에서 consensus 라운드 cap 기본값이 뭐야?"
    assert detect_concrete_anchors(topic) is True
    assert clarity_short_circuit(topic) is True


def test_clarity_short_circuit_ascii_space_after_extension() -> None:
    topic = "room.py consensus cap default"
    assert detect_concrete_anchors(topic) is True
    assert clarity_short_circuit(topic) is True


def test_clarity_short_circuit_path_with_trailing_colon() -> None:
    topic = "see src/foo/bar.py: what is exported?"
    assert detect_concrete_anchors(topic) is True


def test_clarity_short_circuit_vague_topic_still_false() -> None:
    topic = "팀 생산성을 개선하고 싶어"
    assert clarity_short_circuit(topic) is False
