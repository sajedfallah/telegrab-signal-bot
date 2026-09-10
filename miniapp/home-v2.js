(() => {
  const tgWebApp = window.Telegram?.WebApp;
  const DEFAULT_NEXUS_ENTRY_URL = 'https://t.me/nexus_publicc';
  let homeRequest = 0;

  function h(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  }

  function icon(name, className = 'nexus-inline-icon') {
    return window.NexusIcons?.svg?.(name, className) || '';
  }

  function track(name, metadata = {}) {
    window.NexusProduct?.track?.(name, metadata);
  }

  function dt(value) {
    if (!value) return '—';
    if (window.NexusProduct?.humanDate) return window.NexusProduct.humanDate(value, true);
    try { return new Date(value).toLocaleString('fa-IR-u-ca-persian'); } catch (_) { return String(value); }
  }

  function shortDate(value) {
    if (!value) return '—';
    if (window.NexusProduct?.humanDate) return window.NexusProduct.humanDate(value, false);
    try { return new Date(value).toLocaleDateString('fa-IR-u-ca-persian'); } catch (_) { return String(value); }
  }

  function go(destination) {
    if (!destination) return;
    track('home_cta', { destination });
    if (destination === 'performance') {
      window.NexusTrackRecord?.open?.();
      return;
    }
    if (destination === 'trades') {
      window.NexusTrades?.open?.();
      return;
    }
    if (['home', 'signals', 'subscriptions', 'account', 'guide', 'support'].includes(destination)) {
      render(destination);
    }
  }

  function section(title, body, className = '') {
    return `<section class="home-v2-section ${className}"><div class="section-head"><h2>${h(title)}</h2></div>${body}</section>`;
  }

  function spotlight(data) {
    const item = data || { kind: 'WELCOME', title_fa: 'به NEXUS خوش آمدید', subtitle_fa: 'مرکز روزانه سیگنال، عملکرد و AutoTrade.' };
    return `<section class="hero home-v2-spotlight nexus-animated-hero">
      <div class="nexus-motion-orb orb-a" aria-hidden="true"></div>
      <div class="nexus-motion-orb orb-b" aria-hidden="true"></div>
      <div class="home-brand-lockup">
        <img class="home-brand-logo" src="./assets/brand/nexus-logo.svg" alt="NEXUS" loading="eager" decoding="async" />
        <div><span class="eyebrow">NEXUS</span><b>Trading Intelligence</b></div>
      </div>
      <div class="eyebrow">${h(item.kind || 'NEXUS')}</div>
      <h1>${h(item.title_fa || '')}</h1>
      <p>${h(item.subtitle_fa || '')}</p>
      <div class="hero-actions home-v2-actions">
        <button class="btn primary nexus-enter-btn" data-enter-nexus>${icon('arrowUpRight')}<span>ورود به نکسوس</span></button>
        ${item.cta_fa ? `<button class="btn ghost" data-home-go="${h(item.destination || '')}">${h(item.cta_fa)}</button>` : ''}
      </div>
    </section>`;
  }

  function attention(items) {
    if (!items?.length) return '';
    return section('نیاز به توجه', items.map(item => `
      <article class="home-attention-card">
        <div><span class="badge warning-badge">${h(item.kind)}</span><h3>${h(item.title_fa)}</h3></div>
        <button class="btn ghost" data-home-go="${h(item.destination || '')}">${h(item.cta_fa || 'بررسی')}</button>
      </article>`).join(''), 'home-v2-priority');
  }

  function today(data) {
    if (!data) return '';
    const active = Number(data.active_signals || 0);
    return section('امروز در NEXUS', `
      <div class="home-today-row">
        <div><b>${h(active)}</b><span>سیگنال فعال</span></div>
        <div><b>${h(data.closed_signals || 0)}</b><span>بسته‌شده امروز</span></div>
      </div>
      ${active > 0 ? '<button class="btn ghost full home-today-cta" data-home-go="signals">مشاهده سیگنال فعال</button>' : ''}
      <small class="home-asof">آخرین بروزرسانی: ${h(dt(data.as_of))}</small>`, 'home-v2-today');
  }

  function performanceCard(data) {
    if (!data) return '';
    return section('عملکرد NEXUS', `
      <div class="home-periods" id="homePerformancePeriods">
        ${['7','30','90','all'].map(key => `<button class="tab ${String(data.period) === key ? 'active' : ''}" data-performance-period="${key}">${key === 'all' ? 'ALL' : key + 'D'}</button>`).join('')}
      </div>
      <div class="home-stat-grid" id="homePerformanceStats">
        <div><b>${h(data.total)}</b><span>کل سیگنال‌ها</span></div>
        <div class="metric-primary"><b>${h(data.win_rate)}%</b><span>Win Rate</span></div>
        <div><b>${h(data.wins)}</b><span>WIN</span></div>
        <div><b>${h(data.losses)}</b><span>LOSS</span></div>
      </div>
      <div class="home-performance-secondary"><span>BE: <b>${h(data.be)}</b></span>${Number(data.avg_rr || 0) > 0 ? `<span>Avg RR: <b>${h(data.avg_rr)}</b></span>` : ''}</div>
      <button class="text-btn home-section-cta" data-home-go="performance">مشاهده عملکرد کامل</button>
      <p class="home-disclaimer">${h(data.disclaimer_fa || '')}</p>`, 'home-v2-performance');
  }

  function resultMeta(item) {
    if (item.status !== 'CLOSED') return null;
    const code = String(item.result || 'UNKNOWN').toUpperCase();
    const label = item.result_label_fa || ({
      WIN: 'سود', LOSS: 'ضرر', BE: 'سر‌به‌سر', PARTIAL: 'بسته‌شدن بخشی', CANCELLED: 'لغوشده', EXPIRED: 'منقضی‌شده'
    })[code] || 'نتیجه ثبت نشده';
    return { code, label };
  }

  function resultBadge(item) {
    const meta = resultMeta(item);
    if (!meta) return '';
    return `<div class="home-result ${h(meta.code.toLowerCase())}"><b>${h(meta.code)}</b><span>${h(meta.label)}</span></div>`;
  }

  function recentSignals(rows) {
    const items = (rows || []).slice(0, 3);
    if (!items.length) {
      return section('سیگنال‌های اخیر', `<div class="empty-state nexus-empty-state">${icon('signals')}<b>سیگنالی برای نمایش وجود ندارد</b><span>فقط سیگنال‌های معتبر و قابل نمایش در این بخش نشان داده می‌شوند.</span></div>`);
    }
    return section('سیگنال‌های اخیر', `<div class="home-signal-list">${items.map(item => `
      <article class="home-signal-card compact ${item.locked ? 'locked' : ''}" data-home-signal="${h(item.id)}">
        <div class="home-signal-compact-main">
          <div class="home-signal-symbol"><strong>${h(item.symbol)}</strong><small>${h(dt(item.published_at))}</small></div>
          <span class="direction-chip ${h(String(item.direction || '').toLowerCase())}">${item.locked ? icon('lock', 'nexus-lock-icon') : h(item.direction || '—')}</span>
          <span class="status-pill ${item.status === 'CLOSED' ? 'neutral' : 'success'}">${h(item.status || 'ACTIVE')}</span>
        </div>
        ${resultBadge(item)}
      </article>`).join('')}</div>
      <button class="text-btn home-section-cta" data-home-go="signals">مشاهده همه سیگنال‌ها ${icon('arrowLeft')}</button>`);
  }

  function offer(data) {
    if (!data) return '';
    return section('برای شما', `<article class="home-offer-card"><div><span class="badge">${h(data.kind)}</span><h3>${h(data.title_fa)}</h3>${data.subtitle_fa ? `<p>${h(data.subtitle_fa)}</p>` : ''}</div><button class="btn primary" data-home-go="${h(data.destination || 'subscriptions')}">${h(data.cta_fa || 'مشاهده')}</button></article>`);
  }

  function contentCard(title, item, iconName) {
    if (!item) return '';
    return section(title, `<article class="home-content-card" data-content-id="${h(item.id || '')}">
      <span class="nexus-card-icon">${icon(iconName)}</span>
      <div><h3>${h(item.title_fa || '')}</h3>${item.body_fa ? `<p>${h(item.body_fa)}</p>` : ''}</div>
      ${item.cta_fa ? `<button class="text-btn" data-content-destination="${h(item.destination || '')}" data-content-url="${h(item.url || '')}">${h(item.cta_fa)} ${icon('arrowLeft')}</button>` : ''}
    </article>`, 'home-v2-content');
  }

  function whyNexus() {
    return section('چرا NEXUS؟', `<div class="home-why-grid">
      <article><span class="nexus-card-icon">${icon('shield')}</span><b>شفافیت</b><span>نتایج WIN، LOSS و BE در عملکرد NEXUS حفظ می‌شوند.</span></article>
      <article><span class="nexus-card-icon">${icon('signals')}</span><b>سیگنال ساختاریافته</b><span>Entry، SL، TP و وضعیت چرخه معامله در یک ساختار مشخص.</span></article>
      <article><span class="nexus-card-icon">${icon('trades')}</span><b>AutoTrade</b><span>اجرای واجد شرایط روی MT5 با وضعیت و سابقه اجرای شخصی.</span></article>
    </div>`);
  }

  function community() {
    return section('NEXUS Community', `<div class="info-strip"><div><span class="nexus-card-icon small">${icon('community')}</span><b>کانال عمومی و جامعه NEXUS</b></div><button class="text-btn" data-enter-nexus>ورود</button></div>`);
  }

  function autotradeHealth(data) {
    if (!data) return '';
    const stateName = String(data.state || 'NEEDS_ATTENTION').toUpperCase();
    const stateClass = stateName === 'HEALTHY' ? 'success' : stateName === 'DISCONNECTED' ? 'danger' : 'warning';
    const title = stateName === 'HEALTHY' ? 'AutoTrade متصل و فعال است' : stateName === 'DISCONNECTED' ? 'اتصال AutoTrade قطع است' : 'AutoTrade نیاز به بررسی دارد';
    const cta = stateName === 'HEALTHY' ? 'معاملات من' : 'بررسی وضعیت اتصال';
    return section('AutoTrade من', `<article class="home-health-card ${stateClass}">
      <div class="signal-top"><span class="badge">${h(stateName)}</span><span>${h(data.mt5_account ? `MT5 ****${String(data.mt5_account).slice(-4)}` : 'MT5 —')}</span></div>
      <h3>${h(title)}</h3>
      <div class="home-health-meta"><span>معاملات باز <b>${h(data.open_trades ?? 0)}</b></span><span>Pending <b>${h(data.pending_orders ?? 0)}</b></span></div>
      <small>آخرین Sync: ${h(dt(data.last_sync_at))}</small>
      <button class="btn ghost full" data-home-go="trades">${h(cta)}</button>
    </article>`);
  }

  function tradePreview(data) {
    if (!data) return '';
    const rows = [...(data.open || []).map(x => ({...x, _kind:'OPEN'})), ...(data.history || []).map(x => ({...x, _kind:x.status || x.event_type || 'HISTORY'}))].slice(0, 3);
    if (!rows.length) return section('معاملات من', `<div class="empty-state nexus-empty-state">${icon('trades')}<b>معامله فعالی وجود ندارد</b><span>وقتی اجرای واقعی جدیدی ثبت شود این بخش بروزرسانی می‌شود.</span></div>`);
    return section('معاملات من', `<div class="home-trade-list">${rows.map(row => `
      <article><div><b>${h(row.symbol || '—')}</b><small>${h(row.direction || row.event_type || '')}</small></div><span>${h(row._kind)}</span><em class="${Number(row.profit || 0) < 0 ? 'negative' : ''}">${row.profit != null ? h(Number(row.profit).toFixed(2) + ' $') : '—'}</em></article>`).join('')}</div>
      <button class="text-btn home-section-cta" data-home-go="trades">مشاهده همه معاملات ${icon('arrowLeft')}</button>`);
  }

  function subscription(data) {
    if (!data) return '';
    const rows = [];
    if (data.vip) rows.push(`<div class="kv"><span>VIP</span><b>${h(shortDate(data.vip_expires_at))}</b></div>`);
    if (data.autotrade) rows.push(`<div class="kv"><span>AutoTrade</span><b>${h(shortDate(data.autotrade_expires_at))}</b></div>`);
    if (!rows.length) return '';
    return section('وضعیت اشتراک', `<div class="home-subscription-card">${rows.join('')}<button class="text-btn home-section-cta" data-home-go="account">مدیریت حساب</button></div>`);
  }

  function renderSection(key, payload) {
    const map = {
      needs_attention: () => attention(payload.needs_attention),
      spotlight: () => spotlight(payload.spotlight),
      performance: () => performanceCard(payload.performance),
      recent_signals: () => recentSignals(payload.recent_signals),
      why_nexus: whyNexus,
      offer: () => offer(payload.offer),
      community,
      today: () => today(payload.today),
      autotrade_health: () => autotradeHealth(payload.autotrade_health),
      trades_preview: () => tradePreview(payload.trades_preview),
      subscription: () => subscription(payload.subscription),
      market_insight: () => contentCard('تحلیل امروز', payload.market_insight, 'chart'),
      academy: () => contentCard('آکادمی NEXUS', payload.academy, 'book'),
    };
    return map[key]?.() || '';
  }

  function normalizedOrder(payload) {
    const order = Array.isArray(payload.section_order) ? [...payload.section_order] : [];
    const filtered = order.filter((key, index) => key !== 'spotlight' && order.indexOf(key) === index);
    return ['spotlight', ...filtered];
  }

  async function switchPerformance(period) {
    try {
      const data = await api(`/performance?period=${encodeURIComponent(period)}`);
      const host = document.getElementById('homePerformanceStats');
      if (host) host.innerHTML = `
        <div><b>${h(data.total)}</b><span>کل سیگنال‌ها</span></div>
        <div class="metric-primary"><b>${h(data.win_rate)}%</b><span>Win Rate</span></div>
        <div><b>${h(data.wins)}</b><span>WIN</span></div>
        <div><b>${h(data.losses)}</b><span>LOSS</span></div>`;
      document.querySelectorAll('[data-performance-period]').forEach(btn => btn.classList.toggle('active', btn.dataset.performancePeriod === period));
      track('performance_view', { period, source: 'home' });
    } catch (err) {
      toast('دریافت آمار عملکرد با مشکل مواجه شد.');
    }
  }

  function enterNexus() {
    const url = DEFAULT_NEXUS_ENTRY_URL;
    track('home_cta', { action: 'enter_nexus', url });
    openTelegramLink(url);
  }

  function bindHomeActions() {
    view.querySelectorAll('[data-home-go]').forEach(el => el.addEventListener('click', () => go(el.dataset.homeGo)));
    view.querySelectorAll('[data-go]').forEach(el => el.addEventListener('click', () => render(el.dataset.go)));
    view.querySelectorAll('[data-action]').forEach(el => el.addEventListener('click', () => handleAction(el.dataset.action, el)));
    view.querySelectorAll('[data-enter-nexus]').forEach(el => el.addEventListener('click', enterNexus));
    view.querySelectorAll('[data-performance-period]').forEach(el => el.addEventListener('click', () => switchPerformance(el.dataset.performancePeriod)));
    view.querySelectorAll('[data-content-destination],[data-content-url]').forEach(el => el.addEventListener('click', () => {
      track('content_open', { content_id: el.closest('[data-content-id]')?.dataset.contentId || null, destination: el.dataset.contentDestination || null });
      if (el.dataset.contentUrl) openExternal(el.dataset.contentUrl);
      else go(el.dataset.contentDestination);
    }));
  }

  async function hydrateNexusHome() {
    if (state.route !== 'home' || !tgWebApp?.initData) return;
    const requestId = ++homeRequest;
    const skeleton = window.NexusProduct?.skeleton?.('home', 5) || '<div class="empty-state">در حال دریافت داشبورد NEXUS...</div>';
    view.innerHTML = `<div class="home-v2-loading">${skeleton}</div>`;
    try {
      const payload = await api('/home');
      if (requestId !== homeRequest || state.route !== 'home') return;
      state.home = payload;
      state.experience = payload.experience || state.experience;
      window.NexusExperience?.renderNavigation?.(state.experience?.navigation || []);
      const order = normalizedOrder(payload);
      view.innerHTML = `<div class="home-v2">${order.map(key => renderSection(key, payload)).join('')}</div>`;
      bindHomeActions();
      track('home_view', { segment: payload.experience?.segment, lifecycle: payload.experience?.lifecycle, sections: order });
    } catch (err) {
      console.error('NEXUS Home V2 failed', err);
      if (requestId !== homeRequest || state.route !== 'home') return;
      view.innerHTML = `<div class="empty-state home-v2-error">دریافت داشبورد NEXUS با مشکل مواجه شد.<br><button class="btn ghost" id="retryHomeV2">تلاش مجدد</button></div>`;
      document.getElementById('retryHomeV2')?.addEventListener('click', hydrateNexusHome);
    }
  }

  window.hydrateNexusHome = hydrateNexusHome;
  hydrateNexusHome();
})();
