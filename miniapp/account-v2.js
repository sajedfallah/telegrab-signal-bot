(() => {
  function h(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  }

  function icon(name, className = 'nexus-inline-icon') {
    return window.NexusIcons?.svg?.(name, className) || '';
  }

  function normalizeText(value) {
    return String(value ?? '').replace(/[\u200E\u200F]/g, '').trim();
  }

  function dt(value) {
    if (!value) return '—';
    try { return new Date(value).toLocaleString('fa-IR'); } catch (_) { return String(value); }
  }

  function stateLabel(value) {
    return ({ACTIVE:'فعال',EXPIRING:'رو به پایان',EXPIRED:'منقضی',INACTIVE:'غیرفعال'})[String(value || '').toUpperCase()] || String(value || '');
  }

  function stateClass(value) {
    const key = String(value || '').toUpperCase();
    if (key === 'ACTIVE') return 'success';
    if (key === 'EXPIRING') return 'warning';
    if (key === 'EXPIRED') return 'danger';
    return 'muted';
  }

  function accountLevel(user) {
    const key = String(user?.level?.key || 'member').toLowerCase();
    return ({diamond:'DIAMOND',gold:'GOLD',silver:'SILVER',member:'MEMBER'})[key] || 'MEMBER';
  }

  function serviceCta(kind, data) {
    const stateName = String(data?.state || 'INACTIVE').toUpperCase();
    if (kind === 'vip') {
      if (stateName === 'ACTIVE') return '<button class="btn ghost full" data-account-action="vip-open">ورود به VIP</button>';
      if (stateName === 'EXPIRING') return '<button class="btn primary full" data-account-action="plans">تمدید VIP</button>';
      if (stateName === 'EXPIRED') return '<button class="btn primary full" data-account-action="plans">فعال‌سازی مجدد VIP</button>';
      return '<button class="btn primary full" data-account-action="plans">مشاهده پلن‌های VIP</button>';
    }
    if (stateName === 'ACTIVE' || stateName === 'EXPIRING') {
      return '<button class="btn ghost full" data-account-action="trades">مدیریت AutoTrade</button>';
    }
    if (stateName === 'EXPIRED') return '<button class="btn primary full" data-account-action="plans">فعال‌سازی مجدد AutoTrade</button>';
    return '<button class="btn primary full" data-account-action="plans">مشاهده AutoTrade</button>';
  }

  function serviceCard(kind, data) {
    const isVip = kind === 'vip';
    const title = isVip ? 'VIP' : 'AutoTrade';
    const badgeClass = stateClass(data?.state);
    const expiry = data?.expires_at ? dt(data.expires_at) : '—';
    const remaining = data?.remaining_days;
    const extra = isVip ? '' : `
      <div class="account-v2-mini-grid">
        <div><span>MT5</span><b>${data?.mt5_bound ? 'متصل' : 'متصل نیست'}</b></div>
        <div><span>EA</span><b>${h(data?.ea_status || '—')}</b></div>
      </div>
      ${data?.last_seen_at ? `<small class="account-v2-last">Last Seen: ${h(dt(data.last_seen_at))}</small>` : ''}`;
    return `<article class="account-v2-service">
      <div class="signal-top"><div><span class="badge ${isVip ? 'vip-badge' : ''}">${title}</span></div><span class="status-pill ${badgeClass}">${h(stateLabel(data?.state))}</span></div>
      <div class="account-v2-service-body">
        <div><span>انقضا</span><b>${h(expiry)}</b></div>
        <div><span>روز باقی‌مانده</span><b>${remaining == null ? '—' : h(remaining)}</b></div>
      </div>
      ${extra}
      ${serviceCta(kind, data)}
    </article>`;
  }

  function profile() {
    const user = state.bootstrap?.user || {};
    const name = normalizeText([user.first_name, user.last_name].filter(Boolean).join(' ')) || 'کاربر NEXUS';
    const handle = user.username ? `@${user.username}` : `Telegram ID: ${user.id || '—'}`;
    const level = accountLevel(user);
    return `<section class="profile-card account-v2-profile">
      <img class="account-brand-avatar" src="./assets/brand/nexus-logo.svg" alt="NEXUS" />
      <div class="account-profile-copy"><h2 class="bidi-auto" dir="auto">${h(name)}</h2><p dir="ltr">${h(handle)}</p></div>
      <span class="badge muted account-level-badge">${icon('shield', 'nexus-level-icon')}${h(level)}</span>
    </section>`;
  }

  function utilityGrid(data) {
    return `<section class="account-v2-utilities">
      <button class="menu-card" data-account-action="payments"><span>${icon('wallet')}</span><div><b>پرداخت‌های من</b><small>${h(data?.payments_count ?? 0)} رکورد پرداخت</small></div></button>
      <button class="menu-card" data-account-action="referral"><span>${icon('community')}</span><div><b>دعوت دوستان</b><small>Referral</small></div></button>
      <button class="menu-card" data-account-action="support"><span>${icon('support')}</span><div><b>پشتیبانی</b><small>کمک در پرداخت، اشتراک یا AutoTrade</small></div></button>
      <button class="menu-card" data-account-action="language"><span>${icon('account')}</span><div><b>زبان</b><small>فارسی / English</small></div></button>
    </section>`;
  }

  function bind() {
    view.querySelectorAll('[data-account-action]').forEach(btn => btn.addEventListener('click', async () => {
      const action = btn.dataset.accountAction;
      if (action === 'vip-open') return openVip();
      if (action === 'plans') return render('subscriptions');
      if (action === 'trades') return window.NexusTrades?.open?.();
      if (action === 'payments') return showPayments();
      if (action === 'referral') return showReferral();
      if (action === 'support') return handleAction('support');
      if (action === 'language') return document.getElementById('langBtn')?.click();
    }));
  }

  async function hydrateAccountV2() {
    if (state.route !== 'account') return;
    view.innerHTML = '<div class="empty-state">در حال دریافت وضعیت حساب...</div>';
    try {
      if (!state.bootstrap) state.bootstrap = await api('/bootstrap');
      const data = await api('/account/status');
      view.innerHTML = `${profile()}
        <section class="page-head account-v2-head"><div><div class="eyebrow">STATUS CENTER</div><h1>حساب من</h1></div></section>
        <div class="account-v2-services">${serviceCard('vip', data.vip)}${serviceCard('autotrade', data.autotrade)}</div>
        ${utilityGrid(data)}
        <div class="note-card">دسترسی‌ها، تاریخ انقضا و وضعیت AutoTrade از backend خوانده می‌شوند. مقدار کامل License در این صفحه نمایش داده نمی‌شود.</div>`;
      bind();
    } catch (err) {
      view.innerHTML = `<div class="empty-state">دریافت وضعیت حساب با مشکل مواجه شد.<br><button class="btn ghost" id="retryAccountV2">تلاش مجدد</button></div>`;
      document.getElementById('retryAccountV2')?.addEventListener('click', hydrateAccountV2);
    }
  }

  window.NexusAccount = { open: hydrateAccountV2 };

  const observer = new MutationObserver(() => {
    if (state.route !== 'account') return;
    if (view.querySelector('.account-v2-services') || view.dataset.accountV2Loading === '1') return;
    view.dataset.accountV2Loading = '1';
    Promise.resolve(hydrateAccountV2()).finally(() => { delete view.dataset.accountV2Loading; });
  });
  observer.observe(view, { childList: true, subtree: false });
})();
