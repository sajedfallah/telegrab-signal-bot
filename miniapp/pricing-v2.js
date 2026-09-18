(() => {
  const durations = [30, 90, 180, 365];
  const categories = ['bundle', 'vip', 'autotrade'];
  let selectedDays = 30;
  let planCache = [];
  let carouselIndex = 0;
  let scrollTimer = null;

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

  function durationLabel(days) {
    return ({30:'1 ماه',90:'3 ماه',180:'6 ماه',365:'1 سال'})[Number(days)] || `${days} روز`;
  }

  function categoryTitle(category) {
    return category === 'vip' ? 'VIP' : category === 'autotrade' ? 'AutoTrade' : 'VIP + AutoTrade';
  }

  function categoryDescription(category) {
    return category === 'vip'
      ? 'دسترسی کامل به Signal Center VIP برای اجرای دستی.'
      : category === 'autotrade'
        ? 'اجرای خودکار سیگنال‌های واجد شرایط NEXUS روی MT5 متصل.'
        : 'دسترسی VIP و اجرای خودکار MT5 در یک پلن یکپارچه.';
  }

  function featureList(plan) {
    const features = [
      [plan.vip_access, 'دسترسی به سیگنال VIP'],
      [plan.autotrade_access, 'اجرای خودکار MT5'],
      [plan.autotrade_access, 'معاملات من'],
      [plan.autotrade_access, 'تاریخچه اجرا'],
    ];
    return features.map(([yes, label]) => `<li class="${yes ? 'yes' : 'no'}"><span>${yes ? icon('check', 'nexus-inline-icon') : '–'}</span>${h(label)}</li>`).join('');
  }

  function planFor(category, days) {
    return planCache.find(plan => plan.category === category && Number(plan.days) === Number(days));
  }

  function card(category, index) {
    const plan = planFor(category, selectedDays);
    if (!plan) return `<article class="price-v2-card unavailable" data-carousel-index="${index}" data-product="${h(category)}"><h3>${h(categoryTitle(category))}</h3><div class="empty-state">برای این مدت پلن فعالی وجود ندارد.</div></article>`;
    const currentCode = state.bootstrap?.entitlements?.plan_code;
    const current = currentCode && String(currentCode).toUpperCase() === String(plan.code).toUpperCase();
    return `<article class="price-v2-card ${category === 'bundle' ? 'recommended' : ''}" data-carousel-index="${index}" data-product="${h(category)}" data-plan-code="${h(plan.code)}">
      <div class="price-v2-top"><div><span class="pricing-kicker">${h(plan.code)}</span><h3>${h(categoryTitle(category))}</h3></div>${category === 'bundle' ? '<span class="badge vip-badge">پیشنهاد NEXUS</span>' : ''}</div>
      <p>${h(categoryDescription(category))}</p>
      <div class="price-v2-price"><b>${h(plan.price_usdt)}</b><span>USDT / ${h(durationLabel(plan.days))}</span></div>
      ${current ? '<div class="status-panel success">پلن فعلی شما</div>' : ''}
      <ul>${featureList(plan)}</ul>
      <button class="text-btn price-v2-more" data-show-comparison>مشاهده همه امکانات ${icon('arrowLeft')}</button>
      <button class="btn ${category === 'bundle' ? 'primary' : 'ghost'} full" data-select-plan="${h(plan.code)}" data-product-category="${h(category)}">${current ? 'تمدید' : `انتخاب ${h(categoryTitle(category))}`}</button>
    </article>`;
  }

  function mark(yes) {
    return yes ? icon('check', 'nexus-inline-icon') : '–';
  }

  function comparison() {
    return `<section class="price-v2-comparison" id="pricingComparison"><div class="section-head"><h2>مقایسه قابلیت‌ها</h2></div>
      <div class="compare-row head"><span>قابلیت</span><b>VIP</b><b>AutoTrade</b><b>Bundle</b></div>
      <div class="compare-row"><span>دسترسی VIP</span><b>${mark(true)}</b><b>${mark(false)}</b><b>${mark(true)}</b></div>
      <div class="compare-row"><span>اجرای خودکار MT5</span><b>${mark(false)}</b><b>${mark(true)}</b><b>${mark(true)}</b></div>
      <div class="compare-row"><span>معاملات من</span><b>${mark(false)}</b><b>${mark(true)}</b><b>${mark(true)}</b></div>
      <div class="compare-row"><span>تاریخچه اجرا</span><b>${mark(false)}</b><b>${mark(true)}</b><b>${mark(true)}</b></div>
    </section>`;
  }

  function carouselIndicator() {
    return `<div class="price-carousel-meta"><b id="priceCarouselCount">${carouselIndex + 1}/${categories.length}</b><div class="price-carousel-dots">${categories.map((_, i) => `<button class="${i === carouselIndex ? 'active' : ''}" data-carousel-dot="${i}" aria-label="پلن ${i + 1}"></button>`).join('')}</div><span>برای مقایسه ورق بزنید</span></div>`;
  }

  function updateCarouselIndicator(index, {event = false} = {}) {
    carouselIndex = Math.max(0, Math.min(categories.length - 1, Number(index) || 0));
    const count = document.getElementById('priceCarouselCount');
    if (count) count.textContent = `${carouselIndex + 1}/${categories.length}`;
    document.querySelectorAll('[data-carousel-dot]').forEach(dot => dot.classList.toggle('active', Number(dot.dataset.carouselDot) === carouselIndex));
    document.querySelectorAll('.price-v2-card').forEach(cardEl => cardEl.classList.toggle('carousel-active', Number(cardEl.dataset.carouselIndex) === carouselIndex));
    if (event) track('product_swipe', { category: categories[carouselIndex], days: selectedDays, index: carouselIndex });
  }

  function bindCarousel() {
    const grid = document.querySelector('.price-v2-grid');
    if (!grid) return;
    grid.addEventListener('scroll', () => {
      window.clearTimeout(scrollTimer);
      scrollTimer = window.setTimeout(() => {
        const cards = [...grid.querySelectorAll('.price-v2-card')];
        if (!cards.length) return;
        const gridRect = grid.getBoundingClientRect();
        const center = gridRect.left + gridRect.width / 2;
        const nearest = cards.reduce((best, cardEl) => {
          const rect = cardEl.getBoundingClientRect();
          const distance = Math.abs((rect.left + rect.width / 2) - center);
          return !best || distance < best.distance ? {cardEl, distance} : best;
        }, null);
        if (nearest) updateCarouselIndicator(Number(nearest.cardEl.dataset.carouselIndex), {event: true});
      }, 100);
    }, {passive: true});
    document.querySelectorAll('[data-carousel-dot]').forEach(dot => dot.addEventListener('click', () => {
      const index = Number(dot.dataset.carouselDot);
      grid.querySelector(`[data-carousel-index="${index}"]`)?.scrollIntoView({behavior:'smooth',inline:'center',block:'nearest'});
      updateCarouselIndicator(index, {event: true});
    }));
    updateCarouselIndicator(carouselIndex);
  }

  function renderPricing() {
    const durationButtons = durations.map(days => `<button class="tab ${days === selectedDays ? 'active' : ''}" data-duration="${days}">${durationLabel(days)}</button>`).join('');
    view.innerHTML = `<section class="page-head"><div><div class="eyebrow">NEXUS PLANS</div><h1>پلن مناسب خودت را انتخاب کن</h1><p class="modal-muted">VIP، AutoTrade و Bundle را بر اساس نیازت مقایسه کن.</p></div></section>
      <div class="price-v2-duration">${durationButtons}</div>
      ${carouselIndicator()}
      <div class="price-v2-grid">${categories.map((category, index) => card(category, index)).join('')}</div>
      ${comparison()}
      <div class="note-card">قیمت‌ها و وضعیت پلن‌ها مستقیماً از Pricing Engine backend خوانده می‌شوند.</div>`;
    view.querySelectorAll('[data-duration]').forEach(btn => btn.addEventListener('click', () => {
      selectedDays = Number(btn.dataset.duration);
      carouselIndex = 0;
      renderPricing();
      track('pricing_view', { days: selectedDays, action: 'duration_change' });
    }));
    view.querySelectorAll('[data-select-plan]').forEach(btn => btn.addEventListener('click', () => {
      btn.closest('.price-v2-card')?.classList.add('selected');
      track('product_selected', { plan_code: btn.dataset.selectPlan, category: btn.dataset.productCategory, days: selectedDays });
      openOrderSummary(btn.dataset.selectPlan);
    }));
    view.querySelectorAll('[data-show-comparison]').forEach(btn => btn.addEventListener('click', () => document.getElementById('pricingComparison')?.scrollIntoView({behavior:'smooth',block:'start'})));
    bindCarousel();
    categories.forEach(category => {
      const plan = planFor(category, selectedDays);
      if (plan) track('product_card_viewed', { plan_code: plan.code, category, days: selectedDays });
    });
  }

  function modeLabel(mode) {
    return ({new:'خرید جدید',extend:'تمدید',upgrade:'ارتقا',add_vip:'افزودن VIP',add_auto:'افزودن AutoTrade'})[mode] || mode;
  }

  async function openOrderSummary(code) {
    track('checkout_start', { plan_code: code, stage: 'quote' });
    try {
      showModal('خلاصه سفارش', window.NexusProduct?.skeleton?.('checkout', 3) || '<div class="empty-state">در حال محاسبه مبلغ...</div>');
      const quote = await api('/quote', { method: 'POST', body: JSON.stringify({ plan_code: code }) });
      const credit = Number(quote.upgrade_credit_usdt || 0);
      const setup = Number(quote.setup_fee_usdt || 0);
      const discount = Number(quote.discount_percent || 0);
      showModal('خلاصه سفارش', `
        <div class="order-v2-head"><div><span class="badge">${h(modeLabel(quote.mode))}</span><h3>${h(quote.plan.title_fa)}</h3></div><b>${h(quote.total_usdt)} USDT</b></div>
        <div class="kv"><span>مدت</span><b>${h(durationLabel(quote.duration_days))}</b></div>
        <div class="kv"><span>قیمت پایه</span><b>${h(quote.base_usdt)} USDT</b></div>
        ${setup > 0 ? `<div class="kv"><span>هزینه راه‌اندازی</span><b>${h(quote.setup_fee_usdt)} USDT</b></div>` : ''}
        ${credit > 0 ? `<div class="kv"><span>اعتبار باقیمانده</span><b>− ${h(quote.upgrade_credit_usdt)} USDT</b></div>` : ''}
        ${discount > 0 ? `<div class="kv"><span>تخفیف</span><b>${h(quote.discount_percent)}%</b></div>` : ''}
        <div class="order-v2-total"><span>مبلغ نهایی</span><b>${h(quote.total_usdt)} USDT</b></div>
        <p class="modal-muted">مبالغ بالا همان Quote backend هستند و در frontend دوباره محاسبه نشده‌اند.</p>
        <button class="btn primary full" id="continueCheckout">ادامه به پرداخت</button>`);
      setTimeout(() => document.getElementById('continueCheckout')?.addEventListener('click', () => choosePayment(code, quote)), 0);
    } catch (err) {
      toast(err.message || 'محاسبه سفارش با مشکل مواجه شد.');
    }
  }

  function choosePayment(code, quote) {
    track('checkout_start', { plan_code: code, stage: 'payment_method' });
    showModal('روش پرداخت', `<div class="purchase-head"><b>${h(quote.plan.title_fa)}</b><span>${h(quote.total_usdt)} USDT</span></div>
      <p class="modal-muted">پس از انتخاب روش پرداخت، invoice جدید با نرخ و اعتبار زمانی همان لحظه ساخته می‌شود.</p>
      <div class="method-grid"><button class="btn ghost" id="v2PayRial">پرداخت ریالی</button><button class="btn primary" id="v2PayUsdt">پرداخت USDT</button></div>`);
    setTimeout(() => {
      document.getElementById('v2PayRial')?.addEventListener('click', () => createInvoice(code, 'rial'));
      document.getElementById('v2PayUsdt')?.addEventListener('click', () => createInvoice(code, 'usdt'));
    }, 0);
  }

  async function hydratePricingV2() {
    if (state.route !== 'subscriptions') return;
    view.innerHTML = window.NexusProduct?.skeleton?.('pricing', 3) || '<div class="empty-state">در حال دریافت پلن‌ها...</div>';
    try {
      const data = await api('/plans');
      planCache = data.plans || [];
      if (!state.bootstrap) state.bootstrap = { plans: planCache, entitlements: {} };
      else state.bootstrap.plans = planCache;
      renderPricing();
      track('pricing_view', { days: selectedDays, source: 'plans' });
    } catch (err) {
      view.innerHTML = `<div class="empty-state">دریافت پلن‌ها با مشکل مواجه شد.<br><button class="btn ghost" id="retryPricingV2">تلاش مجدد</button></div>`;
      document.getElementById('retryPricingV2')?.addEventListener('click', hydratePricingV2);
    }
  }

  window.NexusPricing = { open: hydratePricingV2, orderSummary: openOrderSummary };

  const observer = new MutationObserver(() => {
    if (state.route !== 'subscriptions') return;
    if (view.querySelector('.price-v2-grid') || view.dataset.pricingLoading === '1') return;
    view.dataset.pricingLoading = '1';
    Promise.resolve(hydratePricingV2()).finally(() => { delete view.dataset.pricingLoading; });
  });
  observer.observe(view, { childList: true, subtree: false });
})();
