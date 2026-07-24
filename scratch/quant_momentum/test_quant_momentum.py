"""Unit tests for quant_momentum screener + backtest."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quant_momentum import (
    DataError,
    backtest,
    load_ohlcv,
    load_universe,
    main,
    max_drawdown,
    month_end_trading_days,
    momentum_at,
    period_equal_weight_return,
    screen,
)

FIX_DIR = Path(__file__).resolve().parent / "data"


def _make_ohlcv(dates: list[str], closes: list[float], path: Path) -> Path:
    rows = []
    for d, c in zip(dates, closes, strict=True):
        rows.append(
            {
                "date": d,
                "open": c,
                "high": c,
                "low": c,
                "close": c,
                "volume": 1000,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


class TestLoadErrors:
    def test_empty_csv(self, tmp_path: Path):
        p = tmp_path / "EMPTY.csv"
        p.write_text("")
        with pytest.raises(DataError, match="Empty CSV"):
            load_ohlcv(p)

    def test_header_only_csv(self, tmp_path: Path):
        p = tmp_path / "HDR.csv"
        p.write_text("date,open,high,low,close,volume\n")
        with pytest.raises(DataError, match="Empty CSV"):
            load_ohlcv(p)

    def test_missing_columns(self, tmp_path: Path):
        p = tmp_path / "BAD.csv"
        p.write_text("date,close\n2021-01-04,10\n")
        with pytest.raises(DataError, match="Missing required columns"):
            load_ohlcv(p)


class TestMomentumAndScreen:
    def test_needs_n_plus_one_rows(self, tmp_path: Path):
        """Claude #1: lookback N requires N+1 trading days."""
        dates = [f"2021-01-{d:02d}" for d in range(4, 14)]  # 10 calendar weekdays-ish
        # Use explicit business-like sequence of 10 rows
        dates = pd.bdate_range("2021-01-04", periods=10).strftime("%Y-%m-%d").tolist()
        closes = [100 + i for i in range(10)]
        path = _make_ohlcv(dates, closes, tmp_path / "X.csv")
        df = load_ohlcv(path)
        as_of = df["date"].iloc[-1]

        assert momentum_at(df, as_of, lookback=9) is not None  # 10 rows = 9+1
        assert momentum_at(df, as_of, lookback=10) is None  # needs 11

        # Exact formula: close[-1]/close[-(N+1)] - 1
        mom = momentum_at(df, as_of, lookback=5)
        assert mom == pytest.approx(closes[-1] / closes[-(5 + 1)] - 1)

    def test_screen_threshold_and_topk(self, tmp_path: Path):
        dates = pd.bdate_range("2021-01-04", periods=30).strftime("%Y-%m-%d").tolist()
        # UP: strong rise in last 20 days; FLAT: flat; DOWN: fall
        up = [100.0] * 10 + [100.0 + i for i in range(1, 21)]  # last = 120
        flat = [50.0] * 30
        down = [80.0] * 10 + [80.0 - i for i in range(1, 21)]  # last = 60

        universe = {
            "UP": load_ohlcv(_make_ohlcv(dates, up, tmp_path / "UP.csv")),
            "FLAT": load_ohlcv(_make_ohlcv(dates, flat, tmp_path / "FLAT.csv")),
            "DOWN": load_ohlcv(_make_ohlcv(dates, down, tmp_path / "DOWN.csv")),
        }
        hits = screen(universe, lookback=20, threshold=0.05, top_k=5)
        symbols = [h.symbol for h in hits]
        assert "UP" in symbols
        assert "DOWN" not in symbols
        assert "FLAT" not in symbols
        assert hits[0].symbol == "UP"

    def test_screen_skips_short_history(self, tmp_path: Path):
        long_dates = pd.bdate_range("2021-01-04", periods=25).strftime("%Y-%m-%d").tolist()
        short_dates = pd.bdate_range("2021-01-04", periods=5).strftime("%Y-%m-%d").tolist()
        universe = {
            "LONG": load_ohlcv(
                _make_ohlcv(long_dates, [100 + i for i in range(25)], tmp_path / "LONG.csv")
            ),
            "SHORT": load_ohlcv(
                _make_ohlcv(short_dates, [10 + i for i in range(5)], tmp_path / "SHORT.csv")
            ),
        }
        hits = screen(universe, lookback=20, threshold=-1.0, top_k=5)
        assert [h.symbol for h in hits] == ["LONG"]


class TestMonthEndsAndBacktest:
    def test_month_end_keeps_year(self):
        """Claude #3: Jan 2021 and Jan 2022 must be distinct month-ends."""
        dates = pd.DatetimeIndex(
            ["2021-01-29", "2021-02-26", "2022-01-31", "2022-02-28"]
        )
        ends = month_end_trading_days(dates)
        assert ends == [
            pd.Timestamp("2021-01-29"),
            pd.Timestamp("2021-02-26"),
            pd.Timestamp("2022-01-31"),
            pd.Timestamp("2022-02-28"),
        ]

    def test_empty_portfolio_month_is_zero_and_counts(self, tmp_path: Path):
        """Claude #2: no names above threshold → period return 0, in win-rate denom."""
        dates = pd.bdate_range("2021-01-04", "2021-06-30")
        # Strictly declining → momentum always negative → empty picks every month
        closes = [200.0 - i * 0.5 for i in range(len(dates))]
        path = _make_ohlcv(
            dates.strftime("%Y-%m-%d").tolist(), closes, tmp_path / "DOWN.csv"
        )
        universe = {"DOWN": load_ohlcv(path)}
        result = backtest(universe, lookback=5, threshold=0.50, top_k=3)
        assert result.n_periods >= 1
        assert all(r == 0.0 for r in result.period_returns)
        assert result.cumulative_return == pytest.approx(0.0)
        assert result.win_rate == pytest.approx(0.0)

    def test_equal_weight_mean_return(self, tmp_path: Path):
        dates = ["2021-01-29", "2021-02-26"]
        a = load_ohlcv(_make_ohlcv(dates, [100.0, 110.0], tmp_path / "A.csv"))  # +10%
        b = load_ohlcv(_make_ohlcv(dates, [200.0, 200.0], tmp_path / "B.csv"))  # 0%
        r = period_equal_weight_return(
            {"A": a, "B": b},
            ["A", "B"],
            pd.Timestamp("2021-01-29"),
            pd.Timestamp("2021-02-26"),
        )
        assert r == pytest.approx(0.05)

    def test_mdd_from_nav(self):
        assert max_drawdown([1.0, 1.2, 0.9, 1.0]) == pytest.approx((1.2 - 0.9) / 1.2)

    def test_backtest_on_fixture_universe(self):
        universe = load_universe(FIX_DIR)
        assert set(universe) >= {"AAA", "BBB", "CCC", "DDD", "EEE"}
        # Fixture spans 2021-2022 so year-month grouping is exercised
        years = {d.year for df in universe.values() for d in df["date"]}
        assert 2021 in years and 2022 in years

        result = backtest(universe, lookback=20, threshold=0.05, top_k=3)
        assert result.n_periods >= 12  # ~23 months of data → many periods
        assert -1.0 < result.cumulative_return < 10.0
        assert 0.0 <= result.mdd <= 1.0
        assert 0.0 <= result.win_rate <= 1.0


class TestCLI:
    def test_screen_cli(self, capsys):
        rc = main(
            [
                "--data-dir",
                str(FIX_DIR),
                "-n",
                "20",
                "-t",
                "0.0",
                "-k",
                "3",
                "screen",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "symbol" in out
        assert "AAA" in out or "BBB" in out

    def test_backtest_cli(self, capsys):
        rc = main(["--data-dir", str(FIX_DIR), "backtest"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "cumulative return" in out
        assert "MDD" in out
        assert "win rate" in out

    def test_missing_column_cli(self, tmp_path: Path, capsys):
        bad = tmp_path / "BAD.csv"
        bad.write_text("date,close\n2021-01-04,1\n")
        rc = main(["--data-dir", str(tmp_path), "screen"])
        assert rc == 1
        assert "Missing required columns" in capsys.readouterr().err

    def test_empty_csv_cli(self, tmp_path: Path, capsys):
        (tmp_path / "EMPTY.csv").write_text("")
        rc = main(["--data-dir", str(tmp_path), "screen"])
        assert rc == 1
        assert "Empty CSV" in capsys.readouterr().err
