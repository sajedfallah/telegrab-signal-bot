(() => {
  const tradeState = { tab: 'open', offset: 0, limit: 20, loading: false, lastHealth: null, balanceHidden: localStorage.getItem('nexus-hide-balance') === '1', activeKpi: 'balance' };

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

  function money(value, currency = 'USD') {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    try {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency || 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(n);
    } catch (_) {
      return `${n.toFixed(2)} ${currency || 'USD'}`;
    }
  }

  function signedMoney(value, currency = 'USD') {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    const absolute = money(Math.abs(n), currency);
    if (n > 0) return `+${absolute}`;
    if (n < 0) return `-${absolute}`;
    return absolute;
  }

  function signedPercent(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
  }

  function relativeSync(value) {
    if (!value) return 'بدون Sync';
    const ts = new Date(value).getTime();
    if (!Number.isFinite(ts)) return dt(value);
    const seconds = Math.max(0, Math.round((Date.now() - ts) / 1000));
    if (seconds < 60) return `${seconds} ثانیه پیش`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} دقیقه پیش`;
    const hours = Math.floor(minutes / 60);
    return `${hours} ساعت پیش`;
  }

  function maskedAccount(value) {
    const raw = String(value || '').trim();
    if (!raw) return 'MT5 —';
    return `****${raw.slice(-4)}`;
  }

  function eyeIcon(hidden) {
    return hidden
      ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M10.6 10.7a2 2 0 0 0 2.7 2.7M9.9 4.3A10.5 10.5 0 0 1 12 4c5.2 0 8.8 4.6 9.7 6a1.7 1.7 0 0 1 0 2c-.5.8-1.8 2.6-3.8 4M6.2 6.2C4.3 7.4 3 9.2 2.3 10.1a1.7 1.7 0 0 0 0 2C3.2 13.4 6.8 18 12 18c1.1 0 2.1-.2 3-.5"/></svg>'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.3 10.1C3.2 8.6 6.8 4 12 4s8.8 4.6 9.7 6.1a1.7 1.7 0 0 1 0 1.8C20.8 13.4 17.2 18 12 18s-8.8-4.6-9.7-6.1a1.7 1.7 0 0 1 0-1.8Z"/><circle cx="12" cy="11" r="3"/></svg>';
  }

  function normalizeAccountKpi(data) {
    const preview = new URLSearchParams(location.search).get('uiPreview') === 'mt5-kpi';
    const source = data?.account_metrics || data?.financials || data?.mt5?.metrics || {};
    const stateData = data?.state || {};
    const rawState = String(stateData.state || '').toUpperCase();
    let connection = rawState === 'HEALTHY' ? 'LIVE' : rawState === 'DISCONNECTED' ? 'OFFLINE' : 'STALE';

    const actual = {
      connection,
      account_number: data?.mt5?.account_number,
      broker: data?.mt5?.broker || data?.broker,
      balance: source.balance,
      equity: source.equity,
      open_pnl: source.open_pnl ?? source.floating_pnl,
      today_pnl: source.today_pnl,
      today_pnl_percent: source.today_pnl_percent,
      currency: source.currency || 'USD',
      last_seen_at: stateData.last_sync_at || data?.mt5?.last_seen_at,
    };

    if (!preview) return actual;

    return {
      connection: 'LIVE',
      account_number: actual.account_number || '50254',
      broker: actual.broker || 'Roco Broker Ltd',
      balance: Number.isFinite(Number(actual.balance)) ? actual.balance : 10428.50,
      equity: Number.isFinite(Number(actual.equity)) ? actual.equity : 10512.30,
      open_pnl: Number.isFinite(Number(actual.open_pnl)) ? actual.open_pnl : 83.80,
      today_pnl: Number.isFinite(Number(actual.today_pnl)) ? actual.today_pnl : 83.80,
      today_pnl_percent: Number.isFinite(Number(actual.today_pnl_percent)) ? actual.today_pnl_percent : 0.81,
      currency: actual.currency || 'USD',
      last_seen_at: actual.last_seen_at || new Date(Date.now() - 4000).toISOString(),
      preview: true,
    };
  }

  function kpiConfig(m) {
    const configs = {
      balance: {
        label: 'Balance',
        title: 'Account Balance',
        value: money(m.balance, m.currency),
        subLeft: signedMoney(m.today_pnl, m.currency) + ' Today',
        subRight: signedPercent(m.today_pnl_percent),
        trend: Number(m.today_pnl || 0),
      },
      equity: {
        label: 'Equity',
        title: 'Live Equity',
        value: money(m.equity, m.currency),
        subLeft: 'Balance ' + money(m.balance, m.currency),
        subRight: signedMoney(Number(m.equity || 0) - Number(m.balance || 0), m.currency),
        trend: Number(m.equity || 0) - Number(m.balance || 0),
      },
      today: {
        label: 'Today',
        title: 'Today P&L',
        value: signedMoney(m.today_pnl, m.currency),
        subLeft: 'Daily Performance',
        subRight: signedPercent(m.today_pnl_percent),
        trend: Number(m.today_pnl || 0),
      },
      floating: {
        label: 'Floating',
        title: 'Open P&L',
        value: signedMoney(m.open_pnl, m.currency),
        subLeft: 'Equity ' + money(m.equity, m.currency),
        subRight: 'Live',
        trend: Number(m.open_pnl || 0),
      },
    };
    return configs[tradeState.activeKpi] || configs.balance;
  }

  function previewSeries(key) {
    const series = {
      balance: [24,23,24,22,20,21,17,18,15,16,12,13,10,12,8,9,6,8,4,5,2],
      equity: [27,26,24,25,21,19,20,16,17,13,15,11,12,8,10,6,8,5,6,3,4],
      today: [31,29,30,26,27,23,24,20,22,18,19,14,16,12,13,9,11,7,8,4,5],
      floating: [22,24,21,23,18,20,17,19,14,16,12,15,10,12,8,10,6,9,5,7,4],
    };
    return series[key] || series.balance;
  }

  function sparkPaths(values) {
    const width = 100;
    const height = 42;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(1, max - min);
    const pts = values.map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = 4 + ((v - min) / span) * 31;
      return [x, y];
    });
    const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(' ');
    const area = `${line} L100,42 L0,42 Z`;
    return { line, area };
  }

  function accountKpiCard(data) {
    const m = normalizeAccountKpi(data);
    const hidden = tradeState.balanceHidden;
    const hasNumbers = [m.balance, m.equity, m.open_pnl].some(v => Number.isFinite(Number(v)));
    const stale = m.connection !== 'LIVE';
    const metric = kpiConfig(m);
    const metricClass = metric.trend > 0 ? 'positive' : metric.trend < 0 ? 'negative' : 'neutral';
    const privateValue = value => hidden ? '••••••••' : value;
    const tabs = [
      ['balance','Balance'],
      ['equity','Equity'],
      ['today','Today'],
      ['floating','Floating'],
    ];
    const activeIndex = Math.max(0, tabs.findIndex(([key]) => key === tradeState.activeKpi));

    if (!hasNumbers && !m.preview) {
      return `<article class="mt5-account-kpi uiverse-inspired" data-connection="${h(m.connection.toLowerCase())}">
        <div class="mt5-kpi-head">
          <div><div class="mt5-kpi-kicker">MT5 ACCOUNT</div><div class="mt5-kpi-account">${h(maskedAccount(m.account_number))}${m.broker ? ` · ${h(m.broker)}` : ''}</div></div>
          <span class="mt5-live-badge"><i></i>${h(m.connection)}</span>
        </div>
        <div class="mt5-kpi-empty"><span>Account Balance</span><strong>—</strong><p>پس از دریافت Snapshot مالی از MT5، موجودی زنده حساب اینجا نمایش داده می‌شود.</p></div>
        <div class="mt5-kpi-sync">${stale ? 'Last known' : 'Synced'} · ${h(relativeSync(m.last_seen_at))}</div>
      </article>`;
    }

    const series = m.preview ? previewSeries(tradeState.activeKpi) : null;
    const paths = series ? sparkPaths(series) : null;

    return `<article class="mt5-account-kpi uiverse-inspired ${metricClass}" data-connection="${h(m.connection.toLowerCase())}" data-active-kpi="${h(tradeState.activeKpi)}">
      <div class="mt5-kpi-head">
        <div>
          <div class="mt5-kpi-kicker">MT5 ACCOUNT</div>
          <div class="mt5-kpi-account">${h(maskedAccount(m.account_number))} · ${h(m.broker || 'MetaTrader 5')}</div>
        </div>
        <span class="mt5-live-badge"><i></i>${h(m.connection)}</span>
      </div>

      <div class="mt5-kpi-switch" style="--active-index:${activeIndex}">
        <div class="mt5-kpi-switch-slider" aria-hidden="true"></div>
        ${tabs.map(([key,label]) => `<button type="button" data-kpi-tab="${key}" class="${tradeState.activeKpi === key ? 'active' : ''}">${label}</button>`).join('')}
      </div>

      <div class="mt5-kpi-main">
        <div class="mt5-kpi-main-label">${h(metric.title)}</div>
        <div class="mt5-kpi-main-row">
          <strong class="mt5-kpi-main-value" dir="ltr">${h(privateValue(metric.value))}</strong>
          <button class="mt5-privacy-toggle" type="button" data-balance-toggle aria-label="${hidden ? 'Show values' : 'Hide values'}">${eyeIcon(hidden)}</button>
        </div>
        <div class="mt5-kpi-main-stats ${metricClass}" dir="ltr">
          <span>${h(privateValue(metric.subLeft))}</span>
          <b>${h(privateValue(metric.subRight))}</b>
        </div>
      </div>

      <div class="mt5-kpi-chart ${paths ? '' : 'empty'}">
        ${paths ? `<svg viewBox="0 0 100 42" preserveAspectRatio="none" aria-label="${h(metric.title)} trend">
          <defs>
            <linearGradient id="mt5KpiArea-${h(tradeState.activeKpi)}" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="currentColor" stop-opacity=".30"></stop>
              <stop offset="100%" stop-color="currentColor" stop-opacity="0"></stop>
            </linearGradient>
          </defs>
          <path class="area" d="${paths.area}" fill="url(#mt5KpiArea-${h(tradeState.activeKpi)})"></path>
          <path class="line" d="${paths.line}"></path>
        </svg>` : '<div class="mt5-chart-placeholder">Trend data will appear here after MT5 history sync.</div>'}
      </div>

      <div class="mt5-kpi-foot">
        <span class="mt5-kpi-sync">${stale ? 'Last known' : 'Synced'} · ${h(relativeSync(m.last_seen_at))}</span>
        ${m.preview ? '<span class="mt5-preview-pill">UI PREVIEW</span>' : ''}
      </div>
    </article>`;
  }

  function renderAccountKpi(data) {
    tradeState.lastHealth = data || tradeState.lastHealth || {};
    const host = document.getElementById('tradeAccountKpi');
    if (!host) return;
    host.innerHTML = accountKpiCard(tradeState.lastHealth);
    host.querySelector('[data-balance-toggle]')?.addEventListener('click', () => {
      tradeState.balanceHidden = !tradeState.balanceHidden;
      localStorage.setItem('nexus-hide-balance', tradeState.balanceHidden ? '1' : '0');
      renderAccountKpi(tradeState.lastHealth);
    });
    host.querySelectorAll('[data-kpi-tab]').forEach(btn => btn.addEventListener('click', () => {
      tradeState.activeKpi = btn.dataset.kpiTab || 'balance';
      renderAccountKpi(tradeState.lastHealth);
    }));
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
    const previewMode = new URLSearchParams(location.search).get('uiPreview') === 'mt5-kpi';
    const experience = state.experience;
    if (!experience?.features?.trades && !previewMode) {
      render('subscriptions');
      return;
    }
    state.route = 'trades';
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.toggle('active', btn.dataset.route === 'trades'));
    view.innerHTML = `<section class="page-head"><div><div class="eyebrow">MY EXECUTION</div><h1>معاملات من</h1></div></section>
      <div id="tradeAccountKpi"></div>
      <div id="tradeHealthV2">${window.NexusProduct?.skeleton?.('health', 1) || '<div class="empty-state">در حال بررسی AutoTrade...</div>'}</div>
      <div class="plan-tabs trades-v2-tabs"><button class="tab active" data-trades-tab="open">باز</button><button class="tab" data-trades-tab="pending">Pending</button><button class="tab" data-trades-tab="history">تاریخچه</button></div>
      <div class="stack" id="tradesV2List">${window.NexusProduct?.skeleton?.('trades', 3) || '<div class="empty-state">در حال دریافت...</div>'}</div>
      <button class="btn ghost full" id="tradesV2More" hidden>نمایش بیشتر</button>`;
    document.querySelectorAll('[data-trades-tab]').forEach(btn => btn.addEventListener('click', () => selectTab(btn.dataset.tradesTab)));
    document.getElementById('tradesV2More')?.addEventListener('click', () => { tradeState.offset += tradeState.limit; loadTab({ append: true }); });
    try {
      const health = await api('/autotrade/status');
      renderAccountKpi(health);
      const host = document.getElementById('tradeHealthV2');
      if (host) host.innerHTML = healthCard(health);
    } catch (err) {
      renderAccountKpi({});
      const host = document.getElementById('tradeHealthV2');
      if (host) host.innerHTML = '<div class="status-panel">وضعیت AutoTrade در دسترس نیست.</div>';
    }
    selectTab('open');
    track('trades_view', { tab: 'open' });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  window.NexusTrades = { open: openTradesV2, detail: openDetail, liveDetail: openLiveDetail };
  if (window.NexusExperience) window.NexusExperience.renderTrades = openTradesV2;

  if (new URLSearchParams(location.search).get('uiPreview') === 'mt5-kpi') {
    window.addEventListener('DOMContentLoaded', () => {
      document.body.classList.remove('landing-active');
      document.getElementById('nexusLanding')?.setAttribute('hidden', '');
      window.setTimeout(() => openTradesV2(), 60);
    }, { once: true });
  }

  document.addEventListener('click', event => {
    const target = event.target.closest?.('[data-route="trades"],[data-home-go="trades"]');
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openTradesV2();
  }, true);
})();
