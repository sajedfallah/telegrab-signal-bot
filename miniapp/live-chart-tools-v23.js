(() => {
  'use strict';

  const PAGE = '.nexus-live-charts-page';
  const PANEL = '.live-chart-panel';
  const BASE_HOST = 'nexusLiveChartCanvas';
  const BROKER_HOST = 'nexusBrokerChartCanvas';
  const STORE_PREFIX = 'nexus:chart-drawings:v23:';
  const contexts = new Map();

  const state = {
    tool: null,
    first: null,
    hover: null,
    canvas: null,
    ctx: null,
    page: null,
    resizeObserver: null,
    redrawTimer: null,
    signalTimer: null,
    signals: [],
    nexusOverlay: true,
    factoryReady: false,
    factoryAttempts: 0,
    recoveryAttempted: false,
  };

  const labels = {
    horizontal: 'Horizontal',
    trend: 'Trend Line',
    rectangle: 'Rectangle',
    fib: 'Fibonacci',
    risk: 'Risk / Reward',
  };

  const number = value => {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };

  function currentSymbol() {
    const broker = window.NexusLiveChartsForex?.current?.();
    if (broker) return String(broker).toUpperCase();
    return String(window.NexusLiveCharts?.current?.().symbol || '').toUpperCase();
  }

  function currentTimeframe() {
    const active = document.querySelector('[data-live-timeframe].active');
    return String(active?.dataset?.liveTimeframe || window.NexusLiveCharts?.current?.().timeframe || '5m');
  }

  function storageKey() {
    return `${STORE_PREFIX}${currentSymbol() || 'UNKNOWN'}:${currentTimeframe()}`;
  }

  function drawings() {
    try {
      const value = JSON.parse(localStorage.getItem(storageKey()) || '[]');
      return Array.isArray(value) ? value : [];
    } catch (_) {
      return [];
    }
  }

  function save(items) {
    try { localStorage.setItem(storageKey(), JSON.stringify(items)); } catch (_) {}
    draw();
  }

  function activeContext() {
    const brokerHost = document.getElementById(BROKER_HOST);
    if (brokerHost?.isConnected) {
      const broker = contexts.get(BROKER_HOST);
      if (broker?.chart && broker?.series) return broker;
    }
    const base = contexts.get(BASE_HOST);
    return base?.chart && base?.series ? base : null;
  }

  function proxiedChart(host, chart) {
    const hostId = host?.id || `nexus-chart-${contexts.size + 1}`;
    const context = { host, chart: null, rawChart: chart, series: null };

    const proxy = new Proxy(chart, {
      get(target, prop) {
        if (prop === 'addSeries' || prop === 'addCandlestickSeries') {
          const method = target[prop];
          if (typeof method !== 'function') return undefined;
          return (...args) => {
            const series = method.apply(target, args);
            context.series = series;
            draw();
            return series;
          };
        }
        if (prop === 'remove') {
          const method = target.remove;
          return (...args) => {
            contexts.delete(hostId);
            draw();
            return typeof method === 'function' ? method.apply(target, args) : undefined;
          };
        }
        const value = Reflect.get(target, prop, target);
        return typeof value === 'function' ? value.bind(target) : value;
      },
    });

    context.chart = proxy;
    contexts.set(hostId, context);
    return proxy;
  }

  function installFactory() {
    const lib = window.LightweightCharts;
    const current = lib?.createChart;
    if (typeof current !== 'function') {
      if (state.factoryAttempts++ < 400) setTimeout(installFactory, 25);
      return;
    }
    if (current.__nexusV23) {
      state.factoryReady = true;
      return;
    }

    const original = current.__nexusOriginal || current;
    const wrapped = function(host, options) {
      const raw = original.call(lib, host, options);
      return proxiedChart(host, raw);
    };
    wrapped.__nexusV23 = true;
    wrapped.__nexusOriginal = original;
    lib.createChart = wrapped;
    state.factoryReady = true;

    setTimeout(recoverContextIfNeeded, 120);
  }

  function markup() {
    return `<div class="nexus-chart-tools-v23" aria-label="Chart drawing tools">
      <div class="nexus-chart-tools-scroll">
        <button type="button" class="nexus-chart-tool is-active" data-v23-tool="cursor"><span>↖</span><small>Cursor</small></button>
        <button type="button" class="nexus-chart-tool" data-v23-tool="horizontal"><span>─</span><small>H-Line</small></button>
        <button type="button" class="nexus-chart-tool" data-v23-tool="trend"><span>↗</span><small>Trend</small></button>
        <button type="button" class="nexus-chart-tool" data-v23-tool="rectangle"><span>▭</span><small>Zone</small></button>
        <button type="button" class="nexus-chart-tool" data-v23-tool="fib"><span>F</span><small>Fib</small></button>
        <button type="button" class="nexus-chart-tool" data-v23-tool="risk"><span>RR</span><small>Risk</small></button>
        <span class="nexus-chart-tool-divider" aria-hidden="true"></span>
        <button type="button" class="nexus-chart-tool nexus-chart-tool-nexus is-active" data-v23-nexus><span>◉</span><small>NEXUS</small></button>
        <button type="button" class="nexus-chart-tool" data-v23-undo><span>↶</span><small>Undo</small></button>
        <button type="button" class="nexus-chart-tool" data-v23-clear><span>⌫</span><small>Clear</small></button>
        <button type="button" class="nexus-chart-tool" data-v23-full><span>⛶</span><small>Full</small></button>
      </div>
      <div class="nexus-chart-tool-hint" id="nexusChartToolHintV23">Cursor فعال است</div>
    </div>`;
  }

  function hint(text) {
    const el = document.getElementById('nexusChartToolHintV23');
    if (el) el.textContent = text;
  }

  function syncButtons() {
    document.querySelectorAll('[data-v23-tool]').forEach(button => {
      const cursor = button.dataset.v23Tool === 'cursor';
      button.classList.toggle('is-active', state.tool ? button.dataset.v23Tool === state.tool : cursor);
    });
    document.querySelector('[data-v23-nexus]')?.classList.toggle('is-active', state.nexusOverlay);
  }

  function selectTool(tool) {
    state.tool = tool === 'cursor' ? null : tool;
    state.first = null;
    state.hover = null;
    syncButtons();
    updateCanvasMode();
    if (state.tool && !activeContext()) {
      hint('در حال اتصال ابزار به چارت...');
      recoverContextIfNeeded();
    } else {
      hint(state.tool ? `${labels[state.tool]}: نقطه اول را روی چارت انتخاب کنید` : 'Cursor فعال است');
    }
    draw();
    try { window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.(); } catch (_) {}
  }

  function ensureToolbar(page) {
    const controls = page.querySelector('.live-chart-controls');
    if (!controls || page.querySelector('.nexus-chart-tools-v23')) return;
    controls.insertAdjacentHTML('afterend', markup());
    page.querySelectorAll('[data-v23-tool]').forEach(button => button.addEventListener('click', () => selectTool(button.dataset.v23Tool)));
    page.querySelector('[data-v23-undo]')?.addEventListener('click', undo);
    page.querySelector('[data-v23-clear]')?.addEventListener('click', clear);
    page.querySelector('[data-v23-nexus]')?.addEventListener('click', toggleNexus);
    page.querySelector('[data-v23-full]')?.addEventListener('click', toggleFullscreen);
    syncButtons();
  }

  function ensureCanvas(page) {
    const panel = page.querySelector(PANEL);
    if (!panel) return;
    let canvas = panel.querySelector('#nexusChartDrawingCanvasV23');
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.id = 'nexusChartDrawingCanvasV23';
      canvas.className = 'nexus-chart-drawing-canvas-v23';
      panel.appendChild(canvas);
      canvas.addEventListener('pointerup', pointerUp);
      canvas.addEventListener('pointermove', pointerMove);
      canvas.addEventListener('pointerleave', () => { state.hover = null; draw(); });
    }
    state.canvas = canvas;
    state.ctx = canvas.getContext('2d');
    updateCanvasMode();

    state.resizeObserver?.disconnect?.();
    if (window.ResizeObserver) {
      state.resizeObserver = new ResizeObserver(resizeCanvas);
      state.resizeObserver.observe(panel);
    }
    resizeCanvas();
  }

  function resizeCanvas() {
    const canvas = state.canvas;
    const panel = canvas?.parentElement;
    if (!canvas || !panel) return;
    const rect = panel.getBoundingClientRect();
    const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
    const w = Math.max(1, Math.round(rect.width));
    const h = Math.max(1, Math.round(rect.height));
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    draw();
  }

  function updateCanvasMode() {
    if (!state.canvas) return;
    state.canvas.classList.toggle('is-drawing', Boolean(state.tool));
  }

  function pointerPoint(event) {
    const context = activeContext();
    if (!context?.chart || !context?.series || !state.canvas) return null;
    const rect = state.canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
    const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
    const time = context.chart.timeScale?.().coordinateToTime?.(x);
    const price = context.series.coordinateToPrice?.(y);
    if (time == null || !Number.isFinite(Number(price))) return null;
    return { time, price: Number(price) };
  }

  function pointerUp(event) {
    if (!state.tool) return;
    const point = pointerPoint(event);
    if (!point) {
      hint('اتصال چارت آماده نیست؛ یک‌بار نماد یا تایم‌فریم را تغییر دهید');
      recoverContextIfNeeded();
      return;
    }
    if (state.tool === 'horizontal') {
      const next = drawings();
      next.push({ type: 'horizontal', p1: point });
      save(next);
      hint('Horizontal ثبت شد');
      return;
    }
    if (!state.first) {
      state.first = point;
      hint(`${labels[state.tool]}: نقطه دوم را انتخاب کنید`);
      draw();
      return;
    }
    const next = drawings();
    next.push({ type: state.tool, p1: state.first, p2: point });
    save(next);
    state.first = null;
    state.hover = null;
    hint(`${labels[state.tool]} ثبت شد`);
    try { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light'); } catch (_) {}
  }

  function pointerMove(event) {
    if (!state.tool || !state.first) return;
    state.hover = pointerPoint(event);
    draw();
  }

  function screen(point) {
    const context = activeContext();
    if (!context?.chart || !context?.series || !point) return null;
    const x = context.chart.timeScale?.().timeToCoordinate?.(point.time);
    const y = context.series.priceToCoordinate?.(Number(point.price));
    return x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y) ? null : { x, y };
  }

  function clearSurface() {
    if (!state.canvas || !state.ctx) return null;
    const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
    state.ctx.setTransform(1, 0, 0, 1, 0, 0);
    state.ctx.clearRect(0, 0, state.canvas.width, state.canvas.height);
    state.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { width: state.canvas.width / dpr, height: state.canvas.height / dpr };
  }

  function line(x1, y1, x2, y2, color, width = 1.4, dash = []) {
    const ctx = state.ctx;
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

  function tag(text, x, y, color) {
    const ctx = state.ctx;
    ctx.save();
    ctx.font = '600 10px Vazirmatn, Segoe UI, sans-serif';
    const width = Math.ceil(ctx.measureText(text).width) + 12;
    const left = Math.max(3, x - width);
    const top = Math.max(3, y - 10);
    ctx.fillStyle = 'rgba(8,15,24,.88)';
    ctx.strokeStyle = color;
    ctx.lineWidth = .8;
    if (ctx.roundRect) {
      ctx.beginPath(); ctx.roundRect(left, top, width, 20, 6); ctx.fill(); ctx.stroke();
    } else {
      ctx.fillRect(left, top, width, 20); ctx.strokeRect(left, top, width, 20);
    }
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, left + width / 2, top + 10);
    ctx.restore();
  }

  function drawItem(item, size, preview = false) {
    if (!item?.p1) return;
    const a = screen(item.p1);
    if (!a) return;
    const context = activeContext();

    if (item.type === 'horizontal') {
      const color = preview ? 'rgba(96,165,250,.65)' : '#60a5fa';
      line(0, a.y, size.width, a.y, color, 1.3, [6,4]);
      tag(Number(item.p1.price).toFixed(2), size.width - 6, a.y, color);
      return;
    }

    const b = screen(item.p2);
    if (!b) return;

    if (item.type === 'trend') {
      line(a.x, a.y, b.x, b.y, preview ? 'rgba(34,211,238,.6)' : '#22d3ee', 1.7);
      return;
    }

    if (item.type === 'rectangle') {
      const x = Math.min(a.x,b.x), y = Math.min(a.y,b.y), w = Math.abs(b.x-a.x), h = Math.abs(b.y-a.y);
      state.ctx.save();
      state.ctx.fillStyle = 'rgba(99,102,241,.12)';
      state.ctx.strokeStyle = 'rgba(129,140,248,.92)';
      state.ctx.fillRect(x,y,w,h); state.ctx.strokeRect(x,y,w,h); state.ctx.restore();
      return;
    }

    if (item.type === 'fib') {
      [0,.236,.382,.5,.618,.786,1].forEach(level => {
        const price = item.p1.price + (item.p2.price-item.p1.price)*level;
        const y = context.series.priceToCoordinate?.(price);
        if (y == null) return;
        line(Math.min(a.x,b.x), y, Math.max(a.x,b.x), y, '#fbbf24', level === .5 || level === .618 ? 1.4 : .9, [4,4]);
      });
      return;
    }

    if (item.type === 'risk') {
      const entry = Number(item.p1.price), stop = Number(item.p2.price), risk = Math.abs(entry-stop);
      if (!(risk > 0)) return;
      const target = entry + (stop < entry ? 1 : -1) * risk * 2;
      const targetY = context.series.priceToCoordinate?.(target);
      if (targetY == null) return;
      const x = Math.min(a.x,b.x), w = Math.max(60, Math.abs(b.x-a.x)+70);
      state.ctx.save();
      state.ctx.fillStyle = 'rgba(34,197,94,.12)'; state.ctx.fillRect(x,Math.min(a.y,targetY),w,Math.abs(a.y-targetY));
      state.ctx.fillStyle = 'rgba(244,63,94,.14)'; state.ctx.fillRect(x,Math.min(a.y,b.y),w,Math.abs(a.y-b.y));
      state.ctx.restore();
      line(x,a.y,x+w,a.y,'#60a5fa'); line(x,b.y,x+w,b.y,'#fb7185'); line(x,targetY,x+w,targetY,'#4ade80');
      tag('ENTRY',x+w-4,a.y,'#60a5fa'); tag('SL',x+w-4,b.y,'#fb7185'); tag('TP 2R',x+w-4,targetY,'#4ade80');
    }
  }

  function normalizeSymbol(value) {
    return String(value || '').toUpperCase().replace(/\.EC$/,'').replace(/[^A-Z0-9]/g,'');
  }

  function drawSignals(size) {
    if (!state.nexusOverlay) return;
    const symbol = normalizeSymbol(currentSymbol());
    if (!symbol) return;
    state.signals.filter(item => normalizeSymbol(item?.symbol) === symbol && String(item?.status || 'ACTIVE').toUpperCase() !== 'CLOSED').slice(0,2).forEach(signal => {
      const levels = [];
      const entry = number(signal.entry_price), sl = number(signal.stop_loss);
      if (entry != null) levels.push(['ENTRY',entry,'#38bdf8']);
      if (sl != null) levels.push(['SL',sl,'#fb7185']);
      (Array.isArray(signal.targets) ? signal.targets : []).slice(0,3).forEach((target,index) => {
        const p = number(target?.price); if (p != null) levels.push([`TP${target.target_no || index+1}`,p,'#4ade80']);
      });
      levels.forEach(([name,price,color]) => {
        const y = activeContext()?.series?.priceToCoordinate?.(price);
        if (y == null) return;
        line(0,y,size.width,y,color,name === 'ENTRY' ? 1.6 : 1.1,name === 'ENTRY' ? [] : [6,4]);
        tag(`NEXUS ${name}${signal.code ? ` #${signal.code}` : ''}`,size.width-6,y,color);
      });
    });
  }

  function draw() {
    const size = clearSurface();
    if (!size || !activeContext()) return;
    drawings().forEach(item => drawItem(item,size,false));
    drawSignals(size);
    if (state.tool && state.first && state.hover) drawItem({type:state.tool,p1:state.first,p2:state.hover},size,true);
  }

  function undo() {
    const next = drawings();
    next.pop();
    save(next);
    hint('آخرین رسم حذف شد');
  }

  function clear() {
    save([]);
    state.first = null; state.hover = null;
    hint('رسم‌های این نماد و تایم‌فریم پاک شد');
  }

  function toggleNexus() {
    state.nexusOverlay = !state.nexusOverlay;
    try { localStorage.setItem('nexus:chart:nexus-overlay:v23',state.nexusOverlay ? '1':'0'); } catch (_) {}
    syncButtons();
    hint(state.nexusOverlay ? 'NEXUS Overlay فعال شد' : 'NEXUS Overlay خاموش شد');
    draw();
  }

  async function toggleFullscreen() {
    const page = document.querySelector(PAGE);
    if (!page) return;
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (page.requestFullscreen) {
        await page.requestFullscreen();
      } else {
        page.classList.toggle('nexus-chart-pseudo-fullscreen');
      }
    } catch (_) {
      page.classList.toggle('nexus-chart-pseudo-fullscreen');
    }
    setTimeout(resizeCanvas,50);
  }

  async function refreshSignals() {
    if (!document.querySelector(PAGE)) return;
    const initData = window.Telegram?.WebApp?.initData || '';
    if (!initData) return;
    try {
      const response = await fetch('/miniapp/api/signals?state=ACTIVE&access=ALL&limit=20&offset=0', {
        cache: 'no-store',
        headers: { 'X-Telegram-Init-Data': initData },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      state.signals = Array.isArray(data?.items) ? data.items : [];
      draw();
    } catch (_) {
      state.signals = [];
      draw();
    }
  }

  function recoverContextIfNeeded() {
    if (!document.querySelector(PAGE) || activeContext() || !state.factoryReady || state.recoveryAttempted) return;
    state.recoveryAttempted = true;
    hint('در حال اتصال ابزارها به موتور چارت...');
    if (!window.NexusLiveCharts?.open) return;
    setTimeout(() => {
      if (!activeContext() && document.querySelector(PAGE)) {
        window.NexusLiveCharts.open();
      }
    }, 80);
  }

  function initPage(page) {
    if (!page) return;
    if (state.page !== page) {
      state.page = page;
      state.first = null; state.hover = null;
      state.recoveryAttempted = false;
      try { state.nexusOverlay = localStorage.getItem('nexus:chart:nexus-overlay:v23') !== '0'; } catch (_) {}
    }
    ensureToolbar(page);
    ensureCanvas(page);
    syncButtons();
    refreshSignals();
    clearInterval(state.signalTimer);
    state.signalTimer = setInterval(refreshSignals,10000);
    clearInterval(state.redrawTimer);
    state.redrawTimer = setInterval(draw,200);
    setTimeout(recoverContextIfNeeded,180);
  }

  function teardown() {
    state.resizeObserver?.disconnect?.(); state.resizeObserver = null;
    state.canvas = null; state.ctx = null; state.page = null;
    state.first = null; state.hover = null;
    clearInterval(state.signalTimer); state.signalTimer = null;
    clearInterval(state.redrawTimer); state.redrawTimer = null;
  }

  const observer = new MutationObserver(() => {
    const page = document.querySelector(PAGE);
    if (page) initPage(page); else if (state.page) teardown();
  });
  observer.observe(document.getElementById('view') || document.body,{childList:true,subtree:true});

  document.addEventListener('click',event => {
    if (event.target.closest?.('[data-live-symbol],[data-live-fx],[data-live-timeframe]')) {
      state.first = null; state.hover = null; state.recoveryAttempted = false;
      setTimeout(() => { draw(); recoverContextIfNeeded(); },120);
    }
  },true);
  document.addEventListener('fullscreenchange',() => setTimeout(resizeCanvas,50));
  window.addEventListener('resize',resizeCanvas,{passive:true});

  installFactory();
  initPage(document.querySelector(PAGE));

  window.NexusChartTools = {
    select: selectTool,
    undo,
    clear,
    redraw: draw,
    contextReady: () => Boolean(activeContext()),
    scope: () => `${currentSymbol()}:${currentTimeframe()}`,
  };
})();
