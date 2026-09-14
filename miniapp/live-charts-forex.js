(() => {
  const brokerMarkets = {
    XAUUSD: 'Gold',
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

  let selected = null;
  let selectedTimeframe = '5m';
  let chart = null;
  let series = null;
  let pollTimer = null;
  let requestGeneration = 0;

  function setBaseCanvasVisible(visible) {
    const canvas = document.getElementById('nexusLiveChartCanvas');
    if (canvas) canvas.style.visibility = visible ? '' : 'hidden';
  }

  function removeBrokerChart() {
    requestGeneration += 1;
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = null;
    try { chart?.remove?.(); } catch (_) {}
    chart = null;
    series = null;
    document.getElementById('nexusBrokerChartCanvas')?.remove();
  }

  function leaveBrokerMode() {
    if (!selected) return;
    selected = null;
    removeBrokerChart();
    view.querySelectorAll('[data-live-fx]').forEach(btn => btn.classList.remove('active'));
    setBaseCanvasVisible(true);
  }

  function ensureBrokerCanvas() {
    const panel = view.querySelector('.live-chart-panel');
    if (!panel) return null;
    let host = document.getElementById('nexusBrokerChartCanvas');
    if (!host) {
      host = document.createElement('div');
      host.id = 'nexusBrokerChartCanvas';
      host.style.position = 'absolute';
      host.style.inset = '0';
      host.style.zIndex = '2';
      host.style.width = '100%';
      host.style.height = '100%';
      panel.appendChild(host);
    }
    return host;
  }

  function createBrokerChart() {
    const host = ensureBrokerCanvas();
    if (!host || !window.LightweightCharts?.createChart) return false;
    try { chart?.remove?.(); } catch (_) {}
    chart = window.LightweightCharts.createChart(host, {
      width: Math.max(280, host.clientWidth),
      height: Math.max(390, host.clientHeight),
      layout: {
        background: { type: 'solid', color: '#080d13' },
        textColor: '#81909c',
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: 'rgba(111, 139, 158, 0.08)' },
        horzLines: { color: 'rgba(111, 139, 158, 0.08)' },
      },
      rightPriceScale: {
        borderColor: 'rgba(111, 139, 158, 0.16)',
        scaleMargins: { top: 0.12, bottom: 0.12 },
      },
      timeScale: {
        borderColor: 'rgba(111, 139, 158, 0.16)',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 7,
        barSpacing: 7,
        minBarSpacing: 3,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
      autoSize: true,
    });
    const options = {
      upColor: '#25c998', downColor: '#ef5264',
      borderUpColor: '#25c998', borderDownColor: '#ef5264',
      wickUpColor: '#25c998', wickDownColor: '#ef5264',
      priceLineVisible: true, lastValueVisible: true,
    };
    if (typeof chart.addSeries === 'function' && window.LightweightCharts.CandlestickSeries) {
      series = chart.addSeries(window.LightweightCharts.CandlestickSeries, options);
    } else if (typeof chart.addCandlestickSeries === 'function') {
      series = chart.addCandlestickSeries(options);
    }
    return !!series;
  }

  function setOverlay(title, text, visible = true) {
    const overlay = document.getElementById('liveChartOverlay');
    const titleEl = document.getElementById('liveChartOverlayTitle');
    const textEl = document.getElementById('liveChartOverlayText');
    if (titleEl) titleEl.textContent = title || '';
    if (textEl) textEl.textContent = text || '';
    if (overlay) overlay.hidden = !visible;
  }

  function setStatus(text, mode = '') {
    const status = document.getElementById('liveChartStatus');
    const dot = document.getElementById('liveChartDot');
    if (status) status.textContent = text;
    if (dot) {
      dot.classList.remove('is-live', 'is-stale', 'is-reconnecting');
      if (mode) dot.classList.add(`is-${mode}`);
    }
  }

  function setHeader(symbol, title) {
    const symbolEl = document.getElementById('liveChartSymbol');
    const nameEl = document.getElementById('liveChartMarketName');
    const sourceEl = document.getElementById('liveChartSource');
    if (symbolEl) symbolEl.textContent = symbol;
    if (nameEl) nameEl.textContent = title;
    if (sourceEl) sourceEl.textContent = 'NEXUS / MT5';
  }

  function setPrice(candles) {
    const priceEl = document.getElementById('liveChartPrice');
    const changeEl = document.getElementById('liveChartChange');
    const last = candles?.[candles.length - 1];
    const first = candles?.[Math.max(0, candles.length - 2)];
    if (priceEl) {
      const value = Number(last?.close);
      priceEl.textContent = Number.isFinite(value)
        ? value.toLocaleString('en-US', { maximumFractionDigits: 6 })
        : '—';
    }
    if (changeEl) {
      const a = Number(first?.close);
      const b = Number(last?.close);
      const pct = Number.isFinite(a) && a !== 0 && Number.isFinite(b) ? ((b - a) / a) * 100 : null;
      changeEl.classList.remove('positive', 'negative', 'neutral');
      if (pct == null) {
        changeEl.textContent = 'Last bar —';
        changeEl.classList.add('neutral');
      } else {
        const sign = pct > 0 ? '+' : '';
        changeEl.textContent = `Last bar ${sign}${pct.toFixed(3)}%`;
        changeEl.classList.add(pct > 0 ? 'positive' : pct < 0 ? 'negative' : 'neutral');
      }
    }
  }

  async function fetchCandles(symbol, timeframe, generation) {
    const url = `/miniapp/api/market-candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&limit=500`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
      let payload = {};
      try { payload = await response.json(); } catch (_) {}
      if (generation !== requestGeneration || symbol !== selected) return;
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      const candles = Array.isArray(payload.candles) ? payload.candles : [];
      if (!candles.length) throw new Error('No broker candles returned');
      if (!series && !createBrokerChart()) throw new Error('Chart engine unavailable');
      series.setData(candles.map(item => ({
        time: Number(item.time),
        open: Number(item.open), high: Number(item.high), low: Number(item.low), close: Number(item.close),
      })));
      chart?.timeScale?.().fitContent?.();
      setHeader(symbol, brokerMarkets[symbol]);
      setPrice(candles);
      setOverlay('', '', false);
      setStatus(payload.stale ? 'STALE MT5' : 'LIVE MT5', payload.stale ? 'stale' : 'live');
    } catch (error) {
      if (generation !== requestGeneration || symbol !== selected) return;
      console.error('[NEXUS][BROKER_CHARTS] feed failed', symbol, timeframe, error);
      setHeader(symbol, brokerMarkets[symbol]);
      setOverlay(
        `${symbol} broker feed unavailable`,
        'داده ساختگی نمایش داده نمی‌شود. Market Feed ادمین MT5 باید آنلاین باشد و کندل معتبر بروکر را به NEXUS ارسال کند.',
        true,
      );
      setStatus('MT5 FEED OFFLINE', 'stale');
      const priceEl = document.getElementById('liveChartPrice');
      if (priceEl) priceEl.textContent = '—';
    } finally {
      clearTimeout(timeout);
      if (generation === requestGeneration && symbol === selected) {
        pollTimer = setTimeout(() => fetchCandles(symbol, timeframe, generation), 5000);
      }
    }
  }

  function openBroker(symbol) {
    const title = brokerMarkets[symbol];
    if (!title) return;
    removeBrokerChart();
    selected = symbol;
    const generation = ++requestGeneration;
    setBaseCanvasVisible(false);
    view.querySelectorAll('[data-live-symbol]').forEach(btn => btn.classList.toggle('active', btn.dataset.liveSymbol === symbol));
    view.querySelectorAll('[data-live-fx]').forEach(btn => btn.classList.toggle('active', btn.dataset.liveFx === symbol));
    setHeader(symbol, title);
    setOverlay('در حال دریافت داده MT5...', `${symbol} · ${selectedTimeframe}`, true);
    setStatus('CONNECTING MT5', 'reconnecting');
    createBrokerChart();
    fetchCandles(symbol, selectedTimeframe, generation);
  }

  function injectForexSymbols() {
    const symbols = view.querySelector('.live-chart-symbols');
    if (!symbols || symbols.querySelector('[data-live-fx]')) return;
    const divider = document.createElement('span');
    divider.className = 'live-chart-market-divider';
    divider.textContent = 'FX';
    symbols.appendChild(divider);
    Object.keys(brokerMarkets).filter(symbol => symbol !== 'XAUUSD').forEach(symbol => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'live-chart-chip live-chart-fx-chip';
      button.dataset.liveFx = symbol;
      button.textContent = symbol;
      button.addEventListener('click', () => openBroker(symbol));
      symbols.appendChild(button);
    });
  }

  document.addEventListener('click', event => {
    const nativeSymbol = event.target.closest?.('[data-live-symbol]');
    if (nativeSymbol?.dataset.liveSymbol === 'XAUUSD') {
      event.preventDefault();
      event.stopImmediatePropagation();
      openBroker('XAUUSD');
      return;
    }
    if (nativeSymbol && selected) {
      leaveBrokerMode();
      return;
    }

    const timeframe = event.target.closest?.('[data-live-timeframe]');
    if (timeframe && selected) {
      event.preventDefault();
      event.stopImmediatePropagation();
      selectedTimeframe = timeframe.dataset.liveTimeframe || selectedTimeframe;
      view.querySelectorAll('[data-live-timeframe]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.liveTimeframe === selectedTimeframe);
      });
      openBroker(selected);
    }
  }, true);

  const observer = new MutationObserver(() => {
    if (!view.querySelector('.nexus-live-charts-page')) {
      selected = null;
      removeBrokerChart();
      return;
    }
    injectForexSymbols();
  });
  observer.observe(view, { childList: true, subtree: true });
  injectForexSymbols();

  window.NexusLiveChartsForex = {
    symbols: () => Object.keys(brokerMarkets),
    current: () => selected,
    open: openBroker,
  };
})();
