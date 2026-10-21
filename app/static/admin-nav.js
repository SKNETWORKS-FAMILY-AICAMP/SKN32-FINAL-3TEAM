/* Progressive enhancement: links and native details work without this file. */
(() => {
  const nav = document.getElementById('admin-navigation');
  if (!nav) return;
  const groups = [...nav.querySelectorAll('details')];
  const toggle = document.querySelector('.admin-menu-toggle');
  const mobile = window.matchMedia('(max-width: 700px)');
  const hover = window.matchMedia('(hover: hover) and (pointer: fine)');
  let timer;
  const close = (group) => {
    group.open = false;
    group.dataset.pinned = 'false';
    group.querySelector('summary').setAttribute('aria-expanded', 'false');
  };
  const closeAll = () => { clearTimeout(timer); groups.forEach(close); };
  const open = (group) => {
    clearTimeout(timer);
    groups.filter(other => other !== group).forEach(close);
    group.open = true;
    group.querySelector('summary').setAttribute('aria-expanded', 'true');
  };
  groups.forEach((group, index) => {
    const trigger = group.querySelector('summary');
    const panel = group.querySelector('.admin-nav-sub-list');
    panel.id = `admin-subnav-${index}`;
    trigger.setAttribute('aria-controls', panel.id);
    trigger.setAttribute('aria-expanded', 'false');
    trigger.addEventListener('click', event => {
      event.preventDefault();
      if (group.dataset.pinned === 'true') close(group);
      else { open(group); group.dataset.pinned = 'true'; }
    });
    group.addEventListener('pointerenter', () => {
      if (hover.matches && !mobile.matches) open(group);
    });
    group.addEventListener('pointerleave', () => {
      if (hover.matches && !mobile.matches && group.dataset.pinned !== 'true') {
        timer = setTimeout(() => {
          if (!group.contains(document.activeElement)) close(group);
        }, 180);
      }
    });
    group.addEventListener('focusout', event => {
      if (!group.contains(event.relatedTarget)) close(group);
    });
    group.addEventListener('keydown', event => {
      const links = [...panel.querySelectorAll('a')];
      if (event.key === 'Escape') {
        event.preventDefault(); event.stopPropagation(); close(group); trigger.focus();
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault(); open(group);
        const current = links.indexOf(document.activeElement);
        const next = current < 0 ? (event.key === 'ArrowDown' ? 0 : links.length - 1)
          : (current + (event.key === 'ArrowDown' ? 1 : -1) + links.length) % links.length;
        links[next].focus();
      }
    });
  });
  toggle.hidden = false;
  document.documentElement.classList.add('admin-nav-ready');
  const closeMobile = () => {
    nav.classList.remove('is-expanded'); toggle.setAttribute('aria-expanded', 'false');
    closeAll();
  };
  toggle.addEventListener('click', () => {
    const expanded = nav.classList.toggle('is-expanded');
    toggle.setAttribute('aria-expanded', String(expanded));
    if (!expanded) closeAll();
  });
  document.addEventListener('click', event => {
    if (!nav.contains(event.target) && !toggle.contains(event.target)) closeMobile();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && mobile.matches && nav.classList.contains('is-expanded')) {
      closeMobile(); toggle.focus();
    }
  });
  mobile.addEventListener('change', closeMobile);
  window.addEventListener('pagehide', closeAll);
})();
