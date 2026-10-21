/* 🆕 2026-10-21 (ksr) — 품목 선택지 옆 「?」 도움말 팝업. 문구 칸은 fetch 로 갈아 끼워지므로 문서에 한 번만 건다(위임). */
(() => {
  document.addEventListener('click',event=>{
    const open=event.target.closest('[data-help-open]');
    if(open){
      event.preventDefault();event.stopPropagation();
      const dialog=open.parentElement.querySelector('dialog.rv-help');
      if(dialog&&!dialog.open){dialog.showModal();dialog.querySelector('.rv-help-body')?.scrollTo({top:0});}
      return;
    }
    if(event.target.closest('[data-help-close]')){event.target.closest('dialog')?.close();return;}
    // 바깥(어두운 배경)을 누르면 닫는다 — 대화상자 자신이 눌린 것은 안쪽이 아닌 자리다
    if(event.target instanceof HTMLDialogElement&&event.target.matches('.rv-help'))event.target.close();
  });
})();
