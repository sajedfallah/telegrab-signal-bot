(() => {
  const forex = {
    EURUSD: 'Euro / US Dollar',
    GBPUSD: 'British Pound / US Dollar',
    USDJPY: 'US Dollar / Japanese Yen',
    AUDUSD: 'Australian Dollar / US Dollar',
    USDCAD: 'US Dollar / Canadian Dollar',
    USDCHF: 'US Dollar / Swiss Franc',
    NZDUSD: 'New Zealand Dollar / US Dollar',
  };

  const view = document.getElementById('view');
  if (!view) return;

  let selectedFx = null;
  let selectedTimeframe = '5m';

  function setCanvasVisible(visible) {
    const canvas = document.getElementById('nexusLiveChartCanvas');
    if (canvas) canvas.style.visibility = visible ? '' : 'hidden';
  }

  function setUnavailable(symbol) {
    const title = forex[symbol];
    if (!title) return;

    selectedFx = symbol;
    setCanvasVisible(false);

    view.querySelectorAll('[data-live-symbol]').forEach(btn => btn.classList.remove('active'));
    view.querySelectorAll('[data-live-fx]').forEach(btn => btn.classList.toggle('active', btn.dataset.liveFx === symbol));

    const symbolEl = document.getElementById('liveChartSymbol');
    const nameEl = document.getElementById('liveChartMarketName');
    const priceEl = document.getElementById('liveChartPrice');
    const changeEl = document.getElementById('liveChartChange');
    const sourceEl = document.getElementById('liveChartSource');
    const statusEl = document.getElementById('liveChartStatus');
    const dot = document.getElementById('liveChartDot');
    const overlay = document.getElementById('liveChartOverlay');
    const overlayTitle = document.getElementById('liveChartOverlayTitle');
    const overlayText = document.getElementById('liveChartOverlayText');

    if (symbolEl) symbolEl.textContent = symbol;
    if (nameEl) nameEl.textContent = title;
    if (priceEl) priceEl.textContent = '—';
    if (changeEl) {
      changeEl.textContent = '24h —';
      changeEl.classList.remove('positive', 'negative');
      changeEl.classList.add('neutral');
    }
    if (sourceEl) sourceEl.textContent = 'NEXUS / MT5';
    if (statusEl) statusEl.textContent = 'UNAVAILABLE';
    if (dot) {
      dot.classList.remove('is-live', 'is-reconnecting');
      dot.classList.add('is-stale');
    }
    if (overlayTitle) overlayTitle.textContent = `${symbol} data unavailable`;
    if (overlayText) overlayText.textContent = 'برای فارکس فقط داده معتبر NEXUS / MT5 نمایش داده می‌شود. Feed کندل Broker هنوز به Live Charts متصل نشده است.';
    if (overlay) overlay.hidden = false;
  }

  function leaveFxMode() {
    if (!selectedFx) return;
    selectedFx = null;
    view.querySelectorAll('[data-live-fx]').forEach(btn => btn.classList.remove('active'));
    setCanvasVisible(true);
  }

  function injectForexSymbols() {
    const symbols = view.querySelector('.live-chart-symbols');
    if (!symbols || symbols.querySelector('[data-live-fx]')) return;

    const divider = document.createElement('span');
    divider.className = 'live-chart-market-divider';
    divider.textContent = 'FX';
    symbols.appendChild(divider);

    Object.keys(forex).forEach(symbol => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'live-chart-chip live-chart-fx-chip';
      button.dataset.liveFx = symbol;
      button.textContent = symbol;
      button.addEventListener('click', () => setUnavailable(symbol));
      symbols.appendChild(button);
    });
  }

  document.addEventListener('click', event => {
    const nativeSymbol = event.target.closest?.('[data-live-symbol]');
    if (nativeSymbol && selectedFx) {
      leaveFxMode();
      return;
    }

    const timeframe = event.target.closest?.('[data-live-timeframe]');
    if (timeframe && selectedFx) {
      event.preventDefault();
      event.stopImmediatePropagation();
      selectedTimeframe = timeframe.dataset.liveTimeframe || selectedTimeframe;
      view.querySelectorAll('[data-live-timeframe]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.liveTimeframe === selectedTimeframe);
      });
      setUnavailable(selectedFx);
    }
  }, true);

  const observer = new MutationObserver(() => {
    if (!view.querySelector('.nexus-live-charts-page')) {
      selectedFx = null;
      return;
    }
    injectForexSymbols();
  });

  observer.observe(view, { childList: true, subtree: true });
  injectForexSymbols();

  window.NexusLiveChartsForex = {
    symbols: () => Object.keys(forex),
    current: () => selectedFx,
  };
})();
