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
    if (window.NexusProduct?.normalizeBidi) return window.NexusProduct.normalizeBidi(value);
    return String(value ?? '').replace(/[\u200E\u200F\u202A-\u202E\u2066-\u2069]/g, '').replace(/\s+/g, ' ').trim();
  }

  function dt(value) {
    if (!value) return '—';
    if (window.NexusProduct?.humanDate) return window.NexusProduct.humanDate(value, false);
    try { return new Date(value).toLocaleDateString('fa-IR-u-ca-persian', {year:'numeric',month:'long',day:'numeric'}); } catch (_) { return String(value); }
  }

  function dtFull(value) {
    if (!value) return '—';
    if (window.NexusProduct?.humanDate) return window.NexusProduct.humanDate(value, true);
    try { return new Date(value).toLocaleString('fa-IR-u-ca-persian'); } catch (_) { return String(value); }
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

  function vipCard(data) {
    const stateName = String(data?.state || 'INACTIVE').toUpperCase();
    let cta = 'مشاهده پلن‌های VIP';
    let action = 'plans';
    if (stateName === 'ACTIVE') { cta = 'ورود به VIP'; action = 'vip-open'; }
    if (stateName === 'EXPIRING') cta = 'تمدید VIP';
    if (stateName === 'EXPIRED') cta = 'فعال‌سازی مجدد VIP';
    const remaining = data?.remaining_days;
    return `<article class="account-v2-service account-v2-vip">
      <div class="account-service-title"><div><span class="badge vip-badge">VIP</span><h2>دسترسی VIP</h2></div><span class="status-pill ${stateClass(data?.state)}">${h(stateLabel(data?.state))}</span></div>
      <div class="account-service-summary">
        <span>${data?.expires_at ? `فعال تا <b>${h(dt(data.expires_at))}</b>` : 'اشتراک فعالی ثبت نشده است.'}</span>
        ${remaining != null ? `<strong>${h(remaining)} روز باقی‌مانده</strong>` : ''}
      </div>
      <button class="btn ${stateName === 'ACTIVE' ? 'ghost' : 'primary'} full" data-account-action="${h(action)}">${h(cta)}</button>
    </article>`;
  }

  function autoCheck(yes, label) {
    return `<span class="account-inline-check ${yes ? 'ok' : 'off'}">${yes ? icon('check') : icon('close')}<b>${h(label)}</b></span>`;
  }

  function autotradeCard(data) {
    const setup = String(data?.setup_state || 'NO_SUBSCRIPTION').toUpperCase();
    const health = data?.health || {};
    const checks = [
      autoCheck(!!data?.active, 'اشتراک'),
      autoCheck(!!data?.license_valid, 'لایسنس'),
      autoCheck(!!data?.mt5_bound, 'MT5'),
      autoCheck(String(health.state || '').toUpperCase() === 'HEALTHY', 'EA'),
    ].join('');
    return `<article class="account-v2-service account-v2-autotrade ${h(setup.toLowerCase())}">
      <div class="account-service-title"><div><span class="badge">AutoTrade</span><h2>${h(data?.headline_fa || 'AutoTrade')}</h2></div><span class="status-pill ${stateClass(data?.state)}">${h(stateLabel(data?.state))}</span></div>
      <p class="account-state-message">${h(data?.message_fa || '')}</p>
      <div class="account-inline-checks">${checks}</div>
      ${data?.mt5_account_masked ? `<div class="account-meta-line"><span>حساب MT5</span><b dir="ltr">${h(data.mt5_account_masked)}</b></div>` : ''}
      ${data?.last_seen_at ? `<div class="account-meta-line"><span>آخرین Sync</span><b>${h(dtFull(data.last_seen_at))}</b></div>` : ''}
      <button class="btn ${setup === 'CONNECTED' ? 'ghost' : 'primary'} full" data-account-action="${h(data?.cta_action || 'plans')}">${h(data?.cta_fa || 'مشاهده AutoTrade')}</button>
    </article>`;
  }

  function profile() {
    const user = state.bootstrap?.user || {};
    const name = normalizeText([user.first_name, user.last_name].filter(Boolean).join(' ')) || 'کاربر NEXUS';
    const handle = user.username ? `@${normalizeText(user.username)}` : `Telegram ID: ${user.id || '—'}`;
    const level = accountLevel(user);
    return `<section class="profile-card account-v2-profile">
      <img class="account-brand-avatar" src="./assets/brand/nexus-logo.svg" alt="NEXUS" decoding="async" />
      <div class="account-profile-copy"><h2 class="bidi-safe account-owner-name" dir="rtl"><bdi>${h(name)}</bdi></h2><p dir="ltr">${h(handle)}</p></div>
      <span class="badge muted account-level-badge">${icon('shield', 'nexus-level-icon')}${h(level)}</span>
    </section>`;
  }

  function utilityGrid(data) {
    return `<section class="account-v2-utilities">
      <button class="menu-card" data-account-action="payments"><span>${icon('wallet')}</span><div><b>پرداخت‌های من</b><small>${h(data?.payments_count ?? 0)} رکورد پرداخت</small></div></button>
      <button class="menu-card" data-account-action="referral"><span>${icon('community')}</span><div><b>دعوت دوستان</b><small>Referral</small></div></button>
      <button class="menu-card" data-account-action="support"><span>${icon('support')}</span><div><b>پشتیبانی</b><small>پرداخت، اشتراک و AutoTrade</small></div></button>
      <button class="menu-card" data-account-action="language"><span>${icon('account')}</span><div><b>زبان</b><small>فارسی / English</small></div></button>
      ${data?.is_admin ? `<button class="menu-card admin-only-card" data-account-action="home-content"><span>${icon('book')}</span><div><b>محتوای Home</b><small>مدیریت تحلیل امروز و آکادمی</small></div></button>` : ''}
    </section>`;
  }

  function adminContentRows(items) {
    if (!items?.length) return '<div class="empty-state compact-empty">محتوایی ثبت نشده است.</div>';
    return `<div class="admin-content-list">${items.map(item => `<article>
      <div><span class="badge">${h(item.content_type)}</span><b>${h(item.title_fa)}</b><small>${h(item.audience)} · ${item.active ? 'فعال' : 'غیرفعال'}</small></div>
      <button class="btn ghost" data-content-toggle="${h(item.id)}" data-content-active="${item.active ? '0' : '1'}">${item.active ? 'غیرفعال' : 'فعال'}</button>
    </article>`).join('')}</div>`;
  }

  async function openHomeContentAdmin() {
    showModal('مدیریت محتوای Home', window.NexusProduct?.skeleton?.('list', 3) || '<div class="empty-state">در حال دریافت...</div>');
    try {
      const data = await api('/admin/content');
      const body = document.getElementById('modalBody');
      if (!body) return;
      body.innerHTML = `<div class="admin-content-form">
        <select class="text-input" id="contentType"><option value="market_insight">تحلیل امروز</option><option value="academy">آکادمی NEXUS</option></select>
        <select class="text-input" id="contentAudience"><option value="ALL">همه</option><option value="GUEST">Guest</option><option value="VIP">VIP</option><option value="AUTOTRADE">AutoTrade</option><option value="BUNDLE">Bundle</option><option value="EXPIRING">رو به پایان</option><option value="EXPIRED">منقضی</option></select>
        <input class="text-input" id="contentTitle" maxlength="160" placeholder="عنوان" />
        <textarea class="text-input admin-content-body" id="contentBody" maxlength="900" placeholder="متن کوتاه"></textarea>
        <input class="text-input" id="contentCta" maxlength="80" placeholder="متن دکمه (اختیاری)" />
        <input class="text-input" id="contentUrl" maxlength="500" placeholder="لینک (اختیاری)" dir="ltr" />
        <button class="btn primary full" id="createHomeContent">ثبت محتوا</button>
      </div>${adminContentRows(data.items)}`;
      body.querySelectorAll('[data-content-toggle]').forEach(btn => btn.addEventListener('click', async () => {
        await api(`/admin/content/${encodeURIComponent(btn.dataset.contentToggle)}/state`, {method:'POST', body:JSON.stringify({active:btn.dataset.contentActive === '1'})});
        openHomeContentAdmin();
      }));
      document.getElementById('createHomeContent')?.addEventListener('click', async () => {
        const title = normalizeText(document.getElementById('contentTitle')?.value || '');
        if (!title) return toast('عنوان محتوا را وارد کنید.');
        await api('/admin/content', {method:'POST', body:JSON.stringify({
          content_type: document.getElementById('contentType')?.value || 'market_insight',
          audience: document.getElementById('contentAudience')?.value || 'ALL',
          title_fa: title,
          body_fa: normalizeText(document.getElementById('contentBody')?.value || '') || null,
          cta_fa: normalizeText(document.getElementById('contentCta')?.value || '') || null,
          url: String(document.getElementById('contentUrl')?.value || '').trim() || null,
          priority: 100,
          active: true
        })});
        toast('محتوا ثبت شد.');
        openHomeContentAdmin();
      });
    } catch (err) {
      const body = document.getElementById('modalBody');
      if (body) body.innerHTML = `<div class="empty-state">دریافت محتوای Home ناموفق بود.<br><button class="btn ghost" id="retryHomeContentAdmin">تلاش مجدد</button></div>`;
      document.getElementById('retryHomeContentAdmin')?.addEventListener('click', openHomeContentAdmin);
    }
  }

  function bind() {
    view.querySelectorAll('[data-account-action]').forEach(btn => btn.addEventListener('click', async () => {
      const action = btn.dataset.accountAction;
      if (action === 'vip-open') return openVip();
      if (action === 'plans') return render('subscriptions');
      if (action === 'trades') return window.NexusTrades?.open?.();
      if (action === 'guide') return render('guide');
      if (action === 'payments') return showPayments();
      if (action === 'referral') return showReferral();
      if (action === 'support') return handleAction('support');
      if (action === 'language') return document.getElementById('langBtn')?.click();
      if (action === 'home-content') return openHomeContentAdmin();
    }));
  }

  async function hydrateAccountV2() {
    if (state.route !== 'account') return;
    view.innerHTML = window.NexusProduct?.skeleton?.('account', 4) || '<div class="empty-state">در حال دریافت وضعیت حساب...</div>';
    try {
      if (!state.bootstrap) state.bootstrap = await api('/bootstrap');
      const data = await api('/account/status');
      view.innerHTML = `${profile()}
        <section class="page-head account-v2-head"><div><div class="eyebrow">STATUS CENTER</div><h1>حساب من</h1></div></section>
        <div class="account-v2-services">${vipCard(data.vip)}${autotradeCard(data.autotrade)}</div>
        ${utilityGrid(data)}
        <div class="note-card">دسترسی‌ها، تاریخ انقضا و وضعیت AutoTrade از backend خوانده می‌شوند. مقدار کامل License در این صفحه نمایش داده نمی‌شود.</div>`;
      bind();
      window.NexusProduct?.fixBidiSurfaces?.(view);
      window.NexusProduct?.track?.('account_view', { vip_state: data.vip?.state, autotrade_state: data.autotrade?.setup_state });
    } catch (err) {
      view.innerHTML = `<div class="empty-state">دریافت وضعیت حساب با مشکل مواجه شد.<br><button class="btn ghost" id="retryAccountV2">تلاش مجدد</button></div>`;
      document.getElementById('retryAccountV2')?.addEventListener('click', hydrateAccountV2);
    }
  }

  window.NexusAccount = { open: hydrateAccountV2, openHomeContentAdmin };

  const observer = new MutationObserver(() => {
    if (state.route !== 'account') return;
    if (view.querySelector('.account-v2-services') || view.dataset.accountV2Loading === '1') return;
    view.dataset.accountV2Loading = '1';
    Promise.resolve(hydrateAccountV2()).finally(() => { delete view.dataset.accountV2Loading; });
  });
  observer.observe(view, { childList: true, subtree: false });
})();
