(() => {
  const navHost = document.querySelector('.bottom-nav');

  function html(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  }

  function dateTime(value) {
    if (!value) return '—';
    try { return new Date(value).toLocaleString('fa-IR'); } catch (_) { return String(value); }
  }

  function money(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? `${number.toFixed(2)} $` : '—';
  }

  function statusClass(value) {
    const raw = String(value || '').toUpperCase();
    if (['ACTIVE', 'OPEN', 'CONNECTED', 'HEALTHY', 'EXECUTED', 'CLOSED'].includes(raw)) return 'success';
    return '';
  }

  function setActiveNav(route) {
    document.querySelectorAll('.nav-item').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.route === route);
    });
  }

  function renderNavigation(items) {
    if (!navHost || !Array.isArray(items) || !items.length) return;
    navHost.replaceChildren(...items.map(item => {
      const button = document.createElement('button');
      button.className = `nav-item${item.route === state.route ? ' active' : ''}`;
      button.dataset.route = item.route;
      button.innerHTML = `<span>${html(item.icon || '•')}</span><small>${html(item.label_fa || item.label_en || item.route)}</small>`;
      button.addEventListener('click', () => {
        if (item.route === 'trades') renderTrades();
        else render(item.route);
      });
      return button;
    }));
  }

  function renderLifecycleMarker(experience) {
    document.body.dataset.nexusSegment = experience.segment || 'GUEST';
    document.body.dataset.nexusLifecycle = experience.lifecycle || 'GUEST';
  }

  function tradeRows(rows, kind) {
    if (!rows?.length) {
      const text = kind === 'open'
        ? 'در حال حاضر معامله بازی توسط AutoTrade ثبت نشده است.'
        : kind === 'pending'
          ? 'در حال حاضر سفارش Pending ثبت نشده است.'
          : 'هنوز سابقه معامله‌ای ثبت نشده است.';
      return `<div class="empty-state">${text}</div>`;
    }
    return rows.map(row => {
      const status = row.status || row.event_type || (kind === 'open' ? 'OPEN' : kind === 'pending' ? 'PENDING' : '');
      return `<article class="signal-card trade-experience-card">
        <div class="signal-top">
          <span class="badge">${html(row.direction || row.order_type || row.event_type || 'TRADE')}</span>
          <span class="status-pill ${statusClass(status)}">${html(status)}</span>
        </div>
        <h3>${html(row.symbol || '—')}</h3>
        <div class="kv"><span>Ticket</span><b>${html(row.ticket || row.identifier || '—')}</b></div>
        ${row.volume != null ? `<div class="kv"><span>Volume</span><b>${html(row.volume)}</b></div>` : ''}
        ${row.entry_price != null ? `<div class="kv"><span>Entry</span><b>${html(row.entry_price)}</b></div>` : ''}
        ${row.current_price != null ? `<div class="kv"><span>Current</span><b>${html(row.current_price)}</b></div>` : ''}
        ${row.stop_loss != null ? `<div class="kv"><span>SL</span><b>${html(row.stop_loss)}</b></div>` : ''}
        ${row.take_profit != null ? `<div class="kv"><span>TP</span><b>${html(row.take_profit)}</b></div>` : ''}
        ${row.profit != null ? `<div class="kv"><span>P/L</span><b>${html(money(row.profit))}</b></div>` : ''}
        ${row.created_at ? `<div class="kv"><span>Time</span><b>${html(dateTime(row.created_at))}</b></div>` : ''}
      </article>`;
    }).join('');
  }

  async function ensureBootstrap() {
    if (state.bootstrap) return state.bootstrap;
    state.bootstrap = await api('/bootstrap');
    return state.bootstrap;
  }

  async function renderTrades() {
    const experience = state.experience;
    if (!experience?.features?.trades) {
      render('subscriptions');
      return;
    }

    state.route = 'trades';
    setActiveNav('trades');
    view.innerHTML = `
      <section class="page-head"><div><div class="eyebrow">AUTOTRADE</div><h1>معاملات من</h1></div></section>
      <div class="status-panel" id="tradeHealth">در حال دریافت وضعیت AutoTrade...</div>
      <div class="plan-tabs" id="tradeTabs">
        <button class="tab active" data-trade-tab="open">باز</button>
        <button class="tab" data-trade-tab="pending">Pending</button>
        <button class="tab" data-trade-tab="history">تاریخچه</button>
      </div>
      <div class="stack" id="tradeList"><div class="empty-state">در حال دریافت معاملات...</div></div>`;

    try {
      const bootstrapData = await ensureBootstrap();
      const auto = bootstrapData.autotrade || {};
      const health = document.getElementById('tradeHealth');
      const mt5 = auto.mt5 || null;
      if (health) {
        health.classList.toggle('success', !!auto.entitled && !!mt5);
        health.innerHTML = auto.entitled
          ? `<b>${mt5 ? 'AutoTrade متصل' : 'AutoTrade فعال — نیاز به بررسی اتصال'}</b><br><span class="modal-muted">${mt5 ? `MT5 ${html(mt5.account_number)} · آخرین Sync: ${html(dateTime(mt5.last_seen_at))}` : 'حساب MT5 متصل نیست.'}</span>`
          : '<b>AutoTrade فعال نیست.</b>';
      }

      const dataByTab = {
        open: auto.open_positions || [],
        pending: auto.pending_orders || [],
        history: auto.history || [],
      };
      const list = document.getElementById('tradeList');
      const tabs = [...document.querySelectorAll('[data-trade-tab]')];
      const selectTab = key => {
        tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.tradeTab === key));
        if (list) list.innerHTML = tradeRows(dataByTab[key], key);
      };
      tabs.forEach(tab => tab.addEventListener('click', () => selectTab(tab.dataset.tradeTab)));
      selectTab('open');
    } catch (err) {
      const list = document.getElementById('tradeList');
      if (list) list.innerHTML = `<div class="empty-state">دریافت اطلاعات معاملات با مشکل مواجه شد.<br><button class="btn ghost" id="retryTrades">تلاش مجدد</button></div>`;
      document.getElementById('retryTrades')?.addEventListener('click', renderTrades);
    }
  }

  async function loadExperience() {
    if (!window.Telegram?.WebApp?.initData) return;
    try {
      const experience = await api('/experience');
      state.experience = experience;
      renderLifecycleMarker(experience);
      renderNavigation(experience.navigation);
    } catch (err) {
      console.error('NEXUS experience context failed', err);
      // Keep the legacy four-item navigation as a safe fallback.
    }
  }

  loadExperience();
})();
