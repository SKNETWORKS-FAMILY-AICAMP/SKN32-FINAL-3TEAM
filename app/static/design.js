document.documentElement.classList.add('cl-js');
/* The add operation is server-rendered; carry only the input scroll offset across it. */
(() => {
  const list=document.querySelector('.cl-input-scroll');
  const form=list?.closest('form');
  if(!form)return;
  const key='copylane-review-add-scroll';
  form.addEventListener('submit',event=>{
    try{
      sessionStorage.removeItem(key);
      if(event.submitter?.name!=='op'||event.submitter.value!=='add')return;
      sessionStorage.setItem(key,JSON.stringify({
        at:Date.now(),top:list.scrollTop,x:window.scrollX,y:window.scrollY,
        count:[...form.elements].filter(el=>el.matches('textarea[name="text"]')).length,
        selected:form.dataset.selectedCopy||'1',
        destination:new URL(form.action,location.href).pathname
      }));
    }catch{/* Storage may be unavailable; the server form remains usable. */}
  });
  let saved;
  try{saved=JSON.parse(sessionStorage.getItem(key)||'null');sessionStorage.removeItem(key);}catch{return;}
  const count=form.querySelectorAll('textarea[name="text"]').length;
  if(!saved||saved.destination!==location.pathname||Date.now()-saved.at>30000||
     ![saved.top,saved.x,saved.y,saved.count,saved.at].every(Number.isFinite)||
     (count!==saved.count+1&&count!==saved.count))return;
  const restore=()=>{
    list.scrollTop=Math.max(0,saved.top);
    window.scrollTo({left:saved.x,top:saved.y,behavior:'instant'});
  };
  window.addEventListener('pageshow',()=>{window.dispatchEvent(new CustomEvent('review:restore-copy',{detail:saved.selected}));restore();requestAnimationFrame(restore);},{once:true});
})();
/* Explicit review steps progressively enhance the existing server-provided branches. */
(() => {
  const panel=document.querySelector('.rv-results-pane');
  if(panel){
    const rounds=[...panel.querySelectorAll('.rv-round')];
    const tabs=[...panel.querySelectorAll('[data-result-tab]')];
    const sections=[...panel.querySelectorAll('[data-result-copy]')];
    const form=document.getElementById('review-input-form');
    const cards=[...document.querySelectorAll('[data-input-copy]')];
    const navs=[...document.querySelectorAll('[data-copy-nav]')];
    const editors=panel.querySelector('.cl-detail-editors');
    const mainCard=panel.querySelector('.rv-card');
    const selectionKey='copylane-review-focused-copy';
    let restoredSelection;
    try{const saved=JSON.parse(sessionStorage.getItem(selectionKey)||'null');sessionStorage.removeItem(selectionKey);if(saved&&saved.path===location.pathname&&Date.now()-saved.at<90000&&cards.some(c=>c.dataset.inputCopy===saved.number))restoredSelection=saved.number;}catch{}
    let selectedCopy=restoredSelection||tabs[0]?.dataset.resultTab||cards[0]?.dataset.inputCopy;
    let editing=false,focusReady=false;
    if(editors&&form){
      cards.forEach(card=>{card.querySelectorAll('textarea,button,input,select').forEach(control=>control.setAttribute('form',form.id));editors.append(card);});
      document.querySelector('.cl-focus-review')?.classList.add('cl-focus-ready');
    }
    const visible=el=>el.getClientRects().length>0;
    const currentRounds=()=>rounds.filter(r=>getComputedStyle(r).display!=='none');
    function updateFocus(){
      if(!focusReady||!editors)return;
      const card=cards.find(c=>c.dataset.inputCopy===selectedCopy);
      const text=card?.querySelector('textarea')?.value||'';
      const section=sections.find(s=>s.dataset.resultCopy===selectedCopy);
      form.dataset.selectedCopy=selectedCopy;
      panel.querySelector('[data-focus-copy-title]').textContent='문구 '+selectedCopy;
      navs.forEach(nav=>{const on=nav.dataset.copyNav===selectedCopy;nav.setAttribute('aria-pressed',String(on));nav.classList.toggle('is-active',on);});
      cards.forEach(c=>{c.hidden=c!==card||!editing;});
      editors.hidden=!editing;
      const enginePending=mainCard?.hasAttribute('data-engine-state');
      if(mainCard)mainCard.hidden=!section&&!enginePending;
      const quote=panel.querySelector('[data-focus-quote]');quote.hidden=editing||!!section;quote.textContent=text||'문구를 입력해주세요.';
      panel.querySelector('[data-focus-unsent]').hidden=!!section||enginePending;
      panel.querySelectorAll('[data-edit-copy]').forEach(button=>{button.textContent=editing?'편집 닫기':'문구 편집';button.setAttribute('aria-expanded',String(editing));});
      const judge=panel.querySelector('[data-focus-judge]');judge.value='judge:'+selectedCopy;judge.textContent=section?'문구 다시 검수하기':'문구 검수하기';judge.classList.toggle('is-quiet',!!section&&card?.dataset.dirty!=='true');
      const pending=section?.dataset.pending==='true';
      panel.querySelector('[data-focus-action-note]').textContent=pending?'이 문구에 필요한 조건을 확인해주세요.':card?.dataset.dirty==='true'?'수정한 문구를 다시 검수해주세요.':section?'검수 결과는 법적 확정 판단이 아니에요.':'선택한 문구를 검수해보세요.';
      if(section){
        const active=section.querySelector('.rv-res.is-shown')||section;
        const sentences=[...active.querySelectorAll('.rv-sent')].filter(visible);
        const overview=active.querySelector('.cl-result-overview');
        const firstText=sentences[0]?.querySelector('.rv-text');
        if(sentences.length===1&&overview&&firstText&&overview.parentElement!==sentences[0])firstText.after(overview);
      }
    }
    function selectCopy(number,focus=false){
      if(!cards.some(card=>card.dataset.inputCopy===number))return;
      selectedCopy=number;
      editing=!sections.some(section=>section.dataset.resultCopy===number);
      tabs.forEach(tab=>{const on=tab.dataset.resultTab===number;tab.setAttribute('aria-selected',String(on));tab.tabIndex=on?0:-1;if(on&&focus)tab.focus({preventScroll:true});});
      sections.forEach(section=>{section.hidden=section.dataset.resultCopy!==number;});
      panel.querySelectorAll('[data-result-extra]').forEach(el=>{el.hidden=el.dataset.resultExtra!==number;});
      document.querySelectorAll('[data-input-copy]').forEach(el=>el.classList.toggle('is-active',el.dataset.inputCopy===number));
      panel.scrollTop=0;refreshHeading();
    }
    tabs.forEach((tab,index)=>{
      tab.addEventListener('click',()=>selectCopy(tab.dataset.resultTab));
      tab.addEventListener('keydown',event=>{let next;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;event.preventDefault();selectCopy(tabs[next].dataset.resultTab,true);});
    });
    function refreshHeading(){
      const active=currentRounds();
      const asking=active.some(r=>r.dataset.uiStage!=='result');
      panel.dataset.reviewState=asking?'asking':'result';
      const pageTitle=document.querySelector('[data-review-page-title]');if(pageTitle)pageTitle.textContent='문구 검수';
      const conditions=document.querySelector('.cl-review-conditions');if(conditions)conditions.hidden=asking;
      const resultFooter=panel.querySelector('.cl-result-footer');if(resultFooter)resultFooter.hidden=asking;
      const title=panel.querySelector('[data-review-title]');
      if(title)title.textContent='검수 결과';
      sections.forEach(section=>{
        const number=section.dataset.resultCopy;
        const pending=active.some(r=>r.closest('[data-result-copy]')===section&&r.dataset.uiStage!=='result');
        section.dataset.pending=String(pending);
        const input=document.querySelector('[data-input-copy="'+number+'"]');
        const dirty=input?.dataset.dirty==='true';
        const stale=section.querySelector('[data-result-stale]');if(stale)stale.hidden=!dirty;
        const round=active.find(r=>r.closest('[data-result-copy]')===section);
        const summary=round?round.querySelector('.rv-res.is-shown .cl-result-overview'):section.querySelector('.cl-result-overview');
        const outcome=summary?.classList.contains('cl-result-hold')?'추가 검토 필요':summary?.classList.contains('cl-result-certificate')?'표현 수정 필요':summary?.classList.contains('cl-result-guidance')?'자료 확인 필요':'검수 완료';
        const state=dirty?'수정됨 · 재검수 필요':pending?'조건 확인 필요':outcome;
        const tab=tabs.find(t=>t.dataset.resultTab===number);
        if(tab){tab.querySelector('[data-tab-status]').textContent=state;tab.dataset.pending=String(pending);}
        const inputStatus=document.querySelector('[data-input-status="'+number+'"]');if(inputStatus){inputStatus.textContent=state;inputStatus.dataset.pending=String(pending||dirty);}
        const navStatus=document.querySelector('[data-nav-status="'+number+'"]');if(navStatus){navStatus.textContent=state;navStatus.dataset.pending=String(pending||dirty||outcome!=='검수 완료');}
      });
      if(resultFooter)resultFooter.hidden=sections.some(s=>s.dataset.resultCopy===selectedCopy&&s.dataset.pending==='true');
      const badge=panel.querySelector('.rv-live');
      if(badge){
        const heading=panel.querySelector('.rv-risk-head');if(heading&&badge.parentElement!==heading)heading.append(badge);
        const flags=[...panel.querySelectorAll('.rv-flag')].filter(visible).length;
        badge.dataset.uiSummary=asking?'추가 정보 확인 필요':(flags?'확인할 문장 있음':'검수 완료');
      }
      updateFocus();
    }
    // Product selection is a native POST. JavaScript only updates presentation;
    // it never substitutes a precomputed branch for a product-aware judgment.
    rounds.forEach(round=>{
      round.querySelectorAll('.cl-review-progress li').forEach((li,i)=>{
        const step={type:0,cert:1,food:1,result:2}[round.dataset.uiStage];
        li.classList.toggle('is-current',i===step);li.classList.toggle('is-done',i<step);
        if(i===step)li.setAttribute('aria-current','step');else li.removeAttribute('aria-current');
      });
    });
    focusReady=true;
    document.addEventListener('submit',event=>{
      if(event.target!==form&&!panel.contains(event.target))return;
      let number=Number(selectedCopy);
      const op=event.submitter?.name==='op'?event.submitter.value:'';
      if(/^(judge|sample):\d+$/.test(op))number=Number(op.split(':')[1]);
      if(/^del:\d+$/.test(op)){const deleted=Number(op.split(':')[1]);if(deleted<number)number--;else if(deleted===number)number=Math.min(number,Math.max(1,cards.length-1));}
      try{sessionStorage.setItem(selectionKey,JSON.stringify({number:String(number),path:new URL(event.target.action,location.href).pathname,at:Date.now()}));}catch{}
    });
    navs.forEach(nav=>nav.addEventListener('click',()=>{
      selectCopy(nav.dataset.copyNav);
      if(window.matchMedia('(max-width:47.999rem)').matches)panel.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
    }));
    window.addEventListener('review:restore-copy',event=>{if(typeof event.detail==='string')selectCopy(event.detail);});
    if(cards.length)selectCopy(selectedCopy);
    panel.querySelectorAll('[data-edit-copy]').forEach(button=>button.addEventListener('click',()=>{
      editing=!editing;updateFocus();
      if(editing){panel.scrollTop=0;cards.find(card=>card.dataset.inputCopy===selectedCopy)?.querySelector('textarea')?.focus({preventScroll:true});}
    }));
    document.querySelectorAll('[data-input-copy] textarea').forEach(input=>{
      const original=input.value;
      input.addEventListener('focus',()=>{const number=input.closest('[data-input-copy]').dataset.inputCopy;if(tabs.some(t=>t.dataset.resultTab===number)&&number!==selectedCopy)selectCopy(number);});
      input.addEventListener('input',()=>{const card=input.closest('[data-input-copy]');card.dataset.dirty=String(input.value!==original);const preview=document.querySelector('[data-nav-preview="'+card.dataset.inputCopy+'"]');if(preview)preview.textContent=input.value||'문구를 입력해주세요.';refreshHeading();});
    });
    document.querySelector('[data-focus-conditions]')?.addEventListener('click',()=>{
      const current=rounds.find(visible);
      const retry=current?.querySelector('.rv-redo button[name=op]');
      if(current?.dataset.uiStage==='result'&&retry)retry.click();
      panel.focus({preventScroll:true});panel.scrollTo({top:0,behavior:'smooth'});refreshHeading();
    });
  }
  // 🔄 2026-10-21 (ksr) — 이력 상세가 갈아 끼워지므로 문서에 위임한다
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-copy-history]');if(!button)return;
    const text=button.closest('.history-detail')?.querySelector('.history-detail-text')?.textContent||'';
    try{await navigator.clipboard.writeText(text);button.textContent='복사 완료';}
    catch{button.textContent='문구를 직접 선택해 복사해주세요';}
  });
})();

document.querySelector('[data-copy-review]')?.addEventListener('click',async event=>{
  const paragraphs=[...document.querySelectorAll('.rv-results-pane .rv-text')].filter(el=>el.getClientRects().length);
  const text=paragraphs.map(el=>el.textContent.trim()).join('\n');
  if(!text)return;
  try{await navigator.clipboard.writeText(text);event.currentTarget.textContent='복사 완료';}
  catch{event.currentTarget.textContent='문구를 직접 선택해 복사해주세요';}
});
