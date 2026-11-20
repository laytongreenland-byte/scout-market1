'use strict';
let snapshot=null,filter='all';
const $=id=>document.getElementById(id);
const escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeLink=s=>{try{let u=new URL(s);return ['https:','http:'].includes(u.protocol)?u.href:null}catch{return null}};
const nzTime=s=>{if(!s)return 'Time unverified';const d=new Date(s);return Number.isNaN(+d)?'Time unverified':d.toLocaleString('en-NZ',{timeZone:'Pacific/Auckland',day:'numeric',month:'short',hour:'numeric',minute:'2-digit',hour12:true})+' NZ time'};
const fmt=n=>Number(n).toLocaleString('en-NZ',{maximumFractionDigits:2,minimumFractionDigits:2});
const ageHours=s=>s?(Date.now()-new Date(s).getTime())/3600000:Infinity;
function selectTab(tab){document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.id==='tab-'+tab));document.querySelectorAll('.bottom-nav button').forEach(b=>{let active=b.dataset.tab===tab;b.classList.toggle('active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});scrollTo({top:0,behavior:'instant'})}
function eventHtml(e){const url=safeLink(e.url);const tag=e.type==='SEC'?'US FILING':e.type==='MACRO'?'MACRO':'NZX';const tagClass=e.sentiment==='negative'?'negative':e.sentiment==='positive'?'research':e.type==='MACRO'?'macro':'';return `<${url?'a href="'+escapeHtml(url)+'" target="_blank" rel="noopener noreferrer"':'div'} class="event-card"><div class="event-head"><span class="tag ${tagClass}">${tag}${e.ticker?' · '+escapeHtml(e.ticker):''}</span><time>${escapeHtml(nzTime(e.published_at))}</time></div><strong>${escapeHtml(e.title||'Untitled disclosure')}</strong><div class="event-meta">${escapeHtml(e.source||'Unknown source')}${e.primary?' · Primary source':' · Secondary feed'}${e.form?' · '+escapeHtml(e.form):''}${url?' · Open source ↗':''}</div></${url?'a':'div'}>`}
function prioritiesHtml(items){if(!items.length)return `<div class="empty-state card"><div class="empty-icon">◎</div><strong>No convincing research trigger detected</strong><p>That's a valid result. The scanner does not turn routine announcements into buying tips. Your ChatGPT weekly research is separate from this page.</p></div>`;return items.slice(0,5).map(e=>`<div class="card" style="margin-bottom:9px"><div class="event-head"><span class="tag research">RESEARCH · NOT A BUY SIGNAL</span><time>${escapeHtml(nzTime(e.published_at))}</time></div><strong style="display:block;font-size:13px;line-height:1.5">${escapeHtml(e.title)}</strong><p style="font-size:12px;line-height:1.6;color:var(--sub);margin-top:10px">${escapeHtml(e.reason||'Material-looking development requiring manual verification.')}</p>${safeLink(e.url)?`<a style="display:block;margin-top:9px;font-size:12px" href="${escapeHtml(safeLink(e.url))}" target="_blank" rel="noopener noreferrer">Read source →</a>`:''}</div>`).join('')}
function quoteHtml(q){const valid=typeof q.price==='number'&&q.price>0;const stale=Boolean(q.stale)||ageHours(q.price_at)>75;const pct=q.change_pct;const ch=typeof pct==='number'?`<div class="quote-change ${pct>0?'up':pct<0?'down':''}">${pct>0?'+':''}${fmt(pct)}% vs previous close</div>`:`<div class="quote-change">Change unavailable</div>`;return `<div class="quote-row"><div class="ticker-circle">${escapeHtml(q.symbol.slice(0,5))}</div><div class="quote-left"><strong>${escapeHtml(q.symbol)}</strong><div>${valid?(stale?'STALE · ':'As of ')+escapeHtml(nzTime(q.price_at)):'No verified quote'} · ${escapeHtml(q.source||'Finnhub')}</div></div><div class="quote-right"><div class="quote-price">${valid?escapeHtml(q.currency||'USD')+' '+fmt(q.price):'—'}</div>${valid&&!stale?ch:stale?'<div class="quote-change down">Stale — verify independently</div>':''}</div></div>`}
// Transparent, evidence-backed opportunity screen. A rank is NOT a trade instruction.
const badgeStatus=s=>s==='INVESTIGATE'?'investigate':s==='LOW PRIORITY'?'low':'watch';
function pricePlanHtml(p,compact=false){
  if(!p)return '<div class="price-plan plan-missing">No current entry-price assessment available.</div>';
  const signal=String(p.signal||'NO RELIABLE PRICE RANGE');
  const cls=signal==='ENTRY CANDIDATE'?'plan-entry':signal==='ABOVE BASE CASE'||signal==='POSSIBLE VALUE TRAP'||signal==='QUALITY GATE NOT MET'?'plan-risk':signal==='WAIT FOR ENTRY'?'plan-wait':'plan-missing';
  const money=v=>typeof v==='number'&&Number.isFinite(v)&&v>0?'USD '+fmt(v):'Not available';
  let html='<section class="price-plan '+cls+'"><div class="plan-header"><strong>'+escapeHtml(signal)+'</strong><span>ILLUSTRATIVE · NOT A TRADE ORDER</span></div>';
  if(typeof p.entry_ceiling==='number'){
    html+='<div class="plan-values"><div><span>'+(signal==='ENTRY CANDIDATE'?'Research entry zone':signal==='QUALITY GATE NOT MET'?'Unqualified scenario zone':'Possible entry zone (not triggered)')+'</span><strong>'+money(p.entry_floor)+' – '+money(p.entry_ceiling)+'</strong></div><div><span>Review / take-profit zone</span><strong>'+money(p.exit_review_low)+' – '+money(p.exit_review_high)+'</strong></div></div>';
  }else{
    html+='<p class="plan-reason">'+escapeHtml(p.reason||'Insufficient market evidence')+'</p>';
  }
  if(!compact && typeof p.entry_ceiling==='number'){
    html+='<div class="plan-downside">Bear-case scenario: '+money(p.bear_case)+' · Illustrative base-case change from current quote: '+(typeof p.scenario_upside_pct==='number'?(p.scenario_upside_pct>0?'+':'')+fmt(p.scenario_upside_pct)+'%':'—')+'</div>';
    html+='<p class="plan-reason">'+escapeHtml(p.reason||'')+'</p>';
    if(p.assumptions)html+='<div class="plan-method">Inputs: trailing P/E '+escapeHtml(p.assumptions.trailing_pe)+'× · assumed earnings growth '+escapeHtml(p.assumptions.earnings_growth_assumed_pct)+'% · scenario exit P/E '+escapeHtml(p.assumptions.scenario_exit_pe)+'× · valuation haircut '+escapeHtml(p.assumptions.valuation_haircut_pct)+'%. Upper entry limit also capped by the lower half of the reported 52-week range.</div>';
    html+='<div class="plan-method">'+escapeHtml(p.horizon||'Scenario only')+' · Quote '+escapeHtml(nzTime(p.as_of))+'. Financial ratios may reflect older accounting periods. '+escapeHtml(p.caution||'')+'</div>';
  }
  return html+'</section>';
}

function candidateHtml(c,compact=false){
  const score=typeof c.score==='number'?c.score+'/100':'—';
  const price=typeof c.price==='number'?`USD ${fmt(c.price)}`:'No fresh quote';
  const risks=(c.risks||[]).slice(0,compact?1:3).map(r=>`<li>${escapeHtml(r)}</li>`).join('');
  const evidence=(c.evidence||[]).filter(e=>safeLink(e.url)).slice(0,compact?1:3).map(e=>`<a href="${escapeHtml(safeLink(e.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(e.label)} ↗</a>`).join(' · ');
  return `<article class="card candidate ${badgeStatus(c.status)}"><div class="flex-between"><div class="candidate-brand"><strong>${escapeHtml(c.symbol)}</strong><span>${escapeHtml(c.name||'')}</span></div><span class="grade">${score}</span></div><div class="flex-between candidate-sub"><span class="status ${badgeStatus(c.status)}">${escapeHtml(c.status||'WATCH')}</span><span>${price}</span></div>${pricePlanHtml(c.price_plan,compact)}<p class="plain-verdict">${escapeHtml(ScoutCompass.explainCandidate(c))}</p><p class="candidate-thesis">${escapeHtml(c.why||'Review underlying company financials before drawing conclusions.')}</p>${!compact?`<div class="risk-label">MAIN RISKS</div><ul class="risk-list">${risks}</ul><div class="evidence">${evidence||'No verified evidence links yet'}</div><div class="asof">Quote: ${escapeHtml(nzTime(c.as_of))} · Metrics: ${escapeHtml(nzTime(c.fundamentals_at))}</div>`:''}<div class="candidate-disclaimer">${compact?'Research ranking, not a buy signal':'Research score is not a profit probability. Independently verify valuation, FX, tax and trading costs.'}</div></article>`;
}
function alertHtml(a){return `<div class="card urgent-card"><div class="flex-between"><span class="tag negative">URGENT RESEARCH · NOT A BUY SIGNAL</span><time>${escapeHtml(nzTime(a.published_at))}</time></div><h3>${escapeHtml(a.symbol)}: ${escapeHtml(a.headline)}</h3><p>${escapeHtml(a.why)}</p><p class="muted">${escapeHtml(a.risk)}</p>${safeLink(a.source_url)?`<a href="${escapeHtml(safeLink(a.source_url))}" target="_blank" rel="noopener noreferrer">Verify source ↗</a>`:''}</div>`}
function renderResearch(data){
  const r=data.research||{};
  const w=r.weekly||{};
  const ml=r.learning||{};
  $('learning-status').textContent=ml.model_active?'EXPERIMENTAL · LIMITED':(ml.status||'COLLECTING');
  $('learning-recorded').textContent=String(ml.recorded_signals??0);
  $('learning-outcomes').textContent=String(ml.matured_outcomes??0);
  $('learning-weeks').textContent=String(ml.matured_weeks??0);
  $('learning-reason').textContent=ml.reason||'No historical outcomes have matured yet.';
  const v=ml.validation;
  $('learning-validation').textContent=v&&v.independent_test_weeks?
    `Purged forward testing: ${v.independent_test_weeks} separated weeks (${v.holdout_samples} stock observations). The model won ${v.fold_wins} folds. Top-quintile excess return vs SPY, gross: model ${v.model_top20_excess_pct}%, rules ${v.rules_top20_excess_pct}%; improvement ${v.lift_percentage_points} points. These are correlated, hypothetical USD price outcomes, not investment profits.`:
    'ML stays off until at least 52 matured weekly cohorts allow six well-separated, forward-only tests. No investment accuracy is established yet.';
  const paper=r.paper_diagnostics||{};
  $('paper-performance').textContent=paper.matured_outcomes?
    `${paper.matured_outcomes} paired 30-day observations from ${paper.matured_weeks} weekly cohorts. ${paper.usable_rule_weeks||0} weeks with enough candidates to compare the highest-scoring 20%. ${paper.usable_rule_weeks?'Average top-quintile gross excess vs SPY: '+paper.mean_excess_pct+'%.':''} ${paper.sufficient_for_comparison?'Still preliminary.':'INSUFFICIENT independent history for performance claims.'} Excludes broker costs, FX movements, tax and dividends.`:
    'No completed 30-day SPY-matched observations yet. A high research score is not evidence of profit.';
  const entries=r.entry_candidates||[];
  const watch=r.entry_watch||[];
  $('entry-status').textContent=entries.length?entries.length+' preliminary entry candidates (verify before trading)':'No evidence-backed entry candidate at current prices';
  $('entry-list').innerHTML=entries.length?entries.slice(0,4).map(c=>candidateHtml(c,false)).join(''):
    '<div class="empty-state card"><strong>NO ENTRY SIGNAL RIGHT NOW</strong><p>Scout has not found a company meeting both its financial-quality and margin-of-safety checks. This is a valid result, not a system failure.</p></div>'+
    watch.slice(0,3).map(c=>candidateHtml(c,false)).join('');
  $('overview-entry').innerHTML=entries.length?candidateHtml(entries[0],true):
    '<div class="card small-notice">No purchase-price scenario currently meets Scout’s conservative evidence checks. See Research for watch levels.</div>';
  const liveMap=new Map([...(r.candidates||[]),...watch,...entries].map(c=>[c.symbol,c]));
  const liveCandidate=c=>{const x=liveMap.get(c.symbol);return x?Object.assign({},c,{price:x.price,as_of:x.as_of,price_plan:x.price_plan}):Object.assign({},c,{price_plan:null})};
  const shortlist=w.shortlist||[];
  $('research-count').textContent=`${r.screened_with_financials||0} of ${r.equity_universe_size||r.universe_size||0} shares screened with financials; ETFs tracked separately`;
  $('research-checked').textContent=r.generated_at?'Screened '+nzTime(r.generated_at):'Awaiting the first research scan';
  $('weekly-status').textContent=w.generated_at?`Research week ${w.week_start} · compiled ${nzTime(w.generated_at)}`:'Waiting for first weekly shortlist';
  $('weekly-verdict').textContent=w.verdict||'No ranked investment candidates yet';
  $('weekly-list').innerHTML=shortlist.length?shortlist.map(c=>candidateHtml(liveCandidate(c),false)).join(''):
    `<div class="empty-state card"><strong>No evidence-backed candidates yet</strong><p>The free service is loading company metrics gradually. Missing data does not count as an opportunity.</p></div>`;
  $('overview-shortlist').innerHTML=shortlist.length?shortlist.slice(0,2).map(c=>candidateHtml(liveCandidate(c),true)).join(''):
    `<div class="empty-state card"><strong>Financial screening still warming up</strong><p>Hourly scans collect prices and rotate through company metrics.</p></div>`;
  const alerts=r.urgent_alerts||[];
  $('urgent-list').innerHTML=alerts.length?alerts.map(alertHtml).join(''):
    `<div class="card small-notice">No independently supported urgent catalyst currently meets Scout's strict research-alert rules.</div>`;
  $('overview-alerts').innerHTML=alerts.length?alerts.slice(0,1).map(alertHtml).join(''):'';
  const moves=r.daily_movers||[];
  $('movers-list').innerHTML=moves.length?moves.slice(0,12).map(m=>`<div class="mover-row"><strong>${escapeHtml(m.symbol)}</strong><span class="${m.change_pct>=0?'up':'down'}">${m.change_pct>=0?'+':''}${fmt(m.change_pct)}%</span><small>${escapeHtml(nzTime(m.price_at))}</small></div>`).join(''):'<p class="muted">No verified moves beyond 4% in the latest quote snapshot.</p>';
  const calls=(r.research_log||[]).slice().reverse();
  $('research-log').innerHTML=calls.length?calls.slice(0,20).map(h=>`<div class="log-row"><strong>${escapeHtml(h.symbol)}</strong><span>Flagged ${escapeHtml(h.flagged_at?.slice(0,10)||'')} at USD ${fmt(h.reference_price||0)}</span><span>${typeof h.return_7d_pct==='number'?`7d: ${h.return_7d_pct>0?'+':''}${fmt(h.return_7d_pct)}%`:'7d: pending'} · ${typeof h.return_30d_pct==='number'?`30d: ${h.return_30d_pct>0?'+':''}${fmt(h.return_30d_pct)}%`:'30d: pending'}</span></div>`).join(''):
   '<p class="muted">No paper-only investigation calls recorded. Scout won’t manufacture a winning track record.</p>';
}

function render(data){snapshot=data;const sources=data.sources||[];const good=sources.filter(s=>s.ok).length;const total=sources.length;const age=ageHours(data.generated_at);const status=data.status==='pending'?'Not connected':!good?'Source failure':age>6?'Stale data':data.status==='ok'?'Scan complete':'Partial scan';$('live-pill').innerHTML=`<span class="dot ${good&&age<=6?'dot-green':good?'dot-amber':'dot-grey'}"></span>${escapeHtml(status)}`;$('scan-time').textContent=data.generated_at?'Checked '+nzTime(data.generated_at):'Not yet run';$('event-count').textContent=data.generated_at?String((data.events||[]).length):'—';$('hero-desc').textContent=data.generated_at?'Public-source developments retrieved':'Awaiting the first source check';$('source-health').textContent=data.generated_at?`${good} of ${total} source checks succeeded · ${age>6?'Refresh delayed or unavailable':'Not a real-time feed'}`:'No verified sources yet';$('data-age').textContent=data.generated_at?'Last scan: '+nzTime(data.generated_at):'Waiting for scan';$('priorities').innerHTML=prioritiesHtml(data.priorities||[]);$('priority-caption').textContent=(data.priorities||[]).length+' research triggers';const events=(data.events||[]).slice().sort((a,b)=>new Date(b.published_at)-new Date(a.published_at));$('latest-events').innerHTML=events.length?events.slice(0,3).map(eventHtml).join(''):`<div class="empty-state card"><strong>No verified disclosures loaded</strong><p>Configure the scanner and check its source health. No news is invented when a source fails.</p></div>`;$('all-events').innerHTML=(events.filter(e=>filter==='all'||e.type===filter).map(eventHtml).join(''))||`<div class="empty-state card"><strong>No matching disclosures</strong><p>Try another filter, or check source availability under Setup.</p></div>`;const quoteList=data.quotes||[];const symbols=data.tracked_symbols||[];const goodQuotes=quoteList.filter(q=>typeof q.price==='number'&&!q.stale&&ageHours(q.price_at)<=75).length;$('quote-warning').textContent=goodQuotes?`Quotes loaded for ${goodQuotes} symbols. May be delayed or stale; check each price timestamp and confirm with a broker before trading.`:'No US prices received. Add a FREE FINNHUB_API_KEY to the GitHub repository secrets, then rerun the scan. NZX prices are not included.';renderResearch(data);ScoutCompass.render(data);ScoutResults.render(data);$('sources-list').innerHTML=sources.length?sources.map(s=>`<div class="source-row"><div><div class="source-name">${escapeHtml(s.name)}</div><div class="source-info">${escapeHtml(s.ok?String(s.count||0)+' records · '+nzTime(s.checked_at):s.error||'Not checked')}</div></div><div class="source-status ${s.ok?'ok':''}">${s.ok?'OK':'Unavailable'}</div></div>`).join(''):`<div class="source-row"><span class="source-name">No source checks have run</span><span class="source-status">Pending</span></div>`}
async function load(){const btn=$('refresh-btn');btn.disabled=true;try{const res=await fetch('./data/latest.json?nocache='+Date.now(),{cache:'no-store'});if(!res.ok)throw new Error('HTTP '+res.status);const data=await res.json();render(data)}catch(e){const initial=snapshot||{generated_at:null,status:'pending',sources:[],quotes:[],events:[],priorities:[],tracked_symbols:['AAPL','MSFT','NVDA','GOOGL','AMZN','META','VOO','QQQ']};render(initial);$('quote-warning').textContent='Cannot read the market snapshot here. Publish this project on GitHub Pages and run the scanner. '+String(e.message||'')}finally{btn.disabled=false}}
function budget(){const start=Math.max(0,Number($('initial-budget').value)||0);const monthly=Math.max(0,Number($('monthly-budget').value)||0);localStorage.setItem('scout-budget',JSON.stringify({start,monthly}));$('allocation').innerHTML=`<div class="bar"><span></span></div><div class="alloc-leg"><span>85% diversified: NZ$${fmt(start*.85)}</span><span>15% reserve: NZ$${fmt(start*.15)}</span></div><div class="hint">Up to NZ$${fmt(monthly)} per month. No assumed returns; keep an emergency cash reserve.</div>`}
function transactionCosts(){
  const amount=Math.max(0,Number($('trade-amount').value)||0);
  const dealing=Math.max(0,Number($('dealing-fee').value)||0);
  const fx=Math.max(0,Number($('fx-fee').value)||0);
  const pct=2*(dealing+fx),cash=amount*pct/100;
  $('cost-result').textContent=`Illustrative round-trip: ${fmt(pct)}% = NZ$${fmt(cash)} on NZ$${fmt(amount)}. A trade must overcome this before any net gain (excluding spread, exchange-rate changes and taxes).`;
  localStorage.setItem('scout-costs',JSON.stringify({amount,dealing,fx}));
}
document.querySelectorAll('.bottom-nav button').forEach(b=>b.addEventListener('click',()=>selectTab(b.dataset.tab)));document.querySelectorAll('[data-goto]').forEach(b=>b.addEventListener('click',()=>selectTab(b.dataset.goto)));document.querySelectorAll('.chip').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('selected',c===b));if(snapshot)render(snapshot)}));$('refresh-btn').addEventListener('click',load);try{const data=JSON.parse(localStorage.getItem('scout-budget')||'{}');if(typeof data.start==='number')$('initial-budget').value=data.start;if(typeof data.monthly==='number')$('monthly-budget').value=data.monthly}catch{}$('initial-budget').addEventListener('input',budget);$('monthly-budget').addEventListener('input',budget);
try{const cfg=JSON.parse(localStorage.getItem('scout-costs')||'{}');for(const [id,value] of [['trade-amount',cfg.amount],['dealing-fee',cfg.dealing],['fx-fee',cfg.fx]])if(typeof value==='number'&&value>=0)$(id).value=value}catch{}
for(const id of ['trade-amount','dealing-fee','fx-fee'])$(id).addEventListener('input',transactionCosts);
ScoutCompass.setup();ScoutResults.setup();budget();transactionCosts();load();setInterval(load,5*60*1000);if('serviceWorker'in navigator&&location.protocol==='https:')navigator.serviceWorker.register('./sw.js').catch(()=>{});
