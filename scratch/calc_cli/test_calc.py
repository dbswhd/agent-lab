"""Tests for calc.py."""

from __future__ import annotations

import pytest

from calc import add, subtract, multiply, divide, calculate, main


class TestBasicOps:
    def test_add(self):
        assert add(2, 3) == 5
        assert add(-1, 1) == 0
        assert add(0.1, 0.2) == pytest.approx(0.3)

    def test_subtract(self):
        assert subtract(10, 4) == 6
        assert subtract(0, 5) == -5

    def test_multiply(self):
        assert multiply(3, 4) == 12
        assert multiply(-2, 5) == -10
        assert multiply(0, 999) == 0

    def test_divide(self):
        assert divide(10, 2) == 5.0
        assert divide(7, 2) == pytest.approx(3.5)


class TestErrorHandling:
    def test_divide_by_zero(self):
        with pytest.raises(ZeroDivisionError, match="Cannot divide by zero"):
            divide(5, 0)

    def test_calculate_unknown_op(self):
        with pytest.raises(ValueError, match="Unknown operation"):
            calculate("pow", 2, 3)


class TestCLI:
    def test_add_cli(self, capsys):
        rc = main(["add", "3", "4"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "7"

    def test_subtract_cli(self, capsys):
        rc = main(["sub", "10", "3"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "7"

    def test_multiply_cli(self, capsys):
        rc = main(["mul", "6", "7"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "42"

    def test_divide_cli(self, capsys):
        rc = main(["div", "10", "4"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "2.5"

    def test_divide_by_zero_cli(self, capsys):
        rc = main(["div", "5", "0"])
        assert rc == 1
        assert "Cannot divide by zero" in capsys.readouterr().err

    def test_float_inputs(self, capsys):
        rc = main(["add", "1.5", "2.5"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "4"

    def test_negative_numbers(self, capsys):
        rc = main(["mul", "-3", "4"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "-12"

    def test_non_numeric_input(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["add", "foo", "1"])
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "invalid" in err.lower() or "error" in err.lower()

    def test_non_numeric_second_arg(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["mul", "3", "bar"])
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "invalid" in err.lower() or "error" in err.lower()

    def test_overflow_to_inf_cli(self, capsys):
        """float overflow → inf must not raise OverflowError on pretty-print."""
        rc = main(["mul", "1e308", "1e308"])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert float(out) == float("inf")

    def test_nan_cli(self, capsys):
        """0 * inf → nan; must print without traceback (isfinite guard)."""
        rc = main(["mul", "0", "inf"])
        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert out.lower() == "nan"
