(() => {
  const view = document.getElementById('view');
  if (!view) return;

  let scheduled = false;

  function isHome() {
    try {
      return String(state?.route || '') === 'home';
    } catch (_) {
      return Boolean(view.querySelector('.home-v2, .home-v2-spotlight'));
    }
  }

  function ensureEntry() {
    scheduled = false;
    if (!isHome()) return;
    if (!view.querySelector('.home-v2, .home-v2-spotlight, .hero')) return;
    if (view.querySelector('[data-open-live-charts]')) return;

    const host = document.createElement('section');
    host.className = 'nexus-live-charts-entry';
    host.dataset.nexusLiveChartsHome = '1';
    host.innerHTML = `
      <button type="button" class="live-chart-entry-card" data-open-live-charts>
        <span class="live-chart-entry-copy">
          <b>Live Charts</b>
          <small>نمودار زنده بازار · Crypto · Gold · Forex</small>
        </span>
        <span class="live-chart-entry-action">باز کردن ←</span>
      </button>`;

    const anchor = view.querySelector('.home-v2-spotlight, .hero');
    if (anchor) anchor.insertAdjacentElement('afterend', host);
    else view.prepend(host);
  }

  function scheduleEnsure() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(ensureEntry);
  }

  document.addEventListener('click', event => {
    const button = event.target.closest?.('[data-open-live-charts]');
    if (!button) return;
    event.preventDefault();
    window.NexusLiveCharts?.open?.();
  }, true);

  const observer = new MutationObserver(scheduleEnsure);
  observer.observe(view, { childList: true, subtree: true });

  window.addEventListener('pageshow', scheduleEnsure);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') scheduleEnsure();
  });

  scheduleEnsure();
  window.setTimeout(scheduleEnsure, 250);
  window.setTimeout(scheduleEnsure, 1000);
})();
