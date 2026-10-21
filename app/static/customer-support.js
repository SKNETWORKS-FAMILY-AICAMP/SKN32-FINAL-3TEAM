(() => {
  const form = document.querySelector('[data-support-form]');
  if (!form) return;
  const body = form.querySelector('textarea');
  const count = form.querySelector('[data-support-count]');
  const update = () => { count.textContent = body.value.length; };
  body.addEventListener('input', update);
  update();
})();
