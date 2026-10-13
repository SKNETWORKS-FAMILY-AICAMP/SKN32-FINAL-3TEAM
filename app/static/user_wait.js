/* app/static/user_wait.js — 오래 걸리는 제출의 「진행 중」 표시 · 소유자 ksr (2026-10-13)

   `data-wait-form` 이 달린 폼을 제출하면 그 안의 `[data-wait]` 를 보이고 제출 버튼을 잠근다.
   카피 생성은 20~50초 걸린다 — 눌렀는데 아무 일도 없어 보여 여러 번 누르는 것을 막는다.
   ★ 직접 쓴 파일이다 — 밖에서 받은 코드가 없고(P0-3), 서버로 아무것도 보내지 않는다.
   🚨 CSP 가 `script-src 'self'` 라 템플릿 안에 인라인으로 옮기면 돌지 않는다.
   ⛔ 이 파일이 안 돌아도 생성은 된다 — 표시만 없다. 점의 움직임은 CSS 다(`.gn-wait`). */
(function () {
  "use strict";

  function set(form, waiting) {
    var note = form.querySelector("[data-wait]");
    if (note) note.hidden = !waiting;
    Array.prototype.forEach.call(form.querySelectorAll('button[type="submit"]'), function (b) {
      b.disabled = waiting;
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll("form[data-wait-form]"), function (form) {
    form.addEventListener("submit", function () {
      /* 제출이 나간 뒤에 잠근다 — 먼저 잠그면 브라우저가 제출을 버리는 일이 있다 */
      setTimeout(function () { set(form, true); }, 0);
    });
  });

  /* 뒤로 가기로 돌아오면 잠긴 채로 남는다 — 풀어 준다 */
  window.addEventListener("pageshow", function () {
    Array.prototype.forEach.call(document.querySelectorAll("form[data-wait-form]"), function (form) {
      set(form, false);
    });
  });
})();
