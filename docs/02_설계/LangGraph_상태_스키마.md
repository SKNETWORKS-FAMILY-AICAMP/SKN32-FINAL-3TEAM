# LangGraph 상태 스키마 — W1 확정 대상

> **작성자** 오한빈 (팀장)
> **작성** 2026-08-16 *(추정)* · **최종 갱신** 2026-08-31 04:31 KST · 🔄 2026-09-21 실물 대조 (`app/graph.py` · `app/contracts.py`) · 🔄 **2026-09-23 상태 넷 · 그래프 셋 (D-266 · D-267 · D-268) — 맨 아래 §개정 2** · 🔄 **2026-09-24 W3 계약 반영 — §개정 3** · 🔄 2026-10-02 `upsert_sentences`(§개정 2) · 🔄 **2026-10-06 실물 대조 (`app/graph.py` · `app/contracts.py` · `app/premise.py` · `app/reasons.py`) — §개정 2 · §개정 3 의 표와 ⬜ 줄 · §개정 4 신설**

> 담당: 그래프·RAG 트랙 (🚨 SPOF — W2 walking skeleton은 2인 페어, D-50). 🔄 **LangGraph 1.2.11** + `langgraph-checkpoint-postgres` **3.1.2** (2026-09-10 확정).

## 상태에 반드시 담을 것 (기획서 3-2 · 3-3)

- 입력: 원문 문구 / 문장 분할 결과 / 제품 컨텍스트(카테고리·인정 기능성)
- 판정 누적: 문장별 (위법유형, 근거 조문 집합, 위험도{코드 하한, 인코더 예측, 최종=max} 🔄 **4단계 R0~R3 (D-130 · D-227 개정 — R4 는 ENUM 에 남았으나 도달 불가)**, 🔄 **`evidence_span`** — 인코더 상향은 이 스팬이 있을 때만 (D-131), 불일치 플래그)
- 재생성 루프: `attempt` **0-base** · 총 라운드 K+1=3 · 🔄 **거부 3종(주장 원장·인용 검증·사후 대조)은 한 카운터** · 서술 재생성 1회 후 슬롯만 렌더 폴백 (D-126) · 실패 사유 누적 · 이전 시도들 · 🔄 실물(09-21) — `rejects`(누적 · 보고용) / `rejected`(**이번 시도** · 리듀서 없음 · 라우터가 읽는다 · I3)
- 진입점 B: 페르소나 목록(팬아웃) · 키워드 선별 결과(허용/차단+사유) · 후보 N=3 · 프론티어 점수
- 종료 분기: 🔄 **2026-09-23 — 검수와 생성이 갈렸다 (D-265 · D-266 · D-268)**. 검수 종착 = 증명서 · **지시** · 보류 · 통과 (루프 없음) · 생성 종착 = 프론티어 · 탐색 실패 · 보류 (🔄 W3 · `GenerateOutcome` · D-274). 아래 줄은 그 전의 기록이다 → ~~종착 넷 `outcome`~~ (D-125) — `pass` → 프론티어 / `certificate` → A·C 는 **판정 직후** 증명서(루프 미진입) / `search_failed` → B 가 K 소진: 원문 유지 + 실증 자료 안내 (🚨 증명서 아님) / `hold` → 전문가 검토. ~~통과 = 확정 ∧ 위험도 ≤ 주의~~ → 🔄 **통과 = 확정 ∧ R0** (D-273) · 보류는 통과가 아니다
- ★ **불가 사유 (D-59)**: 문장별로 `A 자격형 / B 실증형 / C 절대형` 중 하나. **A는 대체 문구 생성 노드로 보내지 않는다** — 표현이 아니라 자격의 문제라 재생성이 같은 위반을 반복한다
- ★ **제품 컨텍스트에 「인정 기능성 보유 여부」가 반드시 들어간다** — 같은 문구가 카테고리·자격에 따라 적법/위법이 갈린다 (D-59)
- ★ **되묻기 노드를 두지 않는다 (D-61)** — A·B는 전제별 분기를 **둘 다 계산해 상태에 담는다**. `interrupt` 불필요. C는 분기도 하지 않는다
- Abstention: 코드가 보류면 인코더가 못 뒤집음 (단조 규칙)
- ★ **판정 상태는 위험도와 다른 축이다** <sub>(🔄 2026-09-03 · 사실원장 「판정 축」)</sub> — 상태는 🔄 **`confirmed / hold(사유코드) / no_basis / unjudged`** (D-127 — 「근거 불일치」는 상태가 아니라 재생성 이벤트) 🔄 **4종**이고 **그래프가 정한다.**
  🚨 **위험도(4단계 순서형)에 섞지 않는다.** D-09 래칫이 `max(코드 하한, 인코더 예측)` 이라 **전순서 위에서만 성립**하는데, 보류·불일치는 서로 비교할 수 없어 `max()` 가 정의되지 않는다.
  ★ 위 「판정 누적」이 이미 두 축을 나눠 갖고 있다 — `위험도{…}` 와 `불일치 플래그`. **화면 배지만 둘을 섞고 있었다.**
- ★ **계측 (D-77)**: `timings: dict[node_name, ms]` *(🔄 실물 — `timings: list[Timing]` 누적 키 · `Timing(node, ms)`)* — **노드 진입·종료 시각을 상태에 적재**한다.
  🚨 **D-43으로 LangSmith·W&B를 배제했으므로 단계별 응답시간을 재 줄 도구가 우리에겐 없다.** 이 필드가 유일한 계측 경로다.
  판정 종료 시 **MLflow(로컬)** 에 run으로 넘긴다 *(⬜ 2026-09-21 — 그래프에서 MLflow 로 넘기는 배선은 아직 없다)* — 응답시간 p50/p95/p99와 **판정/생성 1건 원가**(D-69의 과금 경계 근거)가 여기서 나온다.
  ★ **W2 walking skeleton에서 함께 넣는다.** 나중에 붙이면 그때까지의 측정치가 없다. 공수는 데코레이터 하나 + 상태 필드 하나다.

## TODO (W1)
- [x] ✅ **Pydantic v2 모델로 정의** — `app/contracts.py` (2026-09-10 · D-124 ①). 🚨 **진입점 A 만 덮는다** — B·C 계약은 아직 없다 (D-181). 🔄 **09-12 밤 — B·C 계약도 섰다**(`GenerateRequest/Response` · `AdaptedCopy` · `ComposeRequest/Response`) · 엔진이 없어 `/generate`·`/compose` 는 501. 원 항목: (API 스키마·산식 입출력과 공유)** — **D-124 의 선행 작업이다.** `app/contracts.py` 하나가 팀원 4인의 병렬 착수를 연다. **enum 값은 비우고 필드 구조만 고정**한다 (값은 설계 가정 검증 ①②③ 후)
- [x] ✅ **LangGraph 1.2.11 + langgraph-checkpoint-postgres 3.1.2** — 사실원장 「스택 핀」에 기록 (2026-09-10). 원 항목: → 00_사실원장.md에 기록
- [ ] 체크포인터 postgres 스키마 확인 · 🔄 **판정 종료 시 thread 삭제 + TTL 24h** (D-129) — 원문이 `checkpoints` 에 잔류하지 않게
- [x] ✅ **스텁 배선 완료** — `app/graph.py` (2026-09-10). 라우터 단독 · 컴파일본 대조 · 리듀서 실증까지 게이트 23건. ⛔ 배선하자마자 둘이 잡혔다: 미판정을 통과로 집계 · 컴파일본만 `outcome` None. 원 항목: (D-124) — 라우터 함수는 그래프 없이 단독 테스트 · 스텁 노드로 컴파일해 **방문 순서만** 검증 · 리듀서 키 별도 확인. 🚨 **모델 없이 Phase 0 게이트(end-to-end 1회전)가 성립한다**
- [ ] 페르소나 팬아웃–팬인 reducer 설계
- [ ] ★ **위법 유형 → 불가 사유(A/B/C) 매핑표** 작성 (D-59). 골든셋 라벨에도 이 축이 추가된다

## 🔄 개정 (2026-09-10 · D-181)

**진입점 B·C 가 상태에 아직 없다.** 위 「상태에 반드시 담을 것」이 요구한
`페르소나 목록(팬아웃)` · `키워드 선별 결과(허용/차단+사유)` · `후보 N=3` · `프론티어 점수`
넷이 `app/graph.py` 의 `JudgeState` 에 **빠져 있다.** 이름도 `JudgeState` 라 판정 전용으로 읽힌다.

> 🔄 **2026-09-12 밤 반영** (2026-09-21 대조) — `segment` · `keywords` · `candidates` · `profile` · `adapted` · `ad_format` · `sections` 가
> `JudgeState` 에 들어왔고 게이트가 `ENTRYPOINT_KEYS` 로 본다. 「프론티어 점수」는 따로 두지 않고 `Candidate` 의 칸으로 접었다(D-99).
> ⬜ 남은 것 둘 — 페르소나 **목록**(이 문서) ↔ 계약의 `segment` **하나** 불일치(판정 대기) · `JudgeState` → `PipelineState` 이름 변경(병렬작업 계약 §8 ⑤).

🚨 **화살표를 고쳐 적는다** (D-181). D-164 는 `C ──프로파일──▶ B` 한 방향만 그렸는데,
프로토타입 v7.2 는 매체 선택을 **B 의 후단(「채널별 각색」)**에 두고 C 는 지면 배치를 맡는다.

    B 카피 생성 ─▶ 프론티어 3안 ─▶ 채널별 각색(인스타·블로그·유튜브) ─▶ C 지면 배치
                                     ▲ 매체 프로파일은 여기 산다
    C 는 독립 진입도 받는다 — 종류 선택 → 내용 입력 → 판정 → 템플릿

★ 상태를 넓힐 때 **판정 코어는 하나 그대로다** (D-119). 각색본도 코어를 다시 지난다.

## 🔄 개정 2 (2026-09-23 · D-266 · D-267 · D-268)

**상태를 넷으로, 그래프를 셋으로 갈랐다.** 정본은 `app/graph.py` 다 — 여기는 요약이다.

| 상태 | 담는 것 | 그래프 |
|---|---|---|
| `CoreState` | 입력(`text` · `product`) · `sents` · `laws` · 누적(`evidence` · 🔄 `dict_scans` · `law_results` · `sentences` · `timings`) · 🔄 `branches`(품목 분기 · **리듀서 없는 덮어쓰기 칸** — `premise_branches` 한 노드만 쓴다 · D-319) | **코어 서브그래프** — `split` → `classify` → `retrieve`(1회) → `match_dict` → `encode`(빈 노드) → **법별 팬아웃**(`law_ftc` · `law_food` · `law_cosmetic`) → `merge_laws` → `judge` → `assess_risk` → 🔄 **`premise_branches`**(10-05) → `doc_rules`(빈 노드) |
| `ReviewState` | 코어 출력 + `outcome` · `certificate` — 🔄 **2026-10-06 조립기가 섰다**(`_certificate_of` · 문안은 `app/reasons.py` 의 승인된 일곱 줄 · 열쇠 (법, 유형, 사유) · D-320). 문안이 없는 조합 · 품목 미확정 · 일반상품 · 전용법 미수록이면 증명서를 내지 않고 보류다 — 🔴 **재생성 키가 없다** | **검수** — 코어 → 증명서 · 지시 · 보류 · 통과 · 🔄 2026-10-02 증명서 · 지시는 재료(증명서 · 실증 분기와 뺄 구간)가 없으면 **보류로 내린다** |
| `GenerateState` | `segment` · `product` · `keywords` · `candidates` · `attempt` · `rejects` · `rejected` · `profile` · `adapted` · `outcome` · `timings` | **생성** — 키워드 선별 → 조립 → 주장 원장 → 재판정 → 루프(K+1=3) · ⬜ 노드 여섯은 빈 노드다(10-06) |
| `ComposeState` | `ad_format` · `sections` | 없음 — 이번 범위 밖 |

> 🔄 **2026-10-02 (W5)** — `sentences` 의 리듀서는 `operator.add` 가 아니라 **`upsert_sentences`**(같은 `sent_id` 는 바꿔 끼우고 새 것은 뒤에 붙인다)다. `judge` 가 낸 문장에 `assess_risk` 가 위험도를 붙이고 문서 규칙(W8)이 다시 보류로 바꾸기 때문이다. 누적 키의 리듀서 표는 `app/graph.py` `REDUCER_OF` 한 곳이다(표에 없는 키는 `operator.add`). 🔄 2026-10-05 — `premise_branches` 도 같은 방식으로 문장을 바꿔 끼운다(전제를 몰라 멈춘 문장을 `hold(cat_unknown)` · `hold(premise_unknown)` 로). 상태별 누적 키 목록은 `STATE_REDUCERS` 다 — 코어 · 검수는 `evidence` · `dict_scans` · `law_results` · `sentences` · `timings`.

- 🔴 **코어는 함수 노드가 부른다** — 서브그래프를 노드로 그대로 끼우면 부모의 누적 키가 **두 번 쌓였다**(2026-09-23 실측 · 리눅스). 입출력은 `CORE_IN` · `CORE_OUT` 표 하나다.
- 🔴 **빈 팬아웃은 조용히 그래프를 끝낸다**(같은 날 실측) — 표시광고법이 늘 들어가고, 라우터와 모음이 두 번 막는다.
- 🔴 **생성의 첫 조립이 `attempt=0` 이다** — 종전에는 원문 판정이 0 을 차지해 조립이 두 번뿐이었다 (D-126 의 9회가 6회였다).
- ⬜ 체크포인터 파기(D-129) · 계측 → MLflow · ~~「지시」 종착 값(계약 W3)~~ (✅ W3 · 아래 §개정 3) · 생성 그래프의 `rejudge` 노드가 코어를 부르는 배선(W9) — 아직 없다(10-06 · `rejudge` 는 빈 노드). 그래프 **밖**에서 코어를 다시 부르는 길은 하나 있다 — 아래 §개정 4.
- ✅ 위 「⬜ 남은 것」의 `PipelineState` 개명은 **닫혔다** — 개명 대신 갈랐다(병렬작업 계약 §8 ⑤).

## 🔄 개정 3 (2026-09-24 · W3 계약 · D-273 ~ D-280)

**그래프 상태는 그대로이고 계약이 넓어졌다.** 정본은 `app/contracts.py` 다 — 여기는 요약이다.

| 무엇 | W3 뒤 | 근거 |
|---|---|---|
| 검수 종착 `Outcome` | `pass` · `certificate` · **`guidance`(지시)** · `hold` — 우선순위 보류 > 증명서 > 지시 > 통과 | D-268 · D-274 |
| 생성 종착 `GenerateOutcome` | `frontier` · `search_failed` · `hold` — 검수와 **다른 목록** | D-274 |
| 통과 | **확정 ∧ R0** — 확정 문장은 위반이 없으면 R0, 있으면 R1 이상(계약 · DB 0018 같은 규칙) · 확정 위반에는 불가 사유 필수 | D-273 |
| 보류 사유 `HoldReason` | `low_conf` · `gap2` · `cat_unknown` · `rd1` · 🆕 `premise_unknown` · 🆕 `law_uncovered` | D-263 · D-276 · D-277 |
| 문장 판정 `SentenceJudgment` | 🆕 `not_claim`(판정 대상 아님) · 🆕 `spans`(뺄 구간) · 🆕 `substantiation`(실증 분기) · 🔄 10-01 `fact_check`(사실 확인 분기 `FactBranch` — 수상 · 인증 · 원재료 · 실증 분기와 다른 칸) | D-275 · D-278 · D-263 · D-308 ④ |
| 검수 응답 `JudgeResponse` | 🆕 `category`(품목 · 「일반」 없음) · 🔄 10-02 `category_source`(`classified` · `user_selected` — 품목이 있으면 출처가 있다) · 🆕 `not_reviewed`(미검수 법) · 🆕 `branches`(분기 — 전제 하나씩) · `certificate`(`outcome=certificate` 일 때만 · `Certificate` = `reason` · `explanation` · `guidance`) · `candidates` 는 검수에서 늘 빈 목록 | D-271 · D-276 · D-277 · D-265 · D-320 |
| 🔄 품목 분기 `Branch` | `premise` · `verified`(인정번호 대조 여부 · 기본 False) · `outcome` · `sentences` · `criteria`(기준 문안 · 필수 칸) · `evidence` | D-263 · D-276 · D-319 |
| 🔄 전제 `Premise` | 여섯 — `식품` · `건기식_인정` · `건기식_비인정` · `일반식품_기능성`(09-30) · `화장품` · `일반상품`. 품목 미확정이면 여섯, 식품이면 둘(`식품` · `일반식품_기능성`), 건기식이면 둘(`건기식_인정` · `건기식_비인정`) — `app/premise.py` `PREMISES_OF` | D-276 · D-295 · D-319 |

- ✅ **그래프가 채우는 칸**(2026-10-06 대조 · `app/graph.py`) — `to_response` 는 `category` · `category_source` · `not_reviewed` · `branches` · `certificate` 를 넘긴다(10-02 · 10-05 · 10-06). 법별 노드가 받는 값(`law_payload`)은 `sents` · `product` · `evidence` · `dict_scans` 넷이고, `LawResult` 는 `law` · `sent_ids` · `articles`(이 법이 고른 근거) · `dict_hits` · `provisos`(적용 제외 목) · `weak_hits`(단독판정 자격이 없는 적중) 여섯 칸이다(W4 09-28 · 10-02).
  - 품목은 요청이 준 값을 그대로 싣는다 — `classify` 가 문구로 품목을 판별하지 않으므로 `category_source` 는 품목이 있으면 늘 `user_selected` 다.
  - `branches` 는 기준 문안(`app/premise.py` `CRITERIA`)이 승인돼 있고 DB 가 붙어 있을 때만 채워진다. 문안은 10-06 에 승인됐다(D-319 상태 줄 · 원장 10-03 ㊿-37 · 클론 B).
- ⬜ **계약에는 있으나 아직 채우지 않는 칸**(10-06) — `substantiation`(실증 분기)을 채우는 코드가 `app/` 에 없어 「지시」 종착은 재료가 없으면 보류로 내려간다. `ProductContext.has_recognized_function` · `recognition_no` 를 읽는 코드가 없다(정의뿐) — `Branch.verified` 는 늘 False 다(원장 10-06 ⑤ · 작업공간 · DB 없음).
- ⬜ **DB 저장 칸** — 계약은 문장에 위반을 **여럿** 싣는데 `judgment.violation_type` 은 한 칸이고, `spans` · `not_claim` · 불가 사유 칸이 없다. 그래프가 판정을 DB 에 쓰는 길을 만들 때 정한다(판정 대기).

## 🔄 개정 4 (2026-10-06 · 실물 대조 — 품목 분기 · 증명서 · 그래프 밖 재판정)

**상태 넷 · 그래프 셋은 그대로다.** 10-05 · 10-06 에 코어에 노드 하나와 칸 하나가 늘었고, 검수 화면에 그래프 밖 호출이 하나 붙었다.

| 무엇 | 실물 (10-06) | 근거 |
|---|---|---|
| 코어 순서 | `CORE_BEFORE_LAWS` = `split` · `classify` · `retrieve` · `match_dict` · `encode` / 법별 노드 셋 / `CORE_AFTER_LAWS` = `merge_laws` · `judge` · `assess_risk` · `premise_branches` · `doc_rules` — 컴파일본과 스텁이 이 표 하나를 쓴다 | D-266 · D-267 · D-319 |
| 코어 입출력 | `CORE_IN` = `text` · `product` / `CORE_OUT` = `sents` · `laws` · `evidence` · `dict_scans` · `law_results` · `sentences` · `branches` · `timings` | D-266 |
| 빈 노드 | 코어의 `encode` · `doc_rules` · 생성 그래프의 여섯(`keyword_screen` · `assemble` · `claim_ledger` · `rejudge` · `frontier` · `search_failed`) | `app/graph.py` |
| 품목 분기 | `premise_branches` 가 전제마다 판정을 내고 기록되는 판정을 가장 보수적인 쪽으로 맞춘다. 전제가 하나뿐이면 · 기준 문안이 없으면 · DB 가 없으면 · 미판정 문장이 있으면 아무것도 하지 않는다. 품목이 주어졌고 전제마다 판정이 같으면 분기를 내지 않는다 | D-319 · D-263 ⑦ |
| 증명서 | `certificate` 종착이 `_certificate_of` 로 조립한다. 자격형 · 절대형 문장 중 하나라도 문안이 없으면 증명서를 내지 않고 보류다. ⚠️ 사유가 섞일 때의 규칙(가장 막힌 사유의 글을 잇고 자격 안내는 자격형 증명서에만)은 **팀장 확인 대기** · 인코더 배선 전의 증명서 처리(그대로 · 고지를 붙임 · 끔)는 **미정 · 판정 대기**다 | D-320 상태 줄 |
| 판정 코드의 판 | `JUDGED_BY` = `rule-0.3.0-dict` — 인코더 전 규칙 판정(사전 적중) | D-269 |

### 그래프 밖 재판정 — 검수 화면의 「이 문장 고쳐 쓰기」

- **사실**(10-06 · `lse` 브랜치가 `ohb` 에 병합됨 · 원장 10-06 ② · 클론 A) — 검수 화면의 `POST /u/review/rewrite`(`app/routers/user.py`)가 지적 문장 하나를 로컬 sLLM 서버(`docs/lse/sllm_service.py` · `127.0.0.1:8765` · 별도 `.venv-sllm` · 호출은 `app/routers/sllm_client.py`)에 보내고, 돌아온 문구를 `_rejudge` 가 **앱의 판정 코어로 다시 판정**한다. `_rejudge` 는 `_core_judge` 를 부르고 그것은 `POST /judge` 와 같은 함수다(D-119).
- 이 호출은 **그래프의 노드가 아니다.** 검수 그래프에는 여전히 루프가 없고, 검수 응답의 `candidates` 는 빈 목록이며, 생성 그래프의 `rejudge` 노드와 `POST /generate` · `/compose`(501)는 그대로다.
- 자격형(A) 문장과 위반 유형이 없는 문장은 서버에 보내지 않는다. 서버가 없거나 응답이 깨지면 후보를 그리지 않는다.
- 재판정은 품목 없이 돈다 — 인코더가 붙기 전에는 종착이 전부 보류라 화면의 「재판정 · 통과」 가지에 닿지 않는다(원장 10-06 ⑤ · 작업공간 · DB 없음 · 손으로 세운 48 조합).
- ⚠️ **판정 대기** — 이 고쳐 쓰기와 D-265(검수는 대체 문구를 내지 않는다) · D-270(sLLM 은 설계만 · 상태 줄 「전제 정정 · 결론 재검 대기」 2026-10-06)의 관계, 승인 범위(실사용 · 시연)는 팀장 판정 전이다.

- ⬜ **DB 저장** — 그래프가 판정을 `judgment` 에 쓰는 길은 여전히 없다(§개정 3 마지막 줄 그대로).
