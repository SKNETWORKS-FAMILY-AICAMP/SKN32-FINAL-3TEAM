/* Add input/result pairs locally; existing POST routes remain the fallback. */
(() => {
  const root=document.querySelector('[data-review-pairs]');
  if(!root)return;
  const list=root.querySelector('[data-pairs-list]');
  const form=root.querySelector('#review-input-form');
  const template=root.querySelector('#review-pair-template');
  const pairs=()=>[...list.querySelectorAll('[data-review-pair]')];
  const areas=()=>pairs().map(pair=>pair.querySelector('textarea[name=text]'));
  const originals=new WeakMap();
  const scrollKey='copylane-review-pairs-scroll';
  const message=root.querySelector('[data-pairs-message]');
  let busy=false;
  function showMessage(text){message.textContent=text;message.hidden=!text;}
  function count(pair){
    const input=pair.querySelector('textarea[name=text]');
    const counter=pair.querySelector('[data-count-for]');
    counter.hidden=false;counter.textContent=input.value.length+'/'+input.maxLength;
    // Fallback for browsers that do not support field-sizing: content.
    if(!CSS.supports('field-sizing','content')){input.style.height='auto';input.style.height=Math.max(200,input.scrollHeight)+'px';}
  }
  function refresh(){
    const all=pairs();
    root.querySelector('[data-pair-count]').textContent=all.length;
    root.querySelectorAll('[data-pair-add]').forEach(add=>{add.disabled=all.length>=Number(root.dataset.maxCopies);});
    const bottom=root.querySelector('[data-pairs-bottom]');if(bottom)bottom.hidden=all.length<2;
    root.querySelector('.rv-pairs-all').disabled=!areas().some(input=>input.value.trim());
    all.forEach(pair=>{pair.querySelector('[data-pair-delete]').hidden=all.length<2;pair.querySelector('.rv-pair-judge').disabled=!pair.querySelector('textarea').value.trim();});
  }
  function numberPair(pair,n){
    pair.dataset.reviewPair=String(n);pair.id='review-pair-'+n;
    pair.setAttribute('aria-labelledby','pair-title-'+n);
    pair.querySelector('[data-pair-title]').id='pair-title-'+n;
    pair.querySelector('[data-pair-title]').textContent='문구 '+n;
    const input=pair.querySelector('textarea[name=text]');input.id='text-'+n;
    pair.querySelector('label[for]').htmlFor=input.id;
    pair.querySelector('[data-count-for]').dataset.countFor=input.id;
    pair.querySelector('[data-input-copy]').dataset.inputCopy=String(n);
    pair.querySelector('.rv-pair-input').setAttribute('aria-label','문구 '+n+' 입력');
    pair.querySelector('.rv-pair-result').setAttribute('aria-label','문구 '+n+' 결과');
    const result=pair.querySelector('[data-result-copy]');
    if(result){result.id='result-copy-'+n;result.dataset.resultCopy=String(n);result.setAttribute('aria-label','문구 '+n+' 검수 결과');}
    pair.querySelectorAll('button[name=op]').forEach(button=>{button.value=button.value.replace(/^([a-z]+):\d+/,(_,op)=>op+':'+n);});
    pair.querySelectorAll('input[name=target]').forEach(input=>{input.value=input.value.replace(/^\d+:/,n+':');});
    pair.querySelectorAll('[data-copy-number]').forEach(element=>{element.dataset.copyNumber=String(n);});
    pair.querySelectorAll('.rv-copyno').forEach(element=>{if(element.firstChild?.nodeType===Node.TEXT_NODE)element.firstChild.textContent='문구 '+n+' ';});
    pair.querySelectorAll('.rv-q>.rv-note').forEach(element=>{if(/^이 조건은 문구 \d+에만 적용돼요\.$/.test(element.textContent.trim()))element.textContent='이 조건은 문구 '+n+'에만 적용돼요.';});
    pair.querySelectorAll('.cl-branch-quote').forEach(quote=>{if(quote.firstChild?.nodeType===Node.TEXT_NODE)quote.firstChild.textContent='문구 '+n;});
  }
  function init(pair){
    const input=pair.querySelector('textarea[name=text]');
    originals.set(input,input.value);count(pair);
    const stage=pair.querySelector('.rv-round')?.dataset.uiStage;
    if(stage&&stage!=='result')pair.querySelector('[data-pair-status]').textContent='조건 확인 필요';
    // Keep a single sentence's conclusion next to its text, as in the previous result UI.
    pair.querySelectorAll('.cl-result-overview').forEach(overview=>{
      const scope=overview.closest('.rv-res')||overview.closest('.cl-result-copy');
      const sentences=scope?.querySelectorAll('.rv-sent');
      if(sentences?.length===1){
        const text=sentences[0].querySelector('.rv-text');
        if(text&&overview.parentElement!==sentences[0])text.after(overview);
      }
    });
    pair.querySelectorAll('.rv-sent').forEach(sentence=>{
      if(sentence.querySelector('.rv-sentence-actions'))return;
      const evidence=sentence.querySelector(':scope > details.rv-more');
      const rewrite=sentence.querySelector(':scope > form[action="/u/review/rewrite"]');
      const scope=sentence.closest('.rv-res');
      const redo=scope?.querySelector(':scope > form.rv-redo');
      const isLast=scope&&[...scope.querySelectorAll('.rv-sent')].at(-1)===sentence;
      if(!evidence&&!rewrite&&!(isLast&&redo))return;
      const actions=document.createElement('div');actions.className='rv-sentence-actions';
      sentence.append(actions);
      if(evidence)actions.append(evidence);
      if(rewrite)actions.append(rewrite);
      if(isLast&&redo){
        const note=redo.querySelector(':scope > span.rv-note');
        actions.append(redo);
        if(note){note.classList.add('rv-redo-hint');sentence.append(note);}
      }
    });
  }
  async function updatePair(event,pair){
    if(busy)return;
    const target=event.target,button=event.submitter;
    const data=new FormData(target);
    if(button?.name)data.append(button.name,button.value);
    const number=pair.dataset.reviewPair;
    const top=window.scrollY;
    const input=pair.querySelector('textarea[name=text]');
    const pane=pair.querySelector('.rv-pair-result');
    const wait=pane.querySelector('[data-review-loading]');
    const isJudge=target===form||target.action.endsWith('/answer')||button?.value.startsWith('pick:');
    wait.querySelector('[data-loading-title]').textContent=target.action.endsWith('/rewrite')?'문장을 고쳐 쓰고 있어요':isJudge?'문구를 검수하고 있어요':button?.dataset.waitLabel||'선택한 내용을 확인하고 있어요';
    wait.querySelector('.rv-judging-steps').hidden=!isJudge;
    pane.scrollTop=0;pane.setAttribute('aria-busy','true');wait.hidden=false;
    const controls=[...root.querySelectorAll('button[type=submit]')];
    const oldStates=controls.map(control=>control.disabled);
    controls.forEach(control=>{control.disabled=true;});input.readOnly=true;busy=true;
    showMessage('');
    try{
      const response=await fetch(target.action,{method:'POST',body:new URLSearchParams(data),credentials:'same-origin'});
      const page=new DOMParser().parseFromString(await response.text(),'text/html');
      const replacement=page.querySelector('[data-review-pair="'+number+'"]');
      if(!replacement)throw new Error('No review card in response');
      const fresh=document.importNode(replacement,true);
      pair.replaceWith(fresh);init(fresh);
      const history=page.querySelector('.rv-pairs-footnote');
      if(history)root.querySelector('.rv-pairs-footnote').replaceChildren(...[...history.childNodes].map(node=>document.importNode(node,true)));
      document.dispatchEvent(new CustomEvent('review:updated'));
      fresh.querySelector('[data-pair-title]').setAttribute('tabindex','-1');
      fresh.querySelector('[data-pair-title]').focus({preventScroll:true});
      window.scrollTo({top,behavior:'instant'});
    }catch{
      showMessage('검수 결과를 불러오지 못했어요. 입력한 문구는 유지돼요. 다시 시도해주세요.');
    }finally{
      wait.hidden=true;pane.removeAttribute('aria-busy');input.readOnly=false;busy=false;
      controls.forEach((control,i)=>{if(control.isConnected)control.disabled=oldStates[i];});refresh();
    }
  }
  pairs().forEach(init);refresh();
  // 2026-10-22 (V-08) — user_wait.js 가 pageshow 에서 제출 버튼을 모두 풀어 빈 칸 버튼도 눌렸다 — 그 뒤에 잠금을 다시 맞춘다.
  window.addEventListener('pageshow',()=>{setTimeout(refresh,0);});
  root.addEventListener('input',event=>{
    if(!event.target.matches('textarea[name=text]'))return;
    const input=event.target,pair=input.closest('[data-review-pair]');
    const dirty=input.value!==originals.get(input);
    pair.dataset.dirty=String(dirty);count(pair);
    const stale=pair.querySelector('[data-result-stale]');if(stale)stale.hidden=!dirty;
    if(pair.querySelector('[data-result-copy]'))pair.querySelector('[data-pair-status]').textContent=dirty?'수정됨 · 재검수 필요':'검수 완료';
    refresh();
  });
  document.addEventListener('submit',event=>{
    if(event.target!==form&&!root.contains(event.target))return;
    const button=event.submitter;
    if(event.target===form&&button?.value==='add'){
      event.preventDefault();event.stopImmediatePropagation();
      if(pairs().length>=Number(root.dataset.maxCopies))return;
      const pair=template.content.firstElementChild.cloneNode(true);
      numberPair(pair,pairs().length+1);list.append(pair);init(pair);refresh();
      pair.scrollIntoView({block:'start',behavior:'auto'});pair.querySelector('textarea').focus({preventScroll:true});
      showMessage('새 문구 입력창과 결과창을 추가했어요.');return;
    }
    if(event.target===form&&button?.matches('[data-pair-delete]')){
      event.preventDefault();event.stopImmediatePropagation();
      const pair=button.closest('[data-review-pair]');
      if(pairs().length<2)return;
      pair.remove();pairs().forEach((pair,i)=>numberPair(pair,i+1));refresh();showMessage('문구를 삭제했어요.');return;
    }
    if(event.target===form&&button?.matches('[data-pair-sample]')){
      event.preventDefault();event.stopImmediatePropagation();
      const input=button.closest('[data-review-pair]').querySelector('textarea');
      input.value='건조한 계절에 쓰기 좋은 보습 로션, 산뜻하게 발라보세요.';
      input.dispatchEvent(new Event('input',{bubbles:true}));input.focus({preventScroll:true});return;
    }
    // 2026-10-22 (V-08) — 빈 칸 검수는 서버로 보내지 않고 서버와 같은 안내를 이 자리에 띄운다(응답의 안내는 카드 밖이라 버려졌다).
    const blankPair=event.target===form&&button?.matches('.rv-pair-judge')&&!button.closest('[data-review-pair]')?.querySelector('textarea[name=text]')?.value.trim();
    const blankAll=event.target===form&&button?.value==='all'&&!areas().some(input=>input.value.trim());
    if(blankPair||blankAll){
      event.preventDefault();event.stopImmediatePropagation();showMessage('검수할 문구를 입력해주세요');return;
    }
    if(event.target!==form){
      const pair=event.target.closest('[data-review-pair]');
      if(pair?.dataset.dirty==='true'){
        event.preventDefault();event.stopImmediatePropagation();showMessage('수정한 문구를 먼저 다시 검수해주세요.');return;
      }
      // Native condition/answer/rewrite forms must include every current input.
      const values=areas().map(input=>input.value);
      event.target.querySelectorAll('input[type=hidden][name=text]').forEach(input=>input.remove());
      values.forEach(value=>{const input=document.createElement('input');input.type='hidden';input.name='text';input.value=value;event.target.append(input);});
    }
    const pair=button?.closest('[data-review-pair]')||event.target.closest('[data-review-pair]');
    if(pair&&window.fetch&&window.DOMParser){
      event.preventDefault();event.stopImmediatePropagation();
      updatePair(event,pair);return;
    }
    if(event.target===form&&button?.value==='all')root.querySelectorAll('.rv-pair-result').forEach(pane=>{
      pane.scrollTop=0;
      pane.querySelector('[data-loading-title]').textContent='문구를 검수하고 있어요';
      pane.querySelector('.rv-judging-steps').hidden=false;
    });
    try{sessionStorage.setItem(scrollKey,JSON.stringify({y:window.scrollY,at:Date.now()}));}catch{}
  },true);
  root.addEventListener('click',async event=>{
    const example=event.target.closest('[data-review-example]');
    if(example){
      if(busy)return;
      const pair=example.closest('[data-review-pair]');
      if(!pair)return;
      const input=pair.querySelector('textarea[name=text]');
      input.value=example.dataset.reviewExample;
      input.dispatchEvent(new Event('input',{bubbles:true}));
      input.focus({preventScroll:true});
      showMessage('문구 '+pair.dataset.reviewPair+'에 예시를 넣었어요. ‘이 문구 검수’를 눌러 시작해주세요.');return;
    }
    const button=event.target.closest('[data-copy-pair]');if(!button)return;
    const text=[...button.closest('[data-review-pair]').querySelectorAll('.rv-text')].filter(el=>el.getClientRects().length).map(el=>el.textContent.trim()).join('\n');
    try{await navigator.clipboard.writeText(text);button.textContent='복사 완료';}catch{button.textContent='문구를 직접 선택해 복사해주세요';}
  });
  try{
    const saved=JSON.parse(sessionStorage.getItem(scrollKey)||'null');sessionStorage.removeItem(scrollKey);
    if(saved&&Number.isFinite(saved.y)&&Date.now()-saved.at<90000)window.addEventListener('pageshow',()=>{window.scrollTo({top:saved.y,behavior:'instant'});},{once:true});
  }catch{}
})();
