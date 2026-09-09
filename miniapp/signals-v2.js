(() => {
  const tgWebApp = window.Telegram?.WebApp;
  const signalState = { state: 'ACTIVE', access: 'ALL', offset: 0, limit: 20, loading: false };

  function h(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  }

  function dt(value) {
    if (!value) return '—';
    try { return new Date(value).toLocaleString('fa-IR'); } catch (_) { return String(value); }
  }

  function price(value) {
    if (value == null || value === '') return '—';
    return h(value);
  }

  function targetHtml(targets) {
    if (!targets?.length) return '';
    return `<div class="signal-v2-targets">${targets.map(t => `<span>TP${h(t.target_no)} <b>${price(t.price)}</b></span>`).join('')}</div>`;
  }

  function card(item) {
    const result = item.result ? `<span class="signal-v2-result ${String(item.result).toLowerCase()}">${h(item.result)}</span>` : '';
    const details = item.locked ? `
      <div class="signal-v2-lock"><b>جزئیات VIP قفل است</b><span>Entry، SL، TP و Risk از API ارسال نشده‌اند.</span></div>
      <button class="btn primary full" data-unlock-vip>فعال‌سازی VIP</button>` : `
      <div class="signal-v2-core">
        ${item.entry_price != null ? `<div><span>Entry</span><b>${price(item.entry_price)}</b></div>` : ''}
        ${item.stop_loss != null ? `<div><span>SL</span><b>${price(item.stop_loss)}</b></div>` : ''}
        ${item.risk_percent != null ? `<div><span>Risk</span><b>${h(item.risk_percent)}%</b></div>` : ''}
      </div>
      ${targetHtml(item.targets)}`;
    return `<article class="signal-v2-card ${item.locked ? 'locked' : ''}" data-signal-id="${h(item.id)}">
      <div class="signal-top"><div class="signal-v2-badges"><span class="badge ${item.access === 'VIP' ? 'vip-badge' : ''}">${h(item.access)}</span>${item.code ? `<span class="badge muted">#${h(item.code)}</span>` : ''}</div><span class="status-pill ${item.status === 'CLOSED' ? 'success' : ''}">${h(item.status || '')}</span></div>
      <div class="signal-v2-title"><div><h3>${h(item.symbol || '—')}</h3><small>${h(dt(item.published_at))}</small></div><div class="signal-v2-side">${item.direction ? `<b>${h(item.direction)}</b>` : ''}${result}</div></div>
      ${details}
      <button class="text-btn signal-v2-detail" data-open-signal="${h(item.id)}">جزئیات و Timeline</button>
    </article>`;
  }

  function shell() {
    return `<section class="page-head"><div><div class="eyebrow">SIGNAL CENTER</div><h1>سیگنال‌های NEXUS</h1></div></section>
      <div class="signal-v2-filters">
        <div class="plan-tabs signal-v2-primary"><button class="tab active" data-signal-state="ACTIVE">فعال</button><button class="tab" data-signal-state="CLOSED">بسته‌شده</button></div>
        <div class="signal-v2-access"><button class="tab active" data-signal-access="ALL">همه</button><button class="tab" data-signal-access="FREE">FREE</button><button class="tab" data-signal-access="VIP">VIP</button></div>
      </div>
      <div class="stack" id="signalFeed"><div class="empty-state">در حال دریافت سیگنال‌ها...</div></div>
      <button class="btn ghost full signal-load-more" id="signalLoadMore" hidden>نمایش بیشتر</button>`;
  }

  async function loadSignals({ append = false } = {}) {
    if (signalState.loading || state.route !== 'signals') return;
    signalState.loading = true;
    const feed = document.getElementById('signalFeed');
    const more = document.getElementById('signalLoadMore');
    if (!append && feed) feed.innerHTML = '<div class="empty-state">در حال دریافت سیگنال‌ها...</div>';
    try {
      const query = new URLSearchParams({
        state: signalState.state,
        access: signalState.access,
        limit: String(signalState.limit),
        offset: String(signalState.offset),
      });
      const data = await api(`/signals?${query}`);
      const items = data.items || [];
      const html = items.length ? items.map(card).join('') : (!append ? '<div class="empty-state">در این فیلتر سیگنالی وجود ندارد.</div>' : '');
      if (feed) {
        if (append) feed.insertAdjacentHTML('beforeend', html);
        else feed.innerHTML = html;
      }
      if (more) more.hidden = items.length < signalState.limit;
      bindSignalCards();
    } catch (err) {
      if (feed) feed.innerHTML = `<div class="empty-state">دریافت سیگنال‌ها با مشکل مواجه شد.<br><button class="btn ghost" id="retrySignals">تلاش مجدد</button></div>`;
      document.getElementById('retrySignals')?.addEventListener('click', () => loadSignals());
      if (more) more.hidden = true;
    } finally {
      signalState.loading = false;
    }
  }

  function selectState(value) {
    signalState.state = value;
    signalState.offset = 0;
    document.querySelectorAll('[data-signal-state]').forEach(btn => btn.classList.toggle('active', btn.dataset.signalState === value));
    loadSignals();
  }

  function selectAccess(value) {
    signalState.access = value;
    signalState.offset = 0;
    document.querySelectorAll('[data-signal-access]').forEach(btn => btn.classList.toggle('active', btn.dataset.signalAccess === value));
    loadSignals();
  }

  function timelineHtml(items) {
    if (!items?.length) return '<div class="empty-state">Timeline ثبت‌شده‌ای وجود ندارد.</div>';
    return `<div class="signal-timeline">${items.map(item => `<article><span></span><div><b>${h(item.action || 'UPDATE')}</b><p>${h(item.detail_fa || item.detail_en || '')}</p><small>${h(dt(item.created_at))}</small></div></article>`).join('')}</div>`;
  }

  async function openSignal(id) {
    try {
      const item = await api(`/signals/${encodeURIComponent(id)}`);
      if (item.locked) {
        showModal('سیگنال VIP', `<div class="status-panel">این سیگنال VIP فعال است و جزئیات عملیاتی آن برای حساب شما مجاز نیست.</div><div class="kv"><span>Symbol</span><b>${h(item.symbol)}</b></div><div class="kv"><span>Status</span><b>${h(item.status)}</b></div><button class="btn primary full" id="detailUnlockVip">فعال‌سازی VIP</button>`);
        setTimeout(() => document.getElementById('detailUnlockVip')?.addEventListener('click', () => { closeModal(); render('subscriptions'); }), 0);
        return;
      }
      const targets = targetHtml(item.targets);
      const execution = item.my_execution ? `<div class="status-panel success"><b>وضعیت اجرای من</b><div class="kv"><span>Ticket</span><b>${h(item.my_execution.ticket || '—')}</b></div><div class="kv"><span>Status</span><b>${h(item.my_execution.status || item.my_execution.event_type || 'EXECUTED')}</b></div><button class="btn ghost full" id="goMyTrades">معامله من</button></div>` : '';
      showModal(`Signal ${item.code ? '#' + h(item.code) : ''}`, `
        <div class="signal-detail-head"><div><span class="badge ${item.access === 'VIP' ? 'vip-badge' : ''}">${h(item.access)}</span><h3>${h(item.symbol)}</h3></div><b>${h(item.direction || '')}</b></div>
        <div class="kv"><span>Status</span><b>${h(item.status)}</b></div>
        ${item.entry_price != null ? `<div class="kv"><span>Entry</span><b>${price(item.entry_price)}</b></div>` : ''}
        ${item.stop_loss != null ? `<div class="kv"><span>SL</span><b>${price(item.stop_loss)}</b></div>` : ''}
        ${item.risk_percent != null ? `<div class="kv"><span>Risk</span><b>${h(item.risk_percent)}%</b></div>` : ''}
        ${targets}
        ${item.result ? `<div class="kv"><span>Result</span><b>${h(item.result)}</b></div>` : ''}
        ${execution}
        <h4>Timeline</h4>${timelineHtml(item.timeline)}`);
      setTimeout(() => document.getElementById('goMyTrades')?.addEventListener('click', () => { closeModal(); window.NexusExperience?.renderTrades?.(); }), 0);
    } catch (err) {
      toast('دریافت جزئیات سیگنال با مشکل مواجه شد.');
    }
  }

  function bindSignalCards() {
    view.querySelectorAll('[data-open-signal]').forEach(btn => btn.addEventListener('click', event => {
      event.stopPropagation();
      openSignal(btn.dataset.openSignal);
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
    loadSignals();
  }

  window.hydrateNexusSignals = hydrateNexusSignals;
  document.addEventListener('click', event => {
    const target = event.target.closest?.('[data-route="signals"],[data-go="signals"],[data-home-go="signals"]');
    if (!target) return;
    window.setTimeout(hydrateNexusSignals, 0);
  }, true);
})();
