from __future__ import annotations

"""pytest tests for scratch/line_stats/cli.py"""

import sys
from pathlib import Path

import pytest

# Make the module importable without installation
sys.path.insert(0, str(Path(__file__).parent))

from cli import count_file, run  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# count_file unit tests
# ---------------------------------------------------------------------------


def test_count_file_sample_a():
    lines, chars = count_file(FIXTURES / "sample_a.txt")
    assert lines == 3
    # "Hello, world!\nThis is a sample text file.\nIt has three lines.\n"
    assert chars > 0


def test_count_file_sample_b():
    lines, chars = count_file(FIXTURES / "sample_b.txt")
    assert lines == 5
    assert chars > 0


def test_count_file_sample_c():
    lines, chars = count_file(FIXTURES / "sample_c.txt")
    # file has 4 lines (including blank line)
    assert lines == 4
    assert chars > 0


def test_count_file_char_count_exact(tmp_path):
    f = tmp_path / "exact.txt"
    f.write_text("ab\ncd\n", encoding="utf-8")
    lines, chars = count_file(f)
    assert lines == 2
    assert chars == 6  # 'a','b','\n','c','d','\n'


def test_count_file_single_line_no_newline(tmp_path):
    f = tmp_path / "no_newline.txt"
    f.write_text("hello", encoding="utf-8")
    lines, chars = count_file(f)
    assert lines == 1
    assert chars == 5


def test_count_file_empty(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    lines, chars = count_file(f)
    assert lines == 0
    assert chars == 0


# ---------------------------------------------------------------------------
# run() integration / output tests
# ---------------------------------------------------------------------------


def test_run_single_file(capsys):
    run([FIXTURES / "sample_a.txt"])
    out = capsys.readouterr().out
    assert "sample_a.txt" in out
    assert "TOTAL" in out


def test_run_multiple_files(capsys):
    run([FIXTURES / "sample_a.txt", FIXTURES / "sample_b.txt"])
    out = capsys.readouterr().out
    assert "sample_a.txt" in out
    assert "sample_b.txt" in out
    assert "TOTAL" in out


def test_run_totals_match(tmp_path):
    """TOTAL line count equals sum of individual file counts."""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("line1\nline2\n", encoding="utf-8")
    b.write_text("x\ny\nz\n", encoding="utf-8")

    lines_a, _ = count_file(a)
    lines_b, _ = count_file(b)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run([a, b])

    output = buf.getvalue()
    total_line = [l for l in output.splitlines() if l.startswith("TOTAL")][0]
    reported_total = int(total_line.split()[1])
    assert reported_total == lines_a + lines_b


def test_run_missing_file_warns(tmp_path, capsys):
    real = tmp_path / "real.txt"
    real.write_text("hello\n", encoding="utf-8")
    run([real, Path("/nonexistent/path/ghost.txt")])
    err = capsys.readouterr().err
    assert "ghost.txt" in err


def test_run_no_valid_files_exits(tmp_path):
    with pytest.raises(SystemExit):
        run([Path("/no/such/file.txt")])


def test_run_no_files_exits():
    with pytest.raises(SystemExit):
        run([])


# ---------------------------------------------------------------------------
# CLI entry point (main)
# ---------------------------------------------------------------------------


def test_main_cli(capsys):
    from cli import main

    main([str(FIXTURES / "sample_a.txt"), str(FIXTURES / "sample_b.txt")])
    out = capsys.readouterr().out
    assert "TOTAL" in out
    assert "sample_a" in out
    assert "sample_b" in out
