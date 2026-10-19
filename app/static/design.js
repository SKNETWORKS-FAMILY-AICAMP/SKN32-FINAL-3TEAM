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
        count:form.querySelectorAll('textarea[name="text"]').length,
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
  window.addEventListener('pageshow',()=>{restore();requestAnimationFrame(restore);},{once:true});
})();
/* Explicit review steps progressively enhance the existing server-provided branches. */
(() => {
  const panel=document.querySelector('.rv-results-pane');
  if(panel){
    const rounds=[...panel.querySelectorAll('.rv-round')];
    const tabs=[...panel.querySelectorAll('[data-result-tab]')];
    const sections=[...panel.querySelectorAll('[data-result-copy]')];
    let selectedCopy=tabs[0]?.dataset.resultTab;
    const visible=el=>el.getClientRects().length>0;
    const currentRounds=()=>rounds.filter(r=>getComputedStyle(r).display!=='none');
    function selectCopy(number,focus=false){
      selectedCopy=number;
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
        const state=dirty?'수정됨 · 재검수 필요':pending?'조건 확인 필요':'검수 완료';
        const tab=tabs.find(t=>t.dataset.resultTab===number);
        if(tab){tab.querySelector('[data-tab-status]').textContent=state;tab.dataset.pending=String(pending);}
        const inputStatus=document.querySelector('[data-input-status="'+number+'"]');if(inputStatus){inputStatus.textContent=state;inputStatus.dataset.pending=String(pending||dirty);}
      });
      if(resultFooter)resultFooter.hidden=sections.some(s=>s.dataset.resultCopy===selectedCopy&&s.dataset.pending==='true');
      const badge=panel.querySelector('.rv-live');
      if(badge){
        const heading=panel.querySelector('.rv-risk-head');if(heading&&badge.parentElement!==heading)heading.append(badge);
        const flags=[...panel.querySelectorAll('.rv-flag')].filter(visible).length;
        badge.dataset.uiSummary=asking?'추가 정보 확인 필요':(flags?'확인할 문장 있음':'검수 완료');
      }
    }
    rounds.forEach(round=>{
      const kind=()=>round.querySelector('.rv-k:checked');
      const cert=()=>round.querySelector('.rv-c:checked');
      const next=round.querySelector('[data-review-next]');
      const finish=round.querySelector('[data-review-finish]');
      function update(){
        const selected=kind();
        const leaf=selected?.className.match(/rv-p-(\w+)/)?.[1];
        const p=leaf||cert()?.className.match(/rv-p-(\w+)/)?.[1];
        round.querySelectorAll('.rv-res').forEach(res=>res.classList.toggle('is-shown',!!p&&res.classList.contains('rv-res-'+p)));
        round.querySelectorAll('.rv-opt[for]').forEach(label=>{
          const radio=document.getElementById(label.htmlFor);
          label.classList.toggle('is-selected',!!radio?.checked);
          label.setAttribute('aria-checked',String(!!radio?.checked));
          const group=[...label.parentElement.querySelectorAll('.rv-opt[for]')];
          const checked=group.find(option=>document.getElementById(option.htmlFor)?.checked);
          label.tabIndex=(checked||group[0])===label?0:-1;
        });
        const selectedLabel=selected?.getAttribute('aria-label')||'';
        const note=round.querySelector('[data-selected-kind]');if(note)note.textContent=selectedLabel||'유형을 선택해주세요';
        if(next)next.disabled=!selected;
        if(finish)finish.disabled=!cert();
        round.querySelectorAll('.cl-review-progress li').forEach((li,i)=>{
          const step={type:0,cert:1,result:2}[round.dataset.uiStage];
          li.classList.toggle('is-current',i===step);li.classList.toggle('is-done',i<step);
          if(i===step)li.setAttribute('aria-current','step');else li.removeAttribute('aria-current');
        });
        if(round.dataset.uiStage==='result'&&visible(round)){
          const number=round.closest('.rv-br').dataset.copyNumber;
          const condition=document.querySelector('[data-current-category="'+number+'"]');
          if(condition)condition.textContent=selectedLabel+(selected?.classList.contains('rv-k-hf')?' · '+(cert()?.getAttribute('aria-label')||''):'');
        }
        refreshHeading();
      }
      round.querySelectorAll('.rv-opt[for]').forEach(label=>{
        const radio=document.getElementById(label.htmlFor);
        if(!radio)return;
        // Native label activation focuses the off-screen sibling input and scrolls the pane.
        // Keep focus on the visible option while retaining the original radio state/CSS.
        radio.tabIndex=-1;
        label.setAttribute('role','radio');
        label.parentElement.setAttribute('role','radiogroup');
        label.parentElement.setAttribute('aria-label',radio.classList.contains('rv-c')?'인증 여부':'제품 유형');
        let pointerScroll;
        const captureScroll=()=>({pane:panel.scrollTop,x:window.scrollX,y:window.scrollY});
        label.addEventListener('pointerdown',event=>{pointerScroll=captureScroll();event.preventDefault();});
        label.addEventListener('click',event=>{
          event.preventDefault();
          if(radio.disabled)return;
          const position=pointerScroll||captureScroll();pointerScroll=null;
          radio.checked=true;
          label.focus({preventScroll:true});
          radio.dispatchEvent(new Event('change',{bubbles:true}));
          const restore=()=>{panel.scrollTop=position.pane;window.scrollTo({left:position.x,top:position.y,behavior:'instant'});};
          restore();requestAnimationFrame(restore);
        });
        label.addEventListener('keydown',event=>{
          const options=[...label.parentElement.querySelectorAll('.rv-opt[for]')];
          const index=options.indexOf(label);
          let next;
          if(event.key===' '||event.key==='Enter')next=index;
          else if(event.key==='ArrowRight'||event.key==='ArrowDown')next=(index+1)%options.length;
          else if(event.key==='ArrowLeft'||event.key==='ArrowUp')next=(index+options.length-1)%options.length;
          else if(event.key==='Home')next=0;
          else if(event.key==='End')next=options.length-1;
          else return;
          event.preventDefault();options[next].click();
        });
      });
      round.dataset.uiStage=kind()?(kind().classList.contains('rv-k-hf')?(cert()?'result':'cert'):'result'):'type';
      next?.addEventListener('click',()=>{if(!kind())return;round.dataset.uiStage=kind().classList.contains('rv-k-hf')?'cert':'result';update();panel.scrollTop=0;});
      finish?.addEventListener('click',()=>{if(!cert())return;round.dataset.uiStage='result';update();panel.scrollTop=0;});
      const back=round.querySelector('[data-review-type-back]');
      if(round.dataset.onlyHf==='true'&&back)back.hidden=true;
      back?.addEventListener('click',()=>{round.dataset.uiStage='type';update();panel.scrollTop=0;});
      round.addEventListener('change',update);update();
    });
    panel.querySelectorAll('.rv-br>input[type=checkbox]').forEach(input=>input.addEventListener('change',refreshHeading));
    if(tabs.length)selectCopy(selectedCopy);
    document.querySelectorAll('[data-input-copy] textarea').forEach(input=>{
      const original=input.value;
      input.addEventListener('focus',()=>{const number=input.closest('[data-input-copy]').dataset.inputCopy;if(tabs.some(t=>t.dataset.resultTab===number)&&number!==selectedCopy)selectCopy(number);});
      input.addEventListener('input',()=>{const card=input.closest('[data-input-copy]');card.dataset.dirty=String(input.value!==original);refreshHeading();});
    });
    document.querySelector('[data-focus-conditions]')?.addEventListener('click',()=>{
      const current=rounds.find(visible);
      const retry=current?.querySelector('.rv-redo label');
      if(current?.dataset.uiStage==='result'&&retry)retry.click();
      panel.focus({preventScroll:true});panel.scrollTo({top:0,behavior:'smooth'});refreshHeading();
    });
  }
  document.querySelector('[data-copy-history]')?.addEventListener('click',async event=>{
    const text=document.querySelector('.history-detail-text')?.textContent||'';
    try{await navigator.clipboard.writeText(text);event.currentTarget.textContent='복사 완료';}
    catch{event.currentTarget.textContent='문구를 직접 선택해 복사해주세요';}
  });
})();

document.querySelector('[data-copy-review]')?.addEventListener('click',async event=>{
  const paragraphs=[...document.querySelectorAll('.rv-results-pane .rv-text')].filter(el=>el.getClientRects().length);
  const text=paragraphs.map(el=>el.textContent.trim()).join('\n');
  if(!text)return;
  try{await navigator.clipboard.writeText(text);event.currentTarget.textContent='복사 완료';}
  catch{event.currentTarget.textContent='문구를 직접 선택해 복사해주세요';}
});
