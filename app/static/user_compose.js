/* app/static/user_compose.js — AI 광고 생성 · 섹션 편집기 · 소유자 ksr (2026-10-12)

   프로토타입 v7.2 `draft-editor`(섹션 목록 · 아트보드 · 인스펙터 · 확대/축소)를 옮긴 것이다.
   종류는 셋 — SNS 피드 · 상세페이지 · 배너 300×250. 상세페이지 섹션은 다섯(후킹 · 3분할 · 물품 설명 · 성분 · 필수 표기).
   ★ 직접 쓴 파일이다 — 밖에서 받은 코드가 없다(P0-3). 초안은 화면의 JSON 칸(`#de-data`)에서 읽는다.
   🚨 CSP 가 `script-src 'self'` 라 **`onclick` 같은 인라인 핸들러는 돌지 않는다** — 전부 `data-act` 위임으로 받는다.
   🔴 **판정을 지나지 않은 문구는 지면에 얹지 않는다** (D-63 · D-119). 칸마다 「적은 글」(`text`)과 「얹힌 글」(`live`)이
      따로 있고, 아트보드는 `live` 만 그린다. 고친 글은 서버 판정(`POST /u/compose/judge`)이 받아 줘야 `live` 가 된다.
      판정은 여기서 하지 않는다 — 금지어 목록 같은 것을 이 파일에 두지 않는다.
   🔴 사용자가 적은 글은 **전부 `esc()` 를 거쳐** HTML 에 들어간다 (P2-9).
   ⛔ 지어낸 예시 문구 · 함량을 미리 채우지 않는다 (D-147) — 넘어온 문구와 필수 병기 문구만 얹고 나머지는 빈칸이다.
   ⬜ 저장 · 공유 · 다운로드는 없다. 화면을 새로 고치면 편집한 내용이 사라진다. */
(function () {
  "use strict";

  var root = document.getElementById("de");
  var dataEl = document.getElementById("de-data");
  if (!root || !dataEl) return;
  var D = JSON.parse(dataEl.textContent);
  var JUDGE_URL = root.dataset.judgeUrl;

  /* KRDS 표준형 — 본문 17px · 줄 간격 150% · 접근성 최소 13px. 필수 병기 문구는 본문의 70% 이상 */
  var BODY = 17;
  var MIN_FONT = 13;
  var NOTICE_MIN = Math.round(BODY * 0.7);
  var GAP = 24;
  var PAD = D.key === "banner" ? 14 : 40;
  var ZOOMS = [0.3, 0.4, 0.55, 0.75, 1];
  var IMG_MAX = 5 * 1024 * 1024;

  var TYPES = {
    hook: { name: "후킹", layout: "image-full", imgs: 1, fields: [["head", "헤드라인"], ["sub", "보조 문구"]] },
    point3: {
      name: "핵심 소구점 3분할", layout: "grid-3", imgs: 3,
      fields: [["head", "헤드라인"], ["c1", "1번 문구"], ["c2", "2번 문구"], ["c3", "3번 문구"]],
    },
    spec: { name: "물품 설명", layout: "image-left", imgs: 1, fields: [["head", "헤드라인"], ["body", "본문"]] },
    fact: {
      name: "성분 · 함량", layout: "ledger", imgs: 0, fields: [["head", "헤드라인"], ["rows", "항목 · 값"]],
      hint: "한 줄에 하나씩 「이름: 값」으로 적어요. 표시면에 적힌 그대로 옮겨 주세요.",
    },
    notice: { name: "필수 표기", layout: "notice", imgs: 0, fields: [], locked: true },
    visual: { name: "비주얼", layout: "canvas", imgs: 1, fields: [["head", "헤드라인"], ["sub", "보조 문구"]] },
    caption: { name: "캡션 · 고지", layout: "caption", imgs: 0, fields: [["body", "캡션 본문"]] },
  };
  var SKELETON = {
    detail: ["hook", "point3", "spec", "fact", "notice"],
    sns: ["visual", "caption"],
    banner: ["visual", "caption"],
  };
  var EMPTY = {
    head: "헤드라인을 적어 주세요", sub: "보조 문구를 적어 주세요", body: "본문을 적어 주세요",
    c1: "소구점 1", c2: "소구점 2", c3: "소구점 3", rows: "항목: 값",
  };
  var LONG = { sub: 1, body: 1, rows: 1 };

  var S = {
    blocks: [],
    selected: null,
    zoom: D.key === "detail" ? 0.55 : D.key === "sns" ? 0.4 : 1,
    ratio: 0.7, // 본문 대비 필수 병기 문구 크기
    uid: 0,
  };

  /* ── 작은 도구 ─────────────────────────────────────────────── */

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function nl(v) { return esc(v).replace(/\n/g, "<br>"); }
  function $(id) { return document.getElementById(id); }
  function block(uid) {
    for (var i = 0; i < S.blocks.length; i++) if (S.blocks[i].uid === uid) return S.blocks[i];
    return null;
  }
  function isDoc() { return D.key === "detail"; }
  function say(text) { $("de-msg").textContent = text; }
  /* 병기 문구(`D.note`)를 지면에 그리는 섹션 — `notice`(필수 표기) · `caption`(캡션 · 고지) · 🆕 2026-10-15 (D-344 ⑤) */
  var NOTE_BLOCKS = { notice: true, caption: true };
  function noticeFont() { return Math.max(Math.round(BODY * S.ratio), MIN_FONT); }

  /* ── 넘어온 문구로 첫 칸을 채운다 ──────────────────────────────
     첫 문장 = 헤드라인, 나머지 = 보조 문구. 캡션은 전체. 서버가 판정해 넘긴 문장이라 바로 얹는다.
     `unsure` = 사전에 걸린 표현은 없지만 통과로 확정되지 않은 문장 — 「확인 필요」를 달고 얹는다. */
  function seed(type) {
    var c = D.copy || [];
    if (!c.length) return {};
    var join = function (list) {
      return {
        text: list.map(function (x) { return x.text; }).join(" "),
        unsure: list.some(function (x) { return x.unsure; }),
      };
    };
    if (type === "hook" || type === "visual") {
      var out = { head: join([c[0]]) };
      if (c.length > 1) out.sub = join(c.slice(1));
      return out;
    }
    if (type === "caption") return { body: join(c) };
    return {};
  }

  function makeBlock(type, seeded) {
    var t = TYPES[type];
    var b = {
      uid: "b" + (++S.uid), type: type,
      imgs: [], alts: [],
      text: {},   // 칸에 적은 글
      live: {},   // 판정을 지나 지면에 얹힌 글
      mark: {},   // 얹힌 글의 표시 — "" 통과 · "unsure" 확인 필요
      state: {},  // 칸의 지금 상태 — "" · "unsure" · "dirty" · "busy" · "ng" · "err"
      notes: {},  // 보류 · 오류일 때 보여 줄 까닭
    };
    for (var i = 0; i < t.imgs; i++) { b.imgs.push(null); b.alts.push(""); }
    var s = seeded ? seed(type) : {};
    t.fields.forEach(function (f) {
      var got = s[f[0]];
      b.text[f[0]] = got ? got.text : "";
      b.live[f[0]] = got ? got.text : "";
      b.mark[f[0]] = got && got.unsure ? "unsure" : "";
      b.state[f[0]] = b.mark[f[0]];
    });
    return b;
  }

  function count(b, what) {
    var n = 0;
    TYPES[b.type].fields.forEach(function (f) { if (b.state[f[0]] === what) n++; });
    return n;
  }

  /* ── 섹션 목록 ─────────────────────────────────────────────── */

  function renderList() {
    $("de-count").textContent = S.blocks.length + "개";
    $("de-blocks").innerHTML = S.blocks.map(function (b, i) {
      var t = TYPES[b.type];
      var wait = count(b, "dirty") + count(b, "busy") + count(b, "err");
      var ng = count(b, "ng");
      var unsure = count(b, "unsure");
      var filled = b.imgs.filter(Boolean).length;
      var dot = ng || wait ? " is-bad" : unsure ? " is-warn" : t.locked ? " is-lock" : "";
      var u = esc(b.uid);
      return '<div class="cp-ed-item' + (b.uid === S.selected ? " is-on" : "") + '" data-act="select" data-uid="' + u + '">' +
        '<div class="cp-ed-item-top"><span class="cp-ed-dot' + dot + '"></span><span>' + esc(t.name) + "</span>" +
        "<small>" + (t.locked ? "고정" : i + 1) + "</small></div>" +
        '<div class="cp-ed-item-sub">' +
        (t.imgs ? '<span class="' + (filled === t.imgs ? "is-ok" : "") + '">이미지 ' + filled + "/" + t.imgs + "</span>" : "") +
        (wait ? '<span class="is-bad">판정 대기 ' + wait + "</span>" : "") +
        (ng ? '<span class="is-bad">보류 ' + ng + "</span>" : "") +
        (unsure ? '<span class="is-warn">확인 필요 ' + unsure + "</span>" : "") +
        /* 🆕 2026-10-15 (D-344 ⑤) — 필수 병기 문구는 판정하지 않은 글자다(표지 글자는 서버의 `note_mark` · app/reasons.py) */
        (NOTE_BLOCKS[b.type] && D.note ? '<span class="is-warn">' + esc(D.note_mark) + "</span>" : "") +
        (t.locked ? "" :
          '<span class="cp-ed-item-ctl">' +
          '<button type="button" data-act="up" data-uid="' + u + '" aria-label="위로">↑</button>' +
          '<button type="button" data-act="down" data-uid="' + u + '" aria-label="아래로">↓</button>' +
          '<button type="button" data-act="remove" data-uid="' + u + '" aria-label="삭제">✕</button></span>') +
        "</div></div>";
    }).join("");
  }

  function renderAdd() {
    var keys = isDoc() ? ["hook", "point3", "spec", "fact"] : ["visual", "caption"];
    $("de-add").innerHTML =
      '<select id="de-add-pick" aria-label="추가할 섹션">' +
      keys.map(function (k) { return '<option value="' + k + '">' + esc(TYPES[k].name) + "</option>"; }).join("") +
      '</select><button type="button" data-act="add">+ 섹션 추가</button>';
  }

  /* ── 아트보드 ──────────────────────────────────────────────── */

  var STRIPE = "repeating-linear-gradient(45deg,var(--u-surface2) 0 10px,var(--u-line) 10px 12px)";

  function st(size, weight, color, margin) {
    return "margin:" + (margin || "0") + ";font-size:" + size + "px;font-weight:" + (weight || 400) +
      ";line-height:1.5;color:" + (color || "var(--u-ink)") + ";" + (size >= 24 ? "letter-spacing:-0.4px;" : "");
  }

  /* 얹힌 글만 그린다. 비었으면 흐린 안내 글자 — 지면에 나가는 글이 아니다.
     `lines` 를 주면 그 줄 수에서 자른다(규격이 고정인 캔버스) — 잘린 칸은 초안 검수가 센다 */
  function txt(b, f, style, lines) {
    var v = b.live[f];
    if (v && lines) {
      return '<p data-clamp="1" style="' + style + "display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:" +
        lines + ';overflow:hidden;">' + nl(v) + "</p>";
    }
    if (v) return '<p style="' + style + '">' + nl(v) + "</p>";
    return '<p style="' + style + 'opacity:.45;font-style:italic;">' + esc(EMPTY[f]) + "</p>";
  }

  function imgBox(b, i, style) {
    var src = b.imgs[i];
    var label = Math.max(12, Math.round(Math.min(D.w, 860) / 43));
    var inner = src
      ? '<img src="' + esc(src) + '" alt="' + esc(b.alts[i]) + '" style="width:100%;height:100%;object-fit:cover;display:block;">'
      : '<div style="width:100%;height:100%;background:' + STRIPE + ';display:flex;align-items:center;justify-content:center;">' +
        '<span style="font-size:' + label + "px;font-weight:600;color:var(--u-clay);background:var(--u-surface);padding:.4em .8em;border-radius:999px;\">이미지 " +
        (i + 1) + "</span></div>";
    return '<div data-act="img" data-uid="' + esc(b.uid) + '" data-i="' + i + '" style="' + style + ';overflow:hidden;cursor:pointer;">' + inner + "</div>";
  }

  function ledgerRows(text) {
    return String(text || "").split("\n").map(function (line) { return line.trim(); }).filter(Boolean)
      .map(function (line) {
        var at = line.search(/[:：]/);
        return at < 0 ? [line, ""] : [line.slice(0, at).trim(), line.slice(at + 1).trim()];
      });
  }

  function noticeBody(f) {
    return '<p style="' + st(f, 700, null, "0 0 8px") + '">[광고]</p>' +
      (D.note
        ? '<p style="' + st(f, 400) + '">' + nl(D.note) + "</p>"
        : '<p style="' + st(f, 400, "var(--u-clay)") + 'font-style:italic;">필수 병기 문구가 없어요</p>');
  }

  function blockHTML(b, W) {
    var t = TYPES[b.type];
    var P = PAD;
    var inner = W - P * 2;
    var cw;
    switch (t.layout) {
      case "image-full":
        return '<div style="position:relative;height:1040px;overflow:hidden;">' +
          imgBox(b, 0, "position:absolute;inset:0") +
          '<div style="position:absolute;left:0;right:0;bottom:0;height:58%;background:linear-gradient(transparent,rgba(0,0,0,.68));pointer-events:none;"></div>' +
          '<div style="position:absolute;left:' + P + "px;right:" + P + "px;bottom:" + (P + 16) + 'px;pointer-events:none;">' +
          txt(b, "head", st(44, 700, "#fff", "0 0 16px") + "text-shadow:0 2px 18px rgba(0,0,0,.55);", 4) +
          txt(b, "sub", st(19, 400, "rgba(255,255,255,.92)") + "text-shadow:0 1px 10px rgba(0,0,0,.5);", 6) +
          "</div></div>";

      case "grid-3":
        cw = Math.floor((inner - GAP * 2) / 3);
        return '<div style="padding:' + P + 'px;">' +
          txt(b, "head", st(32, 700, null, "0 0 " + (GAP + 8) + "px") + "text-align:center;") +
          '<div style="display:flex;gap:' + GAP + 'px;">' +
          [0, 1, 2].map(function (i) {
            return '<div style="width:' + cw + 'px;">' +
              imgBox(b, i, "width:" + cw + "px;height:" + cw + "px;border-radius:12px") +
              txt(b, "c" + (i + 1), st(19, 700, null, "16px 0 0") + "text-align:center;") + "</div>";
          }).join("") + "</div></div>";

      case "image-left":
        cw = Math.floor(inner * 0.52);
        return '<div style="padding:' + P + "px;display:flex;gap:" + (GAP + 8) + 'px;align-items:center;">' +
          imgBox(b, 0, "width:" + cw + "px;height:" + Math.round(cw * 1.15) + "px;border-radius:16px;flex-shrink:0") +
          '<div style="flex:1;min-width:0;">' +
          txt(b, "head", st(32, 700, null, "0 0 " + GAP + "px")) +
          txt(b, "body", st(17)) + "</div></div>";

      case "ledger": {
        var rows = ledgerRows(b.live.rows);
        var table = rows.length
          ? rows.map(function (r, i) {
              return '<div style="display:flex;' + (i ? "border-top:1px solid var(--u-line);" : "") + '">' +
                '<div style="width:34%;padding:16px 20px;background:var(--u-surface2);' + st(17, 700) + '">' + esc(r[0]) + "</div>" +
                '<div style="flex:1;padding:16px 20px;' + st(17) + '">' + esc(r[1]) + "</div></div>";
            }).join("")
          : '<div style="padding:16px 20px;' + st(17, 400, "var(--u-clay)") + 'font-style:italic;">항목과 값을 적어 주세요</div>';
        return '<div style="padding:' + P + 'px;">' +
          txt(b, "head", st(32, 700, null, "0 0 " + GAP + "px")) +
          '<div style="border:1px solid var(--u-line);border-radius:12px;overflow:hidden;">' + table + "</div></div>";
      }

      case "notice": {
        var f = noticeFont();
        return '<div style="padding:' + P + 'px;background:var(--u-surface2);">' +
          '<p style="' + st(13, 600, "var(--u-clay)", "0 0 14px") + 'letter-spacing:.06em;">필수 표기 · 삭제할 수 없는 영역</p>' +
          '<div style="border:1px solid var(--u-line);background:var(--u-surface);border-radius:12px;padding:20px 24px;">' +
          noticeBody(f) + "</div>" +
          '<p style="' + st(13, 400, "var(--u-clay)", "14px 0 0") + '">현재 ' + f + "px · 본문 " + BODY + "px 대비 " +
          Math.round((f / BODY) * 100) + "%</p></div>";
      }

      case "canvas": {
        var big = Math.round(D.w * 0.08);
        var tag = Math.max(11, Math.round(big * 0.34));
        var sub = Math.max(12, Math.round(big * 0.44));
        return '<div style="position:relative;width:' + D.w + "px;height:" + D.h + 'px;overflow:hidden;">' +
          imgBox(b, 0, "position:absolute;inset:0") +
          '<div style="position:absolute;left:0;right:0;bottom:0;height:62%;background:linear-gradient(transparent,rgba(0,0,0,.7));pointer-events:none;"></div>' +
          '<div style="position:absolute;left:0;right:0;top:0;padding:' + P + 'px;background:linear-gradient(rgba(0,0,0,.42),transparent);pointer-events:none;">' +
          '<span style="font-size:' + tag + 'px;font-weight:700;line-height:1.5;color:#fff;background:rgba(0,0,0,.55);border-radius:.4em;padding:.25em .7em;">[광고]</span></div>' +
          '<div style="position:absolute;left:' + P + "px;right:" + P + "px;bottom:" + Math.round(P * 1.5) + 'px;pointer-events:none;">' +
          txt(b, "head", "margin:0 0 .2em;font-size:" + big + "px;font-weight:700;line-height:1.3;color:#fff;letter-spacing:-.02em;text-shadow:0 2px 20px rgba(0,0,0,.6);", 3) +
          txt(b, "sub", "margin:0;font-size:" + sub + "px;font-weight:400;line-height:1.5;color:rgba(255,255,255,.94);text-shadow:0 1px 12px rgba(0,0,0,.5);", 2) +
          "</div></div>";
      }

      case "caption": {
        var cp = Math.max(P, 24);
        return '<div style="width:' + captionWidth() + "px;box-sizing:border-box;padding:" + cp + 'px;background:var(--u-surface);border:1px solid var(--u-line);border-radius:16px;">' +
          '<p style="' + st(13, 600, "var(--u-clay)", "0 0 12px") + 'letter-spacing:.06em;">고지 위치 · ' + esc(D.disclose) + "</p>" +
          '<p style="' + st(17, 700, "var(--u-signal-ink)", "0 0 12px") + '">[광고]</p>' +
          txt(b, "body", st(17, 400, null, "0 0 12px")) +
          (D.note ? '<p style="' + st(noticeFont(), 400) + '">' + nl(D.note) + "</p>" : "") +
          "</div>";
      }
    }
    return "";
  }

  function captionWidth() { return Math.max(360, Math.min(D.w, 720)); }

  function renderStage() {
    var z = S.zoom;
    var W = isDoc() ? D.w : Math.max(D.w, captionWidth());
    var body = S.blocks.map(function (b) {
      var on = b.uid === S.selected;
      return '<div data-act="select" data-art="' + esc(b.uid) + '" data-uid="' + esc(b.uid) + '" style="outline:' +
        (on ? "3px solid var(--u-signal)" : "none") + ";outline-offset:" + (isDoc() ? "-3px" : "3px") + ";cursor:pointer;" +
        (isDoc() ? "" : "width:max-content;margin-bottom:28px;border-radius:2px;") + '">' + blockHTML(b, W) + "</div>";
    }).join("");
    if (isDoc()) {
      body = '<div style="width:' + W + 'px;background:var(--u-surface);border:1px solid var(--u-line);overflow:hidden;">' + body + "</div>";
    }
    var stage = $("de-stage");
    var wrap = document.createElement("div");
    wrap.style.cssText = "transform:scale(" + z + ");transform-origin:top left;width:" + W + "px;";
    wrap.innerHTML = body;
    stage.innerHTML = "";
    stage.style.width = Math.round(W * z) + "px";
    stage.appendChild(wrap);
    /* 축소한 만큼 자리도 줄인다 — transform 은 자리를 줄이지 않는다 */
    stage.style.height = Math.round(wrap.offsetHeight * z) + "px";
    $("de-zoom").textContent = Math.round(z * 100) + "%";
  }

  /* ── 인스펙터 ──────────────────────────────────────────────── */

  function statusHTML(b, f) {
    var u = esc(b.uid);
    var judge = function (label, bad) {
      return '<button type="button"' + (bad ? ' class="is-bad"' : ' class="is-main"') +
        ' data-act="judge" data-uid="' + u + '" data-f="' + f + '">' + label + "</button>";
    };
    var notes = (b.notes[f] || []).map(function (n) { return "<div>⚠ " + esc(n) + "</div>"; }).join("");
    switch (b.state[f]) {
      case "dirty":
        return { cls: "", html: judge("판정") + "새로 적은 문구예요. 판정을 지나야 지면에 얹혀요." };
      case "busy":
        return { cls: "", html: "판정 중…" };
      case "ng":
        return {
          cls: " is-bad",
          html: judge("다시 판정", true) +
            (b.live[f] ? "이 문구는 얹지 않았어요. 지면에는 앞서 판정을 지난 문구가 그대로 있어요." : "지면에 얹지 않았어요.") + notes,
        };
      case "err":
        return { cls: " is-bad", html: judge("다시 판정", true) + notes };
      case "unsure":
        return { cls: " is-warn", html: "확인 필요 — 사전에 걸린 표현은 없지만, 통과로 확정된 것은 아니에요." };
    }
    if (!b.text[f]) return { cls: "", html: "비어 있어요 — 지면에 나가지 않아요." };
    return { cls: " is-ok", html: "✓ 판정 통과" };
  }

  function paintStatus(b, f) {
    var node = $("fs-" + b.uid + "-" + f);
    var input = $("fi-" + b.uid + "-" + f);
    if (node) {
      var s = statusHTML(b, f);
      node.className = "cp-ed-st" + s.cls;
      node.innerHTML = s.html;
    }
    if (input) input.classList.toggle("is-ng", b.state[f] === "ng");
    var len = $("fl-" + b.uid + "-" + f);
    if (len) len.textContent = b.text[f].length + "자";
  }

  function renderInspector() {
    var box = $("de-insp");
    var b = block(S.selected);
    if (!b) { box.innerHTML = '<p class="cp-ed-hint">섹션을 선택하세요</p>'; return; }
    var t = TYPES[b.type];
    var u = esc(b.uid);

    var imgs = b.imgs.map(function (src, i) {
      return '<div class="cp-ed-img"><div class="cp-ed-img-top">' +
        '<span class="cp-ed-thumb">' + (src ? '<img src="' + esc(src) + '" alt="">' : "") + "</span>" +
        "<div>이미지 " + (i + 1) + "<small>" + (src ? "등록됨" : "비어 있음") + "</small></div>" +
        '<button type="button" data-act="img" data-uid="' + u + '" data-i="' + i + '">' + (src ? "교체" : "올리기") + "</button>" +
        (src ? '<button type="button" data-act="imgclear" data-uid="' + u + '" data-i="' + i + '">제거</button>' : "") +
        "</div>" +
        '<input type="text" data-alt="' + i + '" data-uid="' + u + '" value="' + esc(b.alts[i]) +
        '" maxlength="200" placeholder="대체 텍스트 (화면 낭독기용)" aria-label="이미지 ' + (i + 1) + ' 대체 텍스트"></div>';
    }).join("");

    var fields = t.fields.map(function (pair) {
      var f = pair[0];
      var id = "fi-" + u + "-" + f;
      var common = ' id="' + id + '" data-field="' + f + '" data-uid="' + u + '" maxlength="' + D.max_text_len + '"';
      var input = LONG[f]
        ? "<textarea" + common + ' rows="' + (f === "rows" ? 5 : 3) + '" placeholder="' + esc(EMPTY[f]) + '">' + esc(b.text[f]) + "</textarea>"
        : '<input type="text"' + common + ' value="' + esc(b.text[f]) + '" placeholder="' + esc(EMPTY[f]) + '">';
      return '<div class="cp-ed-field"><div class="cp-ed-field-top"><label for="' + id + '">' + esc(pair[1]) + "</label>" +
        '<span id="fl-' + u + "-" + f + '"></span></div>' + input +
        '<div class="cp-ed-st" id="fs-' + u + "-" + f + '"></div></div>';
    }).join("");

    /* 🆕 2026-10-15 (D-344 ⑤) — 병기 문구를 그리는 섹션(필수 표기 · 캡션)에는 「판정하지 않은 글자」를 밝힌다 */
    var noteHint = "<h4>필수 병기 문구</h4>" +
      '<p class="cp-ed-hint">' + (D.note
        ? "카피 생성에서 넘어온 문구를 그대로 얹어요. 여기서는 고치지 않아요. " +
          "<b>" + esc(D.note_mark) + "</b> — 판정 엔진이 보지 않은 글자예요. 제품이 받은 인정 · 심사 내용과 같은지 확인해 주세요."
        : "넘어온 필수 병기 문구가 없어요. [광고] 표시만 들어가요.") + "</p>";
    var notice = b.type === "notice"
      ? noteHint +
        "<h4>필수 병기 문구 크기</h4>" +
        '<input type="range" id="de-ratio" min="50" max="100" value="' + Math.round(S.ratio * 100) + '" aria-label="필수 병기 문구 크기">' +
        '<p class="cp-ed-hint" id="de-ratio-note"></p>'
      : "";

    box.innerHTML =
      "<h3>" + esc(t.name) + (t.locked ? " · 고정" : "") + "</h3>" +
      '<p class="cp-ed-layout">' + esc(t.layout) + "</p>" +
      (t.imgs ? "<h4>이미지</h4>" + imgs : "") +
      (t.fields.length ? "<h4>문구 · 고치면 판정을 다시 받아요</h4>" + fields : "") +
      (t.hint ? '<p class="cp-ed-hint">' + esc(t.hint) + "</p>" : "") +
      (b.type === "caption" && D.note ? noteHint : "") +
      notice;

    t.fields.forEach(function (pair) { paintStatus(b, pair[0]); });
    paintRatio();
  }

  function paintRatio() {
    var note = $("de-ratio-note");
    if (!note) return;
    note.textContent = "본문 대비 " + Math.round(S.ratio * 100) + "% · 실제 " + noticeFont() + "px — 법정 하한 " +
      NOTICE_MIN + "px(본문의 70%)과 접근성 하한 " + MIN_FONT + "px 중 큰 값 아래로는 내려가지 않아요.";
  }

  function renderAll() { renderList(); renderStage(); renderInspector(); }

  /* ── 동작 ──────────────────────────────────────────────────── */

  function select(uid, scroll) {
    if (S.selected === uid) return;
    S.selected = uid;
    renderAll();
    if (!scroll) return;
    var el = root.querySelector('[data-art="' + uid + '"]');
    var cont = $("de-stagewrap");
    if (!el || !cont) return;
    var d = el.getBoundingClientRect().top - cont.getBoundingClientRect().top;
    cont.scrollTop = Math.max(0, cont.scrollTop + d - 24);
  }

  function setText(b, f, v) {
    b.text[f] = v;
    b.notes[f] = [];
    if (!v.trim()) {
      /* 글을 지우는 데는 판정이 필요 없다 — 바로 내린다 */
      b.live[f] = "";
      b.mark[f] = "";
      b.state[f] = "";
      renderStage();
    } else if (v === b.live[f]) {
      b.state[f] = b.mark[f];
    } else {
      b.state[f] = "dirty";
    }
    renderList();
    paintStatus(b, f);
  }

  function judge(b, f) {
    var text = b.text[f];
    if (!text.trim() || b.state[f] === "busy") return;
    b.state[f] = "busy";
    paintStatus(b, f);
    renderList();
    fetch(JUDGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      // 카피 생성에서 넘어온 분기 · 인정 문구를 같이 보낸다 — 서버가 같은 품목으로 판정하고 인정 문구는 뺀다
      body: JSON.stringify({ text: text, branch: D.branch || "", fixed: D.fixed || "" }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (res) {
        if (b.text[f] !== text) return; // 판정을 기다리는 동안 글이 바뀌었다 — 이 판정은 버린다
        if (res.state === "ok" || res.state === "unsure") {
          b.live[f] = text;
          b.mark[f] = res.state === "unsure" ? "unsure" : "";
          b.state[f] = b.mark[f];
          b.notes[f] = [];
          renderStage();
          say(res.state === "ok" ? "판정 통과 · 지면에 얹었어요" : "확인 필요 표시를 달고 지면에 얹었어요");
        } else if (res.state === "ng") {
          b.state[f] = "ng";
          b.notes[f] = (res.notes || []).map(function (n) { return "「" + n.text + "」 — " + n.why; });
          say("판정 보류 · 문구를 고쳐 주세요");
        } else {
          b.state[f] = "err";
          b.notes[f] = [res.state === "down" ? "판정 엔진에 연결하지 못했어요." : "판정 엔진이 아직 준비되지 않았어요."];
          say("판정을 받지 못했어요");
        }
      })
      .catch(function () {
        if (b.text[f] !== text) return;
        b.state[f] = "err";
        b.notes[f] = ["판정 요청이 실패했어요. 잠시 뒤 다시 눌러 주세요."];
        say("판정을 받지 못했어요");
      })
      .then(function () {
        renderList();
        if (S.selected === b.uid) paintStatus(b, f);
      });
  }

  function move(uid, dir) {
    var i = S.blocks.indexOf(block(uid));
    var j = i + dir;
    if (i < 0 || j < 0 || j >= S.blocks.length) return;
    if (TYPES[S.blocks[j].type].locked) { say("필수 표기 영역은 항상 마지막에 있어야 해요"); return; }
    S.blocks.splice(j, 0, S.blocks.splice(i, 1)[0]);
    renderList();
    renderStage();
  }

  function remove(uid) {
    var b = block(uid);
    if (!b || TYPES[b.type].locked) { say("이 영역은 지울 수 없어요"); return; }
    S.blocks = S.blocks.filter(function (x) { return x.uid !== uid; });
    if (S.selected === uid) S.selected = S.blocks.length ? S.blocks[0].uid : null;
    renderAll();
  }

  function add() {
    var pick = $("de-add-pick");
    if (!pick || !TYPES[pick.value] || TYPES[pick.value].locked) return;
    var nb = makeBlock(pick.value, false);
    var lockAt = -1;
    S.blocks.forEach(function (b, i) { if (lockAt < 0 && TYPES[b.type].locked) lockAt = i; });
    if (lockAt >= 0) S.blocks.splice(lockAt, 0, nb); else S.blocks.push(nb);
    S.selected = nb.uid;
    renderAll();
  }

  function zoom(d) {
    var i = ZOOMS.indexOf(S.zoom);
    if (i < 0) i = 2;
    S.zoom = ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, i + d))];
    renderStage();
  }

  function pickImage(b, i) {
    var input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (!file) return;
      if (file.type.indexOf("image/") !== 0) { say("이미지 파일만 올릴 수 있어요"); return; }
      if (file.size > IMG_MAX) { say("이미지는 5MB 까지 올릴 수 있어요"); return; }
      var reader = new FileReader();
      reader.onload = function () {
        b.imgs[i] = String(reader.result);
        S.selected = b.uid;
        renderAll();
        say("이미지를 넣었어요 — 서버로 보내지 않고 이 화면에만 있어요");
      };
      reader.onerror = function () { say("이미지를 읽지 못했어요"); };
      reader.readAsDataURL(file);
    });
    input.click();
  }

  /* 초안 검수 — 판정이 아니라 **빠진 것을 세는** 점검이다 */
  function audit() {
    var wait = 0, ng = 0, unsure = 0, noImg = 0, noAlt = 0;
    S.blocks.forEach(function (b) {
      wait += count(b, "dirty") + count(b, "busy") + count(b, "err");
      ng += count(b, "ng");
      unsure += count(b, "unsure");
      b.imgs.forEach(function (src, i) {
        if (!src) noImg++;
        else if (!b.alts[i].trim()) noAlt++;
      });
    });
    var cut = 0;
    Array.prototype.forEach.call($("de-stage").querySelectorAll("[data-clamp]"), function (el) {
      if (el.scrollHeight > el.clientHeight + 1) cut++;
    });
    var parts = [];
    if (cut) parts.push("지면에서 잘린 문구 " + cut + "칸");
    if (ng) parts.push("판정 보류 " + ng + "건");
    if (wait) parts.push("판정 대기 " + wait + "건");
    if (unsure) parts.push("확인 필요 " + unsure + "건");
    if (D.note) parts.push("필수 병기 문구 " + D.note_mark);
    if (noImg) parts.push("빈 이미지 " + noImg + "칸");
    if (noAlt) parts.push("대체 텍스트 누락 " + noAlt + "건");
    say("초안 검수 · " + (parts.length ? parts.join(" · ") : "빠진 것이 없어요"));
  }

  root.addEventListener("click", function (e) {
    var el = e.target.closest("[data-act]");
    if (!el || !root.contains(el)) return;
    var act = el.dataset.act;
    var b = el.dataset.uid ? block(el.dataset.uid) : null;
    var i = Number(el.dataset.i);
    switch (act) {
      case "select": if (b) select(b.uid, !el.dataset.art); break;
      case "up": if (b) move(b.uid, -1); break;
      case "down": if (b) move(b.uid, 1); break;
      case "remove": if (b) remove(b.uid); break;
      case "add": add(); break;
      case "zoom": zoom(Number(el.dataset.d)); break;
      case "audit": audit(); break;
      case "judge": if (b) judge(b, el.dataset.f); break;
      case "img": if (b) pickImage(b, i); break;
      case "imgclear": if (b) { b.imgs[i] = null; b.alts[i] = ""; renderAll(); } break;
    }
  });

  root.addEventListener("input", function (e) {
    var el = e.target;
    if (el.id === "de-ratio") {
      S.ratio = Number(el.value) / 100;
      renderStage();
      paintRatio();
      return;
    }
    var b = el.dataset && el.dataset.uid ? block(el.dataset.uid) : null;
    if (!b) return;
    if (el.dataset.field) setText(b, el.dataset.field, el.value);
    else if (el.dataset.alt != null) b.alts[Number(el.dataset.alt)] = el.value;
  });

  /* ── 시작 ──────────────────────────────────────────────────── */

  S.blocks = (SKELETON[D.key] || []).map(function (type) { return makeBlock(type, true); });
  S.selected = S.blocks.length ? S.blocks[0].uid : null;
  /* 처음 배율은 아트보드 칸에 들어가는 가장 큰 단계로 낮춘다 — 좁은 화면에서 가로 스크롤부터 보이지 않게 */
  (function fit() {
    var room = $("de-stagewrap").clientWidth - 56;
    var width = isDoc() ? D.w : Math.max(D.w, captionWidth());
    var i = ZOOMS.indexOf(S.zoom);
    while (i > 0 && width * ZOOMS[i] > room) i--;
    S.zoom = ZOOMS[i];
  })();
  renderAdd();
  renderAll();
  say(D.label + " 골격 " + S.blocks.length + "개 섹션으로 만들었어요");
})();
