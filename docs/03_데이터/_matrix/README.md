# 판정 매트릭스 원본 (D-90)

`../판정매트릭스.html` 과 `sources.json` 은 **빌드 결과물**이다. 원본은 여기 둘이다.

| 파일 | 무엇 | 손으로 고치나 |
|---|---|:-:|
| `data.js` | 소스 🔄 **82**종의 판정 레코드 — 등급·제약·비용·가치·용도·근거 | ✅ **여기를 고친다** |
| `shell.html` | 화면 골격 — 스타일·필터·행 펼침 | ✅ |
| `sources.json` | `data.js` 의 `SOURCES` 배열만 뽑은 것 — `gen_registry.py` 의 입력 | ❌ 생성물 |

## 다시 만들기

```bash
python scripts/build_matrix.py          # sources.json + 판정매트릭스.html
python scripts/gen_registry.py          # data_sources.yaml
python scripts/extract_rationale.py     # registry_rationale.yaml
uv run pytest -m gate                   # 🚨 여기까지 해야 끝이다
```

어긋났는지만 보려면 쓰지 않는 모드가 있다.

```bash
python scripts/build_matrix.py --check   # 어긋나면 종료코드 1
```

## 🚨 판정을 고칠 때는 `data.js` 를 고친다

`판정매트릭스.html` 이나 `data_sources.yaml` 을 직접 고치면 **다음 빌드에서 날아가고,
그 사이에 두 벌이 갈린다.** 실제로 사실원장이 그렇게 갈린 적이 있다 (D-90 트레이드오프).

`data.js` 에서 쓸 수 있는 값은 다음뿐이다 — 그 밖의 JS 문법을 쓰면
`build_matrix.py` 가 **행·열을 찍고 실패한다.** 조용히 빠지는 것보다 낫다.

```
문자열 '작은따옴표'  ·  객체 {키: 값}  ·  배열 [...]
true / false / null  ·  상수 OK CD NO UN  ·  // 줄 주석
```

★ `id` 가 비었거나 중복이면 빌드가 멈춘다. 매트릭스 id 와 레지스트리 키를 잇는 것은
`extract_rationale.py` 의 `ALIAS` 표다 (D-100) — id 를 바꾸면 거기도 함께 고친다.

## node 를 쓰지 않는 이유

예전에는 이 자리에 `node -e "..."` 한 줄이 적혀 있었고, 그것을 복사해 붙이는 방식이었다.
두 가지가 났다.

1. `sources.json` 만 갱신하고 HTML 을 안 만들어 **둘이 갈리는 상태**가 생겼다.
2. `JSON.stringify` 가 개행으로 끝나지 않아 **커밋마다 `end-of-file-fixer` 훅이 걸렸다.**

그리고 5인 전원 윈도우이고 환경 동일성은 **파이썬 3.11.9 하나로 못 박혀 있다 (D-87).**
매트릭스를 다시 만들려고 node 를 깔게 만들 이유가 없다 —
`build_matrix.py` 가 `data.js` 의 객체 리터럴을 직접 읽는다.
