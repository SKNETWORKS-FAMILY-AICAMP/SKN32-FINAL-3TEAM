/* app/static/user_wait.js — 오래 걸리는 제출의 「진행 중」 표시 · 소유자 ksr (2026-10-13)

   `data-wait-form` 이 달린 폼을 제출하면 그 안의 `[data-wait]` 를 보이고 제출 버튼을 잠근다.
   카피 생성은 20~50초 걸린다 — 눌렀는데 아무 일도 없어 보여 여러 번 누르는 것을 막는다.
   ★ 직접 쓴 파일이다 — 밖에서 받은 코드가 없고(P0-3), 서버로 아무것도 보내지 않는다.
   🚨 CSP 가 `script-src 'self'` 라 템플릿 안에 인라인으로 옮기면 돌지 않는다.
   ⛔ 이 파일이 안 돌아도 생성은 된다 — 표시만 없다. 점의 움직임은 CSS 다(`.gn-wait`).
   🆕 2026-10-15 (점검 0) — 폼에 `data-wait-only` 가 있으면 `data-wait-go` 가 달린 버튼으로 제출할 때만 표시한다
      (검수 폼의 「예시 넣기」 · 「칸 추가」는 금방 끝나 「검수 중」을 띄우지 않는다). 그 버튼에 `data-wait-label` 이
      있으면 누르는 동안 버튼 글자를 그 말로 바꾼다(「검수 중…」 · 「생성 중…」). */
(function () {
  "use strict";

  function set(form, waiting, btn) {
    Array.prototype.forEach.call(form.querySelectorAll("[data-wait]"), function (note) {
      note.hidden = !waiting;
    });
    Array.prototype.forEach.call(form.elements, function (b) {
      if (!b.matches('button[type="submit"]')) return;
      b.disabled = waiting;
      if (!waiting && b.hasAttribute("data-wait-orig")) {
        b.textContent = b.getAttribute("data-wait-orig");
        b.removeAttribute("data-wait-orig");
      }
    });
    if (waiting && btn && btn.hasAttribute("data-wait-label")) {
      btn.setAttribute("data-wait-orig", btn.textContent);
      btn.textContent = btn.getAttribute("data-wait-label");
    }
  }

  Array.prototype.forEach.call(document.querySelectorAll("form[data-wait-form]"), function (form) {
    form.addEventListener("submit", function (e) {
      var btn = e.submitter || null;
      if (form.hasAttribute("data-wait-only") && !(btn && btn.hasAttribute("data-wait-go"))) return;
      /* 제출이 나간 뒤에 잠근다 — 먼저 잠그면 브라우저가 제출을 버리는 일이 있다 */
      setTimeout(function () { set(form, true, btn); }, 0);
    });
  });

  /* 🆕 2026-10-15 (점검 19) — 좁은 화면에서는 결과가 입력칸 아래에 쌓인다. 결과가 그려졌으면 거기로 내려 준다.
     값은 그 화면이 두 줄로 갈라지는 폭이다(`data-scroll-narrow="48rem"`) — 그보다 넓으면 결과가 이미 옆에 보인다 */
  var target = document.querySelector("[data-scroll-narrow]");
  if (target && window.matchMedia &&
      !window.matchMedia("(min-width: " + target.getAttribute("data-scroll-narrow") + ")").matches) {
    target.scrollIntoView({ block: "start" });
  }

  /* 뒤로 가기로 돌아오면 잠긴 채로 남는다 — 풀어 준다 */
  window.addEventListener("pageshow", function () {
    Array.prototype.forEach.call(document.querySelectorAll("form[data-wait-form]"), function (form) {
      set(form, false);
    });
  });
})();
