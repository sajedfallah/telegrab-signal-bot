(() => {
  let selectedPeriod = '30';
  let selectedTab = 'overview';

  function h(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  }

  function icon(name, className = 'nexus-inline-icon') {
    return window.NexusIcons?.svg?.(name, className) || '';
  }

  function symbolIcon(symbol) {
    return window.NexusSymbolVisuals?.icon?.(symbol) || window.NexusSymbolVisuals?.mark?.(symbol) || '';
  }

  function track(name, metadata = {}) {
    window.NexusProduct?.track?.(name, metadata);
  }

  function num(value, digits = 2, suffix = '') {
    if (value == null || value === '') return 'Insufficient Data';
    const n = Number(value);
    return Number.isFinite(n) ? `${n.toFixed(digits)}${suffix}` : 'Insufficient Data';
  }

  function dt(value) {
    if (!value) return '—';
    try { return new Date(value).toLocaleString('fa-IR-u-ca-persian'); } catch (_) { return String(value); }
  }

  function summaryGrid(data) {
    return `<div class="track-stat-grid">
      <div><b>${h(data.total)}</b><span>کل سیگنال‌ها</span></div>
      <div class="metric-primary"><b>${h(data.win_rate)}%</b><span>Win Rate</span></div>
      <div><b>${h(data.wins)}</b><span>WIN</span></div>
      <div><b>${h(data.losses)}</b><span>LOSS</span></div>
      <div><b>${h(data.be)}</b><span>BE</span></div>
    </div>`;
  }

  function rMetrics(risk) {
    if (!risk || risk.status !== 'OK') {
      return `<div class="track-insufficient"><b>Insufficient Data</b><span>برای محاسبه R، Profit Factor و Drawdown باید Entry، Initial SL و Final Exit معتبر موجود باشد.</span></div>`;
    }
    return `<div class="track-risk-grid">
      <div><span>Net R</span><b>${num(risk.net_r, 2, 'R')}</b></div>
      <div><span>Average R</span><b>${num(risk.average_r, 2, 'R')}</b></div>
      <div><span>Profit Factor</span><b>${num(risk.profit_factor, 2)}</b></div>
      <div><span>Max Drawdown</span><b>${num(risk.max_drawdown_r, 2, 'R')}</b></div>
      <div><span>Current Losing Streak</span><b>${h(risk.current_losing_streak)}</b></div>
      <div><span>Max Losing Streak</span><b>${h(risk.maximum_losing_streak)}</b></div>
    </div>`;
  }

  function performanceChart(risk) {
    const curve = risk?.status === 'OK' ? risk.equity_curve_r : null;
    if (!Array.isArray(curve) || curve.length < 2 || !curve.every(value => Number.isFinite(Number(value)))) {
      return '<div class="track-insufficient">داده معتبر کافی برای نمودار عملکرد وجود ندارد.</div>';
    }
    const values = curve.map(Number);
    const low = Math.min(0, ...values), high = Math.max(0, ...values), span = Math.max(0.01, high - low);
    const points = values.map((value, index) => `${(index / (values.length - 1) * 100).toFixed(2)},${(92 - (value - low) / span * 84).toFixed(2)}`).join(' ');
    return `<section class="track-equity-chart" aria-label="نمودار تجمعی R بر پایه معاملات بسته‌شده"><div class="section-head"><h2>روند عملکرد · R</h2></div><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="روند تجمعی ${h(values.length)} معامله"><line x1="0" y1="${(92 - (0 - low) / span * 84).toFixed(2)}" x2="100" y2="${(92 - (0 - low) / span * 84).toFixed(2)}" class="track-zero-line"/><polyline points="${points}"/></svg><small>داده: همان equity_curve_r محاسبه‌شده برای KPIهای Risk. آخرین مقدار ${h(num(values.at(-1), 2, 'R'))}</small></section>`;
  }

  function symbols(rows) {
    if (!rows?.length) return '<div class="empty-state">داده کافی برای تفکیک نمادها وجود ندارد.</div>';
    return `<div class="track-table">${rows.map(row => `<article>
      <div class="track-symbol-copy"><div class="track-symbol-identity">${symbolIcon(row.symbol)}<div><b>${h(row.symbol)}</b><span>${h(row.total)} سیگنال</span></div></div></div>
      <div class="track-winbar" aria-label="Win Rate ${h(row.win_rate)}%"><i style="width:${Math.max(0, Math.min(100, Number(row.win_rate || 0)))}%"></i></div>
      <span class="win">${h(row.wins)} W</span><span class="loss">${h(row.losses)} L</span><span>${h(row.be)} BE</span><em>${h(row.win_rate)}%</em>
    </article>`).join('')}</div>`;
  }

  function channels(data) {
    if (!data) return '';
    return `<div class="track-channel-grid">${Object.entries(data).map(([name, row]) => `<article><span class="badge ${name === 'VIP' ? 'vip-badge' : ''}">${h(name)}</span>${summaryGrid(row)}</article>`).join('')}</div>`;
  }

  function methodology(data) {
    return `<section class="track-integrity"><span>${icon('shield')}</span><div><b>How NEXUS Performance Is Calculated</b><span>${h(data?.verification_note || 'نتایج Signal Track Record از AutoTrade account return جدا نگه داشته می‌شوند.')}</span><small>${h(data?.drawdown_rule || '')}</small></div></section>`;
  }

  function setBody(html) {
    const body = document.getElementById('trackRecordBody');
    if (body) body.innerHTML = html;
  }

  async function loadOverview() {
    setBody(window.NexusProduct?.skeleton?.('performance', 4) || '<div class="empty-state">در حال محاسبه عملکرد...</div>');
    try {
      const [overview, details] = await Promise.all([
        api(`/performance/overview?period=${encodeURIComponent(selectedPeriod)}`),
        api(`/performance/details?period=${encodeURIComponent(selectedPeriod)}`),
      ]);
      setBody(`
        <section class="track-summary">${summaryGrid(overview.summary)}<p>Track Record بر پایه سیگنال‌های CLOSED ثبت‌شده NEXUS است؛ بازده حساب معاملاتی کاربر نیست.</p></section>
        ${performanceChart(overview.risk)}
        <section class="track-section"><div class="section-head"><h2>Risk / R Metrics</h2></div>${rMetrics(overview.risk)}</section>
        <section class="track-section"><div class="section-head"><h2>تفکیک نمادها</h2></div>${symbols(details.symbols)}</section>
        <section class="track-section"><div class="section-head"><h2>رایگان / VIP</h2></div>${channels(details.channels)}</section>
        ${methodology(overview.methodology)}
      `);
      track('performance_view', { period: selectedPeriod, tab: 'overview' });
    } catch (_) {
      setBody('<div class="empty-state">دریافت Performance با مشکل مواجه شد.<br><button class="btn ghost" id="retryTrackRecord">تلاش مجدد</button></div>');
      document.getElementById('retryTrackRecord')?.addEventListener('click', loadOverview);
    }
  }

  function tradeRow(item) {
    if (item.locked) {
      return `<button class="track-trade-row locked" type="button" disabled><div class="track-trade-symbol">${symbolIcon(item.symbol)}<div><b>🔒 ${h(item.symbol)}</b><small>${h(dt(item.close_time))}</small></div></div><span>${item.realized_r == null ? 'CLOSED' : h(num(item.realized_r, 2, 'R'))}</span><em>VIP</em></button>`;
    }
    const direction = item.direction ? ` · ${h(item.direction)}` : '';
    return `<button class="track-trade-row" type="button" data-performance-trade="${h(item.id)}"><div class="track-trade-symbol">${symbolIcon(item.symbol)}<div><b>${h(item.symbol)}${direction}</b><small>${h(dt(item.close_time))}</small></div></div><span>${item.realized_r == null ? h(item.result_value ?? '—') : h(num(item.realized_r, 2, 'R'))}</span><em>${h(item.result_source || 'UNKNOWN')}</em></button>`;
  }

  async function loadHistory() {
    setBody(window.NexusProduct?.skeleton?.('signals', 5) || '<div class="empty-state">در حال دریافت History...</div>');
    try {
      const data = await api(`/performance/trades?period=${encodeURIComponent(selectedPeriod)}&limit=50&offset=0`);
      const items = data.items || [];
      setBody(`<section class="track-section"><div class="section-head"><h2>Trade History</h2><span>${h(data.total)} Trades</span></div>${items.length ? `<div class="track-trades">${items.map(tradeRow).join('')}</div>` : '<div class="empty-state">معامله بسته‌شده‌ای در این بازه وجود ندارد.</div>'}</section>`);
      document.querySelectorAll('[data-performance-trade]').forEach(btn => btn.addEventListener('click', () => openTradeDetail(btn.dataset.performanceTrade)));
      track('performance_view', { period: selectedPeriod, tab: 'history' });
    } catch (_) {
      setBody('<div class="empty-state">دریافت Trade History با مشکل مواجه شد.<br><button class="btn ghost" id="retryTrackHistory">تلاش مجدد</button></div>');
      document.getElementById('retryTrackHistory')?.addEventListener('click', loadHistory);
    }
  }

  function lifecycle(items) {
    if (!items?.length) return '<div class="track-insufficient"><b>Lifecycle Data Unavailable</b><span>برای این معامله رویداد قابل نمایش ثبت نشده است.</span></div>';
    return `<div class="track-lifecycle">${items.map(item => `<article><i></i><div><b>${h(item.action || 'UPDATE')}</b>${item.detail_fa ? `<span>${h(item.detail_fa)}</span>` : ''}${item.value ? `<small>${h(item.value)}</small>` : ''}<time>${h(dt(item.created_at))}</time></div></article>`).join('')}</div>`;
  }

  async function openTradeDetail(id) {
    setBody(window.NexusProduct?.skeleton?.('signals', 4) || '<div class="empty-state">در حال دریافت جزئیات...</div>');
    try {
      const data = await api(`/performance/trades/${encodeURIComponent(id)}`);
      const item = data.trade;
      setBody(`
        <button class="text-btn track-detail-back" id="performanceBackToHistory">← بازگشت به History</button>
        <section class="track-section track-trade-detail">
          <div class="section-head"><h2 class="track-detail-symbol">${symbolIcon(item.symbol)}<span>${h(item.symbol)} · ${h(item.direction)}</span></h2><span class="badge">${h(item.result_source)}</span></div>
          <div class="track-detail-grid">
            <div><span>Entry</span><b>${h(item.initial_entry ?? '—')}</b></div>
            <div><span>Initial SL</span><b>${h(item.initial_sl ?? '—')}</b></div>
            <div><span>Initial TP</span><b>${h(item.initial_tp ?? '—')}</b></div>
            <div><span>Final Exit</span><b>${h(item.final_exit ?? '—')}</b></div>
            <div><span>Realized R</span><b>${item.realized_r == null ? 'Insufficient Data' : h(num(item.realized_r, 2, 'R'))}</b></div>
            <div><span>Result</span><b>${h(item.result_value ?? '—')} ${h(item.result_unit ?? '')}</b></div>
          </div>
        </section>
        <section class="track-section"><div class="section-head"><h2>Lifecycle</h2></div>${lifecycle(item.lifecycle)}</section>
        ${methodology(data.methodology)}
      `);
      document.getElementById('performanceBackToHistory')?.addEventListener('click', loadHistory);
    } catch (err) {
      const message = String(err?.message || '').includes('VIP') ? 'جزئیات این معامله فقط برای کاربران VIP قابل مشاهده است.' : 'دریافت جزئیات معامله با مشکل مواجه شد.';
      setBody(`<div class="empty-state">${h(message)}<br><button class="btn ghost" id="performanceBackToHistory">بازگشت</button></div>`);
      document.getElementById('performanceBackToHistory')?.addEventListener('click', loadHistory);
    }
  }

  async function loadRisk() {
    setBody(window.NexusProduct?.skeleton?.('performance', 3) || '<div class="empty-state">در حال محاسبه Risk...</div>');
    try {
      const data = await api(`/performance/overview?period=${encodeURIComponent(selectedPeriod)}`);
      setBody(`
        <section class="track-section"><div class="section-head"><h2>Risk</h2></div>${rMetrics(data.risk)}</section>
        ${methodology(data.methodology)}
      `);
      track('performance_view', { period: selectedPeriod, tab: 'risk' });
    } catch (_) {
      setBody('<div class="empty-state">دریافت Risk Metrics با مشکل مواجه شد.</div>');
    }
  }

  function load() {
    document.querySelectorAll('[data-track-period]').forEach(btn => btn.classList.toggle('active', btn.dataset.trackPeriod === selectedPeriod));
    document.querySelectorAll('[data-track-tab]').forEach(btn => btn.classList.toggle('active', btn.dataset.trackTab === selectedTab));
    if (selectedTab === 'history') return loadHistory();
    if (selectedTab === 'risk') return loadRisk();
    return loadOverview();
  }

  function openTrackRecord() {
    state.route = 'performance';
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
    view.innerHTML = `<section class="page-head"><div><div class="eyebrow">PERFORMANCE CENTER</div><h1>عملکرد NEXUS</h1><p class="modal-muted">Signal Track Record مبتنی بر داده ثبت‌شده؛ جدا از بازده حساب AutoTrade.</p></div><button class="text-btn" id="trackBack">بازگشت</button></section>
      <div class="track-periods">${['7','30','90','all'].map(key => `<button class="tab ${key === selectedPeriod ? 'active' : ''}" data-track-period="${key}">${key === 'all' ? 'ALL' : key + 'D'}</button>`).join('')}</div>
      <div class="track-tabs"><button class="tab active" data-track-tab="overview">Overview</button><button class="tab" data-track-tab="history">Trade History</button><button class="tab" data-track-tab="risk">Risk</button></div>
      <div id="trackRecordBody">${window.NexusProduct?.skeleton?.('performance', 4) || '<div class="empty-state">در حال دریافت...</div>'}</div>`;
    document.querySelectorAll('[data-track-period]').forEach(btn => btn.addEventListener('click', () => { selectedPeriod = btn.dataset.trackPeriod; load(); }));
    document.querySelectorAll('[data-track-tab]').forEach(btn => btn.addEventListener('click', () => { selectedTab = btn.dataset.trackTab; load(); }));
    document.getElementById('trackBack')?.addEventListener('click', () => render('home'));
    load();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  window.NexusTrackRecord = { open: openTrackRecord, load };

  document.addEventListener('click', event => {
    const target = event.target.closest?.('[data-home-go="performance"],[data-open-track-record]');
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openTrackRecord();
  }, true);
})();
