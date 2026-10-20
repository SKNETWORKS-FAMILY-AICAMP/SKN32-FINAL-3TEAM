/* FAQ filtering stays in this page. Search text is not sent or stored. */
(() => {
  const tools = document.querySelector('[data-faq-tools]');
  if (!tools) return;
  const query = tools.querySelector('input');
  const categories = [...tools.querySelectorAll('[data-faq-category]')];
  const items = [...document.querySelectorAll('[data-faq-item]')];
  const status = document.querySelector('[data-faq-status]');
  const count = document.querySelector('[data-faq-count]');
  const empty = document.querySelector('[data-faq-empty]');
  let category = 'all';
  const normalize = value => value.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, ' ').trim();
  const update = () => {
    const words = normalize(query.value).split(' ').filter(Boolean);
    let matches = 0;
    items.forEach(item => {
      const text = normalize(item.textContent);
      const visible = (category === 'all' || item.dataset.category === category) && words.every(word => text.includes(word));
      item.hidden = !visible;
      if (!visible) item.open = false;
      if (visible) matches++;
    });
    categories.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.faqCategory === category)));
    count.textContent = `${matches}개`;
    status.textContent = words.length ? `검색 결과 ${matches}개` : '';
    empty.hidden = matches !== 0;
  };
  categories.forEach(button => button.addEventListener('click', () => {
    category = button.dataset.faqCategory;
    update();
  }));
  query.addEventListener('input', update);
  tools.querySelector('form').addEventListener('submit', event => { event.preventDefault(); update(); });
  document.querySelector('[data-faq-reset]').addEventListener('click', () => {
    category = 'all';
    query.value = '';
    update();
    query.focus({preventScroll: true});
  });
  tools.hidden = false;
  update();
})();
