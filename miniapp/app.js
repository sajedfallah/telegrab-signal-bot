const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  try { tg.setHeaderColor('#090c11'); tg.setBackgroundColor('#090c11'); } catch (_) {}
}

const API = '/miniapp/api';
const state = { bootstrap: null, route: 'home', planCategory: 'vip' };
const routes = {
  home: 'homeTpl', signals: 'signalsTpl', subscriptions: 'subscriptionsTpl',
  account: 'accountTpl', guide: 'guideTpl', support: 'supportTpl',
};
const view = document.getElementById('view');

function authHeaders(extra = {}) {
  const initData = tg?.initData || '';
  return { ...extra, ...(initData ? { 'X-Telegram-Init-Data': initData } : {}) };
}

async function api(path, options = {}) {
  const headers = authHeaders(options.body ? { 'Content-Type': 'application/json' } : {});
  const res = await fetch(`${API}${path}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

async function bootstrap() {
  if (!tg?.initData) {
    toast('برای دریافت اطلاعات حساب، Mini App را از داخل Telegram باز کنید.');
    return;
  }
  try {
    state.bootstrap = await api('/bootstrap');
    hydrateCurrentView();
  } catch (err) {
    console.error(err);
    toast(`اتصال به حساب NEXUS ناموفق بود: ${err.message}`);
  }
}

function render(route = 'home') {
  state.route = routes[route] ? route : 'home';
  const tpl = document.getElementById(routes[state.route]);
  view.replaceChildren(tpl.content.cloneNode(true));
  document.querySelectorAll('.nav-item').forEach(btn => btn.classList.toggle('active', btn.dataset.route === state.route));
  bindActions();
  hydrateCurrentView();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function bindActions() {
  view.querySelectorAll('[data-go]').forEach(el => el.addEventListener('click', () => render(el.dataset.go)));
  view.querySelectorAll('[data-action]').forEach(el => el.addEventListener('click', () => handleAction(el.dataset.action, el)));
}

function hydrateCurrentView() {
  hydrateTelegramUser();
  if (!state.bootstrap) return;
  if (state.route === 'signals') hydrateSignals();
  if (state.route === 'subscriptions') hydrateSubscriptions();
  if (state.route === 'account') hydrateAccount();
  if (state.route === 'guide') hydrateGuide();
}

function hydrateTelegramUser() {
  const user = state.bootstrap?.user || tg?.initDataUnsafe?.user;
  if (!user) return;
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ');
  const nameEl = document.getElementById('userName');
  const handleEl = document.getElementById('userHandle');
  if (nameEl && name) nameEl.textContent = name;
  if (handleEl) handleEl.textContent = user.username ? `@${user.username}` : `Telegram ID: ${user.id}`;
}

function hydrateSignals() {
  const ent = state.bootstrap.entitlements || {};
  const cards = view.querySelectorAll('.signal-card');
  const vipButton = cards[1]?.querySelector('button');
  if (!vipButton) return;
  if (ent.vip) {
    vipButton.textContent = 'ورود به کانال VIP';
    vipButton.dataset.action = 'vip-signals';
    delete vipButton.dataset.go;
    vipButton.onclick = () => handleAction('vip-signals', vipButton);
    cards[1].querySelector('.lock').textContent = '✓';
  } else {
    vipButton.textContent = 'فعال‌سازی VIP';
  }
}

function hydrateSubscriptions() {
  const tabs = [...view.querySelectorAll('.tab')];
  const categories = ['vip', 'autotrade', 'bundle'];
  tabs.forEach((tab, i) => {
    tab.classList.toggle('active', categories[i] === state.planCategory);
    tab.onclick = () => {
      state.planCategory = categories[i];
      tabs.forEach((x, j) => x.classList.toggle('active', j === i));
      renderPlanCards();
    };
  });
  renderPlanCards();
}

function renderPlanCards() {
  const host = view.querySelector('.pricing-card');
  if (!host || !state.bootstrap) return;
  const plans = (state.bootstrap.plans || []).filter(p => p.category === state.planCategory);
  host.classList.remove('featured');
  host.innerHTML = plans.length ? plans.map(plan => `
    <article class="plan-row">
      <div>
        <div class="pricing-kicker">${escapeHtml(plan.code)}</div>
        <h3>${escapeHtml(plan.title_fa)}</h3>
        <small>${plan.days} روز</small>
      </div>
      <div class="plan-price"><b>${escapeHtml(plan.price_usdt)}</b><span>USDT</span></div>
      <button class="btn primary" data-plan="${escapeHtml(plan.code)}">خرید</button>
    </article>`).join('') : '<div class="empty-state">پلن فعالی در این بخش وجود ندارد.</div>';
  host.querySelectorAll('[data-plan]').forEach(btn => btn.addEventListener('click', () => openPurchase(btn.dataset.plan)));
}

function hydrateAccount() {
  const ent = state.bootstrap.entitlements || {};
  const auto = state.bootstrap.autotrade || {};
  const cards = [...view.querySelectorAll('.menu-card')];
  const actions = ['account-vip', 'account-autotrade', 'account-payments', 'account-referral'];
  cards.forEach((card, i) => {
    card.dataset.action = actions[i];
    card.onclick = () => handleAction(actions[i], card);
  });
  if (cards[0]) cards[0].querySelector('small').textContent = ent.vip ? `فعال تا ${shortDate(ent.vip_expires_at)}` : 'غیرفعال';
  if (cards[1]) cards[1].querySelector('small').textContent = auto.entitled ? (auto.mt5 ? `MT5 ${auto.mt5.account_number}` : 'اشتراک فعال / MT5 متصل نیست') : 'غیرفعال';
  const badge = view.querySelector('.profile-card .badge');
  if (badge) badge.textContent = state.bootstrap.user?.level?.en || 'MEMBER';
}

function hydrateGuide() {
  const cards = [...view.querySelectorAll('.list-card')];
  if (cards[0]) cards[0].onclick = () => handleAction('guide-intro');
  if (cards[1]) cards[1].onclick = () => handleAction('guide-mt5');
}

async function handleAction(action) {
  const links = state.bootstrap?.links || {};
  const actions = {
    'public-channel': () => openTelegramLink(links.public_channel),
    'free-signals': () => openTelegramLink(links.free_signals),
    support: () => openTelegramLink(links.support),
    'vip-signals': () => openVip(),
    'load-plans': () => render('subscriptions'),
    'account-vip': () => showVipStatus(),
    'account-autotrade': () => showAutotrade(),
    'account-payments': () => showPayments(),
    'account-referral': () => showReferral(),
    'guide-intro': () => openExternal(links.guide_intro),
    'guide-mt5': () => openExternal(links.guide_mt5),
  };
  return (actions[action] || (() => toast('این بخش هنوز فعال نشده است.')))();
}

async function openVip() {
  try {
    const data = await api('/vip/access-link', { method: 'POST' });
    openTelegramLink(data.url);
  } catch (err) { toast(err.message); }
}

function showVipStatus() {
  const e = state.bootstrap?.entitlements || {};
  showModal('وضعیت VIP', e.vip
    ? `<div class="status-panel success">دسترسی VIP فعال است.</div><div class="kv"><span>انقضا</span><b>${escapeHtml(formatDate(e.vip_expires_at))}</b></div><button class="btn primary full" id="modalVipBtn">ورود به VIP</button>`
    : `<div class="status-panel">اشتراک VIP فعال نیست.</div><button class="btn primary full" id="modalBuyBtn">مشاهده پلن‌ها</button>`);
  setTimeout(() => {
    document.getElementById('modalVipBtn')?.addEventListener('click', openVip);
    document.getElementById('modalBuyBtn')?.addEventListener('click', () => { closeModal(); render('subscriptions'); });
  });
}

function showAutotrade() {
  const a = state.bootstrap?.autotrade || {};
  const mt5 = a.mt5;
  const positions = a.open_positions || [];
  const history = a.history || [];
  const posHtml = positions.length ? positions.map(p => `<div class="trade-row"><b>${escapeHtml(p.symbol)}</b><span>${escapeHtml(p.direction || '')}</span><em>${Number(p.profit || 0).toFixed(2)}$</em></div>`).join('') : '<div class="empty-state">معامله باز NEXUS وجود ندارد.</div>';
  const histHtml = history.slice(0, 5).map(h => `<div class="trade-row"><b>${escapeHtml(h.symbol || '-')}</b><span>${escapeHtml(h.event_type || h.status || '')}</span><em>${Number(h.profit || 0).toFixed(2)}$</em></div>`).join('');
  showModal('AutoTrade', `
    <div class="status-panel ${a.entitled ? 'success' : ''}">${a.entitled ? 'اشتراک AutoTrade فعال' : 'AutoTrade غیرفعال'}</div>
    <div class="kv"><span>MT5</span><b>${mt5 ? escapeHtml(mt5.account_number) : 'متصل نیست'}</b></div>
    ${mt5 ? `<div class="kv"><span>Broker</span><b>${escapeHtml(mt5.broker || '-')}</b></div><div class="kv"><span>آخرین اتصال</span><b>${escapeHtml(formatDate(mt5.last_seen_at))}</b></div>` : ''}
    ${a.license_key ? `<label class="field-label">License</label><div class="copy-box"><code>${escapeHtml(a.license_key)}</code><button id="copyLicense">کپی</button></div>` : ''}
    <h4>معاملات باز</h4>${posHtml}
    ${histHtml ? `<h4>آخرین رویدادها</h4>${histHtml}` : ''}`);
  setTimeout(() => document.getElementById('copyLicense')?.addEventListener('click', () => copyText(a.license_key)), 0);
}

async function showPayments() {
  try {
    const data = await api('/payments');
    const rows = data.payments || [];
    showModal('پرداخت‌های من', rows.length ? rows.map(p => `
      <div class="payment-row"><div><b>${escapeHtml(p.plan_code || '-')}</b><small>${escapeHtml(shortDate(p.created_at))}</small></div><span class="status-pill ${escapeHtml(p.status)}">${escapeHtml(p.status)}</span></div>`).join('') : '<div class="empty-state">هنوز پرداختی ثبت نشده است.</div>');
  } catch (err) { toast(err.message); }
}

function showReferral() {
  const r = state.bootstrap?.referral || {};
  showModal('دعوت دوستان', `
    <div class="stats-grid"><div><b>${r.invited || 0}</b><span>دعوت</span></div><div><b>${r.successful || 0}</b><span>موفق</span></div><div><b>${r.points || 0}</b><span>امتیاز</span></div></div>
    <label class="field-label">کد دعوت</label><div class="copy-box"><code>${escapeHtml(r.code || '-')}</code><button id="copyRef">کپی</button></div>
    ${r.url ? `<button class="btn primary full" id="shareRef">اشتراک لینک دعوت</button>` : ''}`);
  setTimeout(() => {
    document.getElementById('copyRef')?.addEventListener('click', () => copyText(r.code || ''));
    document.getElementById('shareRef')?.addEventListener('click', () => {
      const url = `https://t.me/share/url?url=${encodeURIComponent(r.url)}&text=${encodeURIComponent('NEXUS')}`;
      openTelegramLink(url);
    });
  });
}

function openPurchase(code) {
  const plan = (state.bootstrap?.plans || []).find(p => p.code === code);
  if (!plan) return toast('پلن پیدا نشد.');
  showModal('خرید اشتراک', `
    <div class="purchase-head"><b>${escapeHtml(plan.title_fa)}</b><span>${escapeHtml(plan.price_usdt)} USDT</span></div>
    <p class="modal-muted">روش پرداخت را انتخاب کنید. مبلغ نهایی از backend محاسبه می‌شود.</p>
    <div class="method-grid"><button class="btn ghost" id="payRial">پرداخت ریالی</button><button class="btn primary" id="payUsdt">پرداخت USDT</button></div>`);
  setTimeout(() => {
    document.getElementById('payRial')?.addEventListener('click', () => createInvoice(code, 'rial'));
    document.getElementById('payUsdt')?.addEventListener('click', () => createInvoice(code, 'usdt'));
  });
}

async function createInvoice(planCode, method) {
  try {
    setModalBusy(true);
    const invoice = await api('/invoices', { method: 'POST', body: JSON.stringify({ plan_code: planCode, payment_method: method }) });
    renderInvoice(invoice);
  } catch (err) { toast(err.message); }
  finally { setModalBusy(false); }
}

function renderInvoice(inv) {
  const payment = inv.payment || {};
  const instruction = inv.payment_method === 'usdt'
    ? `<div class="kv"><span>مبلغ</span><b>${escapeHtml(inv.total_usdt)} USDT</b></div><div class="kv"><span>شبکه</span><b>${escapeHtml(payment.network || '-')}</b></div><label class="field-label">Wallet</label><div class="copy-box"><code>${escapeHtml(payment.wallet || '-')}</code><button id="copyPay">کپی</button></div>`
    : `<div class="kv"><span>مبلغ ریالی</span><b>${Number(inv.final_amount_rial || 0).toLocaleString('fa-IR')} ریال</b></div><div class="kv"><span>صاحب حساب</span><b>${escapeHtml(payment.owner || '-')}</b></div><label class="field-label">شماره کارت</label><div class="copy-box"><code>${escapeHtml(payment.card || '-')}</code><button id="copyPay">کپی</button></div>`;
  showModal('فاکتور پرداخت', `${instruction}
    <div class="kv"><span>اعتبار فاکتور</span><b>${escapeHtml(formatDate(inv.expires_at))}</b></div>
    ${inv.payment_method === 'usdt' ? '<input class="text-input" id="txHash" placeholder="TXID / Transaction Hash (اختیاری)" />' : ''}
    <label class="upload-box">تصویر رسید را انتخاب کنید<input type="file" id="receiptFile" accept="image/jpeg,image/png,image/webp" hidden /></label>
    <div id="receiptName" class="modal-muted">فایلی انتخاب نشده است.</div>
    <button class="btn primary full" id="submitReceipt">ارسال رسید برای تأیید</button>`);
  setTimeout(() => {
    document.getElementById('copyPay')?.addEventListener('click', () => copyText(inv.payment_method === 'usdt' ? payment.wallet : payment.card));
    const file = document.getElementById('receiptFile');
    file?.addEventListener('change', () => { document.getElementById('receiptName').textContent = file.files?.[0]?.name || 'فایلی انتخاب نشده است.'; });
    document.getElementById('submitReceipt')?.addEventListener('click', () => submitReceipt(inv.invoice_id));
  });
}

async function submitReceipt(invoiceId) {
  const input = document.getElementById('receiptFile');
  const file = input?.files?.[0];
  if (!file) return toast('ابتدا تصویر رسید را انتخاب کنید.');
  if (file.size > 5_000_000) return toast('حجم رسید باید کمتر از 5MB باشد.');
  try {
    setModalBusy(true);
    const dataUrl = await readFile(file);
    const tx = document.getElementById('txHash')?.value?.trim() || null;
    const result = await api('/receipts', { method: 'POST', body: JSON.stringify({ invoice_id: invoiceId, image_data_url: dataUrl, transaction_hash: tx }) });
    showModal('رسید ثبت شد', `<div class="status-panel success">رسید با شماره پرداخت ${result.payment_id} ثبت شد و در انتظار تأیید ادمین است.</div><button class="btn primary full" id="doneReceipt">باشه</button>`);
    setTimeout(() => document.getElementById('doneReceipt')?.addEventListener('click', closeModal));
    await bootstrap();
  } catch (err) { toast(err.message); }
  finally { setModalBusy(false); }
}

function ensureModal() {
  if (document.getElementById('modalRoot')) return;
  const root = document.createElement('div');
  root.id = 'modalRoot'; root.className = 'modal-root'; root.hidden = true;
  root.innerHTML = '<div class="modal-backdrop" data-close></div><section class="modal-sheet"><div class="modal-head"><h3 id="modalTitle">NEXUS</h3><button id="modalClose">×</button></div><div id="modalBody"></div></section>';
  document.body.appendChild(root);
  root.querySelector('[data-close]').onclick = closeModal;
  root.querySelector('#modalClose').onclick = closeModal;
}
function showModal(title, html) { ensureModal(); const root = document.getElementById('modalRoot'); document.getElementById('modalTitle').textContent = title; document.getElementById('modalBody').innerHTML = html; root.hidden = false; document.body.classList.add('modal-open'); }
function closeModal() { const root = document.getElementById('modalRoot'); if (root) root.hidden = true; document.body.classList.remove('modal-open'); }
function setModalBusy(busy) { document.querySelector('.modal-sheet')?.classList.toggle('busy', !!busy); }

function openTelegramLink(url) { if (!url) return toast('لینک این بخش تنظیم نشده است.'); if (tg?.openTelegramLink) tg.openTelegramLink(url); else window.open(url, '_blank', 'noopener'); }
function openExternal(url) { if (!url) return toast('لینک راهنما هنوز ثبت نشده است.'); if (tg?.openLink) tg.openLink(url); else window.open(url, '_blank', 'noopener'); }
function readFile(file) { return new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(r.result); r.onerror = reject; r.readAsDataURL(file); }); }
function copyText(text) { if (!text) return; navigator.clipboard?.writeText(text).then(() => toast('کپی شد.')).catch(() => toast(text)); }
function shortDate(v) { if (!v) return '-'; try { return new Date(v).toLocaleDateString('fa-IR'); } catch (_) { return v; } }
function formatDate(v) { if (!v) return '-'; try { return new Date(v).toLocaleString('fa-IR'); } catch (_) { return v; } }
function escapeHtml(v) { return String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
function toast(message) { if (tg?.showPopup) tg.showPopup({ title: 'NEXUS', message: String(message), buttons: [{ type: 'ok' }] }); else alert(message); }

ensureModal();
document.querySelectorAll('.nav-item').forEach(btn => btn.addEventListener('click', () => render(btn.dataset.route)));
document.getElementById('langBtn').addEventListener('click', () => toast('رابط فارسی فعال است. لایه کامل انگلیسی در نسخه بعدی UI اضافه می‌شود.'));
render('home');
bootstrap();
