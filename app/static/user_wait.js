/* app/static/user_wait.js — 오래 걸리는 제출의 「진행 중」 표시 · 소유자 ksr (2026-10-13)

   `data-wait-form` 이 달린 폼을 제출하면 제출 버튼을 잠그고 기다리는 표시를 띄운다.
   카피 생성은 20~50초 걸린다 — 눌렀는데 아무 일도 없어 보여 여러 번 누르는 것을 막는다.
   ★ 직접 쓴 파일이다 — 밖에서 받은 코드가 없고(P0-3), 서버로 아무것도 보내지 않는다.
   🚨 CSP 가 `script-src 'self'` 라 템플릿 안에 인라인으로 옮기면 돌지 않는다.
   ⛔ 이 파일이 안 돌아도 제출은 된다 — 표시만 없다. 움직임은 CSS 다(`user.css` `.ub-*`).
   🆕 2026-10-15 (점검 0) — 폼에 `data-wait-only` 가 있으면 `data-wait-go` 가 달린 버튼으로 제출할 때만 표시한다
      (검수 폼의 「예시 넣기」 · 「칸 추가」는 금방 끝나 띄우지 않는다).
   🔄 2026-10-17 (ksr) — 표시는 공용 덮개(`user/_busy.html`) 하나로 모았다. 폼의 `data-wait-overlay` 가 가리키는 덮개를
      (없으면 화면의 첫 `[data-wait-page]` 를) 띄우고, 덮개에서 `body` 까지 올라가며 길 밖의 형제를 모두 `inert` 로 묶는다
      — 기다리는 동안 메뉴 · 다른 버튼을 누르거나 Tab 으로 옮겨 가지 못한다.
      🚨 덮개를 `body` 로 옮기지 않는다 — 색 토큰이 `.user-shell` 안에만 있어 밖으로 나가면 상자가 투명해진다.
      덮개가 없는 화면은 예전처럼 폼 안의 `[data-wait]` 를 보이고 `data-wait-label` 로 버튼 글자를 바꾼다.
   🔄 2026-10-19 (ksr) — `data-wait-overlay` 가 없고 폼 안에 자기 `[data-wait]` 가 있으면 덮개를 찾지 않는다
      (검수 화면의 고쳐 쓰기 폼은 lse 의 `.rv-think` 를 쓴다 — 화면의 첫 덮개 `busy-rv` 가 대신 뜨지 않게). */
(function () {
  "use strict";

  function overlayOf(form) {
    var id = form.getAttribute("data-wait-overlay");
    if (id) return document.getElementById(id);
    if (form.querySelector("[data-wait]")) return null;
    return document.querySelector("[data-wait-page]");
  }

  function lock(page, waiting) {
    page.hidden = !waiting;
    for (var node = page; node && node !== document.body; node = node.parentNode) {
      Array.prototype.forEach.call(node.parentNode.children, function (el) {
        if (el === node || el.tagName === "SCRIPT") return;
        if (waiting) el.setAttribute("inert", "");
        else el.removeAttribute("inert");
      });
    }
    document.body.setAttribute("aria-busy", waiting ? "true" : "false");
  }

  function set(form, waiting, btn) {
    var page = overlayOf(form);
    if (page) {
      if (waiting) lock(page, true);
    } else {
      Array.prototype.forEach.call(form.querySelectorAll("[data-wait]"), function (note) {
        note.hidden = !waiting;
      });
    }
    Array.prototype.forEach.call(form.querySelectorAll('button[type="submit"]'), function (b) {
      b.disabled = waiting;
      if (!waiting && b.hasAttribute("data-wait-orig")) {
        b.textContent = b.getAttribute("data-wait-orig");
        b.removeAttribute("data-wait-orig");
      }
    });
    if (!page && waiting && btn && btn.hasAttribute("data-wait-label")) {
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
    Array.prototype.forEach.call(document.querySelectorAll("[data-wait-page]"), function (page) {
      lock(page, false);
    });
    Array.prototype.forEach.call(document.querySelectorAll("form[data-wait-form]"), function (form) {
      set(form, false);
    });
  });
})();
