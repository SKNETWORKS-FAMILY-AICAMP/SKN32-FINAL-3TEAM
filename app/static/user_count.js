/* app/static/user_count.js — 입력칸 글자 수 표시 · 소유자 ksr (2026-10-12)

   `data-count-for="<textarea id>"` 가 달린 칸에 「12/2000」을 적는다. 입력할 때마다 다시 센다.
   ★ 직접 쓴 파일이다 — 밖에서 받은 코드가 없고(P0-3), 서버로 아무것도 보내지 않는다.
   🚨 CSP 가 `script-src 'self'` 라 **템플릿 안에 인라인으로 옮기면 돌지 않는다** (`app/api.py` `_CSP_PAGE`).
   ⛔ 길이 제한은 여기서 걸지 않는다 — `maxlength` 와 서버가 건다. 이 파일이 안 돌아도 검수는 된다
      (그때 숫자 칸은 `hidden` 인 채로 남는다 — 멈춘 숫자를 보이지 않는다). */
(function () {
  document.querySelectorAll("[data-count-for]").forEach(function (out) {
    var box = document.getElementById(out.dataset.countFor);
    if (!box) return;
    function draw() {
      out.textContent = box.value.length + "/" + box.maxLength;
    }
    box.addEventListener("input", draw);
    draw();
    out.hidden = false;
  });
})();
