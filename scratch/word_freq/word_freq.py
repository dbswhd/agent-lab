from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path


def count_words(path: Path) -> Counter[str]:
    """파일을 읽어 공백 기준 토큰화, 소문자 정규화 후 빈도 Counter 반환."""
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    text = path.read_text(encoding="utf-8")
    tokens = text.lower().split()
    if not tokens:
        raise ValueError(f"파일이 비어 있습니다: {path}")
    return Counter(tokens)


def top_n(counter: Counter[str], n: int) -> list[tuple[str, int]]:
    return counter.most_common(n)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="텍스트 파일 단어 빈도 분석")
    parser.add_argument("file", help="분석할 텍스트 파일 경로")
    parser.add_argument(
        "-n",
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="상위 N개 출력 (기본: 10)",
    )
    args = parser.parse_args(argv)

    try:
        counter = count_words(Path(args.file))
    except FileNotFoundError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1

    results = top_n(counter, args.top)
    width = max((len(w) for w, _ in results), default=4)
    print(f"{'단어':<{width}}  빈도")
    print("-" * (width + 6))
    for word, freq in results:
        print(f"{word:<{width}}  {freq}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
