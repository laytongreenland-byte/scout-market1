'use strict';
// Paper results are read-only, from the backend's frozen decision journal.
// No trade execution, user brokerage connection or post-hoc price targets.
const ScoutResults=(()=>{
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=x=>typeof x==='number'&&Number.isFinite(x)?x:null;
  const usd=x=>number(x)===null?'—':'US$'+Number(x).toLocaleString('en-NZ',{minimumFractionDigits:2,maximumFractionDigits:2});
  const percent=x=>number(x)===null?'—':(x>0?'+':'')+x.toFixed(2)+'%';
  const when=s=>{if(!s)return 'Unknown date';let d=new Date(s);return isNaN(+d)?'Unknown date':d.toLocaleDateString('en-NZ',{timeZone:'Pacific/Auckland',day:'numeric',month:'short',year:'numeric'})};
  const completed=new Set(['TARGET_REACHED','CLOSED_GAIN','CLOSED_LOSS']);
  const skips=new Set(['QUALITY GATE NOT MET','ABOVE BASE CASE','POSSIBLE VALUE TRAP','NO RELIABLE PRICE RANGE']);
  const unverified=new Set(['UNVERIFIED']);
  let last=null,filter='all',expanded=false;
  const descriptions={
    'TARGET_REACHED':'Sell-review level reached at a later recorded close',
    'CLOSED_GAIN':'Finished with a gain after estimated trading costs',
    'CLOSED_LOSS':'Finished with a loss after estimated trading costs',
    'NO_ENTRY':'Buy price never reached in the 14-day entry window',
    'WAITING_TO_BUY':'Waiting for the proposed buy price to be observed',
    'OPEN':'Hypothetical purchase recorded; the outcome is still developing',
    'OBSERVED_AFTER_SKIP':'Scout avoided this purchase; subsequent price move shown',
    'OBSERVING_SKIP':'Scout said not to buy; observing what happens next',
    'UNVERIFIED':'Insufficient trustworthy price history to judge this idea'
  };
  const statusLabel={
    'TARGET_REACHED':'Target reached',
    'CLOSED_GAIN':'Closed up',
    'CLOSED_LOSS':'Closed down',
    'NO_ENTRY':'Never bought',
    'WAITING_TO_BUY':'Waiting',
    'OPEN':'Open paper trade',
    'OBSERVED_AFTER_SKIP':'Skipped · observed',
    'OBSERVING_SKIP':'Skipped · pending',
    'UNVERIFIED':'Unverified'
  };
  function resultClass(status){
    if(status==='TARGET_REACHED'||status==='CLOSED_GAIN')return 'results-good';
    if(status==='CLOSED_LOSS')return 'results-bad';
    return 'results-neutral';
  }
  function card(row){
    const a=row.result||{},status=a.status||'UNVERIFIED',trade=!skips.has(row.signal);
    const money=(label,n)=>'<div><span>'+esc(label)+'</span><strong>'+esc(usd(n))+'</strong></div>';
    let stats='';
    if(number(a.entry_price)!==null){
      stats+='<div class="results-realized">'+money('Paper entry close',a.entry_price);
      if(number(a.exit_price)!==null)stats+=money('Paper exit close',a.exit_price);
      stats+='</div>';
    }
    if(completed.has(status)){
      stats+='<div class="results-outcomes"><div><span>Net paper return*</span><strong class="'+((a.net_return_pct||0)>0?'results-up':'results-down')+'">'+esc(percent(a.net_return_pct))+'</strong></div>'+
        '<div><span>SPY, same dates</span><strong>'+esc(percent(a.spy_return_pct))+'</strong></div>'+
        '<div><span>Beat SPY by</span><strong class="'+((a.excess_after_cost_pct||0)>0?'results-up':'results-down')+'">'+esc(percent(a.excess_after_cost_pct))+'</strong></div></div>';
    }else if(status==='OBSERVED_AFTER_SKIP'){
      stats+='<p class="results-observed">Stock moved '+esc(percent(a.stock_change_pct))+' versus SPY '+esc(percent(a.spy_change_pct))+' after Scout said not to buy. <strong>Not counted as a win.</strong></p>';
    }
    const originalTargets=number(row.buy_ceiling)!==null&&number(row.sell_review)!==null?
      '<div class="results-original">'+money('Scout said consider buying below',row.buy_ceiling)+money('Scout said review selling near',row.sell_review)+'</div>':
      '<div class="results-original-note">Scout did not have enough suitable valuation evidence for a defensible buy/sell range.</div>';
    return '<article class="card results-card '+resultClass(status)+'">'+
      '<div class="flex-between"><div><strong class="results-symbol">'+esc(row.symbol)+'</strong> <span class="results-company">'+esc(row.name||'')+'</span></div>'+
      '<span class="results-state">'+esc(statusLabel[status]||status)+'</span></div>'+
      '<p class="results-meta">Originally '+esc(row.signal||'Unknown')+' · '+esc(when(row.decision_at))+' · '+esc(usd(row.reference_price))+' at the time</p>'+
      originalTargets+stats+
      '<p class="results-explanation">'+esc(descriptions[status]||a.reason||'Outcome pending')+'</p>'+
      '<details class="results-drill"><summary>Original reasons and risks</summary><p><strong>Why Scout thought this:</strong> '+esc(row.why||'Not recorded')+'</p>'+
      '<p><strong>Main risk noted at the time:</strong> '+esc(row.risk||'Not recorded')+'</p>'+
      '<p><strong>Original quote timestamp:</strong> '+esc(when(row.quote_at))+'</p>'+
      '<p><strong>What happened:</strong> '+esc(a.reason||'No verified outcome yet')+'</p>'+
      (number(a.net_return_pct)!==null?'<p>* The result deducts an illustrative '+esc(number(a.estimated_round_trip_friction_pct)??1)+'% in buy/sell costs; it excludes dividends, splits, NZ FX and tax.</p>':'')+
      '</details></article>';
  }
  function passes(row){
    const status=row.result?.status||'UNVERIFIED';
    if(filter==='trade')return !skips.has(row.signal);
    if(filter==='closed')return completed.has(status);
    if(filter==='loss')return status==='CLOSED_LOSS'||(status==='TARGET_REACHED'&&number(row.result?.net_return_pct)<0);
    if(filter==='skip')return skips.has(row.signal);
    if(filter==='unverified')return unverified.has(status);
    return true;
  }
  function renderList(){
    if(!last)return;
    const list=(last.records||[]).filter(passes);
    const visible=expanded?list:list.slice(0,12);
    $('results-list').innerHTML=visible.length?visible.map(card).join(''):
      '<div class="card small-notice">No records match this category yet. Scout does not create pretend historical results.</div>';
    if(!expanded&&visible.length<list.length){
      const b=document.createElement('button');
      b.type='button';b.className='show-more';
      b.textContent='Show '+(list.length-visible.length)+' more earlier opinions';
      b.addEventListener('click',()=>{expanded=true;renderList()});
      $('results-list').appendChild(b);
    }
  }
  function render(data){
    last=data.research?.scoreboard||{summary:{},records:[],legacy_research_flags:0};
    const s=last.summary||{};
    const count=n=>Number.isFinite(Number(n))?String(n):'0';
    $('results-stats').innerHTML=[
      [count(s.closed),'Completed paper trades'],
      [count(s.positive),'Profitable'],
      [count(s.negative),'Loss-making']
    ].map(x=>'<div><strong>'+esc(x[0])+'</strong><span>'+esc(x[1])+'</span></div>').join('');
    $('results-stat-note').textContent=(s.recorded||0)+' frozen opinions · '+(s.purchase_scenarios||0)+
      ' with buy/sell scenarios · '+(s.opened||0)+' paper positions opened · '+
      (s.not_triggered||0)+' never bought · '+(s.benchmark_beaten||0)+' closed paper trades beat SPY after estimated costs.';
    $('results-coverage').textContent=(last.records||[]).length+' recent records available';
    const legacy=last.legacy_research_flags||0;
    $('results-legacy').innerHTML='<strong>Keeping the score fair</strong><p>'+
      'Scout previously recorded '+esc(legacy)+' earlier INVESTIGATE research flags without frozen buy/sell prices. '+
      'Those earlier ideas are <strong>not graded as trades</strong>: creating target prices after the fact would make the results misleading. '+
      'All new recorded opinions preserve their original levels and explanations.</p>'+
      '<p class="muted">Results are based on later recorded daily closing prices, not intraday trades or actual orders. Missing data stays unverified. Winners and losers both remain visible; a missed entry is not a loss or a win. This historical research does not establish a profitable strategy.</p>';
    renderList();
  }
  function setup(){
    $('results-filter').addEventListener('change',e=>{filter=e.target.value;expanded=false;renderList()});
  }
  return {render,setup};
})();
