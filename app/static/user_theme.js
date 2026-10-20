/* app/static/user_theme.js — 다크 모드 버튼 · 소유자 ksr (2026-10-15 · 점검 01)

   상단바 테마 폼(`data-theme-form`)을 화면을 다시 그리지 않고 처리한다 — 쿠키만 바꾸고(서버는 204) 색은 여기서 바꾼다.
   ⛔ 종전에는 폼 제출 뒤 「지금 주소」로 되돌아가 검수 결과 · 광고 편집이 사라지거나, 결과 주소(`/u/judge`)에서는 405 원문이 떴다.
   ★ 직접 쓴 파일이다(P0-3) · CSP `script-src 'self'` 라 인라인으로 옮기지 않는다.
   ★ 이 파일이 안 돌거나 요청이 실패하면 종전대로 폼이 제출된다 — 색은 그래도 바뀐다. */
(function () {
  "use strict";

  Array.prototype.forEach.call(document.querySelectorAll("form[data-theme-form]"), function (form) {
    form.addEventListener("submit", function (e) {
      var btn = e.submitter;
      if (!btn || !window.fetch || !window.URLSearchParams) return;
      e.preventDefault();
      var body = new URLSearchParams();
      body.set("theme", btn.value);
      fetch(form.action, {
        method: "POST",
        body: body,
        credentials: "same-origin",
        headers: { "x-copylane-theme": "1" }
      }).then(function (r) {
        if (!r.ok) throw new Error(String(r.status));
        var shell = form.closest(".user-shell");
        if (shell) shell.setAttribute("data-theme", btn.value);
        var other = form.querySelector(btn.value === "dark" ? ".tn-to-light" : ".tn-to-dark");
        if (other) other.focus();
      }).catch(function () {
        /* 실패하면 종전 방식 — 같은 버튼으로 제출한다 */
        form.requestSubmit ? form.requestSubmit(btn) : form.submit();
      });
    });
  });
})();
