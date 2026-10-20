/* app/static/review_score.js — 검수 결과 맨 위 요약판 · 소유자 lse (🆕 2026-10-20)

   결과 머리(`.cl-result-overview`) 안에 「문장 N개 · 사용 불가 · 조건부 · 확인 필요 · 통과」 수와 색 막대를 그린다.
   ★ 화면에 이미 그려진 문장 카드(`.rv-sent.rv-t-<톤>`)를 셀 뿐이다 — 판정을 바꾸지 않고 서버로 아무것도 보내지 않는다.
   ★ 직접 쓴 파일이다(P0-3) · CSP `script-src 'self'` 라 인라인으로 옮기지 않는다. 이 파일이 안 돌아도 결과는 그대로 보인다. */
(function () {
  "use strict";
  var TONES = [
    ["bad", "사용 불가"],
    ["orange", "조건부"],
    ["hold", "확인 필요"],
    ["ok", "통과"],
  ];

  function scope(overview) {
    /* 같은 결과 묶음 — 품목 분기 결과(`.rv-res`)가 있으면 그 안, 없으면 결과 카드 */
    return overview.closest(".rv-res") || overview.closest(".cl-result-copy") || overview.parentElement;
  }

  function draw(overview) {
    if (overview.querySelector(".rv-score")) return;
    var box = scope(overview);
    var sents = box ? box.querySelectorAll(".rv-sent") : [];
    if (!sents.length) return;
    var counts = {};
    TONES.forEach(function (t) { counts[t[0]] = 0; });
    Array.prototype.forEach.call(sents, function (s) {
      TONES.forEach(function (t) { if (s.classList.contains("rv-t-" + t[0])) counts[t[0]] += 1; });
    });
    var total = sents.length;
    var el = document.createElement("div");
    el.className = "rv-score";
    var head = document.createElement("p");
    head.className = "rv-score-head";
    head.innerHTML = "<b>" + total + "</b>문장 검수";
    var bar = document.createElement("div");
    bar.className = "rv-score-bar";
    bar.setAttribute("aria-hidden", "true");
    var list = document.createElement("ul");
    list.className = "rv-score-list";
    TONES.forEach(function (t) {
      var n = counts[t[0]];
      if (n) {
        var seg = document.createElement("i");
        seg.className = "rv-seg-" + t[0];
        seg.style.flexGrow = String(n);
        bar.appendChild(seg);
      }
      var li = document.createElement("li");
      li.className = "rv-sc-" + t[0] + (n ? "" : " is-zero");
      li.innerHTML = "<span></span>" + t[1] + " <b>" + n + "</b>";
      list.appendChild(li);
    });
    el.appendChild(head);
    el.appendChild(bar);
    el.appendChild(list);
    overview.appendChild(el);
    overview.classList.add("has-score");
  }

  Array.prototype.forEach.call(document.querySelectorAll(".cl-result-overview"), draw);

  /* 🆕 2026-10-20 — 「예시 문구로 바로 해 보기」: 지금 보이는 문구 칸(없으면 첫 칸)에 글자를 채운다. 제출은 사용자가 한다 */
  Array.prototype.forEach.call(document.querySelectorAll("[data-fill-sample]"), function (btn) {
    btn.addEventListener("click", function () {
      var areas = Array.prototype.filter.call(document.querySelectorAll('textarea[name="text"]'), function (t) {
        return t.offsetParent !== null;
      });
      var ta = areas[0] || document.querySelector('textarea[name="text"]');
      if (!ta) return;
      ta.value = btn.getAttribute("data-fill-sample");
      ta.dispatchEvent(new Event("input", { bubbles: true }));
      ta.focus();
    });
  });
})();
