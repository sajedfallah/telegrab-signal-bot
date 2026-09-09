const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  try { tg.setHeaderColor('#090c11'); tg.setBackgroundColor('#090c11'); } catch (_) {}
}

const routes = {
  home: 'homeTpl',
  signals: 'signalsTpl',
  subscriptions: 'subscriptionsTpl',
  account: 'accountTpl',
  guide: 'guideTpl',
  support: 'supportTpl',
};

const view = document.getElementById('view');

function render(route = 'home') {
  const templateId = routes[route] || routes.home;
  const tpl = document.getElementById(templateId);
  view.replaceChildren(tpl.content.cloneNode(true));
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.route === route);
  });
  bindActions();
  hydrateTelegramUser();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function bindActions() {
  view.querySelectorAll('[data-go]').forEach(el => {
    el.addEventListener('click', () => render(el.dataset.go));
  });
  view.querySelectorAll('[data-action]').forEach(el => {
    el.addEventListener('click', () => handleAction(el.dataset.action));
  });
}

function handleAction(action) {
  const actions = {
    'public-channel': () => openTelegramLink(window.NEXUS_CONFIG?.publicChannelUrl),
    'free-signals': () => openTelegramLink(window.NEXUS_CONFIG?.freeSignalUrl),
    support: () => openTelegramLink(window.NEXUS_CONFIG?.supportUrl),
    'load-plans': () => loadPlans(),
  };
  (actions[action] || (() => toast('این بخش در اتصال به API فعال می‌شود.')))();
}

function openTelegramLink(url) {
  if (!url) return toast('لینک این بخش هنوز در تنظیمات Mini App ثبت نشده است.');
  if (tg?.openTelegramLink) tg.openTelegramLink(url);
  else window.open(url, '_blank', 'noopener');
}

async function loadPlans() {
  const endpoint = window.NEXUS_CONFIG?.plansEndpoint;
  if (!endpoint) return toast('Endpoint پلن‌ها هنوز متصل نشده است.');
  try {
    const res = await fetch(endpoint, { headers: telegramAuthHeaders() });
    if (!res.ok) throw new Error('bad response');
    const data = await res.json();
    console.log('NEXUS plans', data);
    toast('پلن‌ها دریافت شدند. مرحله بعد: اتصال کارت‌های قیمت به API.');
  } catch (_) {
    toast('دریافت پلن‌ها ناموفق بود.');
  }
}

function telegramAuthHeaders() {
  const initData = tg?.initData || '';
  return initData ? { 'X-Telegram-Init-Data': initData } : {};
}

function hydrateTelegramUser() {
  const user = tg?.initDataUnsafe?.user;
  if (!user) return;
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ');
  const nameEl = document.getElementById('userName');
  const handleEl = document.getElementById('userHandle');
  if (nameEl && name) nameEl.textContent = name;
  if (handleEl) handleEl.textContent = user.username ? `@${user.username}` : `Telegram ID: ${user.id}`;
}

function toast(message) {
  if (tg?.showPopup) {
    tg.showPopup({ title: 'NEXUS', message, buttons: [{ type: 'ok' }] });
  } else {
    alert(message);
  }
}

document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => render(btn.dataset.route));
});

document.getElementById('langBtn').addEventListener('click', () => {
  toast('نسخه انگلیسی در لایه Localization متصل می‌شود.');
});

window.NEXUS_CONFIG = window.NEXUS_CONFIG || {
  publicChannelUrl: '',
  freeSignalUrl: '',
  supportUrl: '',
  plansEndpoint: '',
};

render('home');
