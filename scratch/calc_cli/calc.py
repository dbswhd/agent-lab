"""Simple CLI calculator — add, subtract, multiply, divide."""

from __future__ import annotations

import argparse
import math
import sys


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    return a * b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b


OPERATIONS: dict[str, callable] = {
    "add": add,
    "sub": subtract,
    "mul": multiply,
    "div": divide,
}


def calculate(op: str, a: float, b: float) -> float:
    if op not in OPERATIONS:
        raise ValueError(f"Unknown operation '{op}'. Choose from: {', '.join(OPERATIONS)}")
    return OPERATIONS[op](a, b)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="calc",
        description="Simple CLI calculator",
    )
    parser.add_argument("op", choices=list(OPERATIONS), help="Operation: add sub mul div")
    parser.add_argument("a", type=float, help="First number")
    parser.add_argument("b", type=float, help="Second number")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        result = calculate(args.op, args.a, args.b)
        # Print integer form when result is a finite whole number
        if math.isfinite(result) and result == int(result):
            print(int(result))
        else:
            print(result)
        return 0
    except ZeroDivisionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (ValueError, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
