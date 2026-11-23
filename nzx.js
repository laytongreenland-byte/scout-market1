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
  let nzx=null,apac=null,feedback=null,last=null,showAll=false;
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
    const evidence=(c.evidence||[]).filter(x=>sourceUrl(x.url)).slice(0,compact?2:3)
      .map(x=>'<a href="'+safe(sourceUrl(x.url))+'" target="_blank" rel="noopener noreferrer">'+safe(x.label||'Source')+' ↗</a>').join(' · ');
    const p=c.price_plan||{},ready=p.signal==='PAPER ENTRY CANDIDATE';
    const pricePlan=ready?
      '<div class="price-plan plan-wait"><div class="plan-header"><strong>EDUCATIONAL PAPER ENTRY</strong><span>NOT A REAL ORDER</span></div>'+
      '<div class="plan-values"><div><span>Paper buy at later close up to</span><strong>'+money(p.entry_ceiling)+'</strong></div>'+
      '<div><span>Paper profit review after entry</span><strong>+12% from actual paper fill</strong></div></div>'+
      '<p class="plan-reason">Based on a rule screen and issuer-linked disclosures, NOT a fair-value estimate. The proposed entry is 1% above the original quote; if no later verified close qualifies, there is no pretend purchase.</p></div>':
      '<div class="price-plan plan-missing"><div class="plan-header"><strong>NO VALIDATED PAPER ENTRY</strong><span>INCOMPLETE DATA OR QUALITY GATE</span></div>'+
      (!compact?'<p class="plan-reason">'+safe(p.reason||'The financial screen or source evidence is insufficient.')+'</p>':'')+'</div>';
    return '<article class="card candidate watch"><div class="flex-between"><div class="candidate-brand"><strong>NZX:'+safe(c.symbol)+'</strong><span>'+safe(c.name)+'</span></div>'+
      '<span class="grade">'+(val(c.score)?safe(c.score)+'/100':'—')+'</span></div>'+
      '<div class="flex-between candidate-sub"><span class="status watch">'+safe(c.status)+'</span><span>'+price+change+'</span></div>'+
      pricePlan+
      '<p class="candidate-thesis">'+safe(c.why||'Insufficient independently checked issuer financials')+'</p>'+
      (!compact?'<p class="muted">Sector: '+safe(c.industry||'Unverified')+
          ' · Financial period: '+safe(c.financial_period||'Not verified')+
          ' · Earnings and company filings must be independently checked. FX is not needed for NZD trades; liquidity, fees, tax, distributions and corporate actions still matter.</p>':'')+
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
      '<p class="muted">Listed NZX companies are searchable here alongside Scout’s US research. Financial screening and paper-entry conditions appear where the evidence supports them; a price alone is never an entry recommendation.</p>'+
      (visible.length?visible.map(c=>card(c,true)).join(''):'<p>No NZX issuer matches that search or filter.</p>')+
      (visible.length<records.length?'<button type="button" id="nzx-show-more" class="show-more">Show '+(records.length-visible.length)+' more NZX companies</button>':'');
    if($('nzx-show-more'))$('nzx-show-more').addEventListener('click',()=>{showAll=true;renderResearch()});
  }
  function renderWeekly(){
    const target=$('nzx-weekly');if(!target)return;
    const rows=active()?(nzx.weekly?.shortlist||[]):[];
    const funds=active()?(nzx.weekly?.etf_watch||[]):[];
    target.innerHTML='<strong>NZX · THIS WEEK’S RESEARCH WATCH</strong>'+
      '<p class="muted">Independent NZX company financial screens and issuer news. Mechanical NZD paper-trade levels are not real buy/sell instructions and are not mixed with the US learning model.</p>'+
      (rows.length?rows.map(c=>card(c,true)).join(''):
        '<p>No NZX companies currently have sufficiently recent verified prices for watch notes.</p>')+
      (funds.length?'<strong>NZX · CORE ETF RESEARCH</strong><p class="muted">Potential diversified funds to research, not buy rankings. Check the fund factsheet, fees and Sharesies availability.</p>'+funds.map(c=>card(c,true)).join(''):'');
  }
  function renderOverview(){
    const target=$('nzx-overview');if(!target)return;
    if(!active()){target.innerHTML='<p>Regional research is unavailable or still publishing. The US screen continues independently.</p>';return}
    const c=nzx.coverage||{},paper=nzx.paper?.summary||{},us=feedback?.summary?.us||{};
    const reviewed=feedback?.summary?.verified_closed_total||0;
    const lesson=feedback?.lessons?.[0];
    target.innerHTML='<div class="nzx-home-metrics">'+
      '<div><strong>'+safe(c.companies||0)+'</strong><span>NZX companies</span></div>'+
      '<div><strong>'+safe(c.verified_eod||0)+'</strong><span>Verified NZD prices</span></div>'+
      '<div><strong>'+safe(paper.recorded||0)+'</strong><span>Frozen paper ideas</span></div>'+
      '</div>'+
      '<p><strong>'+(reviewed?'Reviewing completed outcomes':'Waiting for later paper outcomes')+'</strong> · NZX '+
      safe(paper.closed||0)+' finished / '+safe(paper.waiting||0)+' waiting; US '+safe(us.closed||0)+
      ' finished. A pending prediction is neither a win nor a loss.</p>'+
      (lesson?'<div class="nzx-lesson-mini"><strong>What Scout has identified</strong><p>'+
        safe(lesson.title)+': '+safe(lesson.change||lesson.detail||'')+'</p></div>':
        '<p>Scout preserves original decisions, then checks later prices before judging the rule.</p>')+
      '<p class="muted">Financial screens '+safe(c.financially_scored||0)+' · Price feed '+
      safe(apac?.markets?.NZX?.status||'unavailable')+' · Last research '+
      safe((nzx.generated_at||'').replace('T',' ').slice(0,16))+
      ' UTC. NZX ML is not enabled under the current data licence.</p>';
    const build=$('nzx-build-id');if(build)build.textContent='NZX INCLUDED';
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
    const old=$('nzx-quote-section');if(old)old.remove();
    target.insertAdjacentHTML('beforeend','<div id="nzx-quote-section" class="card note-card"><strong>NZX · VERIFIED NZD END-OF-DAY PRICES</strong>'+
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
    if(!active()){target.innerHTML='<strong>NZX paper results unavailable</strong>';return}
    const paper=nzx.paper||{},stats=paper.summary||{},records=paper.records||[];
    const us=feedback?.summary?.us||{},lessons=feedback?.lessons||[];
    const lessonCards=lessons.slice(0,5).map(l=>'<div class="nzx-lesson-item"><strong>'+safe(l.title)+
      '</strong><p>'+safe(l.detail||'')+'</p><p><em>Response:</em> '+safe(l.change||'Pending review')+
      '</p></div>').join('');
    const statuses={
      'WAITING_TO_BUY':'Waiting for a later close to reach entry',
      'OPEN':'Paper shares bought at a later observed close',
      'NO_ENTRY':'Entry price never observed within 14 days',
      'TARGET_REACHED':'12% profit review level reached',
      'CLOSED_GAIN':'30-day paper position closed with net gain',
      'CLOSED_LOSS':'30-day paper position closed with net loss',
      'UNVERIFIED':'No reliable closing price or possible corporate action'
    };
    const recordHtml=x=>{
      const result=x.result||{},st=result.status||'WAITING_TO_BUY';
      const entry=result.entry||{};
      const fee=val(result.fees_nzd)?' · Approx. fees '+money(result.fees_nzd):'';
      return '<article class="card results-card"><div class="flex-between"><strong>NZX:'+safe(x.symbol)+' · '+safe(x.name||'')+
        '</strong><span class="results-state">'+safe(st)+'</span></div>'+
        '<p>Scout originally proposed a paper entry up to <strong>'+money(x.entry_ceiling)+'</strong> on '+
        safe(x.original_date)+'. Original reference '+money(x.original_price)+'.</p>'+
        '<p>'+safe(statuses[st]||result.reason||'Pending')+'</p>'+
        (val(entry.price)?'<p>Later observed entry: '+money(entry.price)+' on '+safe(entry.date)+
          ' · '+safe(entry.shares)+' whole shares from a hypothetical NZ$100 budget.</p>':'')+
        (val(result.exit_price)?'<p>Later observed exit: '+money(result.exit_price)+' on '+safe(result.exit_date)+
          ' · <strong>Net paper return '+pct(result.net_return_pct)+'</strong>'+fee+'</p>':'')+
        '<details><summary>Research and methodology</summary><p>'+safe(x.why||'')+'</p>'+
        '<p>Financial report period: '+safe(x.financial_period||'Not verified')+'</p>'+
        (sourceUrl(x.filing_url)?'<a href="'+safe(sourceUrl(x.filing_url))+'" target="_blank" rel="noopener noreferrer">Issuer-linked announcement feed</a>':'')+
        '<p>Close-based paper strategy; illustrative 1% fee each direction. Excludes spreads, distributions, share consolidations and NZ tax.</p></details></article>';
    };
    target.innerHTML='<strong>NZX · LEARNING FROM ITS DECISIONS</strong>'+
      '<p>'+safe(stats.recorded||0)+' original NZX paper ideas · '+safe(stats.closed||0)+' finished · '+
      safe(stats.negative||0)+' losing · '+safe(stats.no_entry||0)+' unfilled; '+
      safe(us.recorded||0)+' US opinions separately tracked.</p>'+
      '<p class="muted">The process is: make an evidence-based prediction, preserve it, check the later outcome, diagnose the error, then test a revised rule against new data. The original opinion is never rewritten.</p>'+
      (lessonCards||'<p>No graded lessons yet. The system must gather later outcomes first.</p>')+
      '<div class="divider"></div><strong>NZX · PAPER-TRADING SCOREBOARD (NZD)</strong>'+
      '<p>'+safe(stats.recorded||0)+' frozen paper opinions · '+safe(stats.opened||0)+' opened positions · '+
      safe(stats.closed||0)+' completed · '+safe(stats.positive||0)+' gains · '+
      safe(stats.negative||0)+' losses · '+safe(stats.no_entry||0)+' missed entry prices.</p>'+
      '<p class="muted">A paper purchase only happens on a subsequent observed NZX closing price, up to 14 days after the original decision. A +12% close triggers a paper profit review; otherwise it closes at a verified price on/after 30 days. No real money, no retrospectively invented wins, and no SPY benchmark comparisons. Fees are illustrative (1% each way).</p>'+
      (records.length?records.slice(0,20).map(recordHtml).join(''):
        '<p>No qualifying NZX paper decision has been frozen yet. Scout is waiting for enough financial evidence and issuer-linked disclosures; it will not invent trades to fill the scoreboard.</p>')+
      '<p class="muted">'+safe(paper.benchmark_status||'NZX benchmark validation pending')+'</p>';
  }
  function renderSource(){
    if(!active())return;
    if($('sources-list'))$('sources-list').insertAdjacentHTML('beforeend',
      '<div class="source-row"><div><div class="source-name">NZX financial research and paper trading (NZD)</div>'+
      '<div class="source-info">'+safe(nzx.coverage?.verified_eod||0)+' verified closing prices of '+
      safe(nzx.coverage?.listed||0)+' listed securities; '+safe(nzx.coverage?.financially_scored||0)+' financially screened</div></div>'+
      '<div class="source-status">RESEARCH ONLY</div></div>');
    if($('nzx-learning'))$('nzx-learning').textContent='NZX outcomes are tracked on a separate NZD paper-trading scoreboard. Machine-learning ranking: NOT ACTIVE. '+(nzx.learning?.reason||'NZX machine-learning validation is unavailable')+
      ' The existing US model and its historical results are unchanged.';
  }
  async function load(){
    nzx=null;apac=null;feedback=null;
    const read=async (path)=>{
      try{
        const response=await fetch('./data/'+path+'?v='+Date.now(),{cache:'no-store'});
        return response.ok?await response.json():null;
      }catch{return null}
    };
    const [n,a,l]=await Promise.all([read('nzx_research.json'),read('apac.json'),read('learning_review.json')]);
    if(n?.market==='NZX'&&n?.currency==='NZD'&&Array.isArray(n.candidates))nzx=n;
    if(a?.markets?.NZX)apac=a;
    if(l?.schema_version===1&&l?.summary&&Array.isArray(l.lessons))feedback=l;
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
