(() => {
  const icon = (name, className = 'nexus-inline-icon') => window.NexusIcons?.svg?.(name, className) || '';
  const escape = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const BIDI_CONTROL_RE = /[\u200E\u200F\u202A-\u202E\u2066-\u2069]/g;
  let notificationCache = null;

  function normalizeBidi(value) {
    return String(value ?? '')
      .replace(BIDI_CONTROL_RE, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function humanDate(value, withTime = false) {
    if (!value) return '—';
    try {
      const date = new Date(value);
      const datePart = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
        year: 'numeric', month: 'long', day: 'numeric'
      }).format(date);
      if (!withTime) return datePart;
      const timePart = new Intl.DateTimeFormat('fa-IR', { hour: '2-digit', minute: '2-digit' }).format(date);
      return `${datePart} · ${timePart}`;
    } catch (_) {
      return normalizeBidi(value);
    }
  }

  function track(eventName, metadata = {}) {
    if (!window.Telegram?.WebApp?.initData || typeof api !== 'function') return;
    const route = typeof state !== 'undefined' ? state.route : null;
    Promise.resolve(api('/events', {
      method: 'POST',
      body: JSON.stringify({ event_name: eventName, route, metadata })
    })).catch(() => {});
  }

  function destinationGo(destination) {
    if (!destination) return;
    if (destination === 'trades') return window.NexusTrades?.open?.();
    if (destination === 'performance') return window.NexusTrackRecord?.open?.();
    if (typeof render === 'function') return render(destination);
  }

  function updateNotificationBadge(count) {
    const badge = document.getElementById('notificationBadge');
    if (!badge) return;
    const n = Math.max(0, Number(count || 0));
    badge.textContent = n > 99 ? '99+' : String(n);
    badge.hidden = n < 1;
  }

  function notificationItem(item) {
    const unread = !item.is_read;
    return `<button class="notification-row ${unread ? 'unread' : ''}" data-notification-source="${escape(item.source)}" data-notification-id="${escape(item.id)}" data-notification-destination="${escape(item.destination || '')}">
      <span class="notification-icon">${icon(item.source === 'autotrade' ? 'trades' : 'bell')}</span>
      <span class="notification-copy"><b>${escape(item.title_fa || 'اعلان NEXUS')}</b>${item.body_fa ? `<small>${escape(item.body_fa)}</small>` : ''}<time>${escape(humanDate(item.created_at, true))}</time></span>
      ${unread ? '<i class="notification-unread" aria-label="خوانده نشده"></i>' : ''}
    </button>`;
  }

  async function fetchNotifications(force = false) {
    if (!force && notificationCache) return notificationCache;
    const data = await api('/notifications?limit=40');
    notificationCache = data;
    updateNotificationBadge(data.unread_count || 0);
    return data;
  }

  async function openNotifications() {
    track('notification_open', { action: 'open_center' });
    showModal('اعلان‌های NEXUS', `<div class="notification-loading">${skeleton('list', 4)}</div>`);
    try {
      const data = await fetchNotifications(true);
      const body = document.getElementById('modalBody');
      if (!body) return;
      body.innerHTML = data.items?.length
        ? `<div class="notification-list">${data.items.map(notificationItem).join('')}</div>`
        : `<div class="empty-state nexus-empty-state">${icon('bell')}<b>اعلان جدیدی وجود ندارد</b><span>رویدادهای مهم NEXUS و AutoTrade اینجا نمایش داده می‌شوند.</span></div>`;
      body.querySelectorAll('[data-notification-id]').forEach(row => row.addEventListener('click', async () => {
        const source = row.dataset.notificationSource;
        const id = row.dataset.notificationId;
        const destination = row.dataset.notificationDestination;
        row.classList.remove('unread');
        row.querySelector('.notification-unread')?.remove();
        try {
          await api(`/notifications/${encodeURIComponent(source)}/${encodeURIComponent(id)}/read`, { method: 'POST' });
          notificationCache = null;
          fetchNotifications(true).catch(() => {});
        } catch (_) {}
        if (destination) {
          closeModal();
          destinationGo(destination);
        }
      }));
    } catch (_) {
      const body = document.getElementById('modalBody');
      if (body) body.innerHTML = '<div class="empty-state">دریافت اعلان‌ها ناموفق بود.<br><button class="btn ghost" id="retryNotifications">تلاش مجدد</button></div>';
      document.getElementById('retryNotifications')?.addEventListener('click', openNotifications);
    }
  }

  function skeleton(kind = 'card', count = 3) {
    return `<div class="nexus-skeleton nexus-skeleton-${escape(kind)}">${Array.from({length: Math.max(1, count)}, () => '<div class="skeleton-block"><i></i><span></span><span></span></div>').join('')}</div>`;
  }

  function fixBidiSurfaces(root = document) {
    root.querySelectorAll?.('.payment-owner,.account-owner-name,.bidi-safe,[data-bidi-safe]').forEach(node => {
      const clean = normalizeBidi(node.textContent);
      if (node.textContent !== clean) node.textContent = clean;
      node.setAttribute('dir', 'rtl');
    });
    root.querySelectorAll?.('.kv').forEach(row => {
      const label = normalizeBidi(row.querySelector('span')?.textContent);
      if (label !== 'صاحب حساب') return;
      const owner = row.querySelector('b');
      if (!owner) return;
      owner.classList.add('payment-owner', 'bidi-safe');
      owner.setAttribute('dir', 'rtl');
      owner.textContent = normalizeBidi(owner.textContent);
    });
  }

  function bindGlobalMicroInteractions() {
    document.addEventListener('click', event => {
      const copyButton = event.target.closest?.('#copyPay,#copyLicense,#copyRef,[data-copy]');
      if (copyButton) {
        const original = copyButton.textContent;
        window.setTimeout(() => {
          copyButton.classList.add('copied');
          copyButton.innerHTML = `${icon('check')}<span>کپی شد</span>`;
          window.setTimeout(() => {
            copyButton.classList.remove('copied');
            copyButton.textContent = original || 'کپی';
          }, 1400);
        }, 80);
      }
    }, true);
  }

  function boot() {
    document.getElementById('notificationsBtn')?.addEventListener('click', openNotifications);
    bindGlobalMicroInteractions();
    fixBidiSurfaces(document);
    new MutationObserver(records => {
      records.forEach(record => record.addedNodes.forEach(node => {
        if (node.nodeType === 1) fixBidiSurfaces(node);
      }));
    }).observe(document.body, { childList: true, subtree: true });

    if (window.Telegram?.WebApp?.initData) {
      track('miniapp_open', { version: 'polish-v3' });
      fetchNotifications(true).catch(() => {});
    }
  }

  window.NexusProduct = {
    normalizeBidi,
    humanDate,
    track,
    skeleton,
    openNotifications,
    fixBidiSurfaces,
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
