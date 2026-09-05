async function _webSignalStatus(id){try{const s=await req(`/signals/${id}/publication`);const p=s.publication||{},j=s.job||{};let box=document.getElementById('pubState');if(box){box.innerHTML=`<div class="row"><span>مرحله انتشار</span><b>${esc(p.stage||'—')}</b></div><div class="row"><span>Screenshot Job</span><b>${esc(j.status||'—')}</b></div>${p.error_text?`<p class="bad" style="padding:8px">${esc(p.error_text)}</p>`:''}`;if(['WAITING_FOR_CHART','CHART_RECEIVED'].includes(p.stage))setTimeout(()=>_webSignalStatus(id),1800);if(p.stage==='PUBLISHED')toast('سیگنال با تصویر واقعی MT5 منتشر و برای AutoTrade فعال شد');}}catch(e){toast(e.message)}}

signals=async function(){
  const d=await req('/signals?limit=150');
  const o=await req('/signals/options');
  const agents=await req('/chart-agents');
  const online=(agents.items||[]).filter(x=>x.online);
  const options=(agents.items||[]).map(x=>`<option value="${esc(x.account_number)}" ${x.online?'':'disabled'}>${esc(x.account_number)} ${x.online?'🟢':'🔴'}</option>`).join('');
  shell(`<div class="section-title"><h2>سیگنال‌ها</h2><span>${d.items.length} مورد</span></div>
  <section class="card"><h3>صدور Signal از Web Admin</h3>
  <p class="muted">مسیر اجباری: Web → MT5 Chart Agent روی VPS → Screenshot واقعی → Flashcard → Telegram → ACTIVE/AutoTrade.</p>
  ${online.length?`<form id="issueForm"><div class="grid" style="grid-template-columns:repeat(3,minmax(0,1fr))">
    <label>حساب Chart Agent<select name="issuer_account" required>${options}</select></label>
    <label>Market<select name="market_type"><option>GOLD</option><option>FOREX</option><option>CRYPTO</option><option>INDEX</option><option>OTHER</option></select></label>
    <label>Symbol<input name="symbol" value="XAUUSD" required></label>
    <label>Direction<select name="direction"><option>BUY</option><option>SELL</option></select></label>
    <label>Timeframe<select name="timeframe"><option>M5</option><option>M15</option><option>H1</option><option>M1</option><option>M30</option><option>H4</option></select></label>
    <label>Order Type<select name="order_type"><option>MARKET</option><option>BUY_LIMIT</option><option>SELL_LIMIT</option><option>BUY_STOP</option><option>SELL_STOP</option><option>BUY_STOP_LIMIT</option><option>SELL_STOP_LIMIT</option></select></label>
    <label>Entry<input name="entry_price" type="number" step="any" required></label>
    <label>Stop Loss<input name="stop_loss" type="number" step="any" required></label>
    <label>Risk %<input name="risk_percent" type="number" step="0.1" value="1" min="0" max="10"></label>
    <label style="grid-column:span 2">Targets (با کاما)<input name="targets" placeholder="2500,2510,2520" required></label>
    <label>Trailing<input name="trailing_code" value="NEXUS_TRAIL_07"></label>
    <label>Destination<select name="destination"><option>BOTH</option><option>VIP</option><option>FREE</option></select></label>
    <label>Volume Mode<select name="volume_mode"><option>RISK</option><option>FIXED</option></select></label>
    <label>Fixed Lot (اختیاری)<input name="lot_size" type="number" step="0.01"></label>
  </div><div class="actions" style="margin-top:12px"><button type="button" id="reviewSignal" class="primary">REVIEW SIGNAL</button></div></form><div id="reviewBox"></div><div id="pubState"></div>`:`<div class="card bad"><b>MT5 Screenshot Agent آفلاین است.</b><p>تا زمانی که حداقل یک حساب مجاز Chart Agent آنلاین نشود، صدور سیگنال وب عمداً مسدود است.</p></div>`}
  </section>
  <section class="card table"><table><thead><tr><th>کد</th><th>نماد</th><th>جهت</th><th>TF</th><th>وضعیت</th><th>مقصد</th><th>Issuer</th></tr></thead><tbody>${d.items.map(x=>`<tr><td>${esc(x.code)}</td><td>${esc(x.symbol)}</td><td>${esc(x.direction)}</td><td>${esc(x.timeframe)}</td><td>${badge(x.status)}</td><td>${esc(x.destination)}</td><td>${esc(x.issuer_type||'—')}</td></tr>`).join('')}</tbody></table></section>`);
  if(!online.length)return;
  const btn=document.getElementById('reviewSignal');
  btn.onclick=()=>{
    const form=document.getElementById('issueForm'),f=new FormData(form),b=Object.fromEntries(f);
    b.entry_price=+b.entry_price;b.stop_loss=+b.stop_loss;b.risk_percent=+b.risk_percent;
    b.targets=String(b.targets).split(',').map(x=>+x.trim()).filter(x=>Number.isFinite(x)&&x>0);
    b.lot_size=b.lot_size?+b.lot_size:null;b.request_id='WEB-'+(crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random());
    const review=document.getElementById('reviewBox');
    review.innerHTML=`<section class="card"><h3>Review Signal</h3><div class="row"><span>${esc(b.symbol)} ${esc(b.direction)} · ${esc(b.timeframe)}</span><b>${esc(b.destination)}</b></div><div class="row"><span>Entry</span><b>${esc(b.entry_price)}</b></div><div class="row"><span>SL</span><b>${esc(b.stop_loss)}</b></div><div class="row"><span>TP</span><b>${esc(b.targets.join(' / '))}</b></div><div class="row"><span>Chart Agent</span><b>${esc(b.issuer_account)}</b></div><div class="actions"><button id="backReview" class="ghost">بازگشت</button><button id="confirmIssue" class="primary">ISSUE SIGNAL</button></div></section>`;
    document.getElementById('backReview').onclick=()=>review.innerHTML='';
    document.getElementById('confirmIssue').onclick=async()=>{if(!confirm('سیگنال برای Screenshot واقعی MT5 و انتشار ارسال شود؟'))return;try{const r=await req('/signals/issue',{method:'POST',body:JSON.stringify(b)});toast(`${r.code} ایجاد شد؛ منتظر Screenshot MT5`);review.innerHTML='';_webSignalStatus(r.id)}catch(e){toast(e.message)}};
  };
};
