const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  try { tg.setHeaderColor('#071019'); tg.setBackgroundColor('#071019'); } catch (_) {}
}

const state = {
  page: 'home',
  data: null,
  loading: true,
  error: null,
};

const titles = {
  home: 'خانه',
  signals: 'سیگنال‌ها',
  subscriptions: 'اشتراک‌ها',
  products: 'محصولات',
  account: 'حساب من',
};

function esc(v = '') {
  return String(v).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function openLink(url) {
  if (!url) return;
  if (tg?.openTelegramLink && /^https:\/\/t\.me\//i.test(url)) tg.openTelegramLink(url);
  else if (tg?.openLink) tg.openLink(url);
  else window.open(url, '_blank', 'noopener');
}

function sendAction(action, payload = {}) {
  const body = JSON.stringify({ action, ...payload });
  if (tg?.sendData) {
    tg.sendData(body);
    return;
  }
  alert('این عملیات داخل Telegram Mini App فعال می‌شود.');
}

function nav(page) {
  state.page = page;
  document.getElementById('page-title').textContent = titles[page] || 'NEXUS';
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.page === page));
  render();
}

function homeView(d) {
  const name = d.account?.user?.first_name ? `، ${esc(d.account.user.first_name)}` : '';
  return `
    <section class="hero">
      <div class="pill">● NEXUS ONLINE</div>
      <h2>به NEXUS خوش آمدی${name}</h2>
      <p>مرکز یکپارچه سیگنال‌ها، اشتراک‌ها، AutoTrade و سرویس‌های معاملاتی NEXUS.</p>
      <div class="button-row"><button class="btn btn-primary" data-open="${esc(d.links.public_channel)}">ورود به کانال عمومی NEXUS</button></div>
    </section>
    <div class="section-title">دسترسی سریع</div>
    <section class="grid">
      <article class="card action-card"><div><span class="pill">SIGNALS</span><h3>سیگنال‌ها</h3><p>دسترسی به کانال سیگنال رایگان و VIP.</p></div><button class="btn btn-secondary" data-nav="signals">مشاهده</button></article>
      <article class="card action-card"><div><span class="pill">MEMBERSHIP</span><h3>اشتراک NEXUS</h3><p>پلن‌های عضویت و دسترسی‌های فعال.</p></div><button class="btn btn-secondary" data-nav="subscriptions">پلن‌ها</button></article>
      <article class="card action-card"><div><span class="pill">ACCOUNT</span><h3>حساب من</h3><p>اطلاعات حساب و وضعیت اتصال Telegram.</p></div><button class="btn btn-secondary" data-nav="account">حساب من</button></article>
      <article class="card action-card"><div><span class="pill">PRODUCTS</span><h3>محصولات</h3><p>محصولات NEXUS در صفحه مستقل.</p></div><button class="btn btn-secondary" data-nav="products">مشاهده محصولات</button></article>
    </section>`;
}

function signalsView(d) {
  return `<section class="card">
    <h3>کانال‌های سیگنال</h3>
    <p>طبق ساختار تأییدشده، فقط Free و VIP در این بخش نمایش داده می‌شوند.</p>
    <div class="signal-row"><div><div class="signal-title">NEXUS Free Signal</div><div class="subtext">سیگنال‌های رایگان NEXUS</div></div><div><span class="badge badge-free">FREE</span> <button class="btn btn-secondary" data-open="${esc(d.links.free_channel)}">ورود</button></div></div>
    <div class="signal-row"><div><div class="signal-title">NEXUS VIP Signal</div><div class="subtext">دسترسی ویژه اعضای VIP</div></div><div><span class="badge badge-vip">VIP</span> <button class="btn btn-primary" data-action="open_vip">ارتقا</button></div></div>
  </section>`;
}

function subscriptionsView(d) {
  const plans = d.plans || [];
  return `<section class="card"><h3>پلن‌های عضویت</h3><p>پلن موردنظر را انتخاب کن. پرداخت و فعال‌سازی توسط هسته NEXUS انجام می‌شود.</p>
    ${plans.map(p => `<div class="plan-row"><div><div class="plan-title">${esc(p.title)}</div><div class="subtext">${esc(p.period)}</div></div><div><div class="price">${esc(p.price)}</div><button class="btn btn-primary" data-action="buy_plan" data-plan="${esc(p.code)}">انتخاب</button></div></div>`).join('') || '<div class="empty">پلن فعالی برای نمایش وجود ندارد.</div>'}
  </section>`;
}

function productsView(d) {
  const products = d.products || [];
  return `<section class="card"><h3>محصولات NEXUS</h3><p>محصولات در صفحه مستقل نمایش داده می‌شوند و در Home قرار نمی‌گیرند.</p>
  ${products.map(p => `<div class="product-row"><div><div class="signal-title">${esc(p.title)}</div><div class="subtext">${esc(p.description)}</div></div><button class="btn btn-secondary" data-action="product" data-product="${esc(p.code)}">مشاهده</button></div>`).join('') || '<div class="empty">محصولی برای نمایش وجود ندارد.</div>'}
  </section>`;
}

function accountView(d) {
  const u = d.account?.user || {};
  const connected = !!d.account?.is_authenticated;
  return `<section class="card"><h3>حساب من</h3>
    <div class="account-row"><span>Telegram</span><span class="badge ${connected ? 'badge-free' : 'badge-off'}">${connected ? 'متصل' : 'Preview Mode'}</span></div>
    <div class="account-row"><span>نام</span><strong>${esc(u.first_name || '—')}</strong></div>
    <div class="account-row"><span>Username</span><strong>${u.username ? '@' + esc(u.username) : '—'}</strong></div>
    <div class="account-row"><span>Telegram ID</span><strong>${esc(u.id || '—')}</strong></div>
    <div class="button-row"><button class="btn btn-secondary" data-action="support">پشتیبانی</button></div>
  </section>`;
}

function render() {
  const root = document.getElementById('app');
  if (state.loading) { root.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>'; return; }
  if (state.error || !state.data) { root.innerHTML = `<section class="card"><h3>اتصال برقرار نشد</h3><p>${esc(state.error || 'خطای نامشخص')}</p><div class="button-row"><button id="retry" class="btn btn-primary">تلاش دوباره</button></div></section>`; document.getElementById('retry')?.addEventListener('click', load); return; }
  const views = {home:homeView,signals:signalsView,subscriptions:subscriptionsView,products:productsView,account:accountView};
  root.innerHTML = views[state.page](state.data);
  bindActions();
}

function bindActions() {
  document.querySelectorAll('[data-nav]').forEach(el => el.addEventListener('click', () => nav(el.dataset.nav)));
  document.querySelectorAll('[data-open]').forEach(el => el.addEventListener('click', () => openLink(el.dataset.open)));
  document.querySelectorAll('[data-action]').forEach(el => el.addEventListener('click', () => {
    const a = el.dataset.action;
    if (a === 'support') return openLink(state.data.links.support);
    if (a === 'open_vip') return sendAction('open_vip');
    if (a === 'buy_plan') return sendAction('buy_plan', { plan: el.dataset.plan });
    if (a === 'product') return sendAction('product', { product: el.dataset.product });
  }));
}

async function load() {
  state.loading = true; state.error = null; render();
  try {
    const headers = {};
    if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;
    const r = await fetch('/api/miniapp/bootstrap', { headers, cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    state.data = await r.json();
  } catch (e) { state.error = e?.message || String(e); }
  finally { state.loading = false; render(); }
}

document.querySelectorAll('.nav-item').forEach(b => b.addEventListener('click', () => nav(b.dataset.page)));
load();
