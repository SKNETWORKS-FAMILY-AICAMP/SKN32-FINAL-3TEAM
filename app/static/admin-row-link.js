/* 표의 한 줄을 눌러도 상세로 간다 — `<tr data-row-href="…">` (2026-10-22 · psj).
   ★ 덧붙임일 뿐이다 — 스크립트가 없어도 줄 안의 링크(이름)로 간다. 키보드는 그 링크로 간다(줄에 tabindex 를 두지 않는다).
   ★ 줄 안의 링크 · 버튼 · 입력을 누른 것은 그대로 둔다. 글자를 드래그해 고른 것은 이동으로 치지 않는다.
   ★ Ctrl/⌘ · 가운데 버튼은 새 탭 — 브라우저 링크와 같은 손버릇. CSP script-src 'self' 라 인라인 대신 이 파일이다. */
(() => {
  const skip = 'a, button, input, select, textarea, label, summary';
  const go = (row, event) => {
    const href = row.dataset.rowHref;
    if (!href || !href.startsWith('/admin/')) return; // 관리자 화면 안의 주소만
    if (event.ctrlKey || event.metaKey || event.button === 1) window.open(href, '_blank', 'noopener');
    else window.location.assign(href);
  };
  document.addEventListener('click', event => {
    const row = event.target.closest('tr[data-row-href]');
    if (!row || event.target.closest(skip)) return;
    if (String(window.getSelection && window.getSelection()).trim()) return;
    go(row, event);
  });
  document.addEventListener('auxclick', event => {
    const row = event.target.closest('tr[data-row-href]');
    if (row && event.button === 1 && !event.target.closest(skip)) go(row, event);
  });
})();
