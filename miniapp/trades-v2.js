(() => {
  const tradeState = { tab: 'open', offset: 0, limit: 20, loading: false };

  function h(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  }

  function dt(value) {
    if (!value) return '—';
    try { return new Date(value).toLocaleString('fa-IR'); } catch (_) { return String(value); }
  }

  function num(value, digits = 2) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : '—';
  }

  function healthCard(data) {
    const stateData = data?.state || {};
    const stateName = stateData.state || 'NEEDS_ATTENTION';
    const ok = stateName === 'HEALTHY';
    const checks = data?.checks || {};
    return `<article class="trade-health-v2 ${ok ? 'healthy' : 'attention'}">
      <div class="signal-top"><span class="badge">${h(stateName)}</span><span class="trade-health-dot ${ok ? 'live' : ''}"></span></div>
      <h2>${ok ? 'AutoTrade متصل و فعال است' : stateName === 'DISCONNECTED' ? 'AutoTrade در حال حاضر متصل نیست' : 'AutoTrade نیاز به بررسی دارد'}</h2>
      <div class="trade-checks">
        <span>${checks.subscription ? '✓' : '–'} اشتراک</span>
        <span>${checks.license ? '✓' : '–'} لایسنس</span>
        <span>${checks.mt5_account ? '✓' : '–'} MT5</span>
        <span>${checks.ea_connected ? '✓' : '–'} EA</span>
      </div>
      <div class="trade-health-meta"><span>MT5</span><b>${h(data?.mt5?.account_number ? `****${String(data.mt5.account_number).slice(-4)}` : '—')}</b><span>Last Sync</span><b>${h(dt(stateData.last_sync_at))}</b></div>
    </article>`;
  }

  function liveCard(item, pending = false) {
    return `<article class="trade-v2-card">
      <div class="signal-top"><div><span class="badge">${h(item.direction || item.order_type || '')}</span>${item.signal_code ? `<span class="badge muted">Signal #${h(item.signal_code)}</span>` : ''}</div><span class="status-pill ${pending ? '' : 'success'}">${h(item.status || (pending ? 'PENDING' : 'OPEN'))}</span></div>
      <div class="trade-v2-title"><div><h3>${h(item.symbol || '—')}</h3><small>Ticket ${h(item.ticket || '—')}</small></div><em class="${Number(item.profit || 0) < 0 ? 'negative' : ''}">${pending ? '—' : h(num(item.profit)) + ' $'}</em></div>
      <div class="trade-v2-grid">
        <div><span>Volume</span><b>${h(item.volume ?? '—')}</b></div>
        <div><span>Entry</span><b>${h(item.entry_price ?? '—')}</b></div>
        ${!pending ? `<div><span>Current</span><b>${h(item.current_price ?? '—')}</b></div>` : ''}
        <div><span>SL</span><b>${h(item.stop_loss ?? '—')}</b></div>
        <div><span>TP</span><b>${h(item.take_profit ?? '—')}</b></div>
        ${pending ? `<div><span>Type</span><b>${h(item.order_type || '—')}</b></div>` : ''}
      </div>
      <small class="trade-v2-time">Sync: ${h(dt(item.last_seen_at))}</small>
    </article>`;
  }

  function historyCard(item) {
    return `<article class="trade-v2-card history" data-trade-detail="${h(item.id)}">
      <div class="signal-top"><div><span class="badge">${h(item.direction || item.event_type || '')}</span>${item.signal_id ? `<span class="badge muted">Signal ${h(item.signal_id)}</span>` : ''}</div><span class="status-pill success">${h(item.status || item.event_type || 'HISTORY')}</span></div>
      <div class="trade-v2-title"><div><h3>${h(item.symbol || '—')}</h3><small>Ticket ${h(item.ticket || '—')}</small></div><em class="${Number(item.profit || 0) < 0 ? 'negative' : ''}">${h(num(item.profit))} $</em></div>
      <div class="trade-v2-grid compact"><div><span>Entry</span><b>${h(item.entry_price ?? '—')}</b></div><div><span>Exit</span><b>${h(item.exit_price ?? '—')}</b></div><div><span>Volume</span><b>${h(item.volume ?? '—')}</b></div></div>
      <small class="trade-v2-time">${h(dt(item.created_at))}</small>
    </article>`;
  }

  function empty(tab) {
    const text = tab === 'open' ? 'در حال حاضر معامله بازی توسط AutoTrade ثبت نشده است.' : tab === 'pending' ? 'در حال حاضر سفارش Pending ثبت نشده است.' : 'هنوز معامله بسته‌شده‌ای ثبت نشده است.';
    return `<div class="empty-state">${text}</div>`;
  }

  async function loadTab({ append = false } = {}) {
    if (tradeState.loading || state.route !== 'trades') return;
    tradeState.loading = true;
    const host = document.getElementById('tradesV2List');
    const more = document.getElementById('tradesV2More');
    if (!append && host) host.innerHTML = '<div class="empty-state">در حال دریافت اطلاعات...</div>';
    try {
      const query = new URLSearchParams({ tab: tradeState.tab, limit: String(tradeState.limit), offset: String(tradeState.offset) });
      const data = await api(`/trades?${query}`);
      const items = data.items || [];
      let content = items.map(item => tradeState.tab === 'history' ? historyCard(item) : liveCard(item, tradeState.tab === 'pending')).join('');
      if (!items.length && !append) content = empty(tradeState.tab);
      if (host) append ? host.insertAdjacentHTML('beforeend', content) : host.innerHTML = content;
      if (more) more.hidden = items.length < tradeState.limit;
      bindTradeDetails();
    } catch (err) {
      if (host) host.innerHTML = `<div class="empty-state">دریافت معاملات با مشکل مواجه شد.<br><button class="btn ghost" id="retryTradesV2">تلاش مجدد</button></div>`;
      document.getElementById('retryTradesV2')?.addEventListener('click', () => loadTab());
      if (more) more.hidden = true;
    } finally {
      tradeState.loading = false;
    }
  }

  async function openDetail(id) {
    try {
      const data = await api(`/trades/${encodeURIComponent(id)}`);
      const item = data.trade || {};
      const source = data.source_signal;
      showModal(`Trade #${h(item.ticket || item.id)}`, `
        <div class="signal-detail-head"><div><span class="badge">${h(item.event_type || 'TRADE')}</span><h3>${h(item.symbol || '—')}</h3></div><b>${h(item.direction || '')}</b></div>
        <div class="kv"><span>Volume</span><b>${h(item.volume ?? '—')}</b></div>
        <div class="kv"><span>Entry</span><b>${h(item.entry_price ?? '—')}</b></div>
        <div class="kv"><span>Exit</span><b>${h(item.exit_price ?? '—')}</b></div>
        <div class="kv"><span>P/L</span><b>${h(num(item.profit))} $</b></div>
        ${item.commission != null ? `<div class="kv"><span>Commission</span><b>${h(num(item.commission))}</b></div>` : ''}
        ${item.swap != null ? `<div class="kv"><span>Swap</span><b>${h(num(item.swap))}</b></div>` : ''}
        ${item.slippage != null ? `<div class="kv"><span>Slippage</span><b>${h(num(item.slippage, 4))}</b></div>` : ''}
        ${source ? `<div class="status-panel"><b>سیگنال مبدا ${source.code ? '#' + h(source.code) : ''}</b><div class="kv"><span>Symbol</span><b>${h(source.symbol)}</b></div><div class="kv"><span>Access</span><b>${h(source.access)}</b></div>${source.locked ? '<small class="modal-muted">جزئیات VIP بر اساس دسترسی حساب شما محدود شده است.</small>' : ''}</div>` : ''}`);
    } catch (err) {
      toast('دریافت جزئیات معامله با مشکل مواجه شد.');
    }
  }

  function bindTradeDetails() {
    view.querySelectorAll('[data-trade-detail]').forEach(card => card.addEventListener('click', () => openDetail(card.dataset.tradeDetail)));
  }

  function selectTab(tab) {
    tradeState.tab = tab;
    tradeState.offset = 0;
    document.querySelectorAll('[data-trades-tab]').forEach(btn => btn.classList.toggle('active', btn.dataset.tradesTab === tab));
    loadTab();
  }

  async function openTradesV2() {
    const experience = state.experience;
    if (!experience?.features?.trades) {
      render('subscriptions');
      return;
    }
    state.route = 'trades';
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.toggle('active', btn.dataset.route === 'trades'));
    view.innerHTML = `<section class="page-head"><div><div class="eyebrow">MY EXECUTION</div><h1>معاملات من</h1></div></section>
      <div id="tradeHealthV2"><div class="empty-state">در حال بررسی AutoTrade...</div></div>
      <div class="plan-tabs trades-v2-tabs"><button class="tab active" data-trades-tab="open">باز</button><button class="tab" data-trades-tab="pending">Pending</button><button class="tab" data-trades-tab="history">تاریخچه</button></div>
      <div class="stack" id="tradesV2List"><div class="empty-state">در حال دریافت...</div></div>
      <button class="btn ghost full" id="tradesV2More" hidden>نمایش بیشتر</button>`;
    document.querySelectorAll('[data-trades-tab]').forEach(btn => btn.addEventListener('click', () => selectTab(btn.dataset.tradesTab)));
    document.getElementById('tradesV2More')?.addEventListener('click', () => { tradeState.offset += tradeState.limit; loadTab({ append: true }); });
    try {
      const health = await api('/autotrade/status');
      const host = document.getElementById('tradeHealthV2');
      if (host) host.innerHTML = healthCard(health);
    } catch (err) {
      const host = document.getElementById('tradeHealthV2');
      if (host) host.innerHTML = '<div class="status-panel">وضعیت AutoTrade در دسترس نیست.</div>';
    }
    selectTab('open');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  window.NexusTrades = { open: openTradesV2, detail: openDetail };
  if (window.NexusExperience) window.NexusExperience.renderTrades = openTradesV2;

  document.addEventListener('click', event => {
    const target = event.target.closest?.('[data-route="trades"],[data-home-go="trades"]');
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openTradesV2();
  }, true);
})();
