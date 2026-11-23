'use strict';
// Separate public listing discovery. This data NEVER counts as quotes,
// financial diligence, Sharesies availability or a Scout buy candidate.
const ScoutMarket=(()=>{
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let catalog=null,latest=null,apac=null,sdd=null,canary=null,query='',type='all',market='all';
  const count=n=>Number(n||0).toLocaleString('en-NZ');
  function render(){
    const stats=$('market-directory-stats'),markets=$('market-directory-markets');
    const list=$('market-directory-results'),footer=$('market-directory-disclaimer');
    if(!stats||!markets||!list||!footer)return;
    if(!catalog||!(catalog.items||[]).length){
      stats.textContent='Exchange directory not yet available. Current Scout price scanning is unaffected.';
      markets.innerHTML='<span>US: discovery pending</span><span>ASX: not connected</span><span>NZX: not connected</span>';
      list.innerHTML='<div class="market-directory-message">The first catalogue refresh may not have completed yet. Try again after a successful market scan.</div>';
      footer.textContent='No unsupported instruments have been added to Scout recommendations.';
      return;
    }
    const total=catalog.counts?.listed_total??catalog.items.length;
    const quoted=latest?.coverage?.quotes_fresh_this_scan??0;
    const screened=latest?.research?.screened_with_financials??0;
    const regionalQuotes=(apac?.quotes||[]).filter(q=>q?.research_only===true&&q?.price_type==='EOD').length;
    stats.textContent=count(total)+' exchange listings discovered (not confirmed Sharesies listings) · '+count(quoted)+' US prices · '+count(screened)+' US companies screened · '+count(regionalQuotes)+' verified regional EOD research closes.';
    const usReady=catalog.status==='READY';
    markets.innerHTML='<span>US: '+esc(usReady?'2 official directories':'partial directory')+'</span>'+
      ['ASX','NZX'].map(m=>'<span>'+m+': '+esc(catalog.markets?.[m]?.status==='DISCOVERED'?count(catalog.markets[m].listed_in_directory)+' listed (no prices)':catalog.markets?.[m]?.status==='STALE_DIRECTORY'?'cached directory (stale)':'not connected')+'</span>').join('');
    for(const m of ['NZX','ASX']){
      const record=apac?.markets?.[m];
      if(record)markets.innerHTML+='<span>'+m+' EOD: '+esc(record.status==='PRICE_RESEARCH'?count(record.recent_prices)+' recent prices':record.status==='NO_API_KEY'?'provider key missing':record.status==='NO_VALID_DIRECTORY'?'directory missing':'no verified prices')+'</span>';
    }
    if(canary){
      const when=String(canary.checked_at||'').slice(0,16).replace('T',' ')+' UTC';
      markets.innerHTML+='<span>Provider check '+esc(when)+': NZX directory '+esc(canary.NZX?.directory||'not tested')+' / NZX price '+esc(canary.NZX?.sample_price||'not tested')+' / ASX price '+esc(canary.ASX?.sample_price||'not tested')+'</span>';
    }
    if(sdd){const n=Object.values(sdd.scans||{}).reduce((a,x)=>a+(Array.isArray(x)?x.length:0),0);
      const asx=sdd.asx_research_status==='ACCESS_DENIED'?'ASX access denied':sdd.asx_research_status==='AVAILABLE'?'ASX research available':'ASX research unavailable';
      markets.innerHTML+='<span>StocksDeepDive: '+esc(count(n)+' research rows; '+asx)+'</span>';
    }
    footer.textContent='Sharesies publicly advertises 5,000+ US, 1,700+ Australian and 120+ NZ company shares, plus 4,500+ ETFs. Those are platform-wide approximate counts, NOT a verified export of tradable symbols. Regional EOD prices appear only when a separate authenticated provider returns validated closes. No NZX/ASX price is included in the original US recommendations, paper trading or learning.';
    if(!query){
      list.innerHTML='<div class="market-directory-message">Search by company or ticker to explore exchange listings. Independent research, when available, is labelled StocksDeepDive and is not a Scout buy signal. <a href="https://stocksdeepdive.com/api" target="_blank" rel="noopener noreferrer">Source and methodology</a>.</div>';
      return;
    }
    const matches=catalog.items.filter(x=>(market==='all'||x.market===market)&&(type==='all'||x.type===type)&&
      ((x.symbol||'').toLowerCase().includes(query)||(x.name||'').toLowerCase().includes(query)));
    const shown=matches.slice(0,35);
    const research=new Map();
    for(const scan of Object.values(sdd?.scans||{}))for(const q of (Array.isArray(scan)?scan:[])){
      if(q?.ticker){const symbol=q.ticker.toUpperCase();if(!research.has(symbol))research.set(symbol,q)}
    }
    const quotes=new Map((apac?.quotes||[]).filter(q=>q&&q.market&&q.symbol&&q.price_type==='EOD'&&q.research_only===true).map(q=>[q.market+':'+q.symbol,q]));
    list.innerHTML=shown.map(x=>'<div class="market-directory-row"><div><strong>'+esc(x.symbol)+'</strong>'+
      '<p>'+esc(x.name||'Unknown security')+'</p></div><small>'+esc(x.exchange)+' · '+esc(x.type)+
      (quotes.has(x.market+':'+x.symbol)?' · EOD '+esc(quotes.get(x.market+':'+x.symbol).currency)+' '+esc(quotes.get(x.market+':'+x.symbol).close)+' ('+esc(quotes.get(x.market+':'+x.symbol).date)+')':'')+
      (research.has(x.market==='ASX'?x.symbol+'.AX':x.symbol)?' · <a href="https://stocksdeepdive.com/s/'+encodeURIComponent(x.market==='ASX'?x.symbol+'.AX':x.symbol)+'" target="_blank" rel="noopener noreferrer">StocksDeepDive research</a>':'')+
      (x.market==='NZX'?' · <a href="https://www.nzx.com/instruments/'+encodeURIComponent(x.symbol)+'" target="_blank" rel="noopener noreferrer">NZX listing</a>':'')+
      (x.market==='ASX'?' · <a href="https://stockanalysis.com/quote/asx/'+encodeURIComponent(x.symbol)+'/" target="_blank" rel="noopener noreferrer">External ASX quote</a>':'')+'</small></div>').join('')+
      '<div class="market-directory-message">'+(matches.length?count(matches.length)+' exchange listings matched. Showing first '+shown.length+'.':'No matching securities in the available exchange directory.')+'</div>';
  }
  async function load(){
    try{
      const response=await fetch('./data/market_catalog.json?nocache='+Date.now(),{cache:'no-store'});
      if(!response.ok)throw Error('Directory unavailable');
      const obj=await response.json();
      if(!obj||!Array.isArray(obj.items)||!obj.counts||obj.sharesies_availability_verified!==false)
        throw Error('Directory schema not recognised');
      catalog=obj;
    }catch{
      catalog=null;
    }
    try{
      const response=await fetch('./data/apac.json?nocache='+Date.now(),{cache:'no-store'});
      if(response.ok){const v=await response.json();if(v&&Array.isArray(v.quotes))apac=v}
    }catch{apac=null}
    try{
      const response=await fetch('./data/regional_canary.json?nocache='+Date.now(),{cache:'no-store'});
      if(response.ok){
        const obj=await response.json();
        if(obj?.research_only===true&&obj.NZX&&obj.ASX)canary=obj;
      }
    }catch{canary=null}
    try{
      const response=await fetch('./data/stocksdeepdive.json?nocache='+Date.now(),{cache:'no-store'});
      if(response.ok){const obj=await response.json();if(obj?.provider==='StocksDeepDive'&&obj?.recommendation_influence===false)sdd=obj}
    }catch{sdd=null}
    render();
  }
  function setup(){
    $('market-directory-search').addEventListener('input',e=>{query=e.target.value.trim().toLowerCase();render()});
    $('market-directory-market').addEventListener('change',e=>{market=e.target.value;render()});
    $('market-directory-type').addEventListener('change',e=>{type=e.target.value;render()});
    load();
  }
  function updateLatest(snapshot){
    latest=snapshot;
    render();
  }
  return {setup,render:updateLatest,load};
})();
