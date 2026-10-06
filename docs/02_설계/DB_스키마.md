# DB 스키마 초안 — W1 확정 대상

> **작성자** 오한빈 (팀장)
> **작성** 2026-08-16 *(추정)* · **최종 갱신** 2026-09-02 KST · 🔄 2026-09-21 실물 대조 (표·체크리스트 상태만 · 설계 판단은 그대로) · 🔄 **2026-10-06 실물 대조** — 런타임 12표와 쓰는 코드 현황 · 마이그레이션 머리 `0024_golden_cond` · 0019 ~ 0024 가 더한 것 · `JUDGMENT` 칸 · 계정 · 벡터 엔티티 (`db/schema.sql` · `app/models.py` · `alembic/versions/` · 설계 판단은 그대로)

> 담당: 데이터·거버넌스 트랙 · 기획서 4-5절 참조. PostgreSQL 16 + pgvector · SQLAlchemy 2.0 + Alembic.
> 🚨 엔진 선택 근거는 **D-95** — MySQL 이 아닌 이유는 취향이 아니라 **D-20 캐스케이드 삭제**에서 도출된다.
> 🚨 **정본은 이 문서가 아니다** — 거버넌스 층은 `db/schema.sql`(사본: [`거버넌스데이터층_DDL.md`](거버넌스데이터층_DDL.md) 부록), 런타임 층은 `app/models.py`(D-89), 변경 이력은 `alembic/versions/` 다. 이 문서는 엔티티 목록과 W1 체크리스트를 든다.

## 엔티티 목록 (기획서 4-5)

- **거버넌스**: SOURCE(등급·제약·용도·이력) · FRAGMENT(추출단위·등급·마스킹) · SOURCE_GRADE(판정 이력: decided_by/reviewed_by/evidence_url)
  - 🔄 실물(2026-09-21) — 별도 표가 아니라 `source` 의 칸 `grade_decided_by`·`grade_reviewed_by`·`grade_evidence_url` + CHECK `ck_source_four_eyes` 다 (`db/schema.sql`)
- **판정(진입점 A)**: 광고문구 · 문장 · 제품카테고리 · 적용법령 · 위법유형 · 판정이력 · 위험도 · 대체문구 · 재판정이력
- **생성(진입점 B)**: 세그먼트(군집id·인원수·`source_set_version`) · 페르소나 · 지향키워드(선별 판정 결과) · 생성후보(프롬프트 버전·시도 회차·스크리닝 결과) · 주장원장(문장fk·주장스팬·출처)
- 🔄 ★ **런타임 층 — 사용자 작업 (D-103)**: WORK_DOC(제품 1개 기준 · `consent` 에 따라 서버/세션) ·
  COPY_SENTENCE(work_doc fk · `raw`/`norm`/`offset_map` · `image_description` · `approved_at`) ·
  JUDGMENT(다형 · 아래) · SLOT_ASSIGNMENT(템플릿 조립) · 🔄 BATCH_RUN(CSV 일괄 판정 · D-105)
  - 🚨 **`product_category` 는 문서가 아니라 판정에 있다** (D-82 · D-105) — 배치는 한 실행 안에서
    SKU 마다 카테고리가 다르고, 카테고리는 **우리가 판별하는 것**이라 판정의 결과다
  - 🚨 **`document` · `sentence` 라는 이름을 쓰지 않는다.** DDL v1.0 이 그 이름을 **수집한 원문**
    (법령·의결서 · `fragment_id` FK · `superseded_at`)에 이미 쓰고 있다. 사용자가 쓴 문구는
    fragment 에서 오지 않으므로 **다른 개체다.** 같은 이름을 쓰면 조인 한 번에 층이 섞인다
- **사전**: 금지표현 · 허용표현(카테고리별) · 완화어휘 금지 사전
  - 🔄 실물(2026-10-06) — `dict_entry` 한 표이고 종류는 `dict_kind`(금지표현 / 적법표현 / 질병표현 / 완화금지)로 가른다. 판정 그래프가 읽는 것은 `금지표현` 이다(`app/graph.py` `match_dict` · `exact_match` 인 항목만 확정의 재료)
- **벡터**: 법령/고시/사례 청크 · 리뷰 임베딩 · 합법 어휘 임베딩 *(초기 계획)*
  - 🔄 실물(2026-10-06) — 임베딩 표는 **`chunk_embedding` 하나**(`vector(1024)` · `model_id` · `input_sha256`)이고 색인된 것은 **법령 · 행정규칙 · 별표의 조문 청크뿐**이다(6,667 전부 법령 원천 · 원장 10-03 ⑰ · 클론 B). 사례 청크 · 리뷰 임베딩 · 합법 어휘 임베딩은 **만들지 않았다**(설계 · 미구현 10-06) — 사례는 학습 · 평가 라벨로만 쓴다([`벡터DB_구축_결과서.md`](벡터DB_구축_결과서.md))
- ★ **인증 (D-66)**: USER(닉네임 · 이메일 · 해시 · **role** `governor` · **`org_id`**) · SESSION *(🔄 초안의 `reviewer`/`governor` 두 역할은 바로 아래 줄대로 `governor` 하나로 정해졌다)*
  - 🚨 **`org_id`는 지금 넣는다.** 지금은 org가 하나여도, 나중에 클라우드 에디션(D-67)에서 붙이려면 **전 테이블을 소급 마이그레이션**해야 한다.
  - 🚨 **인구통계(성별·연령대)는 넣지 않는다 (D-68).** 세그먼트는 회원 속성이 아니라 **입력 파라미터**다.
  - **역할은 `governor` 하나만 강제한다.** 셀러/마케터는 **행동으로 정해지므로** 컬럼으로 두지 않는다 (D-66).
  - 🔄 실물(2026-10-06) — 계정 표가 **둘**이다(D-260 ② · 세션 쿠키도 따로다 `copylane_session` / `copylane_user`).
    - `app_account`(0012) — 관리자 콘솔 로그인. 이니셜 · 표시명 · PHC 해시(`$argon2id$` 접두어 CHECK) · `role` 은 `governor` 만(CHECK) · `disabled_at`. 이메일 칸은 없다. 가입 화면이 없고 `launcher.py admin-add` 로만 만든다
    - `user_account`(0017) — 일반 사용자 가입 · 로그인. **`email`**(유일 · 소문자 CHECK · `@` CHECK) · PHC 해시 · 이름 · `org`(소속 자유 기재 · FK 아님) · 약관 버전과 동의 시각들 · `disabled_at`. 역할 칸은 없다(D-66 「행동이 역할을 정한다」). `email_verified_at` 은 늘 NULL 이다 — 인증 메일을 보내지 않는다
    - 세션은 표가 아니라 **서명 쿠키**다(`app/auth.py`)
    - ⬜ **`org_id` 칸은 어느 표에도 없다**(`app/` · `db/` · `alembic/` 에 0곳) — 위 「지금 넣는다」는 판정이 남아 있다
- ★ **프로필 (D-68 · 10주 범위 밖 · 컬럼만 예약)**: SELLER_PROFILE(닉네임 · **카테고리 태그** · 원하는 광고 유형 ·
  **`visibility`** `private`/`link`/`members` · 소유 증명 상태) — 🚨 **메시지·평판·계약 테이블은 만들지 않는다.**

## 🔄 ★ 층이 둘이다 — 거버넌스 층과 런타임 층 <sub>(2026-09-02 · 🔄 2026-10-06 실물 대조 — 두 층 모두 서 있다)</sub>

| 층 | 무엇 | 상태 |
|---|---|---|
| **거버넌스·수집·학습** | `source` `source_constraint` `source_use` `fragment` `collect_manifest` `document` `sentence` `chunk` `chunk_embedding` `sanction_rule` `penalty_rule` `penal_clause` `dict_entry` `product_fact` `golden_sample` `violation_article` `transform_pair` `segment` `dataset_manifest` — 🔄 **19 테이블 · 뷰 5 · 열거형 14** (2026-10-06 `db/schema.sql` 실측) | ✅ **DDL 에 있고 PostgreSQL 16.13 으로 실측 검증됨** · 적재돼 있다(행 수는 [`데이터베이스_저장소_설계_2차.md`](데이터베이스_저장소_설계_2차.md) §5 — 기기 · 원장 절과 함께) |
| **런타임 — 사용자 작업 · 운영** | `work_doc` `copy_sentence` `batch_run` `judgment` `upload_blob` `slot_assignment`(alembic `6c1f5f12e174` · 09-09 · 여섯 표) · `app_account`(0012) · `app_error_log`(0016) · `user_account` `notice` `terms` `ticket`(0017) — 🔄 **12 테이블** (2026-10-06 `app/models.py` 실측) | 🔄 ✅ **있다.** 쓰는 코드는 표마다 다르다 — 아래 「런타임 층 — 어느 코드가 쓰나」 |

> 그래서 **초기 마이그레이션은 런타임 층부터** 만든다. 거버넌스 층은 수집이 열릴 때(S0-14 통과 후)
> DDL v1.0 을 그대로 옮긴다. 오늘 둘을 한꺼번에 넣으면 **검증할 수 없는 마이그레이션**이 된다.
>
> 🔄 **실제 순서는 반대가 됐다** (2026-09-21 대조) — 거버넌스 `0001_governance`(동결본 `db/schema_0001.sql` · D-225)가 먼저이고
> 런타임 `6c1f5f12e174` 가 그 위다. 🔄 머리는 **`0024_golden_cond`** 다(2026-10-06 · `alembic/versions/` 0001 ~ 0024 가 한 줄로 이어진다).

### 🔄 런타임 층 — 어느 코드가 쓰나 <sub>(2026-10-06 · `app/` · `scripts/` · `launcher.py` 를 표 이름 · 모델 이름으로 찾음)</sub>

| 표 | 넣는 코드 | 읽는 코드 |
|---|---|---|
| `work_doc` · `copy_sentence` · `judgment` | ⬜ **없다** — 판정 그래프의 결과를 DB 에 쓰는 길이 아직 없다(구현계획 ②) | `app/routers/user.py` — 홈 집계(이번 달 판정 · 통과 · 지적 수) · 검수 이력(`judgment` × `copy_sentence` 조인 · 내 문서만). 넣는 코드가 없어 앱만으로는 빈 목록이다 |
| `batch_run` · `upload_blob` · `slot_assignment` | ⬜ 없다 | ⬜ 없다 — 모델과 표만 있다 |
| `app_account` | `scripts/admin_account.py`(`launcher.py admin-add`) | `app/routers/auth.py`(로그인 · 마지막 로그인 시각 갱신) · `app/routers/admin.py` · `scripts/db_reset.py` |
| `app_error_log` | `app/error_log.py`(WARNING 이상 · 백그라운드 기록기 · 보관 기한 지난 행 삭제) | `app/routers/admin_errors.py` |
| `user_account` | `app/routers/user.py`(가입 · 마이페이지 · 끄기) | `app/routers/user.py`(로그인 · 세션) |
| `ticket` | `app/routers/user.py`(문의 접수) | `app/routers/user.py`(내 문의 · 알림) |
| `notice` · `terms` | ⬜ 넣는 코드를 찾지 못했다 | `app/routers/user.py`(알림의 공지 · 가입 때 적는 약관 버전) |

- 🚨 **검수 화면은 픽스처가 아니라 실제 판정 코어를 부른다**(09-29 뒤 · `app/routers/user.py` `_core_judge` → `POST /judge` 와 같은 함수). 다만 그 결과는 화면에만 그려지고 **DB 에 저장되지 않는다.**
- 관리자 화면의 공지 · 약관 · 문의 · 회원 · 통계 라우터(`app/routers/admin_*.py`)에서는 위 표를 읽거나 쓰는 질의를 찾지 못했다(10-06) — 표는 섰고(0017 · D-260) 관리자 쪽 배선은 확인된 것이 없다.

### 🔄 0019 ~ 0024 가 더한 것 <sub>(2026-10-06 · `db/migrations/` · `alembic/versions/`)</sub>

| 판 | 층 | 무엇 |
|---|---|---|
| 0019 `chunk_law` (09-24) | 거버넌스 | `chunk.category TEXT[]` → **`chunk.law TEXT NOT NULL`** + `ck_chunk_law`(표시광고법 · 식품표시광고법 · 화장품법 · 건강기능식품법) · `v_current_chunk` 재생성 (D-271 ①) |
| 0020 `flag_nd` (09-25) | 거버넌스 | `flag_t` 에 **`ND`**(변경금지 — 파생 데이터셋 금지) · 값 12 |
| 0021 `chunk_exempt` (09-28) | 거버넌스 | **`chunk.exempt_of`**(적용 제외 목의 부모 경로 · NULL = 미적재 · '' = 제외 목 아님) + `ck_chunk_exempt`(별표 청크만) · `v_current_chunk` 재생성 (D-238 개정 (나)) |
| 0022 `judgment_ratchet` (09-29) | 런타임 | `judgment` 에 **`ck_judgment_final_not_below_floor`** — 최종 위험도는 하한보다 낮을 수 없다 (D-09) |
| 0023 `sanction_rule_w5` (10-02) | 거버넌스 | `sanction_rule` 에 **`rule_key` · `annex1` · `cover` · `quote` · `fact_kind` · `plan_sha`** + `ck_sanction_cover` · 부분 유일 인덱스 `ux_sanction_rule_key` · `v_risk_lookup` 이 새 칸 다섯을 낸다 (D-305 · D-309 · D-310) |
| 0024 `golden_cond` (10-05) | 거버넌스 | `golden_sample` 에 **`cond`**(C · A · B · M · D · L) · **`evidence_candidate`** + `ck_golden_cond_empty` · `ck_golden_cond_basis` · 뷰 **`v_golden_scored`** · **`v_golden_legal`** 신설 · `v_publishable_golden` 재생성 (D-317) |

- 뷰는 다섯이다 — `v_current_chunk` · `v_publishable_golden` · `v_golden_scored` · `v_golden_legal` · `v_risk_lookup`.
- `db/migrations/*.sql` 은 거버넌스 층의 SQL 본문만 든다. 런타임 층을 고치는 판(0012 · 0014 · 0016 ~ 0018 · 0022)은 alembic 파일에 DDL 을 직접 적는다(각 파일 머리말 · D-89) — 그래서 그 폴더에는 번호가 빠져 있다.

## 🔄 ★ 판정은 다형 참조로 저장한다 <sub>(2026-09-02 · D-103)</sub>

> **오늘 확정하는 것은 스키마가 아니라 「무엇을 오늘 정하지 않아도 되게 만들 것인가」다.**

```
JUDGMENT                                         🔄 2026-10-06 `app/models.py` `Judgment` 실물
  doc_id             FK work_doc ON DELETE CASCADE ← D-129 · 문서가 지워지면 판정도 지워진다
  subject_type       'copy_sentence' | 'claim'   ← 🚨 지금은 copy_sentence 만 쓴다 (CHECK)
  subject_id
  verdict            confirmed | hold | no_basis | unjudged          (CHECK · D-127)
  hold_reason        low_conf | gap2 | cat_unknown | rd1
                     | premise_unknown | law_uncovered               (0018 · 16자 칸)
                     ← hold 일 때만, hold 면 반드시 (ck_judgment_hold_reason)
  product_category                             ← 🚨 D-82 · 판정의 결과다 · 「일반」은 없다 (D-271)
  product_category_source   classified | user_selected               (0018 · D-276)
                     ← 품목이 있으면 출처가 있고 없으면 없다 (ck_judgment_category_source_pair)
  violation_type · evidence(근거 조문 JSONB) · evidence_span(상향 근거 구간 JSONB · D-131)
  risk_floor / risk_final   0 ~ 4 (CHECK · 척도는 R0 ~ R3 · R4 는 도달 불가 · D-227)
  law_version                                  ← 🚨 문장이 아니라 판정에 박는다
  attempt            0 ~ PARAMS.max_attempt    ← 0-base · 재판정 회차 (K=2 · D-126)
  is_public · screened_at                      ← D-68
  judged_at · judged_by(코드/모델 버전)
```

🔄 **판정 행에 걸린 불변식**(CHECK · 2026-10-06 실물) —

| 제약 | 뜻 | 판 |
|---|---|---|
| `ck_judgment_confirmed_risk` | 확정 행은 위반이 없으면 R0, 있으면 R1 이상 — 계약 `_confirmed_risk_invariant` 와 같은 규칙 | 0018 · D-273 |
| `ck_judgment_raise_needs_evidence` | 최종 위험도를 적으려면 하한이 있어야 하고, 하한보다 높으면 근거 구간이 있어야 한다 | 0006 · 0014 · D-131 |
| `ck_judgment_final_not_below_floor` | 최종은 하한보다 낮을 수 없다(래칫) — 계약 `RiskAssessment` 와 같은 규칙 | 0022 · D-09 |

- 제약의 글자는 `app/models.py` 가 정본이고 마이그레이션이 같은 글자를 든다 — 게이트가 맞댄다(D-99).
- ⬜ **계약과 칸이 어긋난 자리**(판정 대기 · [`LangGraph_상태_스키마.md`](LangGraph_상태_스키마.md) §개정 3) — 계약은 문장에 위반을 여럿 싣는데 `violation_type` 은 한 칸이고, 뺄 구간(`spans`) · 판정 대상 아님(`not_claim`) · 불가 사유 · 종착(`outcome`) 칸이 없다. 그래프가 판정을 DB 에 쓰는 길을 만들 때 정한다.

- **왜 다형인가** — 도메인상 규제가 붙는 대상은 문장이 아니라 **주장**이다. 식품표시광고법이 금지하는 것은
  *"질병 예방·치료를 표방하는 것"* 이지 특정 문장이 아니다. 그러나 **주장의 축은 9/17 범위 확정(D-65)에서 정해지고**,
  「기능」의 값 집합은 인정 기능성 원료 데이터가 들어와야 나온다. **지금 정하면 근거 없이 정하는 것이다.**
  다형으로 두면 주장 계층이 열릴 때 **`subject_type='claim'` 행이 추가될 뿐 기존 문장 행은 그대로다** —
  스키마 변경이 아니라 데이터 추가가 된다.
- **왜 `law_version` 이 판정에 붙는가** — 재판정하면 **새 판정 행**이 생기고 이력이 남는다.
  문장에 박으면 덮어쓰게 되고, D-103 의 「재검증 대기」가 *"언제 무엇으로 판정했었나"* 를 잃는다.
- **대가** — 다형 참조라 **FK 무결성이 DB 수준에서 안 걸린다.** 규모가 작아 감당 가능하고,
  게이트 테스트로 대신 막는다 (이 프로젝트가 이미 그렇게 한다).
- 🚨 **승인은 판정의 속성이 아니라 상태다.** `approved_at` 은 COPY_SENTENCE 에 두고, 판정은 여러 번 쌓인다.

### 🚨 위험도 추이는 보관 동의에 걸리지 않게 만든다 <sub>(D-105 · D-96)</sub>

배치 검수의 **위험도 추이**를 리텐션 근거로 채택했는데(D-105 ②), 그것을 `judgment` 조인으로
계산하면 **보관 동의가 없는 사용자에게는 추이가 성립하지 않는다** — D-96 대로 원문
(`copy_sentence`)이 세션 종료와 함께 사라지면 조인 대상이 없어지기 때문이다.

> **`batch_run.summary` 에 집계 스냅샷을 남긴다.** 원문을 지우고 **집계만 남기면** 추이는 남는다.
> 권소라 역검토 회신에서 반려 문구에 적용한 것과 **같은 형태**다 — *"사용자 문서에는 문구와 사유를,
> 우리에게는 집계만."* 그리고 G2 소스의 `raw` 를 지우고 `sha256` 만 남기는 규칙과도 같은 축이다.

### 🚨 이름이 겹친다 — 「주장 원장」과 「주장 계층」은 다른 것이다

| | 주장 원장 (CLAIM_LEDGER) | 주장 계층 (미결) |
|---|---|---|
| 언제 | **Phase 2 · 이미 계획됨** | 9/17 이후 판단 |
| 무엇 | 문장 **안**의 주장 스팬 (`문장fk` · `스팬` · `출처`) | 문장 **위**의 재사용 단위 |
| 역할 | 재생성이 **신규 주장을 끼워 넣지 못하게** 막는 게이트 | 다른 매체·다른 제품에서 **재사용** |
| 관계 | 문장 1 : N 스팬 | 주장 1 : N 문장 |

> **같은 단어를 두 뜻으로 쓰면 반드시 갈린다.** 재사용 단위를 만들 때는 `CLAIM_TEMPLATE` 처럼
> **다른 이름**을 쓴다. 지금은 만들지 않는다.

## 🚨 W1에 반드시 (D-20)

- [x] 모든 청크·학습샘플·사전 항목에 `fragment_id` FK 필수 *(🔄 09-21 확인 — `db/schema.sql` `NOT NULL REFERENCES fragment … ON DELETE CASCADE`)*
- [ ] 소스 단위 캐스케이드 삭제 스크립트 + **테스트까지** (`DELETE source → fragment → 청크/학습샘플/벡터`)
- [ ] Alembic 초기 마이그레이션 + `upgrade → downgrade → upgrade` 롤백 검증 *(🔄 10-06 — 마이그레이션은 섰다(0001 ~ 0024). 새로 세운 DB 와 옮긴 DB 가 같은 모양인지는 `launcher.py db-drift` 가 잰다(원장 10-03 ㊿-24 · 클론 B). ⬜ downgrade 까지 도는 왕복 검증은 기록을 못 찾았다 — `tests/test_db_schema.py` 는 downgrade 의 모양만 본다)*
- [ ] 세그먼트 `source_set_version` → 데이터셋 버전 변경 시 재학습 트리거
- [ ] k-익명성 `K_MIN` 값 확정 (00_사실원장.md에 기록)
- [x] ★ **판정이력에 `is_public` · `screened_at` 컬럼** (D-68) *(🔄 09-21 — `judgment` 에 있다)* — 공개 프로필은 10주 범위 밖이지만,
      나중에 붙이려면 판정 이력 전체를 마이그레이션해야 하므로 **컬럼만 지금 잡아둔다**
- [x] ★ **`SOURCE_GRADE`에 `decided_by != reviewed_by` 제약** (D-66) — 2인 확인을 코드로 강제 *(🔄 09-21 — `source` 의 `ck_source_four_eyes`)*
- [x] ★ **골든셋에 `surface_variant`(S0~S5) · `surface_of`(FK)** (D-91) *(🔄 09-21 확인)* — 회피 표기는 위법 유형과
      **직교하는 축**이다. `rule_id` 에 섞으면 유형별 Recall 이 오염된다. 나중에 붙이려면 골든셋 전체를 재생성해야 한다
- [x] ★ **골든셋·학습샘플 행에 `provenance` · `redistributable`** (D-71) *(🔄 09-21 — `golden_sample` 확인)* — 🚨 상속값을 **행 단위로 복사**한다.
      조인으로 매번 계산하면 소스가 캐스케이드로 지워진 뒤(D-20) 공개 판정의 답이 달라진다
- [x] 🔄 ★ **골든셋에 조건 `cond` · 후보 근거 `evidence_candidate`** (D-317 · 0024 · 2026-10-05) — W1 목록에는 없던 칸이다. 빈 `violations` 가 적법으로 읽히던 것을 막고, 골든을 DB 에서 읽는 문을 뷰 둘(`v_golden_scored` · `v_golden_legal`)로 세웠다
- [x] 🔄 ★ **JUDGMENT 에 `subject_type` · `law_version`** (D-103) *(🔄 09-21 확인 · 10-06 — 그 뒤 보류 사유 · 품목 출처 · 불변식 셋이 늘었다 · 위 JUDGMENT 절)* — 🚨 **주장 계층 도입을
      마이그레이션이 아니라 데이터 추가로 만드는 유일한 장치다.** 나중에 붙이면 판정 행 전체를 옮겨야 한다
- [x] 🔄 ★ **COPY_SENTENCE 에 `image_description`** (D-104) *(🔄 09-21 확인)* — 이미지 설명 생성 보조를 나중에 얹기 위한 자리.
      🚨 **자리를 비워 두는 것이 D-104 가 「지금 넣지 않는다」를 고를 수 있게 한 조건이다**
- [ ] 🔄 ★ **사용자 입력 유래 행에 `consent`** (D-96) *(🔄 09-21 — 문서 단위 `work_doc.consent_store`·`consent_train` 으로 섰다(D-128). 행 단위 `consent` 칸은 없다)* — 🚨 `provenance`·`redistributable` 과 **같은 층**이다.
      기본값은 **미보관**이고, 학습 데이터 구성은 `consent=true` 만 통과시킨다. **나중에 붙이려면
      「동의를 받았는지 알 수 없는 과거 행」이 남고, 그 행들은 영구히 학습에 못 쓴다**
- [ ] ★ **문장·청크에 `raw` / `norm` / `offset_map`** (D-84 ① · D-91) *(🔄 09-21 — 문장(`sentence`·`copy_sentence`)은 있다. 청크는 `text`(인용 단위)/`context`(검색 문맥)로 갈랐다 · 0008 · D-158 · 🔄 10-06 — 청크에 법 축 `law`(0019) · 적용 제외 목 `exempt_of`(0021)가 더 섰다 · [`청크_스키마.md`](청크_스키마.md))* — 매칭은 정규화문에서,
      보고는 원문 좌표로. 보안 P2-9 가 요구하는 `(offset, length)` 구조가 여기 걸려 있다
