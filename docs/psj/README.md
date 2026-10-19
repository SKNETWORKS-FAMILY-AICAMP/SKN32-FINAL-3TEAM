# 박수진 작업 문서 — 판정 인코더 (T2)

> 작업 브랜치 `psj` · 판정 인코더(KcBERT 미세조정 · 9유형 다중 라벨)의 학습 · 평가 · 배포 소스와 보고서를 둔다.
> 채택 판 **D4-20** `copylane-encoder-kcbert-D4-20-기능성편입` · 판 지문 `c451942436f0` · 잠금 채택 2026-10-19 (D-349)

## 규칙

- 🚨 **수치·일정·파라미터는 여기 옮겨 적지 않는다.** 단일 출처는 [`../00_사실원장.md`](../00_사실원장.md) 이다 (D-54). 실험 수치의 출처는 [`reports/D4_실험기록_20261012.md`](reports/D4_실험기록_20261012.md).
- 🚨 **설계 결정은 여기서 하지 않는다.** 결정은 [`../00_설계결정기록.md`](../00_설계결정기록.md) 에 `D-XX` 로만 등재한다 (D-58).
- 🔴 **저장소에 두지 않는 것** (D-249) — 모델 zip · 가중치 · 골든 · 행별 확률 CSV · 행 문장 · 검수판 · API 키. 모델은 `models/`(git 무시), 실험 산출물은 공유 저장소 · 개인 PC 에 둔다.
- 🔴 판 · 문턱은 dev 로만 고른다. 봉인 평가셋은 봉인 회차에만 연다 (D-175 · D-347).

## 폴더

| 폴더 | 내용 |
|---|---|
| `notebooks/` | 인코더 학습 · 비교 노트북 (Colab T4) |
| `e2e_prototype/` | 채점 · 실험 판정 · 배포 폴더 · 진단 스크립트 (+ 이전 판정 로직 시제품) |
| `encoder_data/` | 학습용 추가 데이터 생성 스크립트 (3차 · 실험 전용) |
| `reports/` | 보고서 · 주차 산출물 · 실험 집계표 (`D4-*.md` · `E1-*.md`) |
| `notes/` | 작업 메모 · 인계 · 체크리스트 |

## 1. 채택 판(D4-20)을 다시 만드는 순서

명령은 저장소 루트에서 `uv run` 으로 돈다. `< >` 는 저장소 밖 경로다.

| # | 단계 | 파일 | 어디서 |
|---|---|---|---|
| ① | 데이터 받기 | `launcher.py data-sync` (골든 `94a79fe34363` · 재분할 목록 `preprocess/encoder_resplit.py`) | PC |
| ② | 학습 · 확장 dev 확률 | `notebooks/copylane_encoder_D4-20_기능성편입_20261018.ipynb` → `D4-20_csv.zip` · 모델 zip | Colab T4 (약 13분) |
| ③ | dev 판정 (관문 · 혼동표 · dev 8행) | `e2e_prototype/d4_20_functional.py --base-dir <D4-15 CSV> --d18-dir <D4-18 CSV> --dir <D4-20 CSV>` (`--self-test` 먼저) | PC |
| ④ | 배포 폴더 | `e2e_prototype/make_d415_scheme.py --base-dir <D4-15 CSV> --dir <D4-20 CSV> --model-zip <zip> --run D4-20-기능성편입 --delta 0.03 --functional --out <models 밖>` | PC |
| ⑤ | 앱 그래프 dev | `scripts/eval_graph.py --dev --guide-dev --encoder` (+ `--conditional`) · 213 은 팀장 도구 `build/legit_rate_b.py` | PC |
| ⑥ | 잠금 · 앱 | 팀장이 `models.lock.json` 에 채택 → `launcher.py setting COPYLANE_MODEL_DIR <판 이름>` | 팀장 · PC |
| ⑦ | 서비스 확인 | 단위 테스트(아래 §3) · `e2e_prototype/encoder_cpu_timing.py --model-dir models/<판 이름>` | PC |

## 2. 파일 지도

### 2-1. 노트북 (`notebooks/`)

| 묶음 | 파일 | 비고 |
|---|---|---|
| **현행** | `copylane_encoder_D4-20_기능성편입_20261018.ipynb` | 채택 판 학습 |
| | `copylane_encoder_E1-03_OpenAI임베딩_D4-20기준_20261019.ipynb` | OpenAI 임베딩 비교 (발표용 · KcBERT 우세) |
| 4차 데이터 실험 | `D4-04` 품목입력 · `D4-10` 사실전제학습 · `D4-15` 재분할학습 · `D4-15a` 카드17기준선 · `D4-18` 적법가중 · `D4-19` 화장품사용감 | D4-20 으로 이어진 판 변천 |
| 백본 · 임베딩 비교 | `E1-00` KcELECTRA · `E1-01` KcELECTRA lr5e-5 · `E1-02` OpenAI임베딩 | 발표용 비교 |
| 이전 판 (참고) | `finetune_v7_*` ~ `finetune_v10_*` · `v8_*` · `2차골든셋_*` · `encoder_dryrun_colab_*` | 3차 데이터까지 · 현행 경로 아님 |

### 2-2. 스크립트 (`e2e_prototype/`)

| 묶음 | 파일 | 역할 |
|---|---|---|
| **공통 채점** | `score_encoder_dev.py` | 행별 확률 CSV → 같은 표 · dev 지문 확인 (모든 판정 스크립트가 부른다) |
| | `card17_adopt.py` | D-324 문턱 함수(`d324_thresholds`) |
| **실험 판정 (현행 경로)** | `d4_15_resplit.py` → `d4_16_recall_margin.py` → `d4_17_ensemble_grid.py` → `d4_18_negweight.py` → `d4_19_cosmetic.py` → `d4_20_functional.py` | D4-15 ~ D4-20 · 결과 전 등록 기준으로 판정 · `d4_20_functional.py` 는 E1-03 채점도 겸한다(`--ref-tag` · `--cand-tag`) |
| | `e1_00_electra.py` | E1-00 · E1-01 판정 |
| 실험 판정 (D4-10 까지) | `d4_02_*` · `d4_03_*` · `d4_04_*` · `d4_05_*` · `d4_06_*` · `d4_09_*` · `d4_10_*` · `d4_11_*` ~ `d4_14_*` · `card10_combo.py` · `card17_judge.py` · `matched_recall.py` · `second_pass.py` · `sweep_cand_threshold.py` | 6주차 보고서까지의 실험 |
| **배포 폴더** | `make_d415_scheme.py` | 현행 — 문턱 두 벌(V1 · `--delta`) · 기능성 F1 최대(`--functional`) · 재분할 지문 · 가중치 sha · zip |
| | `make_d410_scheme.py` · `make_card17_scheme.py` · `make_candidate_scheme.py` | 이전 판 |
| **진단 · 서비스** | `encoder_cpu_timing.py` | CPU 추론 시간 |
| | `encoder_probe.py` | 문장 몇 개를 인코더 단독으로 돌려 보기 |
| | `d4_00_precision.py` · `d4_02_case_ci.py` | 정밀도 · 사건 단위 신뢰구간 |
| | `d4_10_gpt213_check.py` · `d4_10_gpt213_exact.py` | 213 행 학습 겹침 대조 |
| | `d4_t_sealed_encoder.py` | 봉인 평가셋 한 회차(10-14 · 한 번만) |
| 판정 로직 시제품 (이전) | `judge_stage1.py` · `judge_stage2.py` · `run_judge_dist.py` · `test_judge_rules.py` · `judge_e2e_prototype.py` | 앱 그래프 배선 전 시제품 · 인코더 층 규칙은 D-340 에서 채택되지 않음 — 앱 성능으로 인용하지 않는다 |
| 기타 | `reasons_representative_draft.py` (+ 테스트) | 유형 후보 대표 · 순서 초안(`app/reasons.py` 흡수용) |
| | `copygen_check.py` | 생성 그래프 점검 하네스(13 사례) |
| | `debug_check.py` · `debug_check2.py` · `debug_raw_probs.py` | 디버그 |

### 2-3. 앱 쪽 인코더 코드 (저장소 공용 · 참고)

| 파일 | 역할 |
|---|---|
| `app/encoder.py` | 모델 폴더 로딩 · `label_scheme.json` 문턱 두 벌 · 문장쌍 입력 · 판 지문(`+encb:`) |
| `app/model_lock.py` · `models.lock.json` | 잠금 — 채택 · 되돌림 판만 로드 (D-333) |
| `app/premise.py` | 전제 → 품목 입력 대응(`encoder_input`) |
| `app/graph.py` | `encode` 노드 · 후보 거름 · 옮김(`_encoder_candidates`) · 절대형 확정(`_absolute_types` · `ENCODER_ABSOLUTE_TAU`) |
| `tests/test_encoder.py` · `test_encode_node.py` · `test_model_lock.py` · `test_absolute_tau.py` · `test_encoder_floor.py` · `test_encoder_estimate.py` | 인코더 단위 테스트 (10-19 · 152 통과) |

## 3. 단위 테스트

```
uv run pytest tests/test_encoder.py tests/test_encode_node.py tests/test_absolute_tau.py tests/test_model_lock.py tests/test_encoder_floor.py tests/test_encoder_estimate.py docs/psj/e2e_prototype/test_judge_rules.py -q
```

## 4. 주요 보고서 (`reports/`)

| 파일 | 내용 |
|---|---|
| `D4_실험기록_20261012.md` | 4차 데이터 실험 등록 · 결과 정본 (D4-00 ~ D4-20 · E1-00 ~ E1-03) |
| `서비스테스트_계획_결과_보고서_판정인코더편_D4-20_박수진_20261019.docx` | 7주차 서비스 테스트 보고서 인코더편 |
| `시스템구성도_판정인코더_박수진_20261019.md` (+ `.png`) | 시스템 구성도 인코더 파트 |
| `판정인코더_E1-03_OpenAI임베딩비교_D4-20기준_보고서_박수진_20261019.docx` | OpenAI 임베딩 비교 |
| `판정인코더_테스트_계획_결과_보고서_소스코드포함_박수진_20261014.docx` | 6주차 테스트 보고서 (D4-10) |
