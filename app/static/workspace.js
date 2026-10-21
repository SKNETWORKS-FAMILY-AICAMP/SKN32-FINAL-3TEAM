/* Progressive enhancements: all original POST forms remain usable without JavaScript. */
(() => {
  const editor = document.querySelector('#product-editor');
  document.querySelector('[data-edit-product]')?.addEventListener('click', () => {
    editor.open = true;
    editor.scrollIntoView({block:'start', behavior:'smooth'});
    editor.querySelector('input:not([type=radio]):not([type=hidden]),textarea')?.focus();
  });
  document.querySelectorAll('.gn-cands').forEach((grid, group) => {
    const cards = [...grid.querySelectorAll('.gn-cand')].filter(card => card.querySelector('form[action="/u/compose"]'));
    if (!cards.length) return;
    const bar = document.createElement('div'); bar.className = 'ws-selection';
    const info = document.createElement('div');
    const label = document.createElement('b'); label.textContent = '선택한 문구';
    const text = document.createElement('p'); text.setAttribute('aria-live','polite');
    const go = document.createElement('button'); go.type = 'button'; go.textContent = '이 문구로 광고 만들기 →';
    info.append(label,text); bar.append(info,go); grid.after(bar);
    let selected;
    cards.forEach((card,index) => {
      const form = card.querySelector('form[action="/u/compose"]');
      const body = form.elements.namedItem('prompt').value;
      const choice = document.createElement('label'); choice.className = 'ws-choice';
      const radio = document.createElement('input'); radio.type = 'radio'; radio.name = `copy-choice-${group}`;
      // Attribute used only for styling; each group retains independent selection.
      radio.setAttribute('data-copy-choice','');
      // 2026-10-20 (lse) — 카드 이름은 템플릿이 단 A안 · B안 · C안(data-name). 없으면 종전대로 「후보 N」
      const name = card.dataset.name || ('후보 ' + (index + 1));
      radio.setAttribute('aria-label', name + ' 선택');
      const number = document.createElement('span'); number.className = 'cl-pill'; number.textContent = name;
      choice.append(number, radio); card.prepend(choice);
      const select = () => {selected=form; text.textContent=body;label.textContent='선택한 문구 · '+name;};
      card.addEventListener('click',event=>{if(event.target.closest('button,details,a,form,input,label'))return;radio.checked=true;select();});
      radio.addEventListener('change',select);
      const metadata = [...card.children].filter(el => el.matches('.gn-meta,.gn-chips'));
      const detail = document.createElement('details'); detail.className='cl-candidate-detail';
      const detailTitle=document.createElement('summary'); detailTitle.textContent='검수 결과 보기'; detail.append(detailTitle);
      metadata.forEach(el=>detail.append(el));
      const footer=document.createElement('div');footer.className='cl-candidate-footer';footer.append(detail);
      card.insertBefore(footer,form);
      const copy = document.createElement('button'); copy.className='ws-copy'; copy.type='button'; copy.textContent='문구 복사';
      copy.addEventListener('click',async () => {
        try {await navigator.clipboard.writeText(body);copy.textContent='복사 완료';}
        catch {copy.textContent='복사할 수 없어요 · 문구를 직접 선택해주세요';}
      });
      footer.append(copy);
      if(index===0){radio.checked=true;select();}
    });
    go.addEventListener('click',()=>selected?.requestSubmit());
    grid.classList.add('ws-enhanced');
  });
  const drawer = document.querySelector('.history-detail');
  if(drawer){
    drawer.focus({preventScroll:true});
    const close = event => {
      event.preventDefault();drawer.remove();
      const url = new URL(location.href);url.searchParams.delete('open_id');history.replaceState(null,'',url);
      document.querySelector('.history-row-open')?.focus();
    };
    drawer.querySelector('[data-close-history]')?.addEventListener('click',close);
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&drawer.isConnected)close(event);});
  }
})();
(() => {
 const input=document.querySelector('#prompt'),head=document.querySelector('[data-preview-head]'),format=document.querySelector('[data-preview-format]');
 if(!input||!head)return;
 const update=()=>{const lines=input.value.trim().split('\n');head.textContent=lines[0]||'광고 문구를 입력해주세요';const sub=document.querySelector('[data-preview-sub]');if(sub)sub.textContent=lines.slice(1).join(' ')||'보조 문구 영역';format.textContent=(document.querySelector('input[name=ad_format]:checked')?.value||'')+' · 배치 예시';};
 input.addEventListener('input',update);document.querySelectorAll('input[name=ad_format]').forEach(r=>r.addEventListener('change',update));update();
})();
document.querySelectorAll('a[href="#gen-form"]').forEach(link=>link.addEventListener('click',()=>{const editor=document.querySelector('#product-editor');if(editor)editor.open=true;}));
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.ws-profile[open],.nt[open]').forEach(d=>{d.open=false;d.querySelector('summary')?.focus();});});
document.addEventListener('click',e=>document.querySelectorAll('.ws-profile[open]').forEach(d=>{if(!d.contains(e.target))d.open=false;}));
