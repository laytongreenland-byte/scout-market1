'use strict';
// Scout Compass: a plain-English, NZ small-investor lens over the existing data.
// Deliberately no third-party services, account login, trading or invented targets.
const ScoutCompass=(()=>{
  const el=id=>document.getElementById(id);
  let latest=null,quoteTerm='',quoteType='all',allQuotes=false;
  let researchTerm='',researchType='all',allResearch=false;
  const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const nzd=n=>Number(n||0).toLocaleString('en-NZ',{minimumFractionDigits:2,maximumFractionDigits:2});
  const reasonBySignal={
    'ENTRY CANDIDATE':'Its screen and hypothetical entry ceiling align. Check primary filings and current costs first.',
    'WAIT FOR ENTRY':'Interesting business, but Scout wants a better price before considering it.',
    'QUALITY GATE NOT MET':'The price may appear cheap, but company-quality requirements are not satisfied.',
    'ABOVE BASE CASE':'The price exceeds Scout’s illustrative base-case valuation.',
    'POSSIBLE VALUE TRAP':'It may be cheap because of an underlying business problem. Investigate before acting.',
    'NO RELIABLE PRICE RANGE':'The inputs or valuation method are not reliable enough to suggest a buy price.'
  };
  function explainCandidate(c){
    const p=c.price_plan||{};
    if(c.status==='INSUFFICIENT DATA')return 'Not enough reliable company information to decide.';
    return reasonBySignal[p.signal]||'Not enough evidence for a confident decision. Research further.';
  }
  function settings(){
    const amount=Math.max(0,Number(el('trade-amount')?.value)||0);
    const dealing=Math.max(0,Number(el('dealing-fee')?.value)||0);
    const fx=Math.max(0,Number(el('fx-fee')?.value)||0);
    const dragPct=(dealing+fx)*2;
    return {amount,dragPct,total:amount*dragPct/100};
  }
  function refreshCost(){
    const target=el('cost-glance');if(!target)return;
    const cfg=settings();
    target.innerHTML='<p><strong>NZ$'+nzd(cfg.total)+'</strong> estimated buy-and-sell fees on a <strong>NZ$'+nzd(cfg.amount)+'</strong> trade.</p>'+
      '<p>That is about <strong>'+nzd(cfg.dragPct)+'%</strong> of the trade before spreads, exchange-rate movements and tax. A good-looking share price can still be a bad small trade.</p>';
  }
  function renderSummary(data){
    const r=data.research||{},cov=data.coverage||{},entries=r.entry_candidates||[];
    const count=cov.configured_symbols??(data.tracked_symbols||[]).length;
    const priced=cov.quotes_fresh_this_scan??(data.quotes||[]).filter(q=>typeof q.price==='number'&&!q.stale).length;
    const screened=cov.financially_screened??r.screened_with_financials??0;
    el('coverage-grid').innerHTML=[[count,'Tracked assets'],[priced,'Recent quotes'],[screened,'Company screens']].map(v=>'<div><strong>'+safe(v[0])+'</strong><span>'+safe(v[1])+'</span></div>').join('');
    el('coverage-disclaimer').textContent='Curated, not the entire market. '+(cov.etf_symbols??0)+' ETFs and '+(cov.equity_symbols??0)+' shares. A quote is NOT a company analysis; many companies are screened on a rotating schedule.';
    if(entries.length){
      const top=entries[0];
      el('compass-check').textContent='PRELIMINARY · VERIFY';
      el('compass-title').textContent=entries.length+' potential entry research candidate'+(entries.length===1?'':'s');
      el('compass-explain').textContent=top.symbol+': '+explainCandidate(top)+' A model screen is not a buy instruction.';
      el('compass-meta').textContent='Based on '+(r.screened_with_financials||0)+' screened companies · forecasts not yet independently validated';
    }else{
      el('compass-check').textContent='NO QUALIFIED ENTRY';
      el('compass-title').textContent='No compelling purchase case right now';
      el('compass-explain').textContent='None of '+screened+' financially screened companies currently passes both the business and purchase-price gates. Doing nothing is a valid outcome.';
      el('compass-meta').textContent=screened<(cov.equity_symbols??screened)?'Research still expanding: financial statements are checked in rotating batches.':'Scout has not established any predictive track record.';
    }
    refreshCost();
  }
  function quotes(){
    if(!latest)return;
    const list=latest.tracked_symbols||[];
    const etf=new Set(latest.etf_symbols||[]);
    const qmap=new Map((latest.quotes||[]).map(q=>[q.symbol,q]));
    const filtered=list.filter(sym=>sym.toLowerCase().includes(quoteTerm)&&
      (quoteType==='all'||(quoteType==='etfs'?etf.has(sym):!etf.has(sym))));
    const shown=allQuotes?filtered:filtered.slice(0,45);
    el('quotes').innerHTML=shown.length?shown.map(sym=>quoteHtml(qmap.get(sym)||{symbol:sym,source:'Finnhub',price:null})).join(''):'<div class="card small-notice">No matching ticker in Scout’s curated selection. This is not a search of the entire stock exchange.</div>';
    const button=el('quote-show-all');
    button.hidden=filtered.length<=45;
    button.textContent=allQuotes?'Show fewer prices':'Show all '+filtered.length+' matching prices';
    const c=latest.coverage||{};
    el('quote-coverage-note').textContent='Successfully fetched '+(c.quotes_fresh_this_scan??'—')+' of '+(c.configured_symbols??list.length)+' quotes. Only '+(c.financially_screened??'—')+' companies have sufficient financial metrics to rank. Missing/unavailable quotes are not silently counted as researched.';
  }
  function discover(){
    if(!latest)return;
    const r=latest.research||{},records=r.candidates||[];
    const matches=records.filter(c=>{
      const signal=c.price_plan?.signal||'NO RELIABLE PRICE RANGE';
      if(researchType==='entry'&&signal!=='ENTRY CANDIDATE')return false;
      if(researchType==='watch'&&!['WAIT FOR ENTRY','NO RELIABLE PRICE RANGE'].includes(signal))return false;
      if(researchType==='risk'&&!['QUALITY GATE NOT MET','ABOVE BASE CASE','POSSIBLE VALUE TRAP'].includes(signal))return false;
      return (c.symbol||'').toLowerCase().includes(researchTerm)||(c.name||'').toLowerCase().includes(researchTerm);
    });
    el('discovery-status').textContent=(r.screened_with_financials||0)+' financially scored · '+records.length+' available to browse';
    const shown=allResearch?matches:matches.slice(0,10);
    el('discovery-list').innerHTML=shown.length?shown.map(c=>candidateHtml(c,true)).join(''):'<div class="card small-notice">Nothing meets these conditions. Try a broader filter or wait for more company financials.</div>';
    if(shown.length<matches.length){
      const b=document.createElement('button');b.type='button';b.className='show-more';
      b.textContent='Show '+(matches.length-shown.length)+' more screened companies';
      b.addEventListener('click',()=>{allResearch=true;discover()});
      el('discovery-list').appendChild(b);
    }
  }
  function setup(){
    el('quote-search').addEventListener('input',e=>{quoteTerm=e.target.value.trim().toLowerCase();allQuotes=false;quotes()});
    el('quote-filter').addEventListener('change',e=>{quoteType=e.target.value;allQuotes=false;quotes()});
    el('quote-show-all').addEventListener('click',()=>{allQuotes=!allQuotes;quotes()});
    el('discovery-search').addEventListener('input',e=>{researchTerm=e.target.value.trim().toLowerCase();allResearch=false;discover()});
    el('discovery-filter').addEventListener('change',e=>{researchType=e.target.value;allResearch=false;discover()});
    for(const id of ['trade-amount','dealing-fee','fx-fee'])el(id).addEventListener('input',refreshCost);
  }
  function render(data){
    latest=data;
    renderSummary(data);
    quotes();
    discover();
  }
  return {setup,render,refreshCost,explainCandidate};
})();
