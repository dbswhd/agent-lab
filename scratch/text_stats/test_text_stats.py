"""Tests for text_stats.py."""

from __future__ import annotations

from pathlib import Path

from text_stats import count_stats, main


class TestCountStats:
    def test_simple_text(self):
        text = "hello world\n"
        assert count_stats(text) == (1, 2, 12)

    def test_mixed_whitespace(self):
        text = "one\ttwo  three\nfour"
        assert count_stats(text) == (2, 4, 19)

    def test_newlines_in_characters(self):
        text = "a\nb\nc\n"
        lines, words, characters = count_stats(text)
        assert lines == 3
        assert words == 3
        assert characters == 6  # includes three newlines

    def test_empty_file(self):
        assert count_stats("") == (0, 0, 0)

    def test_no_trailing_newline(self):
        text = "only one line"
        assert count_stats(text) == (1, 3, 13)

    def test_unicode(self):
        text = "안녕 세계\n"
        lines, words, characters = count_stats(text)
        assert lines == 1
        assert words == 2
        assert characters == len(text)


class TestCLI:
    def test_normal_file(self, tmp_path: Path, capsys):
        path = tmp_path / "sample.txt"
        path.write_text("hello world\nfoo bar\n", encoding="utf-8")
        rc = main([str(path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Lines: 2" in out
        assert "Words: 4" in out
        assert "Characters: 20" in out

    def test_empty_file_cli(self, tmp_path: Path, capsys):
        path = tmp_path / "empty.txt"
        path.write_text("", encoding="utf-8")
        rc = main([str(path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Lines: 0" in out
        assert "Words: 0" in out
        assert "Characters: 0" in out

    def test_missing_file(self, tmp_path: Path, capsys):
        missing = tmp_path / "no_such_file.txt"
        rc = main([str(missing)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "file not found" in err.lower() or "Error" in err

    def test_directory_path(self, tmp_path: Path, capsys):
        rc = main([str(tmp_path)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "Error" in err
