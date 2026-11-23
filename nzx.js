'use strict';
// NZX is visible in Scout's existing screens but is NOT retroactively mixed
// into the USD/SPY model, or displayed with unsupported valuation targets.
const ScoutNZX=(()=>{
  const $=id=>document.getElementById(id);
  const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
  const val=n=>typeof n==='number'&&Number.isFinite(n);
  const money=n=>val(n)?'NZ$'+Number(n).toLocaleString('en-NZ',{minimumFractionDigits:2,maximumFractionDigits:4}):'No verified close';
  const pct=n=>val(n)?(n>0?'+':'')+n.toFixed(2)+'%':'—';
  const sourceUrl=s=>{try{const u=new URL(s);return u.protocol==='https:'?u.href:null}catch{return null}};
  let nzx=null,apac=null,last=null,showAll=false;
  const active=()=>nzx&&nzx.market==='NZX'&&Array.isArray(nzx.candidates);
  const ticker=q=>String(q?.symbol||'').toUpperCase();
  function panel(id,anchor,html,where='afterend'){
    if(!$(id)&&$(anchor))$(anchor).insertAdjacentHTML(where,html);
    return $(id);
  }
  function makePanels(){
    panel('nzx-overview','overview-shortlist','<div id="nzx-overview" class="card note-card" aria-label="New Zealand market research"></div>');
    panel('nzx-discovery','discovery-list','<div id="nzx-discovery" class="card note-card" aria-label="NZX company research"></div>');
    panel('nzx-weekly','weekly-list','<div id="nzx-weekly" class="card note-card" aria-label="NZX weekly watch"></div>');
    panel('nzx-paper','results-list','<div id="nzx-paper" class="card note-card" aria-label="NZX paper research history"></div>');
    panel('nzx-learning','paper-performance','<p id="nzx-learning" class="muted"></p>');
  }
  function statusBar(){
    if(!active())return '<strong>NZX · DATA UNAVAILABLE</strong><p>NZX research has not been published. The US system continues independently.</p>';
    const c=nzx.coverage||{},up=apac?.markets?.NZX||{};
    return '<strong>NZX · NEW ZEALAND RESEARCH</strong><p>'+safe(c.companies||0)+' companies + '+safe(c.etfs||0)+' ETFs · '+
      safe(c.verified_eod||0)+' verified recent NZD closes · '+safe(c.financially_scored||0)+
      ' issuer financial screens. '+safe(up.status||'Data feed pending')+
      '. Not all NZX instruments or Sharesies investments are covered.</p>';
  }
  function card(c,compact=false){
    const price=val(c.price)?money(c.price)+' · '+safe(c.price_date||'undated'):'No validated recent close';
    const change=val(c.change_pct)?' · '+pct(c.change_pct)+' last session':'';
    const evidence=(c.evidence||[]).filter(x=>sourceUrl(x.url)).slice(0,compact?1:2)
      .map(x=>'<a href="'+safe(sourceUrl(x.url))+'" target="_blank" rel="noopener noreferrer">'+safe(x.label||'Source')+' ↗</a>').join(' · ');
    return '<article class="card candidate watch"><div class="flex-between"><div class="candidate-brand"><strong>NZX:'+safe(c.symbol)+'</strong><span>'+safe(c.name)+'</span></div><span class="grade">—</span></div>'+
      '<div class="flex-between candidate-sub"><span class="status watch">'+safe(c.status)+'</span><span>'+price+change+'</span></div>'+
      '<div class="price-plan plan-missing"><div class="plan-header"><strong>NO RELIABLE BUY/SELL RANGE</strong><span>NZD · NOT A TRADE SIGNAL</span></div>'+
      (!compact?'<p class="plan-reason">NZX issuer fundamentals and a validated NZ valuation model have not been connected.</p>':'')+'</div>'+
      '<p class="candidate-thesis">'+safe(c.why||'Insufficient independently checked issuer financials')+'</p>'+
      (!compact?'<p class="muted">Risk: NZX shares may be illiquid; dividends and splits can distort raw closing-price returns.</p>':'')+
      '<div class="evidence">'+(evidence||'No verified source links')+'</div></article>';
  }
  function readFilter(){
    const text=String($('discovery-search')?.value||'').toLowerCase().trim();
    const type=$('discovery-filter')?.value||'all';
    return {text,type};
  }
  function renderResearch(){
    const target=$('nzx-discovery');if(!target)return;
    if(!active()){target.innerHTML=statusBar();return}
    const {text,type}=readFilter();
    const records=nzx.candidates.filter(c=>
      ((c.symbol||'').toLowerCase().includes(text)||(c.name||'').toLowerCase().includes(text))&&
      (type==='all'||(type==='watch'&&c.price!==null)));
    const visible=showAll?records:records.slice(0,8);
    target.innerHTML=statusBar()+
      '<p class="muted">Listed NZX companies are searchable here alongside Scout’s US research. A verified price is not a scored business or an entry recommendation.</p>'+
      (visible.length?visible.map(c=>card(c,true)).join(''):'<p>No NZX issuer matches that search or filter.</p>')+
      (visible.length<records.length?'<button type="button" id="nzx-show-more" class="show-more">Show '+(records.length-visible.length)+' more NZX companies</button>':'');
    if($('nzx-show-more'))$('nzx-show-more').addEventListener('click',()=>{showAll=true;renderResearch()});
  }
  function renderWeekly(){
    const target=$('nzx-weekly');if(!target)return;
    const rows=active()?(nzx.weekly?.shortlist||[]):[];
    const funds=active()?(nzx.weekly?.etf_watch||[]):[];
    target.innerHTML='<strong>NZX · THIS WEEK’S RESEARCH WATCH</strong>'+
      '<p class="muted">Part of Scout’s weekly research, but not mixed into the US valuation ranking. No NZD entry or selling levels are made up.</p>'+
      (rows.length?rows.map(c=>card(c,true)).join(''):
        '<p>No NZX companies currently have sufficiently recent verified prices for watch notes.</p>')+
      (funds.length?'<strong>NZX · CORE ETF RESEARCH</strong><p class="muted">Potential diversified funds to research, not buy rankings. Check the fund factsheet, fees and Sharesies availability.</p>'+funds.map(c=>card(c,true)).join(''):'');
  }
  function renderOverview(){
    const target=$('nzx-overview');if(!target)return;
    const entries=active()?(nzx.weekly?.shortlist||[]):[];
    target.innerHTML=statusBar()+
      (entries.length?'<p>Recent NZX observations to investigate, not confirmed buying opportunities:</p>'+entries.slice(0,2).map(c=>card(c,true)).join(''):
        '<p>No current NZX buy candidate is being claimed. Research is gated on evidence quality.</p>');
  }
  function renderQuotes(){
    const target=$('quotes');if(!target||!active())return;
    const search=String($('quote-search')?.value||'').trim().toLowerCase();
    const quoteType=$('quote-filter')?.value||'all';
    const records=nzx.candidates.filter(c=>(quoteType==='all'||
      (quoteType==='etfs'&&c.type==='ETF')||
      (quoteType==='stocks'&&c.type!=='ETF'))&&
      (c.symbol.toLowerCase().includes(search)||c.name.toLowerCase().includes(search)));
    const prices=records.filter(c=>val(c.price));
    const display=(showAll||search)?records:records.slice(0,15);
    target.insertAdjacentHTML('beforeend','<div class="card note-card"><strong>NZX · VERIFIED NZD END-OF-DAY PRICES</strong>'+
      '<p>'+safe(prices.length)+' of '+safe(records.length)+' matching issuers have recent verified prices. Missing prices remain missing; NZX is not a USD share.</p>'+
      display.map(c=>'<div class="quote-row"><div class="ticker-circle">'+safe(c.symbol.slice(0,5))+'</div>'+
        '<div class="quote-left"><strong>NZX:'+safe(c.symbol)+'</strong><div>'+safe(c.name)+' · '+safe(c.price_date||'No recent EOD')+'</div></div>'+
        '<div class="quote-right"><div class="quote-price">'+money(c.price)+'</div>'+
        (val(c.change_pct)?'<div class="quote-change '+(c.change_pct>=0?'up':'down')+'">'+pct(c.change_pct)+' previous session</div>':'')+
        '</div></div>').join('')+
      ((!showAll&&!search&&records.length>15)?'<p class="muted">Search a symbol or company name to see additional NZX listings.</p>':'')+
      '</div>');
  }
  function renderAlerts(){
    if(!active())return;
    const a=nzx.alerts||[];
    const html=a.map(x=>'<article class="card urgent-card">'+
      '<div class="flex-between"><span class="tag research">NZX PRICE RESEARCH · NOT BUY</span><time>'+safe(x.price_date||'')+'</time></div>'+
      '<strong>'+safe(x.headline||'NZX price movement')+'</strong><p>'+safe(x.why||'')+'</p>'+
      '<p class="muted">'+safe(x.risk||'')+'</p>'+
      (sourceUrl(x.source_url)?'<a href="'+safe(sourceUrl(x.source_url))+'" target="_blank" rel="noopener noreferrer">Verify NZX issuer ↗</a>':'')+
      '</article>').join('');
    if(a.length&&$('urgent-list'))$('urgent-list').insertAdjacentHTML('beforeend',html);
    if(a.length&&$('overview-alerts'))$('overview-alerts').insertAdjacentHTML('beforeend',a.slice(0,1).map(x=>'<div class="card small-notice"><strong>NZX:'+safe(x.symbol)+'</strong> · '+safe(x.headline)+'</div>').join(''));
    if(a.length&&$('movers-list')){
      $('movers-list').insertAdjacentHTML('beforeend',a.slice(0,10).map(x=>
        '<div class="mover-row"><strong>NZX:'+safe(x.symbol)+'</strong><span>price movement research</span><small>'+safe(x.price_date||'')+'</small></div>').join(''));
    }
  }
  function renderPaper(){
    const target=$('nzx-paper');if(!target)return;
    if(!active()){target.innerHTML='<strong>NZX paper observations unavailable</strong>';return}
    const p=nzx.paper||{},s=p.summary||{};
    target.innerHTML='<strong>NZX · PROSPECTIVE RESEARCH RECORD</strong>'+
      '<p>'+safe(s.recorded||0)+' dated watch opinions · '+safe(s.matured_7d||0)+' verified 7-day moves · '+
      safe(s.matured_30d||0)+' verified 30-day moves · <strong>0 actual or hypothetical buys</strong>.</p>'+
      '<p class="muted">These are NZD price-only observations, not paper trades or performance versus SPY. No reliable NZX benchmark, dividend adjustments, trade fees or FX effects are included.</p>'+
      (p.records||[]).slice(0,10).map(x=>'<div class="log-row"><strong>NZX:'+safe(x.symbol)+'</strong><span>'+
        safe(x.original_date)+' · original reference '+money(x.reference_price)+'</span><span>'+
        '7d '+pct(x.change_7d_pct)+' · 30d '+pct(x.change_30d_pct)+'</span></div>').join('')+
      '<p class="muted">'+safe(p.benchmark_status||'No validated NZX benchmark')+'</p>';
  }
  function renderSource(){
    if(!active())return;
    if($('sources-list'))$('sources-list').insertAdjacentHTML('beforeend',
      '<div class="source-row"><div><div class="source-name">NZX issuer research (NZD)</div>'+
      '<div class="source-info">'+safe(nzx.coverage?.verified_eod||0)+' verified closing prices of '+
      safe(nzx.coverage?.listed||0)+' listed issuers; financial valuation not connected</div></div>'+
      '<div class="source-status">RESEARCH ONLY</div></div>');
    if($('nzx-learning'))$('nzx-learning').textContent='NZX learning: NOT ACTIVE. '+(nzx.learning?.reason||'NZX machine-learning validation is unavailable')+
      ' The existing US model and its historical results are unchanged.';
  }
  async function load(){
    nzx=null;apac=null;
    try{
      const responses=await Promise.all([
        fetch('./data/nzx_research.json?nocache='+Date.now(),{cache:'no-store'}),
        fetch('./data/apac.json?nocache='+Date.now(),{cache:'no-store'})
      ]);
      if(responses[0].ok){
        const v=await responses[0].json();
        if(v?.market==='NZX'&&v?.currency==='NZD'&&Array.isArray(v.candidates))nzx=v;
      }
      if(responses[1].ok){
        const v=await responses[1].json();
        if(v?.markets?.NZX)apac=v;
      }
    }catch{nzx=null;apac=null}
  }
  function render(data){
    last=data;makePanels();
    renderOverview();renderResearch();renderWeekly();renderQuotes();
    renderAlerts();renderPaper();renderSource();
  }
  function setup(){
    makePanels();
    for(const id of ['quote-search','quote-filter'])if($(id))
      $(id).addEventListener(id==='quote-search'?'input':'change',()=>{if(last)renderQuotes()});
    for(const id of ['discovery-search','discovery-filter'])if($(id))
      $(id).addEventListener(id==='discovery-search'?'input':'change',()=>{showAll=false;renderResearch()});
  }
  return {load,render,setup};
})();
