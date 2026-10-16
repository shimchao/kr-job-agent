#!/usr/bin/env python3
"""급여 환산·비교와 평가 점수 계산 — AI 가 암산하지 않도록 계산은 여기서 한다.

실행 예:
  python3 scripts/calc.py annual 350 700            # 월급(만원) → 연봉(만원), 12개월 기준
  python3 scripts/calc.py hourly 시급원 [월시간=209]   # 시급(원) → 월 환산(원). 최저임금 금액은 공식 고시를 확인해 직접 넣는다
  python3 scripts/calc.py compare 8400 7000          # A 와 B 의 크기를 말로 출력 (방향 실수 방지)
  python3 scripts/calc.py score 매치=2 직무=1 보상=1 문화=2 위험=1

score: 가중치 매치 35% · 직무 15% · 보상 20% · 문화·공고신뢰 20% · 위험 10%, 각 1~5. 소수 둘째 자리는 반올림(0.05 는 올림).
하지 않는 것: 세금·4대 보험 공제 계산(세후 실수령액은 추정하지 않는다).
"""
import sys
from decimal import ROUND_HALF_UP, Decimal

W = {"매치": Decimal("0.35"), "직무": Decimal("0.15"), "보상": Decimal("0.20"), "문화": Decimal("0.20"), "위험": Decimal("0.10")}


def fmt(n):
    return f"{n:,}" if isinstance(n, int) else f"{n:,.1f}"


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
    try:
        if cmd == "annual":
            for m in a[1:]:
                v = Decimal(m.replace(",", ""))
                print(f"월 {fmt(int(v))}만원 × 12 = 연 {fmt(int(v * 12))}만원 (세전, 12개월 기준 · 상여·성과급 제외)")
        elif cmd == "hourly":
            h = Decimal(a[1].replace(",", ""))
            hours = Decimal(a[2]) if len(a) > 2 else Decimal(209)
            print(f"시급 {fmt(int(h))}원 × {hours}시간 = 월 {fmt(int(h * hours))}원 (세전)")
        elif cmd == "compare":
            x, y = Decimal(a[1].replace(",", "")), Decimal(a[2].replace(",", ""))
            rel = "보다 큼" if x > y else ("보다 작음" if x < y else "과 같음")
            print(f"{fmt(int(x))} 은(는) {fmt(int(y))}{rel} (차이 {fmt(int(abs(x - y)))})")
        elif cmd == "score":
            vals = dict(p.split("=") for p in a[1:])
            if set(vals) != set(W):
                sys.exit(f"다섯 차원을 모두 주세요: {', '.join(W)}")
            total, terms = Decimal(0), []
            for k in W:
                v = Decimal(vals[k])
                if not (1 <= v <= 5):
                    sys.exit(f"{k} 점수는 1~5 사이여야 합니다")
                total += v * W[k]
                terms.append(f"{v}×{W[k]}")
            print(f"{' + '.join(terms)} = {total} → {total.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}")
        else:
            sys.exit(__doc__)
    except (ValueError, IndexError, ArithmeticError):
        sys.exit("입력 형식을 확인하세요.\n\n" + __doc__)


if __name__ == "__main__":
    main()
