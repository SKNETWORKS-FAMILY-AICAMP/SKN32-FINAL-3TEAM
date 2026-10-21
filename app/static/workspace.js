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
  // 🔄 2026-10-21 (ksr) — 이력 상세는 오른쪽에서 밀려 나오고 목록은 왼쪽으로 밀린다(덮지 않는다).
  //    링크(`?open_id=`)는 그대로 두고, 스크립트가 있으면 페이지를 다시 그리지 않고 상세만 갈아 끼운다
  const layout = document.querySelector('.history-layout');
  if(layout){
    const drawerOf = () => layout.querySelector('.history-detail');
    const setUrl = href => {const url=new URL(href,location.href);history.replaceState(null,'',url);};
    const close = event => {
      event?.preventDefault();
      const drawer = drawerOf();if(!drawer||drawer.classList.contains('is-closing'))return;
      drawer.classList.add('is-closing');
      const done = () => drawer.remove();
      drawer.addEventListener('transitionend',done,{once:true});setTimeout(done,400);
      layout.querySelectorAll('.history-row-open').forEach(row=>{row.classList.remove('history-row-open');const c=row.querySelector('.history-row-chevron');if(c)c.textContent='›';});
      const url=new URL(location.href);url.searchParams.delete('open_id');history.replaceState(null,'',url);
    };
    const open = async (row, event) => {
      event.preventDefault();
      try{
        const page=new DOMParser().parseFromString(await (await fetch(row.href,{credentials:'same-origin'})).text(),'text/html');
        const list=page.querySelector('.history-layout .cl-history-table'),fresh=page.querySelector('.history-layout .history-detail');
        if(list)layout.querySelector('.cl-history-table')?.replaceWith(document.importNode(list,true));
        setUrl(row.href);
        if(!fresh){close();return;}
        const drawer=drawerOf();
        if(drawer&&!drawer.classList.contains('is-closing')){drawer.replaceChildren(...[...fresh.childNodes].map(n=>document.importNode(n,true)));drawer.scrollTop=0;}
        else{
          drawer?.remove();
          const node=document.importNode(fresh,true);node.classList.add('is-entering');layout.append(node);
          requestAnimationFrame(()=>requestAnimationFrame(()=>node.classList.remove('is-entering')));
        }
        drawerOf()?.focus({preventScroll:true});
      }catch{location.href=row.href;}
    };
    layout.addEventListener('click',event=>{
      const row=event.target.closest('a.history-row');if(row){open(row,event);return;}
      if(event.target.closest('[data-close-history]'))close(event);
    });
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&drawerOf())close(event);});
    // 위 메뉴줄이 스크롤로 올라가면 상세가 그만큼 위로 붙어 화면 높이를 꽉 채운다(빈 띠가 남지 않게).
    // 본문이 확대(`zoom`)돼 있어 고정 위치도 그 배율로 늘어난다 — 배율로 나눠 맞춘다
    const nav=document.querySelector('.user-topnav'),main=layout.closest('.user-main');
    const place=()=>{
      const drawer=drawerOf();if(!drawer)return;
      if(innerWidth<768||!nav){drawer.style.top='';return;}
      const zoom=parseFloat(getComputedStyle(main||document.body).zoom)||1;
      drawer.style.top=Math.max(0,nav.getBoundingClientRect().bottom)/zoom+'px';
    };
    addEventListener('scroll',place,{passive:true});addEventListener('resize',place);
    new MutationObserver(place).observe(layout,{childList:true});
    place();
    drawerOf()?.focus({preventScroll:true});
  }
})();
(() => {
 const input=document.querySelector('#prompt'),head=document.querySelector('[data-preview-head]'),format=document.querySelector('[data-preview-format]');
 if(!input||!head)return;
 const update=()=>{
   const lines=input.value.trim().split('\n');
   head.textContent=lines[0]||'헤드라인을 적어 주세요';
   const sub=document.querySelector('[data-preview-sub]');
   if(sub)sub.textContent=lines.slice(1).join(' ')||'보조 문구를 적어 주세요';
   const caption=document.querySelector('[data-preview-caption]');
   if(caption)caption.textContent=input.value.trim()||'캡션 본문을 적어 주세요';
   const selected=document.querySelector('input[name=ad_format]:checked');
   const specs={'f-sns':'1080 × 1080 · 1:1','f-detail':'860px · 세로 가변','f-banner':'300 × 250 · 6:5'};
   if(format)format.textContent=(selected?.value||'')+' · '+(specs[selected?.id]||'')+' · 배치 예시';
   const paper=document.querySelector('.ws-layout-paper');
   if(paper&&paper.dataset.format!==selected?.id){paper.scrollTop=0;paper.dataset.format=selected?.id||'';}
 };
 input.addEventListener('input',update);document.querySelectorAll('input[name=ad_format]').forEach(r=>r.addEventListener('change',update));update();
})();
document.querySelectorAll('a[href="#gen-form"]').forEach(link=>link.addEventListener('click',()=>{const editor=document.querySelector('#product-editor');if(editor)editor.open=true;}));
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.ws-profile[open],.nt[open]').forEach(d=>{d.open=false;d.querySelector('summary')?.focus();});});
document.addEventListener('click',e=>document.querySelectorAll('.ws-profile[open]').forEach(d=>{if(!d.contains(e.target))d.open=false;}));
