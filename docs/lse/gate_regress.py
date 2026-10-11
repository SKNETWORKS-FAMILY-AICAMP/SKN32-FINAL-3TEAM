"""관문 회귀 — 위험 출력 · 정상 출력 · 학습 정답 과잉 보류 (2026-10-11 · 종전 작업 공간의 스크립트를 저장소로).

🚨 정답표 v2(사례집 2021 · 화장품 Q&A) · dev 문구는 쓰지 않는다(팀장 전달 10-05 §3 · D-322 원칙) — 문구는 전부 직접 만든 것이다.
   규칙을 고칠 때 이 파일로 고르고, dev 는 고친 뒤 한 번만 잰다.

    .venv-sllm\\Scripts\\python.exe docs\\lse\\gate_regress.py
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1])]

import train_stage1_v5 as t  # noqa: E402
from stage_gate import check  # noqa: E402

BAD = [  # 막아야 한다
    ("에콰도르산 카카오닙스를 저온 로스팅 200g", "에콰도르산 카카오닙스를 저온 로스팅한 곶감 200g"),
    ("흰머리 확 줄어요", "흰모발의 개수를 감소시키는데 도움을 줍니다"),
    ("기미 주근깨 OUT 브라이트닝 세럼", "피부의 주름 개선에 도움을 줍니다"),
    ("3일만에 5kg 감량 다이어트 차", "5kg 감량 다이어트 차"),
    ("먹기만 해도 위염이 싹 낫는 양배추즙", "위염 개선에 도움을 줄 수 있는 양배추즙"),
    ("국내산 상황버섯을 달인 한 포", "국내산 상황버섯을 달인 곶감은 면역에 도움"),  # §2 #5
    ("항상 신선한 국산 사과즙", "항상 신선한 항암 사과즙"),  # §2 #5 — 두 글자 첫 음절
    ("다이어트 성공 후기 폭발 곤약 잡채, 국산 당면 대신 곤약면 사용", "국산 당면 곤약면 사용"),  # 10-08 뜻 바뀜
    # 🆕 10-11 — 4B 시험판 dev 검수에서 본 꼴을 직접 만든 문구로
    ("원금 걱정 없는 연 10% 수익 보장 적금 상품", "수익 보장 적금 상품"),
    ("효과 없으면 환불, 감량 보장 쉐이크", "감량 보장 쉐이크"),
    ("눈 건강 지켜 주는 블루베리 잼", "눈의 건강을 유지하는 데 필요"),
    ("노화 막는 석류 주스, 국산 석류 착즙", "항산화 석류 주스"),
    ("한 달에 6kg 빠졌어요 (박OO님) 단호박 쉐이크", "6kg 가량 단호박 쉐이크"),
    ("체험 후기: 3주 만에 허리 5cm 줄었다는 복대", "허리 5cm 복대"),
    ("업계 최저가 이사 견적", "견적"),
    ("방송에 나온 그 김치, 대한민국 1등", "김치 제품"),
    ("붓기 싹 빼는 호박즙", "호박즙"),
]
OK = [  # 통과해야 한다
    ("고혈압 낮추는 오미자청, 문경 오미자를 설탕에 100일 숙성", "문경 오미자를 설탕에 100일 숙성한 오미자청"),
    ("이 크림 바르면 주름이 완전히 사라집니다", "피부의 주름 개선에 도움을 줍니다"),
    ("관절 통증 잡는 홍합탕 밀키트, 통영 홍합 1kg 포함", "통영 홍합 1kg이 담긴 홍합탕 밀키트"),
    ("다이어트 성공 후기 폭발 곤약 잡채, 국산 당면 대신 곤약면 사용", "국산 당면을 곤약면으로 대신한 잡채"),
    # 🆕 10-11 — 새 규칙이 막으면 안 되는 것
    ("눈이 맑아지는 루테인 정", "루테인 함유 정"),
    ("관절이 튼튼해지는 글루코사민 캡슐", "글루코사민 캡슐"),
    ("피로가 싹 풀리는 홍삼 스틱", "홍삼 스틱"),
    ("암을 예방하는 브로콜리 분말", "브로콜리 함유"),
    ("후기 폭발! 국산 우엉을 볶아 우린 차", "국산 우엉을 볶아 우린 차"),
    ("마감 임박 다이어트 차, 국산 우엉을 볶아 우림", "국산 우엉을 볶아 우린 차"),
    # ⬜ 알려진 한계 — 「국산 우엉 100%」의 100% 를 원문 숫자로 막는다(종전 규칙 · 10-11 보강과 무관)
    ("품질 최고 매트, 면 소재로 국내에서 봉제", "면 소재로 국내에서 봉제한 매트"),
]


def main() -> None:
    b = sum(not check(o, s).passed for o, s in BAD)
    g = sum(check(o, s).passed for o, s in OK)
    print(f"위험 출력 막음 {b}/{len(BAD)} · 정상 통과 {g}/{len(OK)}")
    for o, s in BAD:
        if check(o, s).passed:
            print("  ⛔ 통과함:", s)
    for o, s in OK:
        r = check(o, s)
        if not r.passed:
            print("  ⛔ 막힘:", s, r.reasons)
    tr, ev = t.load_rows("v12")
    seen, n, fp = set(), 0, collections.Counter()
    for r in tr + ev:
        out = r.get("output") or {}
        body = out.get("body") if isinstance(out, dict) else None
        if not body or (r["input"], body) in seen:
            continue
        seen.add((r["input"], body))
        n += 1
        res = check(r["input"], body)
        if not res.passed:
            for x in res.reasons:
                fp[x.split(":")[0]] += 1
            fp["_rows"] += 1
    print(f"학습·평가 정답 {n} 중 보류 {fp['_rows']} ({fp['_rows'] / n:.1%})", {k: v for k, v in fp.most_common() if k != "_rows"})


if __name__ == "__main__":
    main()
