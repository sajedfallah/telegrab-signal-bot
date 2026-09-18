(() => {
  const tradeState = { tab: 'open', offset: 0, limit: 20, loading: false };

  function h(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  }

  function icon(name, className = 'nexus-inline-icon') {
    return window.NexusIcons?.svg?.(name, className) || '';
  }

  function track(name, metadata = {}) {
    window.NexusProduct?.track?.(name, metadata);
  }

  function dt(value) {
    if (!value) return '—';
    if (window.NexusProduct?.humanDate) return window.NexusProduct.humanDate(value, true);
    try { return new Date(value).toLocaleString('fa-IR-u-ca-persian'); } catch (_) { return String(value); }
  }

  function num(value, digits = 2) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : '—';
  }

  function check(yes, label) {
    return `<span class="${yes ? 'ok' : 'off'}">${yes ? icon('check') : icon('close')}<b>${h(label)}</b></span>`;
  }

  function healthCard(data) {
    const stateData = data?.state || {};
    const stateName = String(stateData.state || 'NEEDS_ATTENTION').toUpperCase();
    const ok = stateName === 'HEALTHY';
    const checks = data?.checks || {};
    const title = ok ? 'AutoTrade متصل و فعال است' : stateName === 'DISCONNECTED' ? 'اتصال AutoTrade قطع است' : 'AutoTrade نیاز به بررسی دارد';
    const message = ok ? 'اشتراک، لایسنس، MT5 و EA آماده هستند.' : stateName === 'DISCONNECTED' ? 'آخرین heartbeat معتبر نیست؛ قبل از اتکا به اجرای خودکار اتصال را بررسی کنید.' : 'یکی از اجزای راه‌اندازی یا اتصال نیاز به بررسی دارد.';
    return `<article class="trade-health-v2 ${ok ? 'healthy' : 'attention'} ${stateName === 'DISCONNECTED' ? 'disconnected' : ''}">
      <div class="signal-top"><span class="badge">${h(stateName)}</span><span class="trade-health-dot ${ok ? 'live' : ''}"></span></div>
      <h2>${h(title)}</h2><p>${h(message)}</p>
      <div class="trade-checks">
        ${check(checks.subscription, 'اشتراک')}
        ${check(checks.license, 'لایسنس')}
        ${check(checks.mt5_account, 'MT5')}
        ${check(checks.ea_connected, 'EA')}
      </div>
      <div class="trade-health-meta"><span>حساب MT5</span><b>${h(data?.mt5?.account_number ? `****${String(data.mt5.account_number).slice(-4)}` : '—')}</b><span>آخرین Sync</span><b>${h(dt(stateData.last_sync_at))}</b></div>
      <div class="trade-health-counts"><span>معاملات باز <b>${h(data.open_count ?? 0)}</b></span><span>Pending <b>${h(data.pending_count ?? 0)}</b></span></div>
    </article>`;
  }

  function liveCard(item, pending = false) {
    const ticket = String(item.ticket || '');
    const direction = String(item.direction || item.order_type || '').toUpperCase();
    return `<article class="trade-v2-card live-trade-card" data-live-ticket="${h(ticket)}">
      <div class="signal-top"><div><span class="direction-chip ${h(direction.toLowerCase())}">${h(direction || 'TRADE')}</span>${item.signal_code ? `<span class="badge muted">Signal #${h(item.signal_code)}</span>` : ''}</div><span class="status-pill ${pending ? 'neutral' : 'success'}">${h(item.status || (pending ? 'PENDING' : 'OPEN'))}</span></div>
      <div class="trade-v2-title"><div><h3>${h(item.symbol || '—')}</h3><small>Ticket ${h(ticket || '—')}</small></div><em class="${Number(item.profit || 0) < 0 ? 'negative' : ''}">${pending ? '—' : h(num(item.profit)) + ' $'}</em></div>
      <div class="trade-v2-grid">
        <div><span>Volume</span><b>${h(item.volume ?? '—')}</b></div>
        <div><span>Entry</span><b>${h(item.entry_price ?? '—')}</b></div>
        ${!pending ? `<div><span>Current</span><b>${h(item.current_price ?? '—')}</b></div>` : ''}
        <div><span>SL</span><b>${h(item.stop_loss ?? '—')}</b></div>
        <div><span>TP</span><b>${h(item.take_profit ?? '—')}</b></div>
      </div>
      <div class="trade-card-footer"><small class="trade-v2-time">Sync: ${h(dt(item.last_seen_at))}</small><span>جزئیات ${icon('arrowLeft')}</span></div>
    </article>`;
  }

  function historyCard(item) {
    const direction = String(item.direction || item.event_type || '').toUpperCase();
    return `<article class="trade-v2-card history" data-trade-detail="${h(item.id)}">
      <div class="signal-top"><div><span class="direction-chip ${h(direction.toLowerCase())}">${h(direction || 'TRADE')}</span>${item.signal_id ? `<span class="badge muted">Signal ${h(item.signal_id)}</span>` : ''}</div><span class="status-pill success">${h(item.status || item.event_type || 'HISTORY')}</span></div>
      <div class="trade-v2-title"><div><h3>${h(item.symbol || '—')}</h3><small>Ticket ${h(item.ticket || '—')}</small></div><em class="${Number(item.profit || 0) < 0 ? 'negative' : ''}">${h(num(item.profit))} $</em></div>
      <div class="trade-v2-grid compact"><div><span>Entry</span><b>${h(item.entry_price ?? '—')}</b></div><div><span>Exit</span><b>${h(item.exit_price ?? '—')}</b></div><div><span>Volume</span><b>${h(item.volume ?? '—')}</b></div></div>
      <div class="trade-card-footer"><small class="trade-v2-time">${h(dt(item.created_at))}</small><span>جزئیات ${icon('arrowLeft')}</span></div>
    </article>`;
  }

  function empty(tab) {
    const text = tab === 'open' ? 'در حال حاضر معامله بازی توسط AutoTrade ثبت نشده است.' : tab === 'pending' ? 'در حال حاضر سفارش Pending ثبت نشده است.' : 'هنوز معامله بسته‌شده‌ای ثبت نشده است.';
    return `<div class="empty-state nexus-empty-state">${icon('trades')}<b>${h(text)}</b><span>این بخش فقط از وضعیت واقعی حساب و تاریخچه اجرای ثبت‌شده استفاده می‌کند.</span></div>`;
  }

  async function loadTab({ append = false } = {}) {
    if (tradeState.loading || state.route !== 'trades') return;
    tradeState.loading = true;
    const host = document.getElementById('tradesV2List');
    const more = document.getElementById('tradesV2More');
    if (!append && host) host.innerHTML = window.NexusProduct?.skeleton?.('trades', 3) || '<div class="empty-state">در حال دریافت اطلاعات...</div>';
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

  function timeline(items) {
    if (!items?.length) return '<div class="empty-state compact-empty">رویداد اجرایی بیشتری ثبت نشده است.</div>';
    return `<div class="trade-detail-timeline">${items.map(item => `<article><span></span><div><b>${h(item.event_type || item.status || 'EXECUTION')}</b>${item.profit != null ? `<p>P/L: ${h(num(item.profit))} $</p>` : ''}${item.stop_loss != null ? `<p>SL: ${h(item.stop_loss)}</p>` : ''}${item.take_profit != null ? `<p>TP: ${h(item.take_profit)}</p>` : ''}${item.error_text ? `<p class="negative">${h(item.error_text)}</p>` : ''}<small>${h(dt(item.created_at))}</small></div></article>`).join('')}</div>`;
  }

  function sourceSignal(source) {
    if (!source) return '';
    return `<button class="source-signal-link" data-source-signal="${h(source.id)}"><span><small>سیگنال مبدا</small><b>${source.code ? '#' + h(source.code) : `#${h(source.id)}`}</b></span><span>${h(source.symbol || '')} ${icon('arrowLeft')}</span></button>`;
  }

  function detailBody(data) {
    const item = data.trade || {};
    const direction = String(item.direction || item.order_type || item.event_type || '').toUpperCase();
    return `<div class="trade-detail-v3">
      <div class="signal-detail-head"><div><span class="direction-chip ${h(direction.toLowerCase())}">${h(direction || 'TRADE')}</span><h3>${h(item.symbol || '—')}</h3></div><b>${item.profit != null ? h(num(item.profit)) + ' $' : h(item.status || '')}</b></div>
      <div class="trade-detail-grid">
        <div><span>Broker Ticket</span><b>${h(item.ticket || '—')}</b></div>
        ${item.signal_code ? `<div><span>Signal</span><b>${h(item.signal_code)}</b></div>` : ''}
        <div><span>Volume</span><b>${h(item.volume ?? '—')}</b></div>
        <div><span>Entry</span><b>${h(item.entry_price ?? '—')}</b></div>
        ${item.current_price != null ? `<div><span>Current</span><b>${h(item.current_price)}</b></div>` : ''}
        ${item.exit_price != null ? `<div><span>Exit</span><b>${h(item.exit_price)}</b></div>` : ''}
        <div><span>SL</span><b>${h(item.stop_loss ?? '—')}</b></div>
        <div><span>TP</span><b>${h(item.take_profit ?? '—')}</b></div>
        ${item.realized_r != null ? `<div><span>Realized R</span><b>${h(num(item.realized_r))}R</b></div>` : ''}
        ${item.slippage != null ? `<div><span>Slippage</span><b>${h(num(item.slippage, 4))}</b></div>` : ''}
      </div>
      ${item.error_text ? `<div class="execution-reason"><span>${icon('alert')}</span><p><b>دلیل اجرا/خطا:</b> ${h(item.error_text)}</p></div>` : ''}
      ${sourceSignal(data.source_signal)}
      <h4>Execution Timeline</h4>${timeline(data.timeline || [])}
    </div>`;
  }

  async function openDetail(id) {
    track('trade_detail_view', { execution_id: id, live: false });
    try {
      showModal('جزئیات معامله', window.NexusProduct?.skeleton?.('detail', 3) || '<div class="empty-state">در حال دریافت...</div>');
      const data = await api(`/trades/${encodeURIComponent(id)}`);
      showModal(`Trade #${h(data.trade?.ticket || id)}`, detailBody(data));
      bindSourceSignal();
    } catch (err) {
      toast('دریافت جزئیات معامله با مشکل مواجه شد.');
    }
  }

  async function openLiveDetail(ticket) {
    track('trade_detail_view', { ticket, live: true });
    try {
      showModal('جزئیات معامله زنده', window.NexusProduct?.skeleton?.('detail', 3) || '<div class="empty-state">در حال دریافت...</div>');
      const data = await api(`/trades/live/${encodeURIComponent(ticket)}`);
      showModal(`Ticket #${h(ticket)}`, detailBody(data));
      bindSourceSignal();
    } catch (err) {
      toast('این معامله دیگر در وضعیت زنده وجود ندارد یا دریافت جزئیات ناموفق بود.');
    }
  }

  function bindSourceSignal() {
    document.querySelectorAll('[data-source-signal]').forEach(btn => btn.addEventListener('click', () => {
      const id = btn.dataset.sourceSignal;
      closeModal();
      render('signals');
      window.setTimeout(() => window.hydrateNexusSignals?.() && window.setTimeout(() => document.querySelector(`[data-open-signal="${CSS.escape(id)}"]`)?.click(), 150), 0);
    }));
  }

  function bindTradeDetails() {
    view.querySelectorAll('[data-trade-detail]').forEach(cardEl => cardEl.addEventListener('click', () => openDetail(cardEl.dataset.tradeDetail)));
    view.querySelectorAll('[data-live-ticket]').forEach(cardEl => cardEl.addEventListener('click', () => openLiveDetail(cardEl.dataset.liveTicket)));
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
      <div id="tradeHealthV2">${window.NexusProduct?.skeleton?.('health', 1) || '<div class="empty-state">در حال بررسی AutoTrade...</div>'}</div>
      <div class="plan-tabs trades-v2-tabs"><button class="tab active" data-trades-tab="open">باز</button><button class="tab" data-trades-tab="pending">Pending</button><button class="tab" data-trades-tab="history">تاریخچه</button></div>
      <div class="stack" id="tradesV2List">${window.NexusProduct?.skeleton?.('trades', 3) || '<div class="empty-state">در حال دریافت...</div>'}</div>
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
    track('trades_view', { tab: 'open' });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  window.NexusTrades = { open: openTradesV2, detail: openDetail, liveDetail: openLiveDetail };
  if (window.NexusExperience) window.NexusExperience.renderTrades = openTradesV2;

  document.addEventListener('click', event => {
    const target = event.target.closest?.('[data-route="trades"],[data-home-go="trades"]');
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openTradesV2();
  }, true);
})();
