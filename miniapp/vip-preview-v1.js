(() => {
  'use strict';

  let loading = false;
  let generation = 0;

  function h(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  }

  function statusLabel(value) {
    const key = String(value || '').toUpperCase();
    if (key === 'CLOSED') return 'بسته‌شده';
    if (key === 'WAITING') return 'در انتظار';
    return 'فعال';
  }

  function card(data) {
    const summary = data.summary || {};
    const items = Array.isArray(data.items) ? data.items : [];
    return `<section class="home-v2-section home-vip-preview" data-vip-preview>
      <div class="section-head"><div><span class="eyebrow">VIP LIVE PREVIEW</span><h2>امروز در NEXUS VIP</h2></div><span class="badge vip-badge">LOCKED</span></div>
      <div class="home-vip-summary">
        <div><b>${h(summary.total || 0)}</b><span>Signals</span></div>
        <div><b>${h(summary.closed || 0)}</b><span>Closed</span></div>
        <div><b>${h(summary.active || 0)}</b><span>Active</span></div>
        <div><b>${h(summary.waiting || 0)}</b><span>Waiting</span></div>
      </div>
      ${items.length ? `<div class="home-vip-locked-list">${items.map(item => `<div><span>🔒</span><b>${h(item.symbol || '—')}</b><em class="${h(String(item.status || '').toLowerCase())}">${h(statusLabel(item.status))}</em></div>`).join('')}</div>` : ''}
      <p class="home-vip-note">برای کاربران غیرVIP فقط نماد و وضعیت کلی نمایش داده می‌شود؛ Entry، SL، TP و جزئیات Premium از Backend ارسال نمی‌شوند.</p>
      <button class="btn primary full" type="button" data-vip-preview-cta>${h(data.cta?.label || 'Unlock NEXUS VIP')}</button>
    </section>`;
  }

  function mount(data) {
    if (data?.has_vip || Number(data?.summary?.total || 0) <= 0) return;
    const host = document.querySelector('.home-v2');
    if (!host || host.querySelector('[data-vip-preview]')) return;
    const wrapper = document.createElement('div');
    wrapper.innerHTML = card(data);
    const node = wrapper.firstElementChild;
    const performance = host.querySelector('.home-v2-performance');
    if (performance) host.insertBefore(node, performance);
    else host.appendChild(node);
    node.querySelector('[data-vip-preview-cta]')?.addEventListener('click', () => {
      window.NexusProduct?.track?.('vip_preview_cta', { source: 'home' });
      if (typeof render === 'function') render('subscriptions');
    });
  }

  async function hydrate() {
    if (loading || typeof state === 'undefined' || state.route !== 'home') return;
    const host = document.querySelector('.home-v2');
    if (!host || host.querySelector('[data-vip-preview]')) return;
    if (typeof api !== 'function') return;
    loading = true;
    const request = ++generation;
    try {
      const data = await api('/vip-preview');
      if (request !== generation || typeof state === 'undefined' || state.route !== 'home') return;
      mount(data);
    } catch (error) {
      console.warn('NEXUS VIP preview unavailable', error);
    } finally {
      loading = false;
    }
  }

  const view = document.getElementById('view');
  if (view) {
    new MutationObserver(() => {
      if (typeof state !== 'undefined' && state.route === 'home' && document.querySelector('.home-v2')) {
        queueMicrotask(hydrate);
      }
    }).observe(view, { childList: true, subtree: true });
  }

  window.NexusVipPreview = { hydrate };
  hydrate();
})();
