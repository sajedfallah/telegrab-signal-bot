(() => {
  const tg = window.Telegram?.WebApp;
  tg?.ready();
  tg?.expand();

  const API = '/miniapp/api/admin';
  const FALLBACK_TRAILING = [
    {
      code: 'NEXUS_TRAIL_01',
      name: 'اسکالپینگ محافظه‌کارانه',
      guide: 'در 1R به Break Even می‌رود و سپس حد ضرر را پله‌ای جلو می‌آورد تا سود زودتر محافظت شود.',
      config: {break_even_r: 1.0, trail_step_r: 0.50, lock_step_r: 0.30},
    },
    {
      code: 'NEXUS_TRAIL_02',
      name: 'Step Profit Lock',
      guide: 'قفل سود مرحله‌ای؛ در 1R استاپ روی ورود، در 2R روی +1R و در 3R روی +2R قرار می‌گیرد.',
      config: {steps: [{trigger_r: 1, lock_r: 0}, {trigger_r: 2, lock_r: 1}, {trigger_r: 3, lock_r: 2}]},
    },
    {
      code: 'NEXUS_TRAIL_03',
      name: 'Dynamic ATR',
      guide: 'فاصله Stop بر اساس نوسان ATR تغییر می‌کند؛ در بازار پرنوسان بازتر و در بازار آرام فشرده‌تر می‌شود.',
      config: {activation_r: 1.0, atr_period: 14, atr_multiplier: 2.0},
    },
    {
      code: 'NEXUS_TRAIL_04',
      name: 'ساختار بازار',
      guide: 'در BUY استاپ زیر Swing Low معتبر و در SELL بالای Swing High معتبر حرکت می‌کند و هرگز عقب نمی‌رود.',
      config: {activation_r: 1.0, swing_left: 2, swing_right: 2, buffer_points: 0},
    },
    {
      code: 'NEXUS_TRAIL_05',
      name: 'VIP Runner',
      guide: 'در TP1 و TP2 بخشی از حجم بسته می‌شود و Runner با ساختار بازار و ATR پشتیبان مدیریت می‌شود.',
      config: {tp1_close_pct: 30, tp2_close_pct: 30, runner_pct: 40, runner_mode: 'MARKET_STRUCTURE_ATR_FALLBACK', atr_period: 14, atr_multiplier: 2},
    },
    {
      code: 'NEXUS_TRAIL_06',
      name: 'Fast Scalping',
      guide: 'مدل سریع‌تر اسکالپ؛ Break Even در 0.5R و حرکت‌های تریلینگ فشرده‌تر برای حفاظت سریع سود.',
      config: {break_even_r: 0.50, trail_step_r: 0.35, lock_step_r: 0.25},
    },
    {
      code: 'NEXUS_TRAIL_07',
      name: 'NEXUS Smart Hybrid',
      guide: 'مدل هیبرید اصلی NEXUS؛ Break Even، Partial Close، ساختار بازار و ATR fallback را ترکیب می‌کند.',
      config: {break_even_r: 1.0, tp1_close_pct: 30, tp2_close_pct: 30, runner_pct: 40, runner_mode: 'MARKET_STRUCTURE_ATR_FALLBACK', atr_period: 14, atr_multiplier: 2, swing_left: 2, swing_right: 2},
    },
  ];

  const state = {
    side: 'BUY',
    destination: 'BOTH',
    stopMode: 'MANUAL',
    tpMode: 'AUTO',
    volumeMode: 'RISK',
    calculation: null,
    mt5: null,
    preview: null,
    trailingProfiles: [...FALLBACK_TRAILING],
  };

  const $ = (id) => document.getElementById(id);
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
    $('toast').textContent = message;
    $('toast').classList.add('show');
    setTimeout(() => $('toast').classList.remove('show'), 2800);
  }

  function fa(value) {
    return new Intl.NumberFormat('fa-IR', {maximumFractionDigits: 8}).format(Number(value || 0));
  }

  function numeric(id) {
    const raw = String($(id)?.value || '').trim();
    if (!raw) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  }

  function show(view) {
    document.querySelectorAll('.view').forEach((x) => x.classList.toggle('active', x.id === view));
    document.querySelectorAll('.bottom button').forEach((x) => x.classList.toggle('selected', x.dataset.view === view));
    if (view === 'positions') loadPositions();
    if (view === 'logs') loadSignals();
  }

  function setMt5(mt5) {
    state.mt5 = mt5;
    const chip = $('mt5Chip');
    chip.className = 'chip ' + (mt5?.online ? 'online' : 'offline');
    chip.querySelector('span').textContent = mt5?.online ? 'MT5 متصل' : 'MT5 آفلاین';
  }

  function populateSymbols(groups) {
    if (!Array.isArray(groups) || !groups.length) return;
    const select = $('symbol');
    const current = select.value || 'XAUUSD';
    const labels = {GOLD: 'فلزات', INDEX: 'شاخص‌ها', FOREX: 'Forex', CRYPTO: 'Crypto'};
    const pretty = {
      XAUUSD: 'Gold · XAUUSD', XAGUSD: 'Silver · XAGUSD',
      DOWJONES: 'Dow Jones · DOWJONES', NASDAQ: 'Nasdaq · NASDAQ', SPX500: 'S&P 500 · SPX500',
      BTCUSD: 'Bitcoin · BTCUSD', ETHUSD: 'Ethereum · ETHUSD', SOLUSD: 'Solana · SOLUSD',
      BNBUSD: 'BNB · BNBUSD', XRPUSD: 'XRP · XRPUSD', DOGEUSD: 'DOGE · DOGEUSD',
      AVAXUSD: 'AVAX · AVAXUSD', LTCUSD: 'Litecoin · LTCUSD',
    };
    select.innerHTML = groups.map((group) => {
      const key = String(group.key || group.group || '').toUpperCase();
      const symbols = Array.isArray(group.symbols) ? group.symbols : [];
      return `<optgroup label="${esc(group.label || labels[key] || key)}">${symbols.map((symbol) => `<option value="${esc(symbol)}">${esc(pretty[symbol] || symbol)}</option>`).join('')}</optgroup>`;
    }).join('');
    if ([...select.options].some((option) => option.value === current)) select.value = current;
    else if ([...select.options].some((option) => option.value === 'XAUUSD')) select.value = 'XAUUSD';
  }

  function populateTrailingProfiles(items) {
    if (Array.isArray(items) && items.length) state.trailingProfiles = items;
    const select = $('trailingProfile');
    const current = select.value || 'NEXUS_TRAIL_01';
    select.innerHTML = state.trailingProfiles.map((profile) => {
      const number = String(profile.code || '').replace('NEXUS_TRAIL_', '');
      return `<option value="${esc(profile.code)}">${esc(number)} · ${esc(profile.name)}</option>`;
    }).join('');
    if (state.trailingProfiles.some((profile) => profile.code === current)) select.value = current;
    else select.value = state.trailingProfiles[0]?.code || 'NEXUS_TRAIL_01';
    renderTrailingPreview();
  }

  function trailingMechanics(profile) {
    const c = profile?.config || {};
    const tags = [];
    if (Array.isArray(c.steps)) {
      c.steps.forEach((step) => tags.push(`${step.trigger_r}R → ${Number(step.lock_r) === 0 ? 'BE' : `+${step.lock_r}R`}`));
    }
    if (c.break_even_r != null) tags.push(`BE ${c.break_even_r}R`);
    if (c.trail_step_r != null) tags.push(`STEP ${c.trail_step_r}R`);
    if (c.lock_step_r != null) tags.push(`LOCK ${c.lock_step_r}R`);
    if (c.activation_r != null) tags.push(`ACTIVE ${c.activation_r}R`);
    if (c.atr_period != null) tags.push(`ATR ${c.atr_period}`);
    if (c.atr_multiplier != null) tags.push(`ATR ×${c.atr_multiplier}`);
    if (c.swing_left != null || c.swing_right != null) tags.push(`SWING ${c.swing_left ?? 0}/${c.swing_right ?? 0}`);
    if (c.tp1_close_pct != null) tags.push(`TP1 CLOSE ${c.tp1_close_pct}%`);
    if (c.tp2_close_pct != null) tags.push(`TP2 CLOSE ${c.tp2_close_pct}%`);
    if (c.runner_pct != null) tags.push(`RUNNER ${c.runner_pct}%`);
    if (c.runner_mode) tags.push('STRUCTURE + ATR');
    return tags;
  }

  function selectedTrailingProfile() {
    const code = $('trailingProfile')?.value || 'NEXUS_TRAIL_01';
    return state.trailingProfiles.find((profile) => profile.code === code) || FALLBACK_TRAILING.find((profile) => profile.code === code) || FALLBACK_TRAILING[0];
  }

  function renderTrailingPreview() {
    const profile = selectedTrailingProfile();
    if (!profile || !$('trailingPreview')) return;
    const mechanics = trailingMechanics(profile);
    $('trailingPreview').innerHTML = `
      <div class="trail-preview-head"><b>${esc(profile.code)}</b><span>${esc(profile.name)}</span></div>
      <p>${esc(profile.guide || 'این مدل بر اساس Snapshot رسمی NEXUS در Expert اجرا می‌شود.')}</p>
      <div class="trail-mechanics">${mechanics.map((item) => `<span>${esc(item)}</span>`).join('')}</div>`;
  }

  async function bootstrap() {
    try {
      const data = await api('/bootstrap');
      setMt5(data.mt5_admin);
      populateSymbols(data.symbol_catalog);
      populateTrailingProfiles(data.trailing_profiles);
      await Promise.all([loadSignals(), loadPositions()]);
    } catch (e) {
      toast(e.message);
      populateTrailingProfiles(FALLBACK_TRAILING);
      $('signalList').innerHTML = '<div class="empty">این صفحه فقط از داخل تلگرام و برای ادمین‌های مجاز فعال است.</div>';
    }
  }

  function selectedManualTargets() {
    return [1, 2, 3, 4].map((n) => numeric(`manualTp${n}`));
  }

  function setResolvedSl(value) {
    $('resolvedSlBadge').textContent = value ? `SL ${fa(value)}` : '—';
  }

  function clearCalculation(message = 'مقادیر لازم را تکمیل کنید.') {
    state.calculation = null;
    $('riskBox').querySelector('b').textContent = '—';
    setResolvedSl(null);
    if (state.tpMode === 'AUTO') {
      $('targets').innerHTML = `<p>${message}</p>`;
    } else {
      $('manualTargetsResolved').innerHTML = `<p>${message}</p>`;
    }
  }

  function calculatePayload() {
    const entry = numeric('entry');
    if (!entry || entry <= 0) return null;

    const payload = {
      symbol: $('symbol').value,
      direction: state.side,
      entry,
      stop_loss_mode: state.stopMode,
      take_profit_mode: state.tpMode,
    };

    if (state.stopMode === 'MANUAL') {
      const stop = numeric('stopLoss');
      if (!stop || stop <= 0) return null;
      payload.stop_loss = stop;
    } else {
      const distance = numeric('stopDistance');
      if (!distance || distance <= 0) return null;
      payload.stop_distance = distance;
    }

    if (state.tpMode === 'MANUAL') {
      const targets = selectedManualTargets();
      if (targets.some((value) => !value || value <= 0)) return null;
      payload.targets = targets;
    }

    return payload;
  }

  function renderTargets(calc) {
    const cards = calc.targets.map((value, index) => {
      const multiple = calc.target_multipliers?.[index];
      const ratio = Number.isFinite(Number(multiple)) ? ` · ${Number(multiple).toFixed(2).replace(/\.00$/, '')}R` : '';
      return `<article><small>TP${index + 1}${ratio}</small><b>${fa(value)}</b></article>`;
    }).join('');

    if (state.tpMode === 'AUTO') $('targets').innerHTML = cards;
    else $('manualTargetsResolved').innerHTML = cards;
  }

  async function recalculate() {
    const payload = calculatePayload();
    if (!payload) {
      clearCalculation(state.tpMode === 'MANUAL' ? 'SL و چهار TP را کامل وارد کنید.' : 'Entry و تنظیمات SL را کامل وارد کنید.');
      return;
    }

    try {
      const calc = await api('/signals/calculate', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      state.calculation = calc;
      $('riskBox').querySelector('b').textContent = fa(calc.risk);
      setResolvedSl(calc.stop_loss);
      renderTargets(calc);
    } catch (e) {
      state.calculation = null;
      $('riskBox').querySelector('b').textContent = '—';
      setResolvedSl(null);
      const box = state.tpMode === 'AUTO' ? $('targets') : $('manualTargetsResolved');
      box.innerHTML = `<p>${e.message}</p>`;
    }
  }

  function requestId() {
    return `tg-${tg?.initDataUnsafe?.user?.id || 'admin'}-${Date.now()}-${crypto.randomUUID?.() || Math.random().toString(36).slice(2)}`;
  }

  function sizingPayload() {
    if (state.volumeMode === 'RISK') {
      const riskPercent = numeric('riskPercent');
      if (!riskPercent || riskPercent <= 0 || riskPercent > 100) {
        throw new Error('درصد ریسک باید بیشتر از صفر و حداکثر ۱۰۰ باشد.');
      }
      return {volume_mode: 'RISK', risk_percent: riskPercent, lot_size: null};
    }

    const lotSize = numeric('lotSize');
    if (!lotSize || lotSize <= 0) throw new Error('حجم Lot باید بیشتر از صفر باشد.');
    return {volume_mode: 'FIXED', risk_percent: 0, lot_size: lotSize};
  }

  function trailingPayload() {
    const enabled = Boolean($('trailingEnabled').checked);
    if (!enabled) {
      return {
        trailing_enabled: false,
        trailing_profile_code: null,
        trailing_break_even_r: null,
        trailing_step_r: null,
        trailing_lock_r: null,
      };
    }

    const profile = selectedTrailingProfile();
    if (!profile || !/^NEXUS_TRAIL_0[1-7]$/.test(String(profile.code || ''))) {
      throw new Error('یک مدل معتبر Trailing انتخاب کنید.');
    }

    return {
      trailing_enabled: true,
      trailing_profile_code: profile.code,
      trailing_break_even_r: null,
      trailing_step_r: null,
      trailing_lock_r: null,
    };
  }

  function openPreview() {
    const c = state.calculation;
    if (!c) return toast('ابتدا Entry، SL و TP را به‌صورت معتبر تکمیل کنید.');

    let sizing;
    let trailing;
    try {
      sizing = sizingPayload();
      trailing = trailingPayload();
    } catch (e) {
      return toast(e.message);
    }

    const payload = {
      symbol: c.symbol,
      direction: c.direction,
      entry: c.entry,
      stop_loss: c.stop_loss,
      stop_loss_mode: state.stopMode,
      stop_distance: state.stopMode === 'AUTO' ? numeric('stopDistance') : null,
      take_profit_mode: state.tpMode,
      targets: c.targets,
      destination: state.destination,
      timeframe: $('timeframe').value,
      request_id: requestId(),
      digits: c.digits,
      ...sizing,
      ...trailing,
    };

    state.preview = payload;

    const sizingText = sizing.volume_mode === 'RISK'
      ? `${fa(sizing.risk_percent)}% Risk`
      : `${fa(sizing.lot_size)} Lot`;
    const selectedTrail = selectedTrailingProfile();
    const trailingText = trailing.trailing_enabled
      ? `${selectedTrail.code} · ${selectedTrail.name}`
      : 'OFF';

    $('preview').innerHTML = `
      <div class="preview-hero"><strong>${esc(c.symbol)}</strong><em>${esc(c.direction)}</em></div>
      <div class="preview-grid">
        <div><span>ورود</span><b>${fa(c.entry)}</b></div>
        <div><span>SL · ${state.stopMode}</span><b>${fa(c.stop_loss)}</b></div>
        <div><span>ریسک قیمتی</span><b>${fa(c.risk)}</b></div>
        <div><span>حجم / ریسک</span><b>${esc(sizingText)}</b></div>
        ${c.targets.map((value, index) => `<div><span>TP${index + 1} · ${state.tpMode}</span><b>${fa(value)}</b></div>`).join('')}
        <div><span>Trailing</span><b>${esc(trailingText)}</b></div>
        <div><span>مقصد</span><b>${esc(state.destination)}</b></div>
        <div><span>MT5 Admin</span><b>${state.mt5?.online ? 'ONLINE' : 'OFFLINE · WAITING'}</b></div>
      </div>`;
    $('modal').hidden = false;
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
    } catch (e) {
      toast(e.message);
    } finally {
      button.disabled = false;
      button.textContent = 'ارسال به MT5';
    }
  }

  function signalCard(item) {
    const p = JSON.parse(item.payload_json || '{}');
    const job = String(item.chart_job?.status || '').toUpperCase();
    const stage = String(item.signal?.publication_stage || '').toUpperCase();
    const retryable = ['FAILED', 'PUBLISH_FAILED', 'EXPIRED'].includes(String(item.status).toUpperCase()) ||
      (['UPLOADED', 'COMPLETED'].includes(job) && item.status !== 'PUBLISHED' && stage !== 'PUBLISHED');
    const retry = retryable ? `<button class="outline retry-signal" data-request-id="${esc(item.request_id)}">تلاش مجدد</button>` : '';
    const sizing = p.volume_mode === 'FIXED' ? `${p.lot_size || '—'} LOT` : `${p.risk_percent ?? '—'}% RISK`;
    const trail = p.trailing_enabled ? `<p class="hint" style="direction:ltr">TRAIL · ${esc(p.trailing_code || p.trailing_profile_code || 'ON')}</p>` : '';
    return `<article class="card"><div class="card-head"><strong>${esc(p.symbol || item.signal?.symbol || '—')} · ${esc(p.direction || '')}</strong><span class="status ${esc(item.status)}">${esc(item.status)}</span></div><div class="levels"><span>ENTRY<b>${esc(p.entry || '—')}</b></span><span>SL<b>${esc(p.stop_loss || '—')}</b></span><span>SIZE<b>${esc(sizing)}</b></span></div>${trail}${item.error_message ? `<p style="color:var(--red);font-size:10px">${esc(item.error_message)}</p>` : ''}${retry}</article>`;
  }

  async function retrySignal(button) {
    button.disabled = true;
    try {
      const result = await api(`/signals/${encodeURIComponent(button.dataset.requestId)}/retry`, {method: 'POST'});
      toast(result.publication === 'RETRY_QUEUED' ? 'انتشار مجدد در صف قرار گرفت.' : 'درخواست همان سیگنال احیا شد.');
      await loadSignals();
    } catch (e) {
      toast(e.message);
    } finally {
      button.disabled = false;
    }
  }

  async function loadSignals() {
    try {
      const data = await api('/signals');
      setMt5(data.mt5_admin);
      $('signalList').innerHTML = data.items.length ? data.items.map(signalCard).join('') : '<div class="empty">هنوز سیگنالی صادر نشده است.</div>';
      $('logList').innerHTML = data.items.length ? data.items.map(signalCard).join('') : '<div class="empty">لاگی وجود ندارد.</div>';
      $('openCount').textContent = fa(data.items.filter((x) => !['PUBLISHED', 'FAILED'].includes(x.status)).length);
      $('waitingCount').textContent = fa(data.items.filter((x) => x.status === 'WAITING_FOR_MT5').length);
    } catch (e) {
      toast(e.message);
    }
  }

  function positionCard(p, isOrder = false) {
    const signalId = Number(p.signal_id || 0);
    const account = esc(state.mt5?.account_number || '');
    const actions = signalId
      ? `<div class="trade-actions" data-signal="${signalId}" data-account="${account}">${isOrder
        ? '<button data-command="CANCEL_PENDING" class="danger">لغو Pending</button>'
        : '<button data-command="MOVE_SL_TO_ENTRY" class="safe">Break Even</button><button data-command="PARTIAL_CLOSE">Partial Close</button><button data-command="ACTIVATE_TRAILING">Trailing</button><button data-command="UPDATE_SL">تغییر SL</button><button data-command="UPDATE_TP">تغییر TP</button><button data-command="CLOSE_SIGNAL" class="danger">بستن معامله</button>'}</div>`
      : '';
    return `<article class="card"><div class="card-head"><strong>${esc(p.symbol || '—')} · ${esc(p.direction || p.type || '')}</strong><span class="status">${isOrder ? 'PENDING' : 'LIVE'}</span></div><div class="levels"><span>TICKET<b>${esc(p.ticket || '—')}</b></span><span>ENTRY<b>${esc(p.entry_price || p.price_open || '—')}</b></span><span>VOLUME<b>${esc(p.volume || '—')}</b></span></div>${actions}</article>`;
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
      await api(`/signals/${box.dataset.signal}/command`, {
        method: 'POST',
        body: JSON.stringify({command, account_number: box.dataset.account, value}),
      });
      toast('فرمان در صف اجرای MT5 ثبت شد.');
    } catch (e) {
      toast(e.message);
    } finally {
      button.disabled = false;
    }
  }

  async function loadPositions() {
    try {
      const data = await api('/positions');
      setMt5(data.mt5_admin);
      const all = [...data.positions.map((x) => positionCard(x)), ...data.orders.map((x) => positionCard(x, true))];
      $('positionList').innerHTML = all.join('') || '<div class="empty">پوزیشن یا سفارش فعال وجود ندارد.</div>';
      $('positionCount').textContent = fa(all.length);
    } catch (e) {
      toast(e.message);
    }
  }

  function selectSegment(containerId, value) {
    document.querySelectorAll(`#${containerId} button`).forEach((button) => {
      button.classList.toggle('selected', button.dataset.value === value);
    });
  }

  function renderControls() {
    $('manualSlFields').hidden = state.stopMode !== 'MANUAL';
    $('autoSlFields').hidden = state.stopMode !== 'AUTO';
    $('autoTpFields').hidden = state.tpMode !== 'AUTO';
    $('manualTpFields').hidden = state.tpMode !== 'MANUAL';
    $('riskSizingFields').hidden = state.volumeMode !== 'RISK';
    $('lotSizingFields').hidden = state.volumeMode !== 'FIXED';
    $('trailingFields').hidden = !$('trailingEnabled').checked;
    selectSegment('slMode', state.stopMode);
    selectSegment('tpMode', state.tpMode);
    selectSegment('volumeMode', state.volumeMode);
    renderTrailingPreview();
  }

  function scheduleRecalculate() {
    clearTimeout(window.__calc);
    window.__calc = setTimeout(recalculate, 220);
  }

  document.querySelectorAll('.bottom button').forEach((b) => b.onclick = () => show(b.dataset.view));
  document.querySelectorAll('.direction button').forEach((b) => b.onclick = () => {
    state.side = b.dataset.side;
    document.querySelectorAll('.direction button').forEach((x) => x.classList.toggle('selected', x === b));
    scheduleRecalculate();
  });
  document.querySelectorAll('.destination button').forEach((b) => b.onclick = () => {
    state.destination = b.dataset.value;
    document.querySelectorAll('.destination button').forEach((x) => x.classList.toggle('selected', x === b));
  });
  document.querySelectorAll('#slMode button').forEach((b) => b.onclick = () => {
    state.stopMode = b.dataset.value;
    renderControls();
    scheduleRecalculate();
  });
  document.querySelectorAll('#tpMode button').forEach((b) => b.onclick = () => {
    state.tpMode = b.dataset.value;
    renderControls();
    scheduleRecalculate();
  });
  document.querySelectorAll('#volumeMode button').forEach((b) => b.onclick = () => {
    state.volumeMode = b.dataset.value;
    renderControls();
  });
  $('trailingEnabled').addEventListener('change', renderControls);
  $('trailingProfile').addEventListener('change', renderTrailingPreview);
  $('symbol').addEventListener('change', scheduleRecalculate);

  ['entry', 'stopLoss', 'stopDistance', 'manualTp1', 'manualTp2', 'manualTp3', 'manualTp4']
    .forEach((id) => $(id).addEventListener('input', scheduleRecalculate));

  $('signalForm').onsubmit = (e) => { e.preventDefault(); openPreview(); };
  $('publish').onclick = publish;
  $('newSignal').onclick = () => show('create');
  $('refresh').onclick = bootstrap;
  $('reloadSignals').onclick = loadSignals;
  $('reloadPositions').onclick = loadPositions;
  $('closeModal').onclick = $('cancelPreview').onclick = () => { $('modal').hidden = true; };
  $('positionList').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-command]');
    if (button) sendCommand(button);
  });
  ['signalList', 'logList'].forEach((id) => $(id).addEventListener('click', (event) => {
    const button = event.target.closest('.retry-signal');
    if (button) retrySignal(button);
  }));

  populateTrailingProfiles(FALLBACK_TRAILING);
  renderControls();
  bootstrap();
  setInterval(() => { if (document.visibilityState === 'visible') loadSignals(); }, 5000);
})();
