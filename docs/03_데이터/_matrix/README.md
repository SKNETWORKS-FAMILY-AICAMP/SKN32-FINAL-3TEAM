# 판정 매트릭스 원본 (D-90)

`../판정매트릭스.html` 은 **빌드 결과물**이다. 원본은 여기 둘이다.

| 파일 | 무엇 |
|---|---|
| `data.js` | 소스 73종의 판정 레코드 (등급·제약·비용·가치·용도·근거) |
| `shell.html` | 화면 골격 (스타일·필터·행 펼침) |
| `sources.json` | `data.js` 의 `SOURCES` 배열만 뽑은 것 — `scripts/gen_registry.py` 의 입력 |

## 다시 만들기

```bash
# ① HTML 빌드
node -e "const fs=require('fs');\
 fs.writeFileSync('../판정매트릭스.html',\
 fs.readFileSync('shell.html','utf8').replace('/*__DATA__*/', fs.readFileSync('data.js','utf8')))"

# ② 레지스트리 입력 갱신
node -e "let s=require('fs').readFileSync('data.js','utf8');\
 eval(s.replace(/^const /gm,'var '));\
 require('fs').writeFileSync('sources.json',JSON.stringify(SOURCES,null,1)+'\n')"

# ③ 레지스트리 재생성 + 게이트
python ../../../scripts/gen_registry.py && uv run pytest -m gate
```

🚨 **판정을 고칠 때는 `data.js` 를 고친다.** `판정매트릭스.html` 이나 `data_sources.yaml` 을
직접 고치면 다음 빌드에서 날아가고, 그 사이에 두 벌이 갈린다.

## 🚨 끝에 개행을 붙인다

`JSON.stringify` 는 개행으로 끝나지 않는다. 그대로 쓰면 커밋할 때마다
`end-of-file-fixer` 훅이 파일을 고치고 **커밋이 중단된다** — 재빌드마다 반복된다.
위 ② 명령의 `+'\n'` 이 그것을 막는다. `shell.html` 은 개행으로 끝나므로
①(HTML 빌드)은 그대로 두어도 된다.
