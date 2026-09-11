(() => {
  'use strict';

  const tg = window.Telegram?.WebApp;
  const API = '/miniapp/api/admin';
  let setupMode = 'MANUAL';
  let refreshTimer = null;

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));

  const headers = () => ({
    'Content-Type': 'application/json',
    ...(tg?.initData ? {'X-Telegram-Init-Data': tg.initData} : {}),
  });

  async function api(path) {
    const response = await fetch(API + path, {headers: headers(), cache: 'no-store'});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || 'admin live request failed');
    return body;
  }

  function toast(message) {
    const node = $('toast');
    if (!node) return;
    node.textContent = message;
    node.classList.add('show');
    setTimeout(() => node.classList.remove('show'), 2800);
  }

  function signed(value, digits = 2) {
    const number = Number(value);
    return Number.isFinite(number) ? `${number > 0 ? '+' : ''}${number.toFixed(digits)}` : '—';
  }

  function pulse(status) {
    const normalized = String(status || 'UNAVAILABLE').toLowerCase();
    return `<span class="admin-live-pulse ${esc(normalized)}" aria-hidden="true"><svg viewBox="0 0 64 48"><polyline class="pulse-back" points="0.157 23.954, 14 23.954, 21.843 48, 43 0, 50 24, 64 24"></polyline><polyline class="pulse-front" points="0.157 23.954, 14 23.954, 21.843 48, 43 0, 50 24, 64 24"></polyline></svg></span>`;
  }

  function liveBlock(live) {
    if (!live) return '';
    const status = String(live.status || 'UNAVAILABLE').toUpperCase();
    const pnlState = String(live.pnl_state || '').toLowerCase();
    const sync = live.age_seconds != null ? `${Math.round(Number(live.age_seconds))}s ago` : '—';
    const label = status === 'LIVE' ? 'MT5 LIVE'
      : status === 'PENDING' ? 'MT5 PENDING'
      : status === 'STALE' ? 'STALE'
      : 'LIVE DATA UNAVAILABLE';
    if (status === 'UNAVAILABLE') {
      return `<div class="admin-live unavailable"><div class="admin-live-head">${pulse(status)}<b>${label}</b><small>—</small></div></div>`;
    }
    return `<div class="admin-live ${esc(status.toLowerCase())}"><div class="admin-live-head">${pulse(status)}<b>${label}</b><small>${esc(sync)}</small></div><div class="admin-live-grid"><span>CURRENT<b>${esc(live.current_price ?? '—')}</b></span><span>FLOATING P&amp;L<b class="${esc(pnlState)}">${signed(live.floating_pnl)}</b></span><span>CURRENT R<b>${live.current_r == null ? '—' : `${signed(live.current_r)}R`}</b></span><span>VOLUME<b>${esc(live.volume ?? '—')}</b></span><span>LIVE SL<b>${esc(live.stop_loss ?? '—')}</b></span><span>LIVE TP<b>${esc(live.take_profit ?? '—')}</b></span></div></div>`;
  }

  function positionBlock(item) {
    const profit = Number(item?.profit || 0);
    const state = profit > 0 ? 'profit' : profit < 0 ? 'loss' : 'flat';
    const age = item?.last_seen_at
      ? Math.max(0, Math.round((Date.now() - new Date(item.last_seen_at).getTime()) / 1000))
      : null;
    return `<div class="admin-position-live"><span>CURRENT<b>${esc(item?.current_price ?? '—')}</b></span><span>P&amp;L<b class="${state}">${signed(profit)}</b></span><span>SL<b>${esc(item?.stop_loss ?? '—')}</b></span><span>TP<b>${esc(item?.take_profit ?? '—')}</b></span><span>VOLUME<b>${esc(item?.volume ?? '—')}</b></span><span>STATE<b>${esc(item?.status ?? '—')}</b></span><small class="admin-position-sync">Last MT5 Sync: ${age == null ? '—' : `${esc(age)}s ago`}</small></div>`;
  }

  function applySetupMode() {
    const slCard = document.querySelector('#signalForm .accent-red');
    const tpCard = document.querySelector('#signalForm .accent-green');
    const note = $('v066AutoSetupNote');
    const auto = setupMode === 'AUTO';
    if (slCard) slCard.hidden = auto;
    if (tpCard) tpCard.hidden = auto;
    if (note) note.hidden = !auto;
    document.querySelectorAll('#v066SetupMode button').forEach((button) => {
      button.classList.toggle('selected', button.dataset.mode === setupMode);
    });
  }

  function injectSetupMode() {
    const form = $('signalForm');
    if (!form || $('v066SetupModeCard')) return;
    const firstSlCard = form.querySelector('.accent-red');
    const section = document.createElement('section');
    section.id = 'v066SetupModeCard';
    section.className = 'control-card nexus-v066-setup';
    section.innerHTML = `<div class="control-heading"><div><small>SETUP MODE</small><h2>حالت محاسبه ستاپ</h2></div><span class="badge">V0.6.6</span></div><div class="mode-row"><span>روش آماده‌سازی ستاپ</span><div class="segments two" id="v066SetupMode"><button type="button" data-mode="MANUAL" class="selected">MANUAL</button><button type="button" data-mode="AUTO">AUTO SETUP</button></div></div><p id="v066AutoSetupNote" class="nexus-v066-auto-note" hidden>AUTO SETUP تا زمان اتصال Structure Engine به کندل‌های بسته‌شده MT5 به‌صورت Fail-Closed است و هیچ SL ساختگی یا حدسی منتشر نمی‌کند.</p>`;
    if (firstSlCard) form.insertBefore(section, firstSlCard);
    else form.prepend(section);

    section.querySelectorAll('button[data-mode]').forEach((button) => {
      button.addEventListener('click', () => {
        setupMode = button.dataset.mode === 'AUTO' ? 'AUTO' : 'MANUAL';
        applySetupMode();
      });
    });

    const originalSubmit = form.onsubmit;
    form.onsubmit = (event) => {
      if (setupMode === 'AUTO') {
        event.preventDefault();
        event.stopPropagation();
        toast('AUTO SETUP تا اتصال Structure Engine اجازه انتشار ندارد.');
        return false;
      }
      return typeof originalSubmit === 'function' ? originalSubmit.call(form, event) : undefined;
    };
    applySetupMode();
  }

  function decorateSignalContainer(containerId, items) {
    const container = $(containerId);
    if (!container) return;
    const cards = [...container.querySelectorAll(':scope > article.card')];
    items.forEach((item, index) => {
      const card = cards[index];
      if (!card) return;
      card.querySelector('[data-v066-live]')?.remove();
      const host = document.createElement('div');
      host.dataset.v066Live = '1';
      host.innerHTML = liveBlock(item.live);
      if (host.firstElementChild) card.appendChild(host.firstElementChild);
    });
  }

  function decoratePositions(items) {
    const container = $('positionList');
    if (!container) return;
    const cards = [...container.querySelectorAll(':scope > article.card')];
    items.forEach((item, index) => {
      const card = cards[index];
      if (!card) return;
      card.querySelector('[data-v066-position-live]')?.remove();
      const host = document.createElement('div');
      host.dataset.v066PositionLive = '1';
      host.innerHTML = positionBlock(item);
      const block = host.firstElementChild;
      if (block) {
        block.dataset.v066PositionLive = '1';
        card.appendChild(block);
      }
    });
  }

  async function refreshLive() {
    if (document.visibilityState !== 'visible') return;
    try {
      const [signals, positions] = await Promise.all([api('/signals'), api('/positions')]);
      const signalItems = Array.isArray(signals.items) ? signals.items : [];
      decorateSignalContainer('signalList', signalItems);
      decorateSignalContainer('logList', signalItems);
      const positionItems = [
        ...(Array.isArray(positions.positions) ? positions.positions : []),
        ...(Array.isArray(positions.orders) ? positions.orders : []),
      ];
      decoratePositions(positionItems);
    } catch (_) {
      // The primary Admin Desk owns user-visible API errors. This overlay is
      // read-only enhancement and must never break core execution controls.
    }
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshLive, 180);
  }

  injectSetupMode();
  ['signalList', 'logList', 'positionList'].forEach((id) => {
    const node = $(id);
    if (!node) return;
    new MutationObserver((mutations) => {
      const cardChanged = mutations.some((mutation) => [...mutation.addedNodes].some((added) =>
        added.nodeType === 1 && (added.matches?.('article.card') || added.querySelector?.('article.card'))));
      if (cardChanged) scheduleRefresh();
    }).observe(node, {childList: true});
  });
  setTimeout(refreshLive, 700);
  setInterval(refreshLive, 5000);
})();
