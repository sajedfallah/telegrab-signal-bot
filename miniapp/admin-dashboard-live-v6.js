(() => {
  const tg = window.Telegram?.WebApp;
  const API = '/miniapp/api/admin';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const signed = (value, digits = 2) => {
    const n = Number(value);
    return Number.isFinite(n) ? `${n > 0 ? '+' : ''}${n.toFixed(digits)}` : '—';
  };
  const headers = () => ({...(tg?.initData ? {'X-Telegram-Init-Data': tg.initData} : {})});
  let latest = {positions:[], orders:[]};

  function pnlOf(position) {
    const raw = position?.floating_pnl ?? position?.profit ?? position?.pnl ?? position?.profit_float;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  }

  function currentOf(position) {
    return position?.current_price ?? position?.price_current ?? position?.price ?? '—';
  }

  function lastSync(position) {
    const raw = position?.last_seen_at ?? position?.updated_at ?? position?.snapshot_at;
    if (!raw) return '—';
    const ts = new Date(raw).getTime();
    if (!Number.isFinite(ts)) return esc(raw);
    const age = Math.max(0, Math.round((Date.now() - ts) / 1000));
    return `${age}s ago`;
  }

  function liveCard(position) {
    const pnl = pnlOf(position);
    const pnlClass = pnl == null ? 'flat' : pnl > 0 ? 'profit' : pnl < 0 ? 'loss' : 'flat';
    const side = position?.direction ?? position?.type ?? '';
    return `<article class="card admin-dashboard-position ${pnlClass}" data-ticket="${esc(position?.ticket || '')}">
      <div class="card-head">
        <strong>${esc(position?.symbol || '—')} · ${esc(side)}</strong>
        <span class="status PUBLISHED">LIVE</span>
      </div>
      <div class="levels admin-position-levels">
        <span>TICKET<b>${esc(position?.ticket || '—')}</b></span>
        <span>ENTRY<b>${esc(position?.entry_price ?? position?.price_open ?? '—')}</b></span>
        <span>CURRENT<b>${esc(currentOf(position))}</b></span>
        <span>VOLUME<b>${esc(position?.volume ?? '—')}</b></span>
        <span>FLOATING P&amp;L<b class="${pnlClass}">${pnl == null ? '—' : signed(pnl)}</b></span>
        <span>SL / TP<b>${esc(position?.stop_loss ?? position?.sl ?? '—')} / ${esc(position?.take_profit ?? position?.tp ?? '—')}</b></span>
      </div>
      <div class="admin-position-sync">Last MT5 Sync: ${lastSync(position)}</div>
    </article>`;
  }

  function ensureDashboardHost() {
    const dashboard = $('dashboard');
    if (!dashboard) return null;
    let section = $('dashboardLivePositions');
    if (!section) {
      section = document.createElement('section');
      section.id = 'dashboardLivePositions';
      section.className = 'admin-dashboard-live-section';
      section.innerHTML = `
        <div class="section-head admin-dashboard-live-head">
          <div><small>MT5 LIVE</small><h2>پوزیشن‌های فعال</h2></div>
          <button type="button" id="dashboardReloadPositions">بروزرسانی</button>
        </div>
        <div id="dashboardPositionList" class="stack"><div class="empty">در حال دریافت پوزیشن‌های فعال...</div></div>`;
      const metrics = dashboard.querySelector('.metrics');
      if (metrics?.nextSibling) dashboard.insertBefore(section, metrics.nextSibling);
      else dashboard.appendChild(section);
      $('dashboardReloadPositions')?.addEventListener('click', loadDashboardPositions);
    }
    return $('dashboardPositionList');
  }

  function inlineLive(position) {
    const pnl = pnlOf(position);
    const pnlClass = pnl == null ? 'flat' : pnl > 0 ? 'profit' : pnl < 0 ? 'loss' : 'flat';
    return `<div class="admin-v6-inline-live">
      <span>CURRENT<b>${esc(currentOf(position))}</b></span>
      <span>FLOATING P&amp;L<b class="${pnlClass}">${pnl == null ? '—' : signed(pnl)}</b></span>
      <span>LIVE SL<b>${esc(position?.stop_loss ?? position?.sl ?? '—')}</b></span>
      <span>LIVE TP<b>${esc(position?.take_profit ?? position?.tp ?? '—')}</b></span>
    </div><div class="admin-position-sync">Last MT5 Sync: ${lastSync(position)}</div>`;
  }

  function enrichPositionTab() {
    const list = $('positionList');
    if (!list) return;
    const rows = [...latest.positions, ...latest.orders];
    list.querySelectorAll('.card').forEach(card => {
      card.classList.add('admin-position-card-v6');
      const ticketNode = [...card.querySelectorAll('b')].find(node => /^\d+$/.test(node.textContent.trim()));
      const ticket = ticketNode?.textContent?.trim();
      if (!ticket) return;
      const row = rows.find(item => String(item?.ticket ?? '') === ticket);
      if (!row) return;
      card.querySelector('.admin-v6-inline-live')?.remove();
      const staleSync = card.querySelector('.admin-position-sync');
      if (staleSync) staleSync.remove();
      const actions = card.querySelector('.trade-actions');
      const wrap = document.createElement('div');
      wrap.innerHTML = inlineLive(row);
      const nodes = [...wrap.childNodes];
      nodes.forEach(node => card.insertBefore(node, actions || null));
    });
  }

  async function loadDashboardPositions() {
    const host = ensureDashboardHost();
    if (!host || document.visibilityState !== 'visible') return;
    try {
      const response = await fetch(`${API}/positions`, {headers: headers()});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      const positions = Array.isArray(data.positions) ? data.positions : [];
      const orders = Array.isArray(data.orders) ? data.orders : [];
      latest = {positions, orders};
      host.innerHTML = positions.length ? positions.map(liveCard).join('') : '<div class="empty">پوزیشن فعال NEXUS وجود ندارد.</div>';
      const count = $('positionCount');
      if (count) count.textContent = new Intl.NumberFormat('fa-IR').format(positions.length + orders.length);
      window.setTimeout(enrichPositionTab, 80);
    } catch (error) {
      host.innerHTML = `<div class="empty">دریافت وضعیت Live MT5 ناموفق بود.<br>${esc(error.message)}</div>`;
    }
  }

  function observePositionCards() {
    const list = $('positionList');
    if (!list) return;
    const observer = new MutationObserver(() => window.setTimeout(enrichPositionTab, 0));
    observer.observe(list, {childList:true, subtree:true});
  }

  ensureDashboardHost();
  observePositionCards();
  loadDashboardPositions();
  window.setInterval(loadDashboardPositions, 5000);
})();
