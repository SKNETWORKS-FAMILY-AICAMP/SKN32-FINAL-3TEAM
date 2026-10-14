/* app/static/rewrite_copy.js — 고쳐 쓴 문구 「복사」 버튼 · 소유자 lse (2026-10-14)

   `[data-copy]` 버튼을 누르면 그 값(고친 문구)을 클립보드에 넣고 잠시 「복사됨」으로 바꾼다.
   ★ 직접 쓴 파일이다 — 밖에서 받은 코드가 없고(P0-3), 서버로 아무것도 보내지 않는다.
   🚨 CSP 가 `script-src 'self'` 라 템플릿 안 인라인 스크립트는 돌지 않는다 — 그래서 파일로 둔다.
   ⛔ 이 파일이 안 돌아도 문구는 화면에 그대로 있다 — 손으로 골라 복사하면 된다. */
(function () {
  "use strict";

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    return ok;
  }

  function done(btn, ok) {
    var label = btn.getAttribute("data-label") || btn.textContent;
    btn.setAttribute("data-label", label);
    btn.textContent = ok ? "복사됨 ✓" : "복사하지 못했어요";
    btn.classList.toggle("is-done", ok);
    window.setTimeout(function () {
      btn.textContent = label;
      btn.classList.remove("is-done");
    }, 1600);
  }

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest ? ev.target.closest("[data-copy]") : null;
    if (!btn) return;
    ev.preventDefault();
    var text = btn.getAttribute("data-copy") || "";
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(
        function () { done(btn, true); },
        function () { done(btn, fallbackCopy(text)); }
      );
    } else {
      done(btn, fallbackCopy(text));
    }
  });
})();
