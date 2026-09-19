(() => {
  'use strict';

  const tg = window.Telegram?.WebApp;
  tg?.ready();
  tg?.expand();

  const API = '/miniapp/api/admin';
  const $ = (id) => document.getElementById(id);
  const state = {
    setupMode: 'MANUAL',
    side: 'BUY',
    destination: 'BOTH',
    volumeMode: 'RISK',
    autoSide: 'BUY',
    autoDestination: 'BOTH',
    autoVolumeMode: 'RISK',
    calculation: null,
    preview: null,
    mt5: null,
    loadingSignals: false,
    loadingPositions: false,
    entrySource: 'MANUAL',
  };

  const headers = () => ({
    'Content-Type': 'application/json',
    ...(tg?.initData ? {'X-Telegram-Init-Data': tg.initData} : {}),
  });

  async function api(path, options = {}) {
    const response = await fetch(API + path, {
      ...options,
      headers: {...headers(), ...(options.headers || {})},
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || 'خطا در ارتباط با سرور');
    return body;
  }

  function toast(message) {
    const box = $('toast');
    if (!box) return;
    box.textContent = message;
    box.classList.add('show');
    clearTimeout(window.__adminToastTimer);
    window.__adminToastTimer = setTimeout(() => box.classList.remove('show'), 2800);
  }

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  }

  function adminSymbolIcon(symbol) {
    return window.NexusSymbolVisuals?.icon?.(symbol) || window.NexusSymbolVisuals?.mark?.(symbol) || '';
  }

  function fa(value) {
    return new Intl.NumberFormat('fa-IR', {maximumFractionDigits: 8}).format(Number(value || 0));
  }

  function numeric(id) {
    const raw = String($(id)?.value || '').trim().replace(/,/g, '.');
    if (!raw) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  function signed(value, digits = 2) {
    const number = Number(value);
    return Number.isFinite(number) ? `${number > 0 ? '+' : ''}${number.toFixed(digits)}` : '—';
  }

  function adminSignalPnlClass(live) {
    const status = String(live?.status || '').toUpperCase();
    if (status !== 'LIVE') return '';
    const pnlState = String(live?.pnl_state || '').toUpperCase();
    if (pnlState === 'IN_PROFIT') return 'pnl-profit';
    if (pnlState === 'IN_LOSS') return 'pnl-loss';
    return '';
  }

  function pulse(status) {
    const current = String(status || 'UNAVAILABLE').toLowerCase();
    return `<span class="admin-live-pulse ${esc(current)}" aria-hidden="true"><svg viewBox="0 0 64 48"><polyline class="pulse-back" points="0.157 23.954, 14 23.954, 21.843 48, 43 0, 50 24, 64 24"></polyline><polyline class="pulse-front" points="0.157 23.954, 14 23.954, 21.843 48, 43 0, 50 24, 64 24"></polyline></svg></span>`;
  }

  function liveBlock(live) {
    if (!live) return '';
    const status = String(live.status || 'UNAVAILABLE').toUpperCase();
    const pnlState = String(live.pnl_state || '').toLowerCase();
    const sync = live.age_seconds != null ? `${Math.round(Number(live.age_seconds))}s ago` : '—';
    const label = status === 'LIVE' ? 'MT5 LIVE' : status === 'PENDING' ? 'MT5 PENDING' : status === 'STALE' ? 'STALE' : 'LIVE DATA UNAVAILABLE';
    if (status === 'UNAVAILABLE') {
      return `<div class="admin-live unavailable"><div class="admin-live-head">${pulse(status)}<b>${label}</b><small>—</small></div></div>`;
    }
    return `<div class="admin-live ${esc(status.toLowerCase())}"><div class="admin-live-head">${pulse(status)}<b>${label}</b><small>${esc(sync)}</small></div><div class="admin-live-grid"><span>CURRENT<b>${esc(live.current_price ?? '—')}</b></span><span>FLOATING P&amp;L<b class="${esc(pnlState)}">${signed(live.floating_pnl)}</b></span><span>CURRENT R<b>${live.current_r == null ? '—' : signed(live.current_r) + 'R'}</b></span><span>VOLUME<b>${esc(live.volume ?? '—')}</b></span><span>LIVE SL<b>${esc(live.stop_loss ?? '—')}</b></span><span>LIVE TP<b>${esc(live.take_profit ?? '—')}</b></span></div></div>`;
  }

  function show(view) {
    document.querySelectorAll('.view').forEach((node) => node.classList.toggle('active', node.id === view));
    document.querySelectorAll('.bottom button').forEach((button) => button.classList.toggle('selected', button.dataset.view === view));
    if (view === 'positions') loadPositions();
    if (view === 'logs') loadSignals();
  }

  function setMt5(mt5) {
    state.mt5 = mt5;
    const chip = $('mt5Chip');
    if (!chip) return;
    chip.className = 'chip ' + (mt5?.online ? 'online' : 'offline');
    chip.querySelector('span').textContent = mt5?.online ? 'MT5 متصل' : 'MT5 آفلاین';
  }

  function selectButtons(selector, activeButton) {
    document.querySelectorAll(selector).forEach((button) => button.classList.toggle('selected', button === activeButton));
  }

  function syncModeUI() {
    const auto = state.setupMode === 'AUTO';
    $('manualSetupFields').hidden = auto;
    $('autoSetupFields').hidden = !auto;
    selectButtons('.setup-mode button', document.querySelector(`.setup-mode button[data-mode="${state.setupMode}"]`));
    state.calculation = null;
    state.preview = null;
    if (!auto) scheduleRecalculate();
  }

  function clearManualCalculation(message = 'Entry و Stop Loss را وارد کنید.') {
    state.calculation = null;
    const risk = $('riskBox')?.querySelector('b');
    if (risk) risk.textContent = '—';
    if ($('targets')) $('targets').innerHTML = `<p>${esc(message)}</p>`;
  }

  async function recalculate() {
    if (state.setupMode !== 'MANUAL') return;
    const entry = numeric('entry');
    const stop = numeric('stopLoss');
    if (!entry || !stop || entry <= 0 || stop <= 0) {
      clearManualCalculation();
      return;
    }
    try {
      const calc = await api('/signals/calculate', {
        method: 'POST',
        body: JSON.stringify({symbol: $('symbol').value, direction: state.side, entry, stop_loss: stop}),
      });
      state.calculation = calc;
      $('riskBox').querySelector('b').textContent = fa(calc.risk);
      $('targets').innerHTML = calc.targets.map((value, index) => `<article><small>TP${index + 1} · ${esc(calc.target_multipliers?.[index] ?? '—')}R</small><b>${fa(value)}</b></article>`).join('');
    } catch (error) {
      clearManualCalculation(error.message);
    }
  }

  function scheduleRecalculate() {
    clearTimeout(window.__adminCalcTimer);
    window.__adminCalcTimer = setTimeout(recalculate, 220);
  }

  function requestId() {
    return `tg-${tg?.initDataUnsafe?.user?.id || 'admin'}-${Date.now()}-${crypto.randomUUID?.() || Math.random().toString(36).slice(2)}`;
  }

  function openManualPreview() {
    if (state.setupMode !== 'MANUAL') return;
    const calc = state.calculation;
    if (!calc) return toast('ابتدا Entry و Stop Loss معتبر وارد کنید.');
    const lot = state.volumeMode === 'FIXED' ? numeric('lotSize') : null;
    const riskPercent = state.volumeMode === 'RISK' ? numeric('riskPercent') : null;
    if (state.volumeMode === 'FIXED' && (!lot || lot <= 0)) return toast('در حالت Fixed Lot وارد کردن حجم معتبر اجباری است.');
    if (state.volumeMode === 'RISK' && (!riskPercent || riskPercent <= 0 || riskPercent > 100)) return toast('درصد ریسک معتبر وارد کنید.');
    state.preview = {
      symbol: calc.symbol, direction: calc.direction, entry: calc.entry, stop_loss: calc.stop_loss,
      risk: calc.risk, targets: calc.targets, destination: state.destination, timeframe: $('timeframe').value,
      request_id: requestId(), digits: calc.digits, setup_mode: 'MANUAL', trailing_code: $('trailing').value,
      volume_mode: state.volumeMode, lot_size: lot, risk_percent: riskPercent,
    };
    $('preview').innerHTML = `<div class="preview-hero"><strong class="admin-symbol-identity">${adminSymbolIcon(calc.symbol)}<span>${esc(calc.symbol)}</span></strong><em>${esc(calc.direction)}</em></div><div class="preview-grid"><div><span>ورود</span><b>${fa(calc.entry)}</b></div><div><span>منبع ورود</span><b>${esc(state.entrySource)}</b></div><div><span>حد ضرر</span><b>${fa(calc.stop_loss)}</b></div><div><span>Initial R</span><b>${fa(calc.risk)}</b></div><div><span>Timeframe</span><b>${esc($('timeframe').value)}</b></div><div><span>Trailing</span><b>${esc($('trailing').value)}</b></div><div><span>Volume</span><b>${esc(state.volumeMode)} · ${esc(lot ?? riskPercent)}${lot ? ' lot' : '%'}</b></div><div><span>Destination</span><b>${esc(state.destination)}</b></div>${calc.targets.map((value, index) => `<div><span>TP${index + 1}</span><b>${fa(value)}</b></div>`).join('')}<div><span>MT5 Admin</span><b>${state.mt5?.online ? 'ONLINE' : 'OFFLINE · WAITING'}</b></div></div>`;
    $('modal').hidden = false;
  }

  function validateAutoSetup() {
    if (state.setupMode !== 'AUTO') return;
    const symbol = String($('autoSymbol').value || '').trim().toUpperCase();
    const entry = numeric('autoEntry');
    const timeframe = $('autoTimeframe').value;
    const trailing = $('autoTrailing').value;
    const lot = state.autoVolumeMode === 'FIXED' ? numeric('autoLotSize') : null;
    const riskPercent = state.autoVolumeMode === 'RISK' ? numeric('autoRiskPercent') : null;
    if (!symbol) return toast('نماد Auto Setup را وارد کنید.');
    if (!entry || entry <= 0) return toast('قیمت ورود Auto Setup را وارد کنید.');
    if (state.autoVolumeMode === 'FIXED' && (!lot || lot <= 0)) return toast('حجم Fixed Lot معتبر وارد کنید.');
    if (state.autoVolumeMode === 'RISK' && (!riskPercent || riskPercent <= 0 || riskPercent > 100)) return toast('درصد ریسک معتبر وارد کنید.');
    $('autoTimeframeValue').textContent = timeframe;
    $('autoTrailingValue').textContent = trailing;
    $('autoVolumeValue').textContent = state.autoVolumeMode;
    toast('تنظیمات Auto Setup معتبر است؛ Structure Engine هنوز متصل نیست و انتشار Fail-Closed باقی می‌ماند.');
  }

  async function publish() {
    if (!state.preview) return;
    const button = $('publish');
    button.disabled = true;
    button.textContent = 'در حال ثبت امن…';
    try {
      const result = await api('/signals', {method: 'POST', body: JSON.stringify(state.preview)});
      $('modal').hidden = true;
      toast(result.status === 'WAITING_FOR_MT5' ? 'ثبت شد؛ منتظر اتصال MT5 است.' : 'درخواست برای MT5 ارسال شد.');
      show('logs');
      await loadSignals();
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = 'تأیید و ارسال';
    }
  }

  async function useMarketPrice() {
    try {
      const symbol = String($('symbol').value || '').trim();
      if (!symbol) return toast('ابتدا نماد را انتخاب کنید.');
      const quote = await api(`/market-quote?symbol=${encodeURIComponent(symbol)}`);
      const age = Number(quote.age_seconds);
      if (!quote.fresh || !Number.isFinite(age) || age > 15) throw new Error('قیمت بازار تازه نیست؛ ورود دستی را استفاده کنید.');
      const price = Number(state.side === 'BUY' ? quote.ask : quote.bid);
      if (!Number.isFinite(price) || price <= 0) throw new Error('Bid/Ask معتبر موجود نیست.');
      $('entry').value = String(price);
      state.entrySource = 'MARKET';
      $('quoteStatus').textContent = `${state.side === 'BUY' ? 'Ask' : 'Bid'} ${price} · ${Math.round(age)}s`;
      scheduleRecalculate();
    } catch (error) {
      state.entrySource = 'MANUAL';
      $('quoteStatus').textContent = 'قیمت معتبر MT5 موجود نیست؛ ورود دستی الزامی است.';
      toast(error.message);
    }
  }

  function signalCard(item, {allowRetry = true} = {}) {
    const payload = JSON.parse(item.payload_json || '{}');
    const status = String(item.status || 'UNKNOWN').toUpperCase();
    const job = String(item.chart_job?.status || '').toUpperCase();
    const stage = String(item.signal?.publication_stage || '').toUpperCase();
    const entry = payload.entry ?? item.signal?.entry_price ?? '—';
    const pnlClass = adminSignalPnlClass(item.live);
    const retryable = ['FAILED', 'PUBLISH_FAILED', 'EXPIRED'].includes(status) || (['UPLOADED', 'COMPLETED'].includes(job) && status !== 'PUBLISHED' && stage !== 'PUBLISHED');
    const retry = allowRetry && retryable ? `<button class="outline retry-signal" data-request-id="${esc(item.request_id)}">تلاش مجدد</button>` : '';
    return `<article class="card ${esc(pnlClass)}"><div class="card-head"><strong class="admin-symbol-identity">${adminSymbolIcon(payload.symbol || item.signal?.symbol)}<span>${item.signal?.code ? esc(item.signal.code) + ' · ' : ''}${esc(payload.symbol || item.signal?.symbol || '—')} · ${esc(payload.direction || item.signal?.direction || '')}</span></strong><span class="status ${esc(status)}">${esc(status)}</span></div><div class="levels"><span>ENTRY<b>${esc(entry)}</b></span><span>SL<b>${esc(payload.stop_loss ?? item.signal?.stop_loss ?? '—')}</b></span><span>DEST<b>${esc(payload.destination || item.signal?.destination || '—')}</b></span></div>${liveBlock(item.live)}${item.error_message ? `<p class="admin-signal-error">${esc(item.error_message)}</p>` : ''}${retry}</article>`;
  }

  async function retrySignal(button) {
    button.disabled = true;
    try {
      const result = await api(`/signals/${encodeURIComponent(button.dataset.requestId)}/retry`, {method: 'POST'});
      toast(result.publication === 'RETRY_QUEUED' ? 'انتشار مجدد در صف قرار گرفت.' : 'درخواست همان سیگنال احیا شد.');
      await loadSignals();
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function loadSignals() {
    if (state.loadingSignals) return;
    state.loadingSignals = true;
    try {
      const [data, canonical, rejected] = await Promise.all([api('/signals'), api('/active-signals'), api('/rejected-logs')]);
      setMt5(data.mt5_admin);
      const operational = canonical.items || [];
      $('signalList').innerHTML = operational.length ? operational.map((item) => signalCard(item, {allowRetry: false})).join('') : '<div class="empty">سیگنال عملیاتی منتشرشده‌ای وجود ندارد.</div>';
      const rejectedItems = rejected.items || [];
      $('logList').innerHTML = rejectedItems.length ? rejectedItems.map((item) => signalCard(item, {allowRetry: false})).join('') : '<div class="empty">درخواست ردشده‌ای وجود ندارد.</div>';
      $('publishedCount').textContent = fa(operational.length);
    } catch (error) {
      toast(error.message);
    } finally {
      state.loadingSignals = false;
    }
  }

  function positionCard(position, isOrder = false) {
    const signalId = Number(position.signal_id || 0);
    const account = esc(state.mt5?.account_number || '');
    const rawProfit = position.floating_pnl ?? position.profit ?? position.pnl ?? position.profit_float;
    const profit = rawProfit == null ? null : Number(rawProfit);
    const age = position.last_seen_at ? Math.max(0, Math.round((Date.now() - new Date(position.last_seen_at).getTime()) / 1000)) : null;
    const freshness = !state.mt5?.online ? 'OFFLINE' : age == null ? 'UNAVAILABLE' : age > 120 ? 'STALE' : isOrder ? 'PENDING' : 'LIVE';
    const actions = signalId ? `<details class="admin-action-sheet"><summary>اقدامات ${isOrder ? 'سفارش' : 'پوزیشن'}</summary><div class="trade-actions" data-signal="${signalId}" data-account="${account}">${isOrder ? '<button data-command="CANCEL_PENDING" class="danger">لغو Pending</button>' : '<button data-command="MOVE_SL_TO_ENTRY" class="safe">Break Even</button><button data-command="PARTIAL_CLOSE">Partial Close</button><button data-command="ACTIVATE_TRAILING">Trailing</button><button data-command="UPDATE_SL">تغییر SL</button><button data-command="UPDATE_TP">تغییر TP</button><button data-command="CLOSE_SIGNAL" class="danger">بستن معامله</button>'}</div></details>` : '';
    return `<article class="card"><div class="card-head"><strong class="admin-symbol-identity">${adminSymbolIcon(position.symbol)}<span>${position.signal_code ? esc(position.signal_code) + ' · ' : ''}${esc(position.symbol || '—')} · ${esc(position.direction || position.type || '')}</span></strong><span class="status">${freshness}</span></div><div class="levels admin-position-levels"><span>TICKET<b>${esc(position.ticket || '—')}</b></span><span>ENTRY<b>${esc(position.entry_price ?? position.price_open ?? '—')}</b></span><span>CURRENT<b>${esc(position.current_price ?? '—')}</b></span><span>VOLUME<b>${esc(position.volume ?? '—')}</b></span><span>P&amp;L<b class="${profit > 0 ? 'profit' : profit < 0 ? 'loss' : 'flat'}">${rawProfit == null ? '—' : signed(profit)}</b></span><span>SL / TP<b>${esc(position.stop_loss ?? '—')} / ${esc(position.take_profit ?? '—')}</b></span></div><div class="admin-position-sync">Last MT5 Sync: ${age == null ? '—' : esc(age + 's ago')}</div>${actions}</article>`;
  }

  async function loadPositions() {
    if (state.loadingPositions) return;
    state.loadingPositions = true;
    try {
      const data = await api('/positions');
      setMt5(data.mt5_admin);
      const open = data.positions || [], pending = data.orders || [];
      $('positionList').innerHTML = `<h3>Open Positions</h3>${open.map((item) => positionCard(item)).join('') || '<div class="empty">پوزیشن بازی وجود ندارد.</div>'}<h3>Pending Orders</h3>${pending.map((item) => positionCard(item, true)).join('') || '<div class="empty">سفارش Pending وجود ندارد.</div>'}`;
      $('positionCount').textContent = fa(state.mt5?.online ? open.filter(item => item.last_seen_at && Date.now() - new Date(item.last_seen_at).getTime() <= 120000).length : 0);
    } catch (error) {
      toast(error.message);
    } finally {
      state.loadingPositions = false;
    }
  }

  async function sendCommand(button) {
    const box = button.closest('.trade-actions');
    const command = button.dataset.command;
    let value = null;
    if (['UPDATE_SL', 'UPDATE_TP', 'PARTIAL_CLOSE'].includes(command)) {
      value = prompt(command === 'PARTIAL_CLOSE' ? 'درصد یا حجم Partial Close را وارد کنید:' : 'مقدار جدید را وارد کنید:');
      if (value === null || !String(value).trim()) return;
    }
    if (['CLOSE_SIGNAL', 'CANCEL_PENDING'].includes(command) && !confirm('این عملیات روی MT5 اجرا می‌شود. ادامه می‌دهید؟')) return;
    button.disabled = true;
    try {
      await api(`/signals/${box.dataset.signal}/command`, {method: 'POST', body: JSON.stringify({command, account_number: box.dataset.account, value})});
      toast('فرمان در صف اجرای MT5 ثبت شد.');
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function bootstrap() {
    try {
      const data = await api('/bootstrap');
      setMt5(data.mt5_admin);
      await Promise.all([loadSignals(), loadPositions()]);
    } catch (error) {
      toast(error.message);
      $('signalList').innerHTML = '<div class="empty">این صفحه فقط از داخل تلگرام و برای ادمین‌های مجاز فعال است.</div>';
    }
  }

  document.querySelectorAll('.bottom button').forEach((button) => button.addEventListener('click', () => show(button.dataset.view)));
  document.querySelectorAll('.setup-mode button').forEach((button) => button.addEventListener('click', () => { state.setupMode = button.dataset.mode; syncModeUI(); }));
  document.querySelectorAll('.manual-direction button').forEach((button) => button.addEventListener('click', () => { state.side = button.dataset.side; selectButtons('.manual-direction button', button); scheduleRecalculate(); }));
  document.querySelectorAll('.auto-direction button').forEach((button) => button.addEventListener('click', () => { state.autoSide = button.dataset.autoSide; selectButtons('.auto-direction button', button); }));
  document.querySelectorAll('.destination button').forEach((button) => button.addEventListener('click', () => { state.destination = button.dataset.value; selectButtons('.destination button', button); }));
  document.querySelectorAll('.auto-destination button').forEach((button) => button.addEventListener('click', () => { state.autoDestination = button.dataset.autoDestination; selectButtons('.auto-destination button', button); }));
  document.querySelectorAll('.volume-mode button').forEach((button) => button.addEventListener('click', () => { state.volumeMode = button.dataset.volume; selectButtons('.volume-mode button', button); $('fixedLotLabel').hidden = state.volumeMode !== 'FIXED'; $('riskPercentLabel').hidden = state.volumeMode !== 'RISK'; }));
  document.querySelectorAll('.auto-volume-mode button').forEach((button) => button.addEventListener('click', () => { state.autoVolumeMode = button.dataset.autoVolume; selectButtons('.auto-volume-mode button', button); $('autoFixedLotLabel').hidden = state.autoVolumeMode !== 'FIXED'; $('autoRiskPercentLabel').hidden = state.autoVolumeMode !== 'RISK'; $('autoVolumeValue').textContent = state.autoVolumeMode; }));

  ['symbol', 'entry', 'stopLoss'].forEach((id) => $(id)?.addEventListener('input', scheduleRecalculate));
  $('entry')?.addEventListener('input', () => { state.entrySource = 'MANUAL'; $('quoteStatus').textContent = 'ورود دستی'; });
  $('useMarketPrice')?.addEventListener('click', useMarketPrice);
  $('clearRejectedLogs')?.addEventListener('click', async () => {
    if (!confirm('فقط درخواست‌های ردشده پاک شوند؟ تاریخچه سیگنال و معاملات محفوظ می‌ماند.')) return;
    try { const result = await api('/rejected-logs', {method: 'DELETE'}); toast(`${result.deleted} لاگ ردشده پاک شد.`); await loadSignals(); }
    catch (error) { toast(error.message); }
  });
  $('autoTimeframe')?.addEventListener('change', () => $('autoTimeframeValue').textContent = $('autoTimeframe').value);
  $('autoTrailing')?.addEventListener('change', () => $('autoTrailingValue').textContent = $('autoTrailing').value);
  $('autoValidate')?.addEventListener('click', validateAutoSetup);
  $('signalForm').addEventListener('submit', (event) => { event.preventDefault(); if (state.setupMode === 'MANUAL') openManualPreview(); });
  $('publish').addEventListener('click', publish);
  $('recalculatePreview').addEventListener('click', () => { $('modal').hidden = true; scheduleRecalculate(); });
  $('newSignal').addEventListener('click', () => show('create'));
  $('refresh').addEventListener('click', bootstrap);
  $('reloadSignals').addEventListener('click', loadSignals);
  $('reloadPositions').addEventListener('click', loadPositions);
  $('closeModal').addEventListener('click', () => { $('modal').hidden = true; });
  $('cancelPreview').addEventListener('click', () => { $('modal').hidden = true; });
  $('positionList').addEventListener('click', (event) => { const button = event.target.closest('button[data-command]'); if (button) sendCommand(button); });
  ['signalList', 'logList'].forEach((id) => $(id)?.addEventListener('click', (event) => { const button = event.target.closest('.retry-signal'); if (button) retrySignal(button); }));

  syncModeUI();
  bootstrap();

  setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    if (document.querySelector('#positions.view.active')) loadPositions();
  }, 5000);

  setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    if (document.querySelector('#dashboard.view.active') || document.querySelector('#logs.view.active')) loadSignals();
  }, 5000);
})();
