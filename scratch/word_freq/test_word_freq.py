from __future__ import annotations

import pytest
from pathlib import Path
from collections import Counter

from word_freq import count_words, top_n, main


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.txt"
    p.write_text("apple banana apple cherry banana apple", encoding="utf-8")
    return p


@pytest.fixture
def mixed_case_file(tmp_path: Path) -> Path:
    p = tmp_path / "mixed.txt"
    p.write_text("Apple APPLE apple Banana BANANA", encoding="utf-8")
    return p


@pytest.fixture
def single_word_file(tmp_path: Path) -> Path:
    p = tmp_path / "single.txt"
    p.write_text("hello", encoding="utf-8")
    return p


# ── count_words ───────────────────────────────────────────────────────────────


def test_basic_count(sample_file: Path) -> None:
    c = count_words(sample_file)
    assert c["apple"] == 3
    assert c["banana"] == 2
    assert c["cherry"] == 1


def test_lowercase_normalisation(mixed_case_file: Path) -> None:
    c = count_words(mixed_case_file)
    assert c["apple"] == 3
    assert c["banana"] == 2
    assert "Apple" not in c
    assert "APPLE" not in c


def test_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        count_words(tmp_path / "nonexistent.txt")


def test_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="비어 있습니다"):
        count_words(p)


def test_whitespace_only_file(tmp_path: Path) -> None:
    p = tmp_path / "ws.txt"
    p.write_text("   \n\t  \n", encoding="utf-8")
    with pytest.raises(ValueError, match="비어 있습니다"):
        count_words(p)


def test_single_word(single_word_file: Path) -> None:
    c = count_words(single_word_file)
    assert c["hello"] == 1


# ── top_n ─────────────────────────────────────────────────────────────────────


def test_top_n_order(sample_file: Path) -> None:
    c = count_words(sample_file)
    result = top_n(c, 2)
    assert result[0] == ("apple", 3)
    assert result[1] == ("banana", 2)


def test_top_n_larger_than_vocab(sample_file: Path) -> None:
    c = count_words(sample_file)
    result = top_n(c, 100)
    assert len(result) == 3  # 단어 종류: apple, banana, cherry


def test_top_n_zero(sample_file: Path) -> None:
    c = count_words(sample_file)
    assert top_n(c, 0) == []


# ── main (CLI) ────────────────────────────────────────────────────────────────


def test_cli_default_top10(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "long.txt"
    # 15 가지 단어, 각 1회
    words = " ".join(f"word{i}" for i in range(15))
    p.write_text(words, encoding="utf-8")
    rc = main([str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.strip() and not l.startswith("-") and "빈도" not in l]
    assert len(lines) == 10


def test_cli_custom_n(sample_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([str(sample_file), "-n", "2"])
    assert rc == 0
    out = capsys.readouterr().out
    data_lines = [l for l in out.splitlines() if l.strip() and not l.startswith("-") and "빈도" not in l]
    assert len(data_lines) == 2


def test_cli_file_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["/no/such/file.txt"])
    assert rc == 1
    assert "오류" in capsys.readouterr().err


def test_cli_empty_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")
    rc = main([str(p)])
    assert rc == 1
    assert "오류" in capsys.readouterr().err
