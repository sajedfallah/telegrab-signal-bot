(() => {
  const tgWebApp = window.Telegram?.WebApp;
  const signalState = { state: 'ACTIVE', access: 'ALL', offset: 0, limit: 20, loading: false };

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

  function price(value) {
    if (value == null || value === '') return '—';
    return h(value);
  }

  function signed(value, digits = 2) {
    if (value == null || value === '') return '—';
    const n = Number(value);
    if (!Number.isFinite(n)) return h(value);
    return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`;
  }

  function pulseHtml(status) {
    const key = String(status || 'UNAVAILABLE').toUpperCase();
    return `<span class="nexus-live-pulse ${h(key.toLowerCase())}" aria-hidden="true"><svg viewBox="0 0 64 48"><polyline class="pulse-back" points="0.157 23.954, 14 23.954, 21.843 48, 43 0, 50 24, 64 24"></polyline><polyline class="pulse-front" points="0.157 23.954, 14 23.954, 21.843 48, 43 0, 50 24, 64 24"></polyline></svg></span>`;
  }

  function liveHtml(live, { detail = false } = {}) {
    if (!live) return '';
    const status = String(live.status || 'UNAVAILABLE').toUpperCase();
    const pnlState = String(live.pnl_state || '').toLowerCase();
    const active = status === 'LIVE';
    const label = status === 'LIVE' ? 'MT5 LIVE' : status === 'PENDING' ? 'MT5 PENDING' : status === 'STALE' ? 'STALE' : 'LIVE DATA UNAVAILABLE';
    const sync = live.age_seconds != null ? `${Math.round(Number(live.age_seconds))}s ago` : '—';
    if (status === 'UNAVAILABLE') {
      return `<section class="signal-live-panel unavailable"><div class="signal-live-head">${pulseHtml(status)}<b>${h(label)}</b><small>Broker snapshot unavailable</small></div></section>`;
    }
    const cells = `
      <div><span>Current</span><b>${price(live.current_price)}</b></div>
      <div><span>Floating P&amp;L</span><b class="pnl ${h(pnlState)}">${signed(live.floating_pnl, 2)}</b></div>
      <div><span>Current R</span><b>${live.current_r == null ? '—' : `${signed(live.current_r, 2)}R`}</b></div>
      <div><span>Volume</span><b>${price(live.volume)}</b></div>`;
    const extras = detail ? `
      <div><span>Live SL</span><b>${price(live.stop_loss)}</b></div>
      <div><span>Live TP</span><b>${price(live.take_profit)}</b></div>` : '';
    return `<section class="signal-live-panel ${h(status.toLowerCase())}">
      <div class="signal-live-head">${pulseHtml(status)}<b>${h(label)}</b><small>synced ${h(sync)}</small></div>
      <div class="signal-live-grid">${cells}${extras}</div>
      ${!active && status === 'STALE' ? '<div class="signal-live-warning">آخرین Snapshot بروکر قدیمی است؛ اعداد به‌عنوان Live در نظر گرفته نمی‌شوند.</div>' : ''}
    </section>`;
  }

  function targetHtml(targets) {
    if (!targets?.length) return '';
    return `<div class="signal-v2-targets">${targets.map(t => `<span>TP${h(t.target_no)} <b>${price(t.price)}</b></span>`).join('')}</div>`;
  }

  function resultMeta(item) {
    if (item.status !== 'CLOSED') return null;
    const result = String(item.result || 'UNKNOWN').toUpperCase();
    const labels = {
      WIN: 'سود', LOSS: 'ضرر', BE: 'سر‌به‌سر', PARTIAL: 'بسته‌شدن بخشی',
      CANCELLED: 'لغوشده', EXPIRED: 'منقضی‌شده', UNKNOWN: 'نتیجه ثبت نشده'
    };
    return { result, label: item.result_label_fa || labels[result] || labels.UNKNOWN };
  }

  function resultChip(item) {
    const meta = resultMeta(item);
    if (!meta) return '';
    return `<span class="signal-v2-result ${h(meta.result.toLowerCase())}"><b>${h(meta.result)}</b><span>${h(meta.label)}</span></span>`;
  }

  function isNew(item) {
    if (!item.published_at || item.status === 'CLOSED') return false;
    const t = new Date(item.published_at).getTime();
    return Number.isFinite(t) && Date.now() - t >= 0 && Date.now() - t <= 10 * 60 * 1000;
  }

  function card(item) {
    const direction = String(item.direction || '').toUpperCase();
    const details = item.locked ? `
      <div class="signal-v2-lock">${icon('lock')}<div><b>دسترسی VIP لازم است</b><span>جزئیات عملیاتی این سیگنال برای حساب شما ارسال نشده است.</span></div></div>
      <button class="btn primary full" data-unlock-vip>مشاهده پلن‌های VIP</button>` : `
      <div class="signal-v2-core">
        ${item.entry_price != null ? `<div><span>Entry</span><b>${price(item.entry_price)}</b></div>` : ''}
        ${item.stop_loss != null ? `<div><span>SL</span><b>${price(item.stop_loss)}</b></div>` : ''}
        ${item.risk_percent != null ? `<div><span>Risk</span><b>${h(item.risk_percent)}%</b></div>` : ''}
      </div>
      ${targetHtml(item.targets)}
      ${item.status !== 'CLOSED' ? liveHtml(item.live) : ''}`;
    return `<article class="signal-v2-card ${item.locked ? 'locked' : ''}" data-signal-id="${h(item.id)}">
      <div class="signal-top">
        <div class="signal-v2-badges"><span class="badge ${item.access === 'VIP' ? 'vip-badge' : ''}">${h(item.access)}</span>${item.code ? `<span class="badge muted">#${h(item.code)}</span>` : ''}${isNew(item) ? '<span class="badge new-signal-badge">جدید</span>' : ''}</div>
        <span class="status-pill ${item.status === 'CLOSED' ? 'neutral' : 'success'}">${h(item.status || '')}</span>
      </div>
      <div class="signal-v2-title">
        <div><h3>${h(item.symbol || '—')}</h3><small>${h(dt(item.published_at))}</small></div>
        <div class="signal-v2-side">${direction ? `<b class="direction-chip ${h(direction.toLowerCase())}">${h(direction)}</b>` : ''}${resultChip(item)}</div>
      </div>
      ${details}
      <button class="text-btn signal-v2-detail" data-open-signal="${h(item.id)}">جزئیات و Timeline ${icon('arrowLeft')}</button>
    </article>`;
  }

  function shell() {
    return `<section class="page-head"><div><div class="eyebrow">SIGNAL CENTER</div><h1>سیگنال‌های NEXUS</h1></div><button class="btn ghost compact-btn" data-open-track-record>${icon('chart')}<span>عملکرد NEXUS</span></button></section>
      <div class="signal-v2-filters">
        <div class="signal-filter-group"><span class="filter-label">وضعیت</span><div class="plan-tabs signal-v2-primary"><button class="tab active" data-signal-state="ACTIVE">فعال</button><button class="tab" data-signal-state="CLOSED">بسته‌شده</button></div></div>
        <div class="signal-filter-group"><span class="filter-label">نوع دسترسی</span><div class="signal-v2-access"><button class="tab active" data-signal-access="ALL">همه</button><button class="tab" data-signal-access="FREE">رایگان</button><button class="tab" data-signal-access="VIP">VIP</button></div></div>
      </div>
      <div class="stack signal-feed-transition" id="signalFeed">${window.NexusProduct?.skeleton?.('signals', 3) || '<div class="empty-state">در حال دریافت سیگنال‌ها...</div>'}</div>
      <button class="btn ghost full signal-load-more" id="signalLoadMore" hidden>نمایش بیشتر</button>`;
  }

  function emptyState() {
    const vipLocked = signalState.state === 'ACTIVE' && signalState.access === 'VIP' && !state.bootstrap?.entitlements?.vip;
    if (vipLocked) {
      return `<div class="empty-state nexus-empty-state">${icon('lock')}<b>سیگنال فعال VIP برای این حساب نمایش داده نمی‌شود</b><span>برای مشاهده سیگنال‌های فعال VIP باید دسترسی VIP فعال باشد.</span><button class="btn primary" data-unlock-vip>مشاهده پلن‌ها</button></div>`;
    }
    const label = signalState.state === 'CLOSED' ? 'سیگنال بسته‌شده‌ای در این فیلتر وجود ندارد' : 'سیگنال فعالی وجود ندارد';
    return `<div class="empty-state nexus-empty-state">${icon('signals')}<b>${h(label)}</b><span>در این فیلتر داده معتبر و قابل نمایش ثبت نشده است.</span></div>`;
  }

  async function loadSignals({ append = false, silent = false } = {}) {
    if (signalState.loading || state.route !== 'signals') return;
    signalState.loading = true;
    const feed = document.getElementById('signalFeed');
    const more = document.getElementById('signalLoadMore');
    if (!append && !silent && feed) {
      feed.classList.add('is-loading');
      feed.innerHTML = window.NexusProduct?.skeleton?.('signals', 3) || '<div class="empty-state">در حال دریافت سیگنال‌ها...</div>';
    }
    try {
      const query = new URLSearchParams({
        state: signalState.state,
        access: signalState.access,
        limit: String(signalState.limit),
        offset: String(signalState.offset),
      });
      const data = await api(`/signals?${query}`);
      const items = data.items || [];
      const html = items.length ? items.map(card).join('') : (!append ? emptyState() : '');
      if (feed) {
        feed.classList.remove('is-loading');
        if (append) feed.insertAdjacentHTML('beforeend', html);
        else feed.innerHTML = html;
      }
      if (more) more.hidden = items.length < signalState.limit;
      bindSignalCards();
    } catch (err) {
      if (!silent && feed) {
        feed.classList.remove('is-loading');
        feed.innerHTML = `<div class="empty-state">دریافت سیگنال‌ها با مشکل مواجه شد.<br><button class="btn ghost" id="retrySignals">تلاش مجدد</button></div>`;
      }
      document.getElementById('retrySignals')?.addEventListener('click', () => loadSignals());
      if (!silent && more) more.hidden = true;
    } finally {
      signalState.loading = false;
    }
  }

  function selectState(value) {
    signalState.state = value;
    signalState.offset = 0;
    document.querySelectorAll('[data-signal-state]').forEach(btn => btn.classList.toggle('active', btn.dataset.signalState === value));
    track('signal_filter', { filter: 'state', value });
    loadSignals();
  }

  function selectAccess(value) {
    signalState.access = value;
    signalState.offset = 0;
    document.querySelectorAll('[data-signal-access]').forEach(btn => btn.classList.toggle('active', btn.dataset.signalAccess === value));
    track('signal_filter', { filter: 'access', value });
    loadSignals();
  }

  function timelineHtml(items, className = '') {
    if (!items?.length) return '<div class="empty-state compact-empty">Timeline ثبت‌شده‌ای وجود ندارد.</div>';
    return `<div class="signal-timeline ${className}">${items.map(item => `<article><span></span><div><b>${h(item.label_fa || item.action || item.kind || item.event_type || 'UPDATE')}</b>${item.detail_fa || item.detail_en || item.reason ? `<p>${h(item.detail_fa || item.detail_en || item.reason)}</p>` : ''}${item.ticket ? `<p>Ticket: ${h(item.ticket)}</p>` : ''}${item.profit != null ? `<p>P/L: ${h(Number(item.profit).toFixed(2))} $</p>` : ''}<small>${h(dt(item.created_at))}</small></div></article>`).join('')}</div>`;
  }

  function executionHtml(execution) {
    if (!execution) return '';
    const stateName = String(execution.execution_state || execution.status || 'UNKNOWN').toUpperCase();
    const ok = stateName === 'EXECUTED';
    const received = stateName === 'RECEIVED';
    const title = ok ? 'اجرای من انجام شده است' : received ? 'EA سیگنال را دریافت کرده است' : 'اجرای من انجام نشده است';
    return `<section class="signal-execution-panel ${ok ? 'success' : stateName === 'NOT_RECEIVED' ? 'neutral' : 'warning'}">
      <div class="signal-top"><b>${h(title)}</b><span class="status-pill ${ok ? 'success' : 'neutral'}">${h(stateName)}</span></div>
      ${execution.ticket ? `<div class="kv"><span>Ticket</span><b>${h(execution.ticket)}</b></div>` : ''}
      ${execution.reason_fa ? `<div class="execution-reason"><span>${icon('info')}</span><p><b>دلیل:</b> ${h(execution.reason_fa)}</p></div>` : ''}
      ${execution.timeline?.length ? `<h4>Execution Timeline</h4>${timelineHtml(execution.timeline, 'execution-timeline')}` : ''}
      ${ok ? '<button class="btn ghost full" id="goMyTrades">معامله من</button>' : ''}
    </section>`;
  }

  async function openSignal(id) {
    track('signal_detail', { signal_id: id });
    try {
      const item = await api(`/signals/${encodeURIComponent(id)}`);
      const targets = targetHtml(item.targets);
      const direction = String(item.direction || '').toUpperCase();
      showModal(`Signal ${item.code ? '#' + h(item.code) : ''}`, `
        <div class="signal-detail-head"><div><span class="badge ${item.access === 'VIP' ? 'vip-badge' : ''}">${h(item.access)}</span><h3>${h(item.symbol)}</h3></div>${direction ? `<b class="direction-chip ${h(direction.toLowerCase())}">${h(direction)}</b>` : ''}</div>
        <div class="kv"><span>Status</span><b>${h(item.status)}</b></div>
        ${resultChip(item)}
        ${item.entry_price != null ? `<div class="kv"><span>Entry</span><b>${price(item.entry_price)}</b></div>` : ''}
        ${item.stop_loss != null ? `<div class="kv"><span>SL</span><b>${price(item.stop_loss)}</b></div>` : ''}
        ${item.risk_percent != null ? `<div class="kv"><span>Risk</span><b>${h(item.risk_percent)}%</b></div>` : ''}
        ${targets}
        ${item.status !== 'CLOSED' ? liveHtml(item.live, { detail: true }) : ''}
        ${executionHtml(item.my_execution)}
        ${item.timeline?.length ? `<h4>Signal Timeline</h4>${timelineHtml(item.timeline)}` : ''}`);
      setTimeout(() => document.getElementById('goMyTrades')?.addEventListener('click', () => { closeModal(); window.NexusTrades?.open?.(); }), 0);
    } catch (err) {
      const message = String(err?.message || '');
      if (message.includes('VIP access required')) {
        showModal('دسترسی VIP', `<div class="status-panel">سیگنال فعال VIP برای این حساب مجاز نیست.</div><button class="btn primary full" id="detailUnlockVip">مشاهده پلن‌های VIP</button>`);
        setTimeout(() => document.getElementById('detailUnlockVip')?.addEventListener('click', () => { closeModal(); render('subscriptions'); }), 0);
        return;
      }
      toast('دریافت جزئیات سیگنال با مشکل مواجه شد.');
    }
  }

  function bindSignalCards() {
    view.querySelectorAll('[data-open-signal]').forEach(btn => btn.addEventListener('click', event => {
      event.stopPropagation();
      openSignal(btn.dataset.openSignal);
    }));
    view.querySelectorAll('[data-signal-id]').forEach(cardEl => cardEl.addEventListener('click', event => {
      if (event.target.closest('button')) return;
      openSignal(cardEl.dataset.signalId);
    }));
    view.querySelectorAll('[data-unlock-vip]').forEach(btn => btn.addEventListener('click', event => {
      event.stopPropagation();
      render('subscriptions');
    }));
  }

  function hydrateNexusSignals() {
    if (state.route !== 'signals' || !tgWebApp?.initData) return;
    signalState.offset = 0;
    view.innerHTML = shell();
    document.querySelectorAll('[data-signal-state]').forEach(btn => btn.addEventListener('click', () => selectState(btn.dataset.signalState)));
    document.querySelectorAll('[data-signal-access]').forEach(btn => btn.addEventListener('click', () => selectAccess(btn.dataset.signalAccess)));
    document.getElementById('signalLoadMore')?.addEventListener('click', () => {
      signalState.offset += signalState.limit;
      loadSignals({ append: true });
    });
    view.querySelector('[data-open-track-record]')?.addEventListener('click', () => window.NexusTrackRecord?.open?.());
    loadSignals();
  }

  window.hydrateNexusSignals = hydrateNexusSignals;
  document.addEventListener('click', event => {
    const target = event.target.closest?.('[data-route="signals"],[data-go="signals"],[data-home-go="signals"]');
    if (!target) return;
    window.setTimeout(hydrateNexusSignals, 0);
  }, true);
  window.setInterval(() => {
    if (document.visibilityState !== 'visible' || state.route !== 'signals' || signalState.state !== 'ACTIVE' || signalState.offset !== 0) return;
    loadSignals({ silent: true });
  }, 5000);
})();
