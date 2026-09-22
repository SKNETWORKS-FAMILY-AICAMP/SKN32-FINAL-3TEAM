# `app/static/vendor/` — 외부 스크립트는 **받아서 커밋한다**

🚨 **CDN 을 쓰지 않는다.** 보안점검 **P0-3**(공급망)과 같은 이유다 — 남의 서버가 언제
바뀌었는지 우리는 모른다. 그리고 `app/api.py` 의 CSP 헤더(`_CSP_PAGE` · 모든 응답에 미들웨어가 붙인다)가 `script-src 'self'` 라 **CDN 은 막힌다.** *(🔄 2026-09-21 — 종전엔 `base.html` 의 `<meta>` 였다 · D-212)*

## HTMX 받는 법

```
# 버전을 고정한다 — 「latest」를 쓰지 않는다 (태그는 움직인다 · 기획서 8-4 #9)
curl -L -o app/static/vendor/htmx.min.js https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js

# 무결성 지문을 만든다 (PowerShell)
$b=[IO.File]::ReadAllBytes("app/static/vendor/htmx.min.js")
"sha384-" + [Convert]::ToBase64String([Security.Cryptography.SHA384]::Create().ComputeHash($b))
```

나온 값을 `app/templates/base.html` 의 `integrity="sha384-…"` 에 넣고 그 줄의 주석을 푼다.

★ **HTMX 없이도 화면은 돈다** — 폼은 서버 렌더 POST 로 동작한다. 붙이는 것은 **점진적 향상**이다.

⬜ **아직 안 받았다.** 받는 사람이 같은 커밋에 `integrity` 를 채운다 —
지문 없이 스크립트를 넣지 않는다.
