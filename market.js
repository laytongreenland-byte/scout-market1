'use strict';
// Separate public listing discovery. This data NEVER counts as quotes,
// financial diligence, Sharesies availability or a Scout buy candidate.
const ScoutMarket=(()=>{
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let catalog=null,latest=null,apac=null,sdd=null,query='',type='all';
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
    stats.textContent=count(total)+' exchange listings discovered (US/ASX/NZX) · '+count(quoted)+' US Scout price quotes · '+count(screened)+' US companies screened financially.';
    const usReady=catalog.status==='READY';
    markets.innerHTML='<span>US: '+esc(usReady?'2 official directories':'partial directory')+'</span>'+
      ['ASX','NZX'].map(m=>'<span>'+m+': '+esc(catalog.markets?.[m]?.status==='DISCOVERED'?count(catalog.markets[m].listed_in_directory)+' listed (no prices)':catalog.markets?.[m]?.status==='STALE_DIRECTORY'?'cached directory (stale)':'not connected')+'</span>').join('');
    if(sdd){const n=Object.values(sdd.scans||{}).reduce((a,x)=>a+(Array.isArray(x)?x.length:0),0);
      markets.innerHTML+='<span>StocksDeepDive: '+esc(sdd.status==='AVAILABLE'?count(n)+' research rows':sdd.status==='PARTIAL'?'partial':'unavailable')+'</span>';
    }
    footer.textContent='Exchange directory listings do NOT confirm Sharesies availability. ASX/NZX directory discovery does not include integrated prices, financial screening or investment signals. US screening is unchanged. No discovered listing is a buy recommendation.';
    if(!query){
      list.innerHTML='<div class="market-directory-message">Search by company or ticker to explore exchange listings. Independent research, when available, is labelled StocksDeepDive and is not a Scout buy signal. <a href="https://stocksdeepdive.com/api" target="_blank" rel="noopener noreferrer">Source and methodology</a>.</div>';
      return;
    }
    const matches=catalog.items.filter(x=>(type==='all'||x.type===type)&&
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
      (research.has(x.market==='ASX'?x.symbol+'.AX':x.symbol)?' · <a href="https://stocksdeepdive.com/s/'+encodeURIComponent(x.market==='ASX'?x.symbol+'.AX':x.symbol)+'" target="_blank" rel="noopener noreferrer">StocksDeepDive research</a>':'')+'</small></div>').join('')+
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
      const response=await fetch('./data/stocksdeepdive.json?nocache='+Date.now(),{cache:'no-store'});
      if(response.ok){const obj=await response.json();if(obj?.provider==='StocksDeepDive'&&obj?.recommendation_influence===false)sdd=obj}
    }catch{sdd=null}
    render();
  }
  function setup(){
    $('market-directory-search').addEventListener('input',e=>{query=e.target.value.trim().toLowerCase();render()});
    $('market-directory-type').addEventListener('change',e=>{type=e.target.value;render()});
    load();
  }
  function updateLatest(snapshot){
    latest=snapshot;
    render();
  }
  return {setup,render:updateLatest,load};
})();
