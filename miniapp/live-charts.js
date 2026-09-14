(() => {
  const CHART_ROUTE = 'charts';
  const STALE_AFTER_MS = 15000;
  const MAX_BACKOFF_MS = 30000;

  const instruments = {
    BTCUSDT: { label: 'BTC', title: 'Bitcoin', source: 'BINANCE · DEV ADAPTER', provider: 'binance' },
    ETHUSDT: { label: 'ETH', title: 'Ethereum', source: 'BINANCE · DEV ADAPTER', provider: 'binance' },
    SOLUSDT: { label: 'SOL', title: 'Solana', source: 'BINANCE · DEV ADAPTER', provider: 'binance' },
    XAUUSD: { label: 'XAU', title: 'Gold', source: 'NEXUS / MT5', provider: 'nexus' },
  };

  const timeframes = {
    '1m': '1m',
    '5m': '5m',
    '15m': '15m',
    '1h': '1h',
    '1D': '1d',
  };

  const runtime = {
    symbol: 'BTCUSDT',
    timeframe: '5m',
    chart: null,
    series: null,
    socket: null,
    reconnectTimer: null,
    staleTimer: null,
    resizeObserver: null,
    streamGeneration: 0,
    reconnectAttempt: 0,
    lastLiveAt: 0,
    lastCandleTime: 0,
    destroyed: true,
  };

  const viewEl = document.getElementById('view');
  if (!viewEl) return;

  const originalRender = typeof window.render === 'function' ? window.render : null;

  function safeText(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  function formatPrice(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) return '—';
    if (number >= 1000) return number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (number >= 1) return number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    return number.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 8 });
  }

  function chartMarkup() {
    const symbol = instruments[runtime.symbol];
    return `
      <section class="nexus-live-charts-page" aria-label="NEXUS Live Charts">
        <div class="live-chart-page-head">
          <div>
            <span class="eyebrow">LIVE MARKET</span>
            <h1>Live Charts</h1>
            <p>نمودار زنده بازار برای Crypto، Gold و Forex</p>
          </div>
          <span class="live-chart-page-badge">BETA</span>
        </div>
        <div class="live-chart-shell">
          <header class="live-chart-header">
            <div class="live-chart-symbol-wrap">
              <div class="live-chart-symbol">
                <span class="live-chart-live-dot" id="liveChartDot" aria-hidden="true"></span>
                <h1 id="liveChartSymbol">${safeText(runtime.symbol)}</h1>
              </div>
              <span class="live-chart-market-name" id="liveChartMarketName">${safeText(symbol.title)}</span>
            </div>
            <div class="live-chart-price-wrap">
              <b class="live-chart-price" id="liveChartPrice">—</b>
              <span class="live-chart-change neutral" id="liveChartChange">24h —</span>
            </div>
          </header>

          <div class="live-chart-controls">
            <div class="live-chart-symbols" aria-label="Symbols">
              ${Object.entries(instruments).map(([code, item]) => `
                <button type="button" class="live-chart-chip ${code === runtime.symbol ? 'active' : ''}" data-live-symbol="${code}">${safeText(item.label)}</button>
              `).join('')}
            </div>
            <div class="live-chart-timeframes" aria-label="Timeframes">
              ${Object.keys(timeframes).map(tf => `
                <button type="button" class="live-chart-chip ${tf === runtime.timeframe ? 'active' : ''}" data-live-timeframe="${tf}">${safeText(tf)}</button>
              `).join('')}
            </div>
          </div>

          <div class="live-chart-panel">
            <div id="nexusLiveChartCanvas" role="img" aria-label="Candlestick chart"></div>
            <div class="live-chart-overlay" id="liveChartOverlay">
              <div class="live-chart-overlay-card">
                <strong id="liveChartOverlayTitle">در حال دریافت داده...</strong>
                <span id="liveChartOverlayText">کندل‌های تاریخی در حال بارگذاری هستند.</span>
              </div>
            </div>
          </div>

          <div class="live-chart-statusbar">
            <span>Source: <b id="liveChartSource">${safeText(symbol.source)}</b></span>
            <span id="liveChartStatus">CONNECTING</span>
          </div>
          <a class="live-chart-tv-attribution" href="https://www.tradingview.com/" target="_blank" rel="noopener">Charts by TradingView</a>
        </div>
      </section>`;
  }

  function setOverlay(title, text, visible = true) {
    const overlay = document.getElementById('liveChartOverlay');
    const titleEl = document.getElementById('liveChartOverlayTitle');
    const textEl = document.getElementById('liveChartOverlayText');
    if (!overlay) return;
    if (titleEl) titleEl.textContent = title || '';
    if (textEl) textEl.textContent = text || '';
    overlay.hidden = !visible;
  }

  function setStatus(status, mode = '') {
    const statusEl = document.getElementById('liveChartStatus');
    const dot = document.getElementById('liveChartDot');
    if (statusEl) statusEl.textContent = status;
    if (dot) {
      dot.classList.remove('is-live', 'is-stale', 'is-reconnecting');
      if (mode) dot.classList.add(`is-${mode}`);
    }
  }

  function setHeaderPrice(price, pct = null) {
    const priceEl = document.getElementById('liveChartPrice');
    const changeEl = document.getElementById('liveChartChange');
    if (priceEl) priceEl.textContent = formatPrice(price);
    if (!changeEl) return;

    const value = Number(pct);
    changeEl.classList.remove('positive', 'negative', 'neutral');
    if (!Number.isFinite(value)) {
      changeEl.textContent = '24h —';
      changeEl.classList.add('neutral');
      return;
    }
    const sign = value > 0 ? '+' : '';
    changeEl.textContent = `24h ${sign}${value.toFixed(2)}%`;
    changeEl.classList.add(value > 0 ? 'positive' : value < 0 ? 'negative' : 'neutral');
  }

  function currentInstrument() {
    return instruments[runtime.symbol];
  }

  function updateHeaderIdentity() {
    const item = currentInstrument();
    const symbolEl = document.getElementById('liveChartSymbol');
    const marketEl = document.getElementById('liveChartMarketName');
    const sourceEl = document.getElementById('liveChartSource');
    if (symbolEl) symbolEl.textContent = runtime.symbol;
    if (marketEl) marketEl.textContent = item.title;
    if (sourceEl) sourceEl.textContent = item.source;
  }

  function createChart() {
    const host = document.getElementById('nexusLiveChartCanvas');
    if (!host || !window.LightweightCharts?.createChart) {
      setOverlay('Chart Engine unavailable', 'کتابخانه Lightweight Charts بارگذاری نشده است.', true);
      setStatus('ENGINE ERROR');
      return false;
    }

    runtime.chart = window.LightweightCharts.createChart(host, {
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
      crosshair: {
        mode: window.LightweightCharts.CrosshairMode?.Normal ?? 0,
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
      autoSize: false,
    });

    const seriesOptions = {
      upColor: '#25c998',
      downColor: '#ef5264',
      borderUpColor: '#25c998',
      borderDownColor: '#ef5264',
      wickUpColor: '#25c998',
      wickDownColor: '#ef5264',
      priceLineVisible: true,
      lastValueVisible: true,
    };

    if (typeof runtime.chart.addSeries === 'function' && window.LightweightCharts.CandlestickSeries) {
      runtime.series = runtime.chart.addSeries(window.LightweightCharts.CandlestickSeries, seriesOptions);
    } else if (typeof runtime.chart.addCandlestickSeries === 'function') {
      runtime.series = runtime.chart.addCandlestickSeries(seriesOptions);
    } else {
      setOverlay('Unsupported chart build', 'نسخه Lightweight Charts با API مورد انتظار سازگار نیست.', true);
      return false;
    }

    runtime.resizeObserver = new ResizeObserver(entries => {
      const rect = entries[0]?.contentRect;
      if (!rect || !runtime.chart) return;
      runtime.chart.applyOptions({
        width: Math.max(280, Math.floor(rect.width)),
        height: Math.max(390, Math.floor(host.clientHeight)),
      });
    });
    runtime.resizeObserver.observe(host);
    return true;
  }

  function stopStream() {
    runtime.streamGeneration += 1;
    if (runtime.reconnectTimer) {
      clearTimeout(runtime.reconnectTimer);
      runtime.reconnectTimer = null;
    }
    if (runtime.socket) {
      try {
        runtime.socket.onopen = runtime.socket.onmessage = runtime.socket.onerror = runtime.socket.onclose = null;
        runtime.socket.close();
      } catch (_) {}
      runtime.socket = null;
    }
  }

  function stopStaleTimer() {
    if (runtime.staleTimer) clearInterval(runtime.staleTimer);
    runtime.staleTimer = null;
  }

  function startStaleTimer() {
    stopStaleTimer();
    runtime.staleTimer = setInterval(() => {
      if (runtime.destroyed || currentInstrument().provider !== 'binance') return;
      if (!runtime.lastLiveAt || Date.now() - runtime.lastLiveAt > STALE_AFTER_MS) {
        setStatus('STALE DATA', 'stale');
      }
    }, 5000);
  }

  async function fetchJson(url) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 9000);
    try {
      const response = await fetch(url, { signal: controller.signal, cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async function loadHistorical() {
    stopStream();
    runtime.lastLiveAt = 0;
    runtime.lastCandleTime = 0;
    updateHeaderIdentity();
    setHeaderPrice(null, null);

    document.querySelectorAll('[data-live-symbol]').forEach(btn => btn.classList.toggle('active', btn.dataset.liveSymbol === runtime.symbol));
    document.querySelectorAll('[data-live-timeframe]').forEach(btn => btn.classList.toggle('active', btn.dataset.liveTimeframe === runtime.timeframe));

    const item = currentInstrument();
    if (item.provider !== 'binance') {
      runtime.series?.setData?.([]);
      setOverlay('XAUUSD data unavailable', 'برای طلا فقط داده معتبر NEXUS / MT5 نمایش داده می‌شود. در این نسخه هنوز feed کندل MT5 به Mini App متصل نشده است.', true);
      setStatus('UNAVAILABLE', 'stale');
      return;
    }

    setOverlay('در حال دریافت داده...', `${runtime.symbol} · ${runtime.timeframe}`, true);
    setStatus('LOADING');

    const interval = timeframes[runtime.timeframe];
    const base = 'https://api.binance.com/api/v3';

    try {
      const [klines, ticker] = await Promise.all([
        fetchJson(`${base}/klines?symbol=${encodeURIComponent(runtime.symbol)}&interval=${encodeURIComponent(interval)}&limit=500`),
        fetchJson(`${base}/ticker/24hr?symbol=${encodeURIComponent(runtime.symbol)}`),
      ]);

      if (runtime.destroyed || item !== currentInstrument()) return;

      const candles = Array.isArray(klines) ? klines.map(row => ({
        time: Math.floor(Number(row[0]) / 1000),
        open: Number(row[1]),
        high: Number(row[2]),
        low: Number(row[3]),
        close: Number(row[4]),
      })).filter(c => Number.isFinite(c.time) && Number.isFinite(c.close)) : [];

      if (!candles.length) throw new Error('No candles returned');

      runtime.series.setData(candles);
      runtime.lastCandleTime = Number(candles[candles.length - 1].time || 0);
      runtime.chart?.timeScale?.().fitContent?.();
      setHeaderPrice(Number(ticker.lastPrice), Number(ticker.priceChangePercent));
      setOverlay('', '', false);
      connectStream();
    } catch (error) {
      console.error('[NEXUS][LIVE_CHARTS] bootstrap failed', error);
      setOverlay('Market data unavailable', 'دریافت داده بازار با مشکل مواجه شد. از ساخت کندل یا قیمت جایگزین خودداری شد.', true);
      setStatus('DATA ERROR', 'stale');
    }
  }

  function scheduleReconnect(generation) {
    if (runtime.destroyed || generation !== runtime.streamGeneration) return;
    const delay = Math.min(1000 * (2 ** runtime.reconnectAttempt), MAX_BACKOFF_MS);
    runtime.reconnectAttempt += 1;
    setStatus(`RECONNECTING ${Math.ceil(delay / 1000)}s`, 'reconnecting');
    runtime.reconnectTimer = setTimeout(() => {
      if (!runtime.destroyed && generation === runtime.streamGeneration) connectStream();
    }, delay);
  }

  function connectStream() {
    stopStream();
    if (runtime.destroyed || currentInstrument().provider !== 'binance') return;

    const generation = runtime.streamGeneration;
    const symbol = runtime.symbol.toLowerCase();
    const interval = timeframes[runtime.timeframe];
    const streamUrl = `wss://stream.binance.com:9443/stream?streams=${symbol}@kline_${interval}/${symbol}@ticker`;

    setStatus('CONNECTING');
    let socket;
    try {
      socket = new WebSocket(streamUrl);
    } catch (error) {
      scheduleReconnect(generation);
      return;
    }
    runtime.socket = socket;

    socket.onopen = () => {
      if (generation !== runtime.streamGeneration || runtime.destroyed) return;
      runtime.reconnectAttempt = 0;
      runtime.lastLiveAt = Date.now();
      setStatus('LIVE', 'live');
      startStaleTimer();
    };

    socket.onmessage = event => {
      if (generation !== runtime.streamGeneration || runtime.destroyed) return;
      let message;
      try { message = JSON.parse(event.data); } catch (_) { return; }
      const data = message?.data || message;
      runtime.lastLiveAt = Date.now();
      setStatus('LIVE', 'live');

      if (data?.e === 'kline' && data.k) {
        const k = data.k;
        const candleTime = Math.floor(Number(k.t) / 1000);
        if (!Number.isFinite(candleTime) || candleTime < runtime.lastCandleTime) return;
        runtime.lastCandleTime = candleTime;
        runtime.series?.update?.({
          time: candleTime,
          open: Number(k.o),
          high: Number(k.h),
          low: Number(k.l),
          close: Number(k.c),
        });
        setHeaderPrice(Number(k.c), Number(document.getElementById('liveChartChange')?.dataset?.pct));
        return;
      }

      if (data?.e === '24hrTicker') {
        const pct = Number(data.P);
        const price = Number(data.c);
        const changeEl = document.getElementById('liveChartChange');
        if (changeEl) changeEl.dataset.pct = Number.isFinite(pct) ? String(pct) : '';
        setHeaderPrice(price, pct);
      }
    };

    socket.onerror = () => {
      if (generation === runtime.streamGeneration && !runtime.destroyed) setStatus('STREAM ERROR', 'reconnecting');
    };

    socket.onclose = () => {
      if (generation !== runtime.streamGeneration || runtime.destroyed) return;
      runtime.socket = null;
      scheduleReconnect(generation);
    };
  }

  function bindChartControls() {
    viewEl.querySelectorAll('[data-live-symbol]').forEach(btn => btn.addEventListener('click', () => {
      const next = btn.dataset.liveSymbol;
      if (!instruments[next] || next === runtime.symbol) return;
      runtime.symbol = next;
      loadHistorical();
    }));

    viewEl.querySelectorAll('[data-live-timeframe]').forEach(btn => btn.addEventListener('click', () => {
      const next = btn.dataset.liveTimeframe;
      if (!timeframes[next] || next === runtime.timeframe) return;
      runtime.timeframe = next;
      loadHistorical();
    }));
  }

  function open() {
    destroy(false);
    runtime.destroyed = false;
    try { state.route = CHART_ROUTE; } catch (_) {}
    viewEl.innerHTML = chartMarkup();
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.toggle('active', btn.dataset.route === CHART_ROUTE));
    bindChartControls();
    if (createChart()) loadHistorical();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function destroy(clearView = false) {
    runtime.destroyed = true;
    stopStream();
    stopStaleTimer();
    runtime.resizeObserver?.disconnect?.();
    runtime.resizeObserver = null;
    try { runtime.chart?.remove?.(); } catch (_) {}
    runtime.chart = null;
    runtime.series = null;
    if (clearView && viewEl.querySelector('.nexus-live-charts-page')) viewEl.replaceChildren();
  }

  if (originalRender) {
    const wrappedRender = function(route = 'home') {
      if (route === CHART_ROUTE) {
        open();
        return;
      }
      if (!runtime.destroyed) destroy(false);
      return originalRender(route);
    };
    window.render = wrappedRender;
    try { render = wrappedRender; } catch (_) {}
  }

  document.addEventListener('visibilitychange', () => {
    if (runtime.destroyed || currentInstrument().provider !== 'binance') return;
    if (document.visibilityState === 'visible' && (!runtime.socket || runtime.socket.readyState > 1)) {
      connectStream();
    }
  });

  window.NexusLiveCharts = {
    open,
    destroy: () => destroy(false),
    current: () => ({ symbol: runtime.symbol, timeframe: runtime.timeframe }),
  };
})();
