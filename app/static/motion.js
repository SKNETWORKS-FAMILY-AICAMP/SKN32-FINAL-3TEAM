/* Decorative feedback never changes focus, scroll, visibility or form state. */
(() => {
  const main = document.querySelector('.user-main');
  if (!main || !Element.prototype.animate) return;
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  const active = new Map();
  const visible = element => element && element.getClientRects().length &&
    !element.closest('[hidden]') && getComputedStyle(element).visibility !== 'hidden';
  const fade = (element, duration = 180, delay = 0) => {
    if (preference.matches || document.hidden || !visible(element)) return;
    active.get(element)?.cancel();
    // Opacity alone leaves sticky headers, panel heights and scroll offsets intact.
    const animation = element.animate([{opacity: .78}, {opacity: 1}], {
      duration, delay, easing: 'ease-out'
    });
    active.set(element, animation);
    animation.finished.then(() => {
      if (active.get(element) === animation) active.delete(element);
    }).catch(() => {});
  };
  const cancel = () => { active.forEach(animation => animation.cancel()); active.clear(); };
  preference.addEventListener('change', () => { if (preference.matches) cancel(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) cancel(); });
  window.addEventListener('pagehide', cancel);

  // Content is visible even without JS. Only panels already in view get a small entrance fade.
  const panels = [...main.querySelectorAll(
    '.hm-cards, .hm-stats, .rv-input-pane, .rv-results-pane, .cl-product-section,' +
    '.gn-cands, .cp-card, .cl-history-table, .history-detail, .hg-purposes, .hg-guide, .hg-faq,' +
    '.csb-form, .csb-history, .csb-login'
  )].filter(element => {
    if (!visible(element)) return false;
    const box = element.getBoundingClientRect();
    return box.top < innerHeight && box.bottom > 0;
  });
  panels.slice(0, 4).forEach((panel, index) => fade(panel, 220, index * 25));

  // Opening a disclosure is feedback on the user's action, not an expanding height animation.
  document.addEventListener('toggle', event => {
    const details = event.target;
    if (!(details instanceof HTMLDetailsElement) || !details.open) return;
    if (!details.closest('.user-shell')) return;
    const body = details.querySelector('.fq-answer, .ws-profile-menu, .nt-panel');
    if (body) fade(body, 150);
  }, true);

  let lastSelection = '';
  const selectedToken = () => {
    const form = main.querySelector('#review-input-form');
    const editors = main.querySelector('.cl-detail-editors');
    return `${form?.dataset.selectedCopy || ''}:${editors?.hidden}`;
  };
  lastSelection = selectedToken();
  main.addEventListener('click', event => {
    if (!(event.target instanceof Element) || !event.target.closest(
      '[data-copy-nav], [data-result-tab], [data-edit-copy]'
    )) return;
    requestAnimationFrame(() => {
      const token = selectedToken();
      if (token === lastSelection) return;
      lastSelection = token;
      const panel = main.querySelector('.rv-results-pane');
      if (!panel) return;
      const content = [...panel.querySelectorAll('[data-result-copy], .cl-detail-editors')].find(visible);
      if (content) fade(content, 140);
    });
  });
})();
