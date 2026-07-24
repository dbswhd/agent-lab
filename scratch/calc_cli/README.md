# calc_cli

사칙연산 CLI 계산기.

## 사용법

```bash
python calc.py <op> <a> <b>
```

| op  | 연산 |
|-----|------|
| add | 덧셈 |
| sub | 뺄셈 |
| mul | 곱셈 |
| div | 나눗셈 |

```bash
python calc.py add 3 4    # → 7
python calc.py div 10 4   # → 2.5
python calc.py div 5 0    # → Error: Cannot divide by zero (exit 1)
```

잘못된 입력으로 다루는 것은 **0으로 나누기·비숫자·알 수 없는 op**입니다. `nan`/`inf` 문자열은 argparse `float`이 그대로 받아 IEEE 연산 결과(`nan`/`inf`)를 출력하며, 별도 거부는 **범위 외(OOS)** 입니다.

## 테스트

```bash
pytest test_calc.py -v
```
