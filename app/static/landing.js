/* app/static/landing.js — 랜딩의 움직임 · 소유자 lse (2026-10-14)

   ① 스크롤하면 `[data-reveal]` 이 아래에서 올라오며 나타난다(IntersectionObserver).
   ② 첫 화면에서 마우스를 따라 보라빛 조명이 움직인다(`--mx` · `--my`).
   ③ 미리보기 카드가 마우스 쪽으로 살짝 기운다.
   ★ 직접 쓴 파일이다 — 밖에서 받은 코드가 없고(P0-3), 서버로 아무것도 보내지 않는다.
   🚨 CSP 가 `script-src 'self'` 라 템플릿 안 인라인 스크립트는 돌지 않는다 — 그래서 파일로 둔다.
   ⛔ 이 파일이 안 돌아도 화면은 다 보인다 — 숨김은 `ld-js` 표시가 붙었을 때만 건다. 움직임 줄이기 설정이면 아무것도 하지 않는다. */
(function () {
  "use strict";
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var root = document.documentElement;

  /* ① 스크롤 등장 */
  var items = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && items.length) {
    root.classList.add("ld-js");
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add("is-in");
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    Array.prototype.forEach.call(items, function (el) { io.observe(el); });
  }

  /* ② 마우스를 따라오는 조명 · ③ 카드 기울기 */
  var zone = document.querySelector(".ld-hero-zone");
  var card = document.querySelector(".ld-demo");
  if (!zone) return;
  var raf = 0;
  zone.addEventListener("pointermove", function (ev) {
    if (raf) return;
    raf = window.requestAnimationFrame(function () {
      raf = 0;
      var r = zone.getBoundingClientRect();
      zone.style.setProperty("--mx", ((ev.clientX - r.left) / r.width * 100).toFixed(1) + "%");
      zone.style.setProperty("--my", ((ev.clientY - r.top) / r.height * 100).toFixed(1) + "%");
      if (card) {
        var c = card.getBoundingClientRect();
        var dx = (ev.clientX - (c.left + c.width / 2)) / c.width;
        var dy = (ev.clientY - (c.top + c.height / 2)) / c.height;
        card.style.setProperty("--rx", (-dy * 5).toFixed(2) + "deg");
        card.style.setProperty("--ry", (dx * 7).toFixed(2) + "deg");
      }
    });
  });
  zone.addEventListener("pointerleave", function () {
    if (card) { card.style.setProperty("--rx", "0deg"); card.style.setProperty("--ry", "0deg"); }
  });
})();
