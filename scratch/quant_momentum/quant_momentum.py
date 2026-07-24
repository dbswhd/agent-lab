"""Momentum stock screener + monthly equal-weight backtest CLI (offline CSV)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")


class DataError(ValueError):
    """User-facing data validation error."""


@dataclass(frozen=True)
class ScreenHit:
    symbol: str
    momentum: float


@dataclass(frozen=True)
class BacktestResult:
    cumulative_return: float
    mdd: float
    win_rate: float
    n_periods: int
    period_returns: list[float]


def load_ohlcv(path: Path) -> pd.DataFrame:
    """Load one OHLCV CSV. Raises DataError on empty / missing columns."""
    if not path.is_file():
        raise DataError(f"CSV not found: {path}")

    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise DataError(f"Empty CSV: {path}") from exc

    if df.empty:
        raise DataError(f"Empty CSV: {path}")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataError(
            f"Missing required columns in {path.name}: {', '.join(missing)} "
            f"(need: {', '.join(REQUIRED_COLUMNS)})"
        )

    out = df.loc[:, list(REQUIRED_COLUMNS)].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    if out["date"].isna().any():
        raise DataError(f"Invalid date values in {path.name}")
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if out["close"].isna().any():
        raise DataError(f"Invalid close values in {path.name}")

    out = out.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    out = out.reset_index(drop=True)
    return out


def load_universe(data_dir: Path) -> dict[str, pd.DataFrame]:
    """Load all *.csv under data_dir. Hard-fail on empty / missing columns."""
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise DataError(f"Data directory not found: {data_dir}")

    paths = sorted(data_dir.glob("*.csv"))
    if not paths:
        raise DataError(f"No CSV files in {data_dir}")

    universe: dict[str, pd.DataFrame] = {}
    for path in paths:
        universe[path.stem] = load_ohlcv(path)
    return universe


def momentum_at(df: pd.DataFrame, as_of: pd.Timestamp, lookback: int) -> float | None:
    """
    Trading-day momentum: close[as_of] / close[as_of - lookback] - 1.

    Needs lookback+1 rows on or before as_of (Claude edge-case #1).
    Returns None if insufficient history.
    """
    if lookback < 1:
        raise ValueError("lookback N must be >= 1")

    hist = df.loc[df["date"] <= as_of]
    if len(hist) < lookback + 1:
        return None

    closes = hist["close"].to_numpy()
    return float(closes[-1] / closes[-(lookback + 1)] - 1.0)


def screen(
    universe: dict[str, pd.DataFrame],
    *,
    lookback: int = 20,
    threshold: float = 0.05,
    top_k: int = 5,
    as_of: pd.Timestamp | None = None,
) -> list[ScreenHit]:
    """Select top-K symbols by momentum descending, threshold filter."""
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    if as_of is None:
        as_of = max(df["date"].max() for df in universe.values())

    hits: list[ScreenHit] = []
    for symbol, df in universe.items():
        mom = momentum_at(df, as_of, lookback)
        if mom is None:
            continue
        if mom >= threshold:
            hits.append(ScreenHit(symbol=symbol, momentum=mom))

    hits.sort(key=lambda h: h.momentum, reverse=True)
    return hits[:top_k]


def month_end_trading_days(all_dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Last trading day of each calendar month (year-month aware)."""
    if len(all_dates) == 0:
        return []
    s = pd.Series(all_dates, index=all_dates)
    # period 'M' keeps year+month — avoids Jan'21 / Jan'22 collision (Claude #3)
    grouped = s.groupby(s.index.to_period("M")).max()
    return [pd.Timestamp(ts) for ts in grouped.tolist()]


def period_equal_weight_return(
    universe: dict[str, pd.DataFrame],
    symbols: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> float:
    """
    Equal-weight period return = arithmetic mean of per-symbol simple returns.
    Fractional shares not modeled. Missing price at either end → that symbol skipped.
    Empty symbols → 0.0 (flat / cash month; included in win-rate denom).
    """
    if not symbols:
        return 0.0

    rets: list[float] = []
    for symbol in symbols:
        df = universe[symbol]
        start_rows = df.loc[df["date"] == start, "close"]
        end_rows = df.loc[df["date"] == end, "close"]
        if start_rows.empty or end_rows.empty:
            continue
        p0 = float(start_rows.iloc[0])
        p1 = float(end_rows.iloc[0])
        if p0 == 0:
            continue
        rets.append(p1 / p0 - 1.0)

    if not rets:
        return 0.0
    return float(sum(rets) / len(rets))


def max_drawdown(nav: list[float]) -> float:
    """MDD from rebalance-point NAV series (peak-to-trough)."""
    if not nav:
        return 0.0
    peak = nav[0]
    mdd = 0.0
    for v in nav:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > mdd:
                mdd = dd
    return float(mdd)


def backtest(
    universe: dict[str, pd.DataFrame],
    *,
    lookback: int = 20,
    threshold: float = 0.05,
    top_k: int = 5,
) -> BacktestResult:
    """
    Monthly last-trading-day rebalance, equal-weight mean returns,
    MDD on rebalance NAV, win rate = P(period_return > 0).
    Empty screen months contribute 0.0 and count in the denominator.
    """
    all_dates = pd.DatetimeIndex(
        sorted({d for df in universe.values() for d in df["date"].tolist()})
    )
    rebalance_days = month_end_trading_days(all_dates)
    if len(rebalance_days) < 2:
        raise DataError(
            "Need at least two month-end trading days to run a backtest "
            f"(found {len(rebalance_days)})"
        )

    period_returns: list[float] = []
    for i in range(len(rebalance_days) - 1):
        start = rebalance_days[i]
        end = rebalance_days[i + 1]
        picks = screen(
            universe,
            lookback=lookback,
            threshold=threshold,
            top_k=top_k,
            as_of=start,
        )
        symbols = [h.symbol for h in picks]
        period_returns.append(
            period_equal_weight_return(universe, symbols, start, end)
        )

    nav = [1.0]
    for r in period_returns:
        nav.append(nav[-1] * (1.0 + r))

    cumulative = nav[-1] - 1.0
    mdd = max_drawdown(nav)
    wins = sum(1 for r in period_returns if r > 0)
    win_rate = wins / len(period_returns) if period_returns else 0.0

    return BacktestResult(
        cumulative_return=float(cumulative),
        mdd=float(mdd),
        win_rate=float(win_rate),
        n_periods=len(period_returns),
        period_returns=period_returns,
    )


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="quant_momentum",
        description="Momentum screener + monthly equal-weight backtest (offline CSV)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data",
        help="Directory of per-symbol OHLCV CSVs (default: ./data)",
    )
    parser.add_argument("-n", "--lookback", type=int, default=20, help="Momentum lookback trading days")
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=0.05,
        help="Minimum momentum (e.g. 0.05 = 5%%)",
    )
    parser.add_argument("-k", "--top-k", type=int, default=5, help="Top-K names to hold")
    parser.add_argument(
        "command",
        choices=("screen", "backtest"),
        help="screen: print latest picks; backtest: run monthly rebalance metrics",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.lookback < 1:
            raise DataError("lookback N must be >= 1")
        if args.top_k < 1:
            raise DataError("top-k must be >= 1")

        universe = load_universe(args.data_dir)

        if args.command == "screen":
            hits = screen(
                universe,
                lookback=args.lookback,
                threshold=args.threshold,
                top_k=args.top_k,
            )
            if not hits:
                print(
                    f"No symbols passed threshold {_fmt_pct(args.threshold)} "
                    f"with lookback={args.lookback} (need >= {args.lookback + 1} trading days each)."
                )
                return 0
            print(f"{'symbol':<12} {'momentum':>10}")
            for h in hits:
                print(f"{h.symbol:<12} {_fmt_pct(h.momentum):>10}")
            return 0

        result = backtest(
            universe,
            lookback=args.lookback,
            threshold=args.threshold,
            top_k=args.top_k,
        )
        print("Backtest (monthly last trading day, equal-weight mean returns)")
        print(f"  periods           : {result.n_periods}")
        print(f"  cumulative return : {_fmt_pct(result.cumulative_return)}")
        print(f"  MDD               : {_fmt_pct(result.mdd)}")
        print(f"  win rate          : {_fmt_pct(result.win_rate)}")
        return 0

    except DataError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (ValueError, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
