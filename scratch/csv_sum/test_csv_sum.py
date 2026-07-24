from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from csv_sum import main, sum_column

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Happy-path tests using fixture files
# ---------------------------------------------------------------------------


def test_sum_amount_sales():
    result = sum_column(FIXTURES / "sales.csv", "amount")
    assert result == pytest.approx(1.5 + 2.0 + 3.5 + 0.75)


def test_sum_quantity_sales():
    result = sum_column(FIXTURES / "sales.csv", "quantity")
    assert result == pytest.approx(10 + 5 + 8 + 20)


def test_sum_math_scores():
    result = sum_column(FIXTURES / "scores.csv", "math")
    assert result == pytest.approx(88 + 76 + 95 + 60)


def test_sum_science_scores():
    result = sum_column(FIXTURES / "scores.csv", "science")
    assert result == pytest.approx(92 + 84 + 70 + 78)


# ---------------------------------------------------------------------------
# CLI integration via main()
# ---------------------------------------------------------------------------


def test_cli_prints_result(tmp_path, capsys):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("x,y\n1.0,2.0\n3.0,4.0\n")
    main([str(csv_file), "--column", "x"])
    out = capsys.readouterr().out
    assert float(out.strip()) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_empty_file(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("")
    with pytest.raises(SystemExit, match="empty"):
        sum_column(f, "col")


def test_whitespace_only_file(tmp_path):
    f = tmp_path / "ws.csv"
    f.write_text("   \n  \n")
    with pytest.raises(SystemExit, match="empty"):
        sum_column(f, "col")


def test_missing_column(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n")
    with pytest.raises(SystemExit, match="not found"):
        sum_column(f, "z")


def test_missing_column_error_lists_available(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("foo,bar\n1,2\n")
    with pytest.raises(SystemExit) as exc_info:
        sum_column(f, "baz")
    assert "foo" in str(exc_info.value)
    assert "bar" in str(exc_info.value)


def test_non_numeric_value(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("val\n1\nnot_a_number\n3\n")
    with pytest.raises(SystemExit, match="non-numeric"):
        sum_column(f, "val")


def test_blank_lines_skipped(tmp_path):
    """Python csv.DictReader skips blank lines (row == []) internally.
    So a blank line in the middle of data is silently ignored."""
    f = tmp_path / "data.csv"
    f.write_text("val\n1\n\n3\n")
    # blank line is skipped; sum is 1 + 3 = 4
    assert sum_column(f, "val") == pytest.approx(4.0)


def test_header_only_no_data_rows(tmp_path):
    """A file with only a header row should return 0.0 (no rows to sum)."""
    f = tmp_path / "header_only.csv"
    f.write_text("a,b,c\n")
    result = sum_column(f, "a")
    assert result == pytest.approx(0.0)


def test_single_row(tmp_path):
    f = tmp_path / "single.csv"
    f.write_text("score\n42.5\n")
    assert sum_column(f, "score") == pytest.approx(42.5)


def test_negative_values(tmp_path):
    f = tmp_path / "neg.csv"
    f.write_text("delta\n-10\n5\n-3\n")
    assert sum_column(f, "delta") == pytest.approx(-8.0)


def test_float_precision(tmp_path):
    f = tmp_path / "floats.csv"
    f.write_text("v\n0.1\n0.2\n")
    assert sum_column(f, "v") == pytest.approx(0.3)
