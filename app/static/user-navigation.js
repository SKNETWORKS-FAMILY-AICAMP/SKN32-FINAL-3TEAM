/* Navigation only: review, theme and notification forms keep their own handlers. */
(() => {
  const header = document.querySelector('.user-topnav');
  const toggle = header?.querySelector('.cl-user-menu-toggle');
  const menu = header?.querySelector('.cl-user-navigation');
  if (!toggle || !menu) return;
  toggle.hidden = false;
  header.classList.add('cl-user-nav-ready');
  const closeMenu = () => {
    menu.classList.remove('is-expanded');
    toggle.setAttribute('aria-expanded', 'false');
  };
  toggle.addEventListener('click', () => {
    const open = menu.classList.toggle('is-expanded');
    toggle.setAttribute('aria-expanded', String(open));
  });
  const help = header.querySelector('.cl-user-help');
  document.addEventListener('click', event => {
    if (help && !help.contains(event.target)) help.open = false;
    if (!header.contains(event.target)) closeMenu();
  });
  header.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (help?.open) {
      help.open = false;
      help.querySelector('summary').focus();
    } else if (menu.classList.contains('is-expanded')) {
      closeMenu();
      toggle.focus();
    }
  });
  window.matchMedia('(max-width:1250px)').addEventListener('change', closeMenu);
})();
