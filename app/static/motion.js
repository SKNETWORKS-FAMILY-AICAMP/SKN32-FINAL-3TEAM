/* Decorative feedback never changes focus, scroll, visibility or form state. */
(() => {
  const main = document.querySelector('.user-main');
  if (!main || !Element.prototype.animate) return;
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  const active = new Map();
  const visible = element => element && element.getClientRects().length &&
    !element.closest('[hidden]') && getComputedStyle(element).visibility !== 'hidden';
  const fade = (element, duration = 220, delay = 0) => {
    if (preference.matches || document.hidden || !visible(element)) return;
    if (element.contains(document.activeElement)) return;
    active.get(element)?.cancel();
    // Opacity alone leaves sticky headers, panel heights and scroll offsets intact.
    const animation = element.animate([{opacity: .35}, {opacity: 1}], {
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

  // Below-fold content gets the same once-only entrance when it enters its scroll area.
  // Nothing is hidden while waiting for the observer; skipped motion never hides content.
  const panels = [...main.querySelectorAll(
    '.hm-card, .hm-stats, .hm-sect, .rv-input-pane, .rv-results-pane, .cl-product-section,' +
    '.gn-cand, .cp-card, .cl-history-table, .history-detail, .hg-purposes, .hg-guide, .hg-faq,' +
    '.hg-help-card, .csb-form, .csb-history, .csb-login, .mp-card, .auth-card'
  )];
  if ('IntersectionObserver' in window && !preference.matches) {
    const observer = new IntersectionObserver(entries => {
      let order = 0;
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        fade(entry.target, 320, Math.min(order++, 3) * 45);
      });
    }, {threshold: .08});
    panels.forEach(panel => observer.observe(panel));
    window.addEventListener('pagehide', () => observer.disconnect(), {once:true});
    preference.addEventListener('change', () => { if (preference.matches) observer.disconnect(); });
  } else if (!preference.matches) {
    panels.filter(visible).slice(0, 4).forEach((panel, index) => fade(panel, 300, index * 40));
  }

  // Opening a disclosure is feedback on the user's action, not an expanding height animation.
  document.addEventListener('toggle', event => {
    const details = event.target;
    if (!(details instanceof HTMLDetailsElement) || !details.open) return;
    if (!details.closest('.user-shell')) return;
    const body = details.querySelector('.fq-answer, .ws-profile-menu, .nt-panel');
    if (body) fade(body, 220);
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
      if (content) fade(content, 220);
    });
  });
})();
