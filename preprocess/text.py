"""preprocess/text.py — 문자 수준 정규화 공용 모듈 (전처리 사양 [P2] · D-84 ①).

🚨 **이 파일은 같은 함정을 세 번 밟고 나서 만들어졌다** (D-117).

  ① `law_annex`   — 처분 용어를 `ㆍ`(U+318D)로 나열해 분해가 절반만 됐다
  ② `ftc_triage`  — 「중요한 표시**ㆍ**광고사항」 13건이 `표시·광고` 매칭에서 샜다
  ③ `mfds_press`  — 「표시**.**광고」·「불법**.**부당」 22건이 제목 필터에서 샜다

  셋 다 **같은 문제**이고 셋 다 **다른 파일에서 따로 고쳤다.** 두 번째에 「프로젝트 공용
  정규화로 올려야 한다」고 적어 놓고도 바로 다음 파일에서 또 밟았다 — 기록만으로는
  막히지 않는다. **코드가 한 곳에 있어야 막힌다.**

🚨 여기는 [P2] 정규화 층의 **씨앗**이다. 사양의 N1~N7 이 앞으로 여기 모인다.
   다만 지금 있는 것은 나열 구분자 하나뿐이고, **비파괴 계약(`NormalizedText`)은 아직
   없다.** 오프셋 맵이 필요한 순간(주장 스팬 BIO · 하이라이트 UI)이 오면 사양 1-3 의
   계약을 여기에 세운다 — 그 전까지 이 모듈은 **매칭 직전에만** 쓴다.
"""

from __future__ import annotations

import re

#: 한국어 문서가 낱말을 나열할 때 쓰는 구분자들. 원천마다 다르고 **한 문서 안에서도 섞인다.**
#:
#:   ㆍ U+318D 한글 아래아      「표시ㆍ광고」  ← 법제처·공정위가 즐겨 쓴다
#:   · U+00B7 가운뎃점          「표시·광고」   ← 우리가 표준으로 삼는 것
#:   ․ U+2024 온점             「표시․광고」
#:   ‧ U+2027 하이픈 점
#:   ･ U+FF65 반각 가운뎃점
#:   . U+002E 마침표            「표시.광고」   ← 식약처 보도자료가 즐겨 쓴다
#:   、U+3001 모점
#:   / U+002F 빗금              「허위/과대」
SEPARATORS = "ㆍ·․‧･.、/"

#: 나열 구분자를 가운뎃점 하나로 편다.
_TABLE = str.maketrans(dict.fromkeys(SEPARATORS, "·"))


def sep_norm(text: str) -> str:
    """나열 구분자를 `·` 하나로 통일한다. **매칭 직전에만** 쓴다.

    🚨 **파괴적이다.** 마침표와 빗금까지 가운뎃점으로 바꾸므로 문장 부호·URL·날짜·
       소수점이 함께 망가진다. 원문을 이 결과로 **덮어쓰지 않는다** —
       사양 1-2 가 말하는 「비파괴」는 아직 여기 없다.

    쓰는 자리는 하나다: *낱말이 구분자로 쪼개졌는지* 를 정규식으로 볼 때.

        if PATTERN.search(sep_norm(title)):   # ✅ 매칭에만
            keep(title)                        # ✅ 원문을 보관

        title = sep_norm(title)                # ❌ 원문을 잃는다
    """
    return text.translate(_TABLE)


# ══ 회피 표기 탐지 (전처리 사양 [P11] SURFACE_VARIANTS · D-40) ═══════════
#
# 🚨 **위의 `SEPARATORS` 와 겹치지만 같은 것이 아니다.** 그쪽은 「나열」을 펴는 표
#    (표시ㆍ광고 → 표시·광고)이고, 이쪽은 「낱말이 쪼개졌는가」를 보는 문자 집합이다.
#    합치면 `sep_norm` 이 이미 편 뒤라 회피 표기를 못 세게 된다 — 축이 다르므로 따로 둔다.
#
# 🚨 **여기에 넘기는 것은 원문이다.** 정규화문을 넘기면 `sep_norm` 이 마침표까지 `·` 로
#    펴므로 **문장의 정상 마침표가 구분자로 둔갑**해 오탐이 쏟아진다 (D-117 ②).
#    분류는 「어떻게 쓰였든 같은 뜻인가」를 보고, 회피 표기는 「어떻게 쓰였는가」 자체가 신호다.

#: 🚨 사전([P6])이 아직 없다. 그때까지 **판정 대상 어휘의 최소 집합**으로 센다 —
#:    여기서 나온 수는 하한이지 전량이 아니다. 사전이 서면 다시 센다.
LEX = ["치료", "효과", "완치", "부작용", "다이어트", "미백", "주름", "개선", "예방", "특효"]

#: S2 구분자 삽입 — `치·료` `치.료` `치+료`.
#: 🚨 **공백을 구분자로 넣으면 안 된다** (2026-09-03 오탐으로 확인).
#:    「45**개 선**불식 할부거래업자」가 `개선` 의 회피 표기로 잡혔다. 한국어는 어절을
#:    공백으로 가르므로, 공백 하나만 허용해도 인접 두 어절의 끝·첫 글자가 늘 걸린다.
#: 🚨 구분자는 **글자마다 선택**이다 — 「다·이어트」처럼 한 곳만 쪼개는 것이 실제 모양이다.
#:    대신 선택으로 두면 원형까지 걸리므로 **구분자가 실제로 있는지 뒤에서 확인한다.**
SEP_CHARS = "·.-+~*^/|,_"
_SEPS = r"[" + re.escape(SEP_CHARS) + r"]{0,2}"
_S2 = [
    (w, re.compile(r"(?<![가-힣A-Za-z0-9])" + _SEPS.join(w) + r"(?![가-힣A-Za-z0-9])")) for w in LEX
]

#: S3 자모 분리 — `ㅊl료` `다ㅇㅣ어트`.
#: 🚨 **`ㅇ` 은 세지 않는다.** 공문서는 개인정보를 `대표이사 이ㅇㅇ` · `소갑 제ㅇ호증`
#:    처럼 `ㅇ` 자리표시자로 가려서 보낸다 — 세면 16건이 전부 오탐이 된다 (실측).
_S3 = re.compile(r"[가-힣][ㄱ-ㅆㅈ-ㅎㅏ-ㅣ][가-힣]|[ㄱ-ㅆㅈ-ㅎ][a-zA-Z][가-힣]")

#: S4 zero-width — 자동화 도구 산출물.
_ZW = re.compile(r"[\u200b-\u200f\ufeff\u2060]")


def evasion(text: str) -> list[str]:
    """이 문서에 실재하는 회피 표기 종류. 사양 2-5 의 `evasion_observed`.

    🚨 **원문을 넘긴다.** `sep_norm()` 을 거친 문자열을 넘기면 안 된다 (위 주석).
    """
    flags = []
    if _ZW.search(text):
        flags.append("S4")
    # 🚨 구분자가 실제로 들어간 매칭만 센다 — 원형 낱말은 회피 표기가 아니다.
    if any(any(c in SEP_CHARS for c in m.group(0)) for _, p in _S2 for m in p.finditer(text)):
        flags.append("S2")
    if _S3.search(text):
        flags.append("S3")
    return flags


# ─────────────────────────────────────────────────────────────
#  인용부호 계수기 — **하나만 둔다** (D-160)
# ─────────────────────────────────────────────────────────────

#: 인용부호 가족. **여는 것과 닫는 것을 따로 적지 않는다.**
#:
#: 🚨 원천이 **여는 따옴표로 닫는다** — 사례집에 「‘난임예방‘」·「’암예방‘」이 실제로 있다.
#:    ⛔ 닫는 자리에 `’` 만 두었던 옛 정규식은 그 자리에서 **멈추지 않고 다음 따옴표까지
#:       물었다.** 버려지는 게 아니라 **틀린 값이 만들어진다** —
#:         `난임예방‘,`              뒤 문자열을 물었다
#:         `피로개선‘, ‘뇌건강`       **두 표현이 한 종으로 세어졌다**
#:    ★ 그래서 짝을 안 따지고 **같은 가족 안의 아무 부호**로 닫는다.
#: 🚨 가족을 섞지 않는다 — `“…‘…’…”` 처럼 겹칠 때 안쪽·바깥쪽이 서로 잘리면
#:    둘 다 틀린다. 가족마다 따로 훑고 합친다.
QUOTE_FAMILIES: tuple[str, ...] = ("‘’", "“”", "「」", "『』", '"', "'")


def quoted(
    text: str,
    *,
    min_len: int = 1,
    max_len: int = 120,
    same_line: bool = True,
    families: tuple[str, ...] = QUOTE_FAMILIES,
) -> list[str]:
    """인용부호 안의 표현들. **중복은 남긴다** — 회수와 종수는 부르는 쪽이 나눈다.

    🚨 **계수기를 원천마다 만들지 않는다** (D-117 에서 세 번 밟은 함정).
       세는 범위가 다른 것은 **`min_len` 같은 선언된 파라미터**로 갈라야지,
       각자 쓴 정규식으로 갈리면 「A 는 19종 · B 는 349종」이라는 비교가 성립하지 않는다.

    ★ **여닫이는 글자 모양이 아니라 앞글자가 정한다** — 앞이 글자·숫자면 닫고, 아니면 연다.
      사람이 읽는 방식 그대로다.

        ‘감기예방’, ‘난임예방‘, ’암예방‘
         └열     └닫  └열     └닫(모양은 여는 것)  └열(앞이 공백)  └닫

    ⛔ **세 번 틀리고 이 규칙이 나왔다** (2026-09-08 실측).
       ① 닫는 자리에 `’` 만 두었더니 「‘난임예방‘」에서 멈추지 못하고 다음 따옴표까지 물었다.
          버려지는 게 아니라 **틀린 종이 만들어진다** — 「피로개선‘, ‘뇌건강」은 두 표현인데
          한 종이 됐다 (`mfds_casebook` 19종 중 2종이 이 모양이었다).
       ② 「같은 가족의 아무 부호로 닫는다」로 바꿨더니 **표현 사이의 글**이 잡혔다.
          「‘A’ 등으로 광고 ▲ ‘B’」에서 `’ 등으로 광고 ▲ ‘` 가 한 인용이 됐다
          (`mfds_press` 유령 6종).
       ③ 「줄 안에서 번갈아」로 바꿨더니 **줄바꿈으로 잘린 인용**이 짝을 잃고 그 뒤가 밀렸다.
          PDF 본문은 인용 한복판에서 줄을 바꾼다.
       ★ 앞글자를 보면 셋 다 풀린다.

    🚨 **인용은 줄을 넘지 않는다** (`same_line`). 넘게 두면 표가 실린 PDF 에서 인용 하나가
       옆 칸을 통째로 문다 — 「기미 있죠? 그게 싹 없어지면 **10 월곶중앙로30
       (유통전문판매업)** 서 피부가 깨끗해짐」 같은 것이 한 종이 됐다
       (`mfds_press` 77 → 112종 · 실측 2026-09-08). 줄바꿈에서 **열린 것을 버린다.**
       ⛔ 대신 줄바꿈으로 잘린 인용은 못 줍는다 — 그건 옛 계수기도 못 주웠다. 같은 자리다.

    쓰는 곳
      · `evasion_scan`   `min_len=6, max_len=80` + 판정 어휘 필터 → **평가 표본 종수**
      · `mfds_casebook`  기본값                                   → **학습 입력 후보**
    """
    out: list[str] = []
    for fam in families:
        marks = set(fam)
        start: int | None = None
        for i, ch in enumerate(text):
            if same_line and ch == "\n":
                start = None  # 🚨 줄이 바뀌면 열린 것을 버린다
                continue
            if ch not in marks:
                continue
            prev = text[i - 1] if i else " "
            # 🚨 **글자·숫자 뒤가 아니면 연다.** 공백만 보면 안 된다 — 보도자료는 글머리표를
            #    바짝 붙여 쓴다: 「▲‘다이어트보조제’」·「➌‘기억력 개선(향상)’」·「▹‘골다공증 예방’」.
            #    ⛔ 공백만 여는 것으로 봤을 때 `mfds_press` 에서 **진짜 6종이 사라졌다.**
            # 🚨 `isalnum()` 을 쓰면 안 된다 — **`➌` 같은 원문자 글머리표가 「숫자」로 잡힌다**
            #    (유니코드 No 범주). 그 한 글자 때문에 「‘기억력 개선(향상)’」이 통째로 빠졌다.
            #    `isdecimal()` 은 그것을 숫자로 보지 않는다.
            wordlike = prev.isalpha() or prev.isdecimal()
            if start is None:
                # 🚨 밖에서는 **글자·숫자 뒤가 아니면 연다** — 글머리표가 바짝 붙는다.
                if not wordlike:
                    start = i
            elif prev.isspace():
                # 안에서 **앞이 공백이면** 닫히지 않은 채 새로 열린 것이다 — 앞엣것을 버린다.
                start = i
            else:
                # 🚨 안에서는 **닫는 쪽으로 기운다.** 밖과 같은 기준(글자 아님=열기)을 쓰면
                #    「‘기억력 개선(향상)’」의 `’` 가 앞글자 `)` 때문에 여는 것이 돼
                #    **진짜 인용이 통째로 사라진다** (실측 4종).
                q = " ".join(text[start + 1 : i].split())
                if min_len <= len(q) <= max_len:
                    out.append(q)
                start = None
    return out


def sheet_lengths(rows: list[dict], field: str, min_len: int) -> None:
    """검증셋 표본의 **길이 분포**를 찍는다 (2026-09-09).

    🔴 **왜 이걸 찍는가** — 사람이 채울 검증셋에 낱말과 문장이 섞여 있었다.
       해설서 표본 150건 안에 「배앓이」(3자)와 「가스가 차고 복부 팽만감을 느껴
       배앓이를 겪습니다」(25자)가 같이 들어 있다. 앞엣것은 **맥락이 없어 유형을
       못 고른다** — 사람이 붙이려 해도 못 붙이고, 붙여도 문장 단위 평가에 못 쓴다.

    ⛔ 사례집이 그 증거다 — 인용표현 232종의 중앙 길이가 4자였고, 그중 13종은
       두 유형에 동시에 붙어 있었다(「다이어트」 = 거짓_과장 이자 건강기능식품_오인).
       **다중 라벨이 풍부해서가 아니라 낱말이 라벨을 감당할 만큼 크지 않아서다.**
       그래서 사례집의 성격이 「평가 홀드아웃」에서 「금지 표현 사전」으로 바뀌었다 (D-155).

    🚨 **기본값은 0 이다 — 아무것도 안 거른다.** 하한을 기본으로 걸면 09-08 에 뽑아
       사람에게 이미 넘긴 표본이 조용히 달라진다(같은 seed, 다른 내용). 재현 조건을
       깨지 않는다 (D-54). **거를지는 사람이 정하고, 여기서는 보이게만 한다.**
    """
    lens = sorted(len(" ".join(str(r.get(field, "")).split())) for r in rows)
    if not lens:
        print("     🔴 표본이 비었다 — 하한이 모집단보다 크다.")
        return
    short = sum(1 for x in lens if x < 10)
    print(
        f"     길이 — 중앙 {lens[len(lens) // 2]}자 · 10자 미만 {short}건"
        f" ({short * 100 // len(lens)}%) · 20자 이상 {sum(1 for x in lens if x >= 20)}건"
    )
    if not min_len and short:
        print(
            "     🚨 **낱말이 섞여 있다.** 낱말은 맥락이 없어 사람도 유형을 못 고른다 —\n"
            "        문장 단위 평가에 쓸 표본이라면 `--min-len 20` 으로 다시 뽑는다 (D-155)."
        )


class SheetOverwriteError(RuntimeError):
    """사람이 채운 검증셋을 덮어쓰려 했다."""


#: 사람이 채우는 칸. 🚨 추출기는 **절대** 이 칸을 만들지 않는다 (홀드아웃 자기 채점 방지).
SHEET_HUMAN_FIELDS = ("확정유형", "붙인이", "붙인날")


def _sheet_key(row: dict, fields: tuple[str, ...]) -> str:
    return "\x1f".join(" ".join(str(row.get(f, "")).split()) for f in fields)


def write_sheet(path, rows: list[dict], key_fields: tuple[str, ...]) -> tuple[int, int]:
    """검증셋을 쓴다 — **사람이 채운 값을 이어받고, 잃을 것이 있으면 멈춘다.**

    돌려주는 값: (이어받은 건수, 기존 파일에서 사람이 채워 둔 건수)

    🔴 **왜 이게 필요한가** (2026-09-09) — `--sheet` 가 파일을 **조건 없이 덮어썼다.**
       그런데 인계 문서가 다음 사람에게 시키는 표준 명령이

           uv run python launcher.py extract mfds_casebook --dump --sheet 30

       이다. 라벨을 절반 채운 사람이 이 줄을 다시 돌리면 **그 자리에서 사라진다.**
       조용히 사라지고, `data/derived/` 는 커밋되지 않으므로 git 으로도 못 되돌린다.
       ⛔ 나는 오늘 이 명령을 검증하느라 네 번 돌렸다. 채워져 있었다면 네 번 날렸다.

    ★ **덮어쓰기를 막는 것이 아니라 이어받는다.** 표본 조건이 바뀌어도(`--min-len`)
      겹치는 행의 라벨은 그대로 온다 — 사람이 한 일을 표본 설계 때문에 버리지 않는다.

    🚨 **겹치지 않는 채움이 하나라도 있으면 멈춘다.** 「몇 건 잃습니다」를 찍고 사람이
       정하게 한다. 자동으로 버리지 않는다 — 되돌릴 수 없는 것은 사람이 누른다 (D-51).
    """
    import json  # noqa: PLC0415 — 이 함수만 쓴다
    import pathlib  # noqa: PLC0415

    path = pathlib.Path(path)
    filled: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            old = json.loads(line)
            if any(old.get(f) for f in SHEET_HUMAN_FIELDS):
                filled[_sheet_key(old, key_fields)] = old

    keys = {_sheet_key(r, key_fields) for r in rows}
    lost = [k for k in filled if k not in keys]
    if lost:
        raise SheetOverwriteError(
            f"🔴 {path} 에 사람이 채운 {len(filled)}건이 있고, 그중 {len(lost)}건이 새 표본에\n"
            "   없다. 그대로 쓰면 그 라벨은 사라진다 — `data/derived/` 는 커밋되지 않아\n"
            "   git 으로도 못 되돌린다.\n"
            "  어떻게 하나 —\n"
            f"    ① 먼저 옮겨 둔다:  copy {path} {path}.keep\n"
            "    ② 표본 조건을 원래대로 돌려 이어서 채운다 (같은 seed 면 같은 행이 나온다), 또는\n"
            "    ③ ①의 사본을 보고 새 표본에 손으로 옮긴 뒤 다시 돌린다.\n"
            "  🚨 겹치는 행의 라벨은 자동으로 이어받는다 — 잃는 것은 위 건수뿐이다."
        )

    carried = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            rec = {**r, "붙인이": "", "붙인날": ""}
            old = filled.get(_sheet_key(r, key_fields))
            if old:
                for k in SHEET_HUMAN_FIELDS:
                    rec[k] = old.get(k, rec.get(k))
                carried += 1
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return carried, len(filled)
