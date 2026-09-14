(() => {
  'use strict';

  const PAGE_SELECTOR = '.nexus-live-charts-page';
  const PANEL_SELECTOR = '.live-chart-panel';
  const BASE_HOST_ID = 'nexusLiveChartCanvas';
  const BROKER_HOST_ID = 'nexusBrokerChartCanvas';
  const STORAGE_PREFIX = 'nexus:chart-drawings:v22:';
  const SIGNAL_POLL_MS = 10000;
  const FACTORY_RETRY_MS = 100;
  const MAX_FACTORY_RETRIES = 120;

  const contexts = new Map();
  const state = {
    activeTool: null,
    firstPoint: null,
    hoverPoint: null,
    canvas: null,
    ctx: null,
    resizeObserver: null,
    raf: 0,
    signalTimer: null,
    signals: [],
    nexusOverlay: true,
    factoryRetries: 0,
    initializedPage: null,
  };

  const TOOL_LABELS = {
    horizontal: 'Horizontal',
    trend: 'Trend Line',
    rectangle: 'Rectangle',
    fib: 'Fibonacci',
    risk: 'Risk / Reward',
  };

  function safeNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function currentSymbol() {
    const broker = window.NexusLiveChartsForex?.current?.();
    if (broker) return String(broker).toUpperCase();
    return String(window.NexusLiveCharts?.current?.().symbol || '').toUpperCase();
  }

  function currentTimeframe() {
    const active = document.querySelector('[data-live-timeframe].active');
    if (active?.dataset?.liveTimeframe) return active.dataset.liveTimeframe;
    return String(window.NexusLiveCharts?.current?.().timeframe || '5m');
  }

  function scopeKey() {
    return `${currentSymbol() || 'UNKNOWN'}:${currentTimeframe() || '5m'}`;
  }

  function storageKey() {
    return `${STORAGE_PREFIX}${scopeKey()}`;
  }

  function loadDrawings() {
    try {
      const parsed = JSON.parse(localStorage.getItem(storageKey()) || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
      return [];
    }
  }

  function saveDrawings(drawings) {
    try { localStorage.setItem(storageKey(), JSON.stringify(drawings)); } catch (_) {}
  }

  function mutateDrawings(mutator) {
    const next = loadDrawings();
    mutator(next);
    saveDrawings(next);
    requestDraw();
  }

  function activeContext() {
    const brokerHost = document.getElementById(BROKER_HOST_ID);
    const broker = brokerHost && brokerHost.isConnected ? contexts.get(BROKER_HOST_ID) : null;
    if (broker?.chart && broker?.series) return broker;
    const base = contexts.get(BASE_HOST_ID);
    return base?.chart && base?.series ? base : null;
  }

  function dispatchContextReady(hostId) {
    document.dispatchEvent(new CustomEvent('nexus:live-chart-context-ready', { detail: { hostId } }));
  }

  function wrapSeriesFactory(chart, context, methodName) {
    const original = chart?.[methodName];
    if (typeof original !== 'function' || original.__nexusToolsWrapped) return;
    const wrapped = function(...args) {
      const series = original.apply(chart, args);
      context.series = series;
      dispatchContextReady(context.host?.id || '');
      requestDraw();
      return series;
    };
    wrapped.__nexusToolsWrapped = true;
    chart[methodName] = wrapped;
  }

  function installFactoryHook() {
    const library = window.LightweightCharts;
    const currentFactory = library?.createChart;
    if (typeof currentFactory !== 'function') {
      if (state.factoryRetries++ < MAX_FACTORY_RETRIES) {
        window.setTimeout(installFactoryHook, FACTORY_RETRY_MS);
      }
      return;
    }
    if (currentFactory.__nexusToolsWrapped) return;

    const originalFactory = currentFactory;
    const wrappedFactory = function(host, options) {
      const chart = originalFactory.call(library, host, options);
      const hostId = host?.id || `nexus-chart-${contexts.size + 1}`;
      const context = { host, chart, series: null };
      contexts.set(hostId, context);

      wrapSeriesFactory(chart, context, 'addSeries');
      wrapSeriesFactory(chart, context, 'addCandlestickSeries');

      const originalRemove = typeof chart?.remove === 'function' ? chart.remove.bind(chart) : null;
      if (originalRemove) {
        chart.remove = () => {
          contexts.delete(hostId);
          requestDraw();
          return originalRemove();
        };
      }
      return chart;
    };
    wrappedFactory.__nexusToolsWrapped = true;
    wrappedFactory.__nexusOriginal = originalFactory;
    library.createChart = wrappedFactory;
  }

  function toolbarMarkup() {
    return `
      <div class="nexus-chart-tools-v22" aria-label="Chart drawing tools">
        <div class="nexus-chart-tools-scroll">
          <button type="button" class="nexus-chart-tool is-active" data-chart-tool="cursor" title="Cursor"><span>↖</span><small>Cursor</small></button>
          <button type="button" class="nexus-chart-tool" data-chart-tool="horizontal" title="Horizontal line"><span>─</span><small>H-Line</small></button>
          <button type="button" class="nexus-chart-tool" data-chart-tool="trend" title="Trend line"><span>↗</span><small>Trend</small></button>
          <button type="button" class="nexus-chart-tool" data-chart-tool="rectangle" title="Rectangle zone"><span>▭</span><small>Zone</small></button>
          <button type="button" class="nexus-chart-tool" data-chart-tool="fib" title="Fibonacci retracement"><span>F</span><small>Fib</small></button>
          <button type="button" class="nexus-chart-tool" data-chart-tool="risk" title="Risk reward"><span>RR</span><small>Risk</small></button>
          <span class="nexus-chart-tool-divider" aria-hidden="true"></span>
          <button type="button" class="nexus-chart-tool nexus-chart-tool-nexus is-active" data-chart-nexus-overlay title="NEXUS active signal overlay"><span>◉</span><small>NEXUS</small></button>
          <button type="button" class="nexus-chart-tool" data-chart-undo title="Undo"><span>↶</span><small>Undo</small></button>
          <button type="button" class="nexus-chart-tool" data-chart-clear title="Clear drawings"><span>⌫</span><small>Clear</small></button>
          <button type="button" class="nexus-chart-tool" data-chart-fullscreen title="Fullscreen"><span>⛶</span><small>Full</small></button>
        </div>
        <div class="nexus-chart-tool-hint" id="nexusChartToolHint">ابزار رسم آماده است</div>
      </div>`;
  }

  function ensureToolbar(page) {
    const controls = page.querySelector('.live-chart-controls');
    if (!controls || page.querySelector('.nexus-chart-tools-v22')) return;
    controls.insertAdjacentHTML('afterend', toolbarMarkup());

    page.querySelectorAll('[data-chart-tool]').forEach(button => {
      button.addEventListener('click', () => selectTool(button.dataset.chartTool));
    });
    page.querySelector('[data-chart-nexus-overlay]')?.addEventListener('click', toggleNexusOverlay);
    page.querySelector('[data-chart-undo]')?.addEventListener('click', undoDrawing);
    page.querySelector('[data-chart-clear]')?.addEventListener('click', clearDrawings);
    page.querySelector('[data-chart-fullscreen]')?.addEventListener('click', toggleFullscreen);
  }

  function ensureCanvas(page) {
    const panel = page.querySelector(PANEL_SELECTOR);
    if (!panel) return;
    let canvas = panel.querySelector('#nexusChartDrawingCanvas');
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.id = 'nexusChartDrawingCanvas';
      canvas.className = 'nexus-chart-drawing-canvas';
      canvas.setAttribute('aria-label', 'NEXUS chart drawing overlay');
      panel.appendChild(canvas);
      canvas.addEventListener('pointerup', onPointerUp);
      canvas.addEventListener('pointermove', onPointerMove);
      canvas.addEventListener('pointerleave', () => {
        state.hoverPoint = null;
        requestDraw();
      });
    }
    state.canvas = canvas;
    state.ctx = canvas.getContext('2d');
    setCanvasInteraction();

    state.resizeObserver?.disconnect?.();
    state.resizeObserver = new ResizeObserver(() => resizeCanvas());
    state.resizeObserver.observe(panel);
    resizeCanvas();
  }

  function resizeCanvas() {
    const canvas = state.canvas;
    const panel = canvas?.parentElement;
    if (!canvas || !panel) return;
    const rect = panel.getBoundingClientRect();
    const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
    }
    requestDraw();
  }

  function setHint(text) {
    const hint = document.getElementById('nexusChartToolHint');
    if (hint) hint.textContent = text;
  }

  function setCanvasInteraction() {
    if (!state.canvas) return;
    state.canvas.classList.toggle('is-drawing', Boolean(state.activeTool));
  }

  function selectTool(tool) {
    state.activeTool = tool === 'cursor' ? null : tool;
    state.firstPoint = null;
    state.hoverPoint = null;
    document.querySelectorAll('[data-chart-tool]').forEach(button => {
      const isCursor = button.dataset.chartTool === 'cursor';
      button.classList.toggle('is-active', state.activeTool ? button.dataset.chartTool === state.activeTool : isCursor);
    });
    setCanvasInteraction();
    setHint(state.activeTool ? `${TOOL_LABELS[state.activeTool]}: نقطه اول را انتخاب کنید` : 'Cursor فعال است');
    requestDraw();
    try { window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.(); } catch (_) {}
  }

  function pointerToData(event) {
    const context = activeContext();
    const canvas = state.canvas;
    if (!context?.chart || !context?.series || !canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
    const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
    const time = context.chart.timeScale?.().coordinateToTime?.(x);
    const price = context.series.coordinateToPrice?.(y);
    if (time == null || price == null || !Number.isFinite(Number(price))) return null;
    return { time, price: Number(price) };
  }

  function completeDrawing(secondPoint = null) {
    const tool = state.activeTool;
    const first = state.firstPoint;
    if (!tool || !first) return;
    const drawing = tool === 'horizontal'
      ? { type: tool, p1: first }
      : { type: tool, p1: first, p2: secondPoint };
    if (tool !== 'horizontal' && !secondPoint) return;
    mutateDrawings(drawings => drawings.push(drawing));
    state.firstPoint = null;
    state.hoverPoint = null;
    setHint(`${TOOL_LABELS[tool]} ثبت شد · برای رسم بعدی دوباره انتخاب کنید`);
    try { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light'); } catch (_) {}
  }

  function onPointerUp(event) {
    if (!state.activeTool) return;
    const point = pointerToData(event);
    if (!point) {
      setHint('برای رسم، داخل محدوده کندل‌ها لمس کنید');
      return;
    }
    if (state.activeTool === 'horizontal') {
      state.firstPoint = point;
      completeDrawing();
      return;
    }
    if (!state.firstPoint) {
      state.firstPoint = point;
      setHint(`${TOOL_LABELS[state.activeTool]}: نقطه دوم را انتخاب کنید`);
      requestDraw();
      return;
    }
    completeDrawing(point);
  }

  function onPointerMove(event) {
    if (!state.activeTool || !state.firstPoint) return;
    state.hoverPoint = pointerToData(event);
    requestDraw();
  }

  function undoDrawing() {
    mutateDrawings(drawings => drawings.pop());
    setHint('آخرین رسم حذف شد');
  }

  function clearDrawings() {
    saveDrawings([]);
    state.firstPoint = null;
    state.hoverPoint = null;
    requestDraw();
    setHint('تمام رسم‌های این نماد و تایم‌فریم پاک شد');
  }

  async function toggleFullscreen() {
    const page = document.querySelector(PAGE_SELECTOR);
    if (!page) return;
    try {
      if (!document.fullscreenElement) await page.requestFullscreen?.();
      else await document.exitFullscreen?.();
    } catch (_) {}
  }

  function toggleNexusOverlay() {
    state.nexusOverlay = !state.nexusOverlay;
    try { localStorage.setItem('nexus:chart:nexus-overlay:v22', state.nexusOverlay ? '1' : '0'); } catch (_) {}
    document.querySelector('[data-chart-nexus-overlay]')?.classList.toggle('is-active', state.nexusOverlay);
    setHint(state.nexusOverlay ? 'NEXUS Signal Overlay فعال شد' : 'NEXUS Signal Overlay خاموش شد');
    requestDraw();
  }

  function dataToScreen(point) {
    const context = activeContext();
    if (!context?.chart || !context?.series || !point) return null;
    const x = context.chart.timeScale?.().timeToCoordinate?.(point.time);
    const y = context.series.priceToCoordinate?.(Number(point.price));
    if (x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y)) return null;
    return { x, y };
  }

  function clearCanvas() {
    const canvas = state.canvas;
    const ctx = state.ctx;
    if (!canvas || !ctx) return null;
    const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { width: canvas.width / dpr, height: canvas.height / dpr };
  }

  function line(ctx, x1, y1, x2, y2, color, width = 1.4, dash = []) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.setLineDash(dash);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.restore();
  }

  function label(ctx, text, x, y, color = '#dbeafe', bg = 'rgba(8,15,24,.86)') {
    ctx.save();
    ctx.font = '600 10px Vazirmatn, Segoe UI, sans-serif';
    const padX = 6;
    const width = Math.ceil(ctx.measureText(text).width) + padX * 2;
    const height = 20;
    const left = Math.max(3, x - width);
    const top = Math.max(3, y - height / 2);
    ctx.fillStyle = bg;
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(left, top, width, height, 6);
    else ctx.rect(left, top, width, height);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, left + width / 2, top + height / 2 + .5);
    ctx.restore();
  }

  function drawHorizontal(ctx, drawing, size, preview = false) {
    const p = dataToScreen(drawing.p1);
    if (!p) return;
    const color = preview ? 'rgba(96,165,250,.65)' : '#60a5fa';
    line(ctx, 0, p.y, size.width, p.y, color, preview ? 1 : 1.35, [6, 4]);
    label(ctx, Number(drawing.p1.price).toFixed(2), size.width - 6, p.y, color);
  }

  function drawTrend(ctx, drawing, preview = false) {
    const a = dataToScreen(drawing.p1);
    const b = dataToScreen(drawing.p2);
    if (!a || !b) return;
    line(ctx, a.x, a.y, b.x, b.y, preview ? 'rgba(34,211,238,.60)' : '#22d3ee', preview ? 1 : 1.7);
  }

  function drawRectangle(ctx, drawing, preview = false) {
    const a = dataToScreen(drawing.p1);
    const b = dataToScreen(drawing.p2);
    if (!a || !b) return;
    const x = Math.min(a.x, b.x);
    const y = Math.min(a.y, b.y);
    const w = Math.abs(b.x - a.x);
    const h = Math.abs(b.y - a.y);
    ctx.save();
    ctx.fillStyle = preview ? 'rgba(99,102,241,.08)' : 'rgba(99,102,241,.13)';
    ctx.strokeStyle = preview ? 'rgba(129,140,248,.55)' : 'rgba(129,140,248,.92)';
    ctx.lineWidth = 1.2;
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
    ctx.restore();
  }

  function drawFib(ctx, drawing, preview = false) {
    const a = dataToScreen(drawing.p1);
    const b = dataToScreen(drawing.p2);
    if (!a || !b) return;
    const left = Math.min(a.x, b.x);
    const right = Math.max(a.x, b.x);
    const levels = [0, .236, .382, .5, .618, .786, 1];
    const color = preview ? 'rgba(251,191,36,.55)' : 'rgba(251,191,36,.95)';
    levels.forEach(level => {
      const price = drawing.p1.price + (drawing.p2.price - drawing.p1.price) * level;
      const y = activeContext()?.series?.priceToCoordinate?.(price);
      if (y == null) return;
      line(ctx, left, y, right, y, color, level === .5 || level === .618 ? 1.4 : .9, [4, 4]);
      ctx.save();
      ctx.fillStyle = color;
      ctx.font = '600 9px Segoe UI, sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(`${(level * 100).toFixed(level === 0 || level === 1 ? 0 : 1)}%`, left + 4, y - 3);
      ctx.restore();
    });
  }

  function drawRisk(ctx, drawing, preview = false) {
    const a = dataToScreen(drawing.p1);
    const b = dataToScreen(drawing.p2);
    const context = activeContext();
    if (!a || !b || !context?.series) return;
    const entry = Number(drawing.p1.price);
    const stop = Number(drawing.p2.price);
    const risk = Math.abs(entry - stop);
    if (!(risk > 0)) return;
    const direction = stop < entry ? 1 : -1;
    const target = entry + direction * risk * 2;
    const targetY = context.series.priceToCoordinate?.(target);
    if (targetY == null) return;
    const left = Math.min(a.x, b.x);
    const right = Math.max(a.x, b.x) + 70;
    const x = Math.max(0, left);
    const w = Math.max(42, right - x);
    const entryY = a.y;
    const stopY = b.y;

    ctx.save();
    ctx.globalAlpha = preview ? .62 : 1;
    ctx.fillStyle = 'rgba(34,197,94,.12)';
    ctx.fillRect(x, Math.min(entryY, targetY), w, Math.abs(entryY - targetY));
    ctx.fillStyle = 'rgba(244,63,94,.14)';
    ctx.fillRect(x, Math.min(entryY, stopY), w, Math.abs(entryY - stopY));
    ctx.restore();

    line(ctx, x, entryY, x + w, entryY, '#60a5fa', 1.2);
    line(ctx, x, stopY, x + w, stopY, '#fb7185', 1.2);
    line(ctx, x, targetY, x + w, targetY, '#4ade80', 1.2);
    label(ctx, 'ENTRY', x + w - 4, entryY, '#60a5fa');
    label(ctx, 'SL', x + w - 4, stopY, '#fb7185');
    label(ctx, 'TP 2R', x + w - 4, targetY, '#4ade80');
  }

  function drawOne(ctx, drawing, size, preview = false) {
    if (!drawing?.type || !drawing?.p1) return;
    if (drawing.type === 'horizontal') return drawHorizontal(ctx, drawing, size, preview);
    if (!drawing.p2) return;
    if (drawing.type === 'trend') return drawTrend(ctx, drawing, preview);
    if (drawing.type === 'rectangle') return drawRectangle(ctx, drawing, preview);
    if (drawing.type === 'fib') return drawFib(ctx, drawing, preview);
    if (drawing.type === 'risk') return drawRisk(ctx, drawing, preview);
  }

  function normalizeSignalSymbol(value) {
    return String(value || '').toUpperCase().replace(/\.EC$/i, '').replace(/[^A-Z0-9]/g, '');
  }

  function signalPrices(signal) {
    const prices = [];
    const entry = safeNumber(signal?.entry_price);
    const stop = safeNumber(signal?.stop_loss);
    if (entry != null) prices.push({ label: 'ENTRY', price: entry, color: '#38bdf8' });
    if (stop != null) prices.push({ label: 'SL', price: stop, color: '#fb7185' });
    (Array.isArray(signal?.targets) ? signal.targets : []).slice(0, 3).forEach((target, index) => {
      const price = safeNumber(target?.price);
      if (price != null) prices.push({ label: `TP${target.target_no || index + 1}`, price, color: '#4ade80' });
    });
    return prices;
  }

  function drawNexusSignals(ctx, size) {
    if (!state.nexusOverlay) return;
    const symbol = normalizeSignalSymbol(currentSymbol());
    if (!symbol) return;
    const matches = state.signals
      .filter(item => normalizeSignalSymbol(item?.symbol) === symbol && String(item?.status || 'ACTIVE').toUpperCase() !== 'CLOSED')
      .slice(0, 2);
    matches.forEach((signal, signalIndex) => {
      const prices = signalPrices(signal);
      prices.forEach((item, index) => {
        const y = activeContext()?.series?.priceToCoordinate?.(item.price);
        if (y == null) return;
        line(ctx, 0, y, size.width, y, item.color, item.label === 'ENTRY' ? 1.6 : 1.15, item.label === 'ENTRY' ? [] : [6, 4]);
        const suffix = signal?.code ? ` #${signal.code}` : signalIndex ? ` ${signalIndex + 1}` : '';
        label(ctx, `NEXUS ${item.label}${suffix}`, size.width - 6, y, item.color);
      });
    });
  }

  function render() {
    state.raf = 0;
    const size = clearCanvas();
    if (!size || !document.querySelector(PAGE_SELECTOR)) return;
    const context = activeContext();
    if (!context?.chart || !context?.series) return;

    loadDrawings().forEach(drawing => drawOne(state.ctx, drawing, size, false));
    drawNexusSignals(state.ctx, size);

    if (state.activeTool && state.firstPoint && state.hoverPoint) {
      drawOne(state.ctx, { type: state.activeTool, p1: state.firstPoint, p2: state.hoverPoint }, size, true);
    }
  }

  function requestDraw() {
    if (state.raf) return;
    state.raf = requestAnimationFrame(render);
  }

  async function refreshSignals() {
    if (!document.querySelector(PAGE_SELECTOR)) return;
    const apiFn = typeof window.api === 'function' ? window.api : (typeof api === 'function' ? api : null);
    if (!apiFn) return;
    try {
      const data = await apiFn('/signals?state=ACTIVE&access=ALL&limit=20&offset=0');
      state.signals = Array.isArray(data?.items) ? data.items : [];
      requestDraw();
    } catch (_) {
      state.signals = [];
      requestDraw();
    }
  }

  function startSignalPolling() {
    if (state.signalTimer) clearInterval(state.signalTimer);
    refreshSignals();
    state.signalTimer = setInterval(refreshSignals, SIGNAL_POLL_MS);
  }

  function stopSignalPolling() {
    if (state.signalTimer) clearInterval(state.signalTimer);
    state.signalTimer = null;
  }

  function syncScope() {
    state.firstPoint = null;
    state.hoverPoint = null;
    requestDraw();
    refreshSignals();
  }

  function initializePage(page) {
    if (!page || state.initializedPage === page) return;
    state.initializedPage = page;
    try { state.nexusOverlay = localStorage.getItem('nexus:chart:nexus-overlay:v22') !== '0'; } catch (_) {}
    ensureToolbar(page);
    ensureCanvas(page);
    page.querySelector('[data-chart-nexus-overlay]')?.classList.toggle('is-active', state.nexusOverlay);
    startSignalPolling();
    requestDraw();
  }

  function teardownPage() {
    if (!state.initializedPage) return;
    state.resizeObserver?.disconnect?.();
    state.resizeObserver = null;
    state.canvas = null;
    state.ctx = null;
    state.firstPoint = null;
    state.hoverPoint = null;
    state.initializedPage = null;
    stopSignalPolling();
    if (state.raf) cancelAnimationFrame(state.raf);
    state.raf = 0;
  }

  const observer = new MutationObserver(() => {
    const page = document.querySelector(PAGE_SELECTOR);
    if (page) initializePage(page);
    else teardownPage();
    requestDraw();
  });
  observer.observe(document.getElementById('view') || document.body, { childList: true, subtree: true });

  document.addEventListener('nexus:live-chart-context-ready', requestDraw);
  document.addEventListener('click', event => {
    if (event.target.closest?.('[data-live-symbol], [data-live-fx], [data-live-timeframe]')) {
      window.setTimeout(syncScope, 80);
    }
  }, true);
  document.addEventListener('fullscreenchange', () => window.setTimeout(resizeCanvas, 40));
  window.addEventListener('resize', resizeCanvas, { passive: true });

  function redrawLoop() {
    if (document.querySelector(PAGE_SELECTOR)) requestDraw();
    requestAnimationFrame(redrawLoop);
  }

  installFactoryHook();
  initializePage(document.querySelector(PAGE_SELECTOR));
  redrawLoop();

  window.NexusChartTools = {
    clear: clearDrawings,
    undo: undoDrawing,
    select: selectTool,
    refreshSignals,
    scope: scopeKey,
  };
})();
