(() => {
  const durations = [30, 90, 180, 365];
  let selectedDays = 30;
  let planCache = [];

  function h(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  }

  function durationLabel(days) {
    return ({30:'1 ماه',90:'3 ماه',180:'6 ماه',365:'1 سال'})[Number(days)] || `${days} روز`;
  }

  function categoryTitle(category) {
    return category === 'vip' ? 'VIP' : category === 'autotrade' ? 'AutoTrade' : 'VIP + AutoTrade';
  }

  function categoryDescription(category) {
    return category === 'vip'
      ? 'دسترسی به سیگنال‌های VIP NEXUS؛ اجرای معامله به‌صورت دستی مگر AutoTrade نیز فعال باشد.'
      : category === 'autotrade'
        ? 'اجرای خودکار سیگنال‌های واجد شرایط NEXUS روی MT5 متصل.'
        : 'دسترسی VIP به‌همراه اجرای خودکار سیگنال‌های واجد شرایط روی MT5.';
  }

  function featureList(plan) {
    const features = [
      [plan.vip_access, 'دسترسی به سیگنال VIP'],
      [plan.vip_access, 'جزئیات کامل VIP'],
      [plan.autotrade_access, 'اجرای خودکار MT5'],
      [plan.autotrade_access, 'وضعیت معاملات شخصی'],
      [plan.autotrade_access, 'Execution History'],
    ];
    return features.map(([yes, label]) => `<li class="${yes ? 'yes' : 'no'}"><span>${yes ? '✓' : '–'}</span>${h(label)}</li>`).join('');
  }

  function planFor(category, days) {
    return planCache.find(plan => plan.category === category && Number(plan.days) === Number(days));
  }

  function card(category) {
    const plan = planFor(category, selectedDays);
    if (!plan) return `<article class="price-v2-card unavailable"><h3>${h(categoryTitle(category))}</h3><div class="empty-state">برای این مدت پلن فعالی وجود ندارد.</div></article>`;
    const currentCode = state.bootstrap?.entitlements?.plan_code;
    const current = currentCode && String(currentCode).toUpperCase() === String(plan.code).toUpperCase();
    return `<article class="price-v2-card ${category === 'bundle' ? 'recommended' : ''}">
      <div class="price-v2-top"><div><span class="pricing-kicker">${h(plan.code)}</span><h3>${h(categoryTitle(category))}</h3></div>${category === 'bundle' ? '<span class="badge vip-badge">پیشنهاد NEXUS</span>' : ''}</div>
      <p>${h(categoryDescription(category))}</p>
      <div class="price-v2-price"><b>${h(plan.price_usdt)}</b><span>USDT / ${h(durationLabel(plan.days))}</span></div>
      ${current ? '<div class="status-panel success">پلن فعلی شما</div>' : ''}
      <ul>${featureList(plan)}</ul>
      <button class="btn ${category === 'bundle' ? 'primary' : 'ghost'} full" data-select-plan="${h(plan.code)}">${current ? 'تمدید' : `انتخاب ${h(categoryTitle(category))}`}</button>
    </article>`;
  }

  function comparison() {
    return `<section class="price-v2-comparison"><div class="section-head"><h2>مقایسه قابلیت‌ها</h2></div>
      <div class="compare-row head"><span>قابلیت</span><b>VIP</b><b>AutoTrade</b><b>Bundle</b></div>
      <div class="compare-row"><span>VIP Signals</span><b>✓</b><b>–</b><b>✓</b></div>
      <div class="compare-row"><span>Automatic MT5</span><b>–</b><b>✓</b><b>✓</b></div>
      <div class="compare-row"><span>My Trades</span><b>–</b><b>✓</b><b>✓</b></div>
      <div class="compare-row"><span>Execution History</span><b>–</b><b>✓</b><b>✓</b></div>
    </section>`;
  }

  function renderPricing() {
    const durationButtons = durations.map(days => `<button class="tab ${days === selectedDays ? 'active' : ''}" data-duration="${days}">${durationLabel(days)}</button>`).join('');
    view.innerHTML = `<section class="page-head"><div><div class="eyebrow">NEXUS PLANS</div><h1>پلن مناسب خودت را انتخاب کن</h1><p class="modal-muted">VIP، AutoTrade و Bundle را بر اساس نیازت مقایسه کن.</p></div></section>
      <div class="price-v2-duration">${durationButtons}</div>
      <div class="price-v2-grid">${card('vip')}${card('autotrade')}${card('bundle')}</div>
      ${comparison()}
      <div class="note-card">قیمت‌ها و وضعیت پلن‌ها مستقیماً از Runtime Plan Catalog در backend خوانده می‌شوند.</div>`;
    view.querySelectorAll('[data-duration]').forEach(btn => btn.addEventListener('click', () => {
      selectedDays = Number(btn.dataset.duration);
      renderPricing();
    }));
    view.querySelectorAll('[data-select-plan]').forEach(btn => btn.addEventListener('click', () => openOrderSummary(btn.dataset.selectPlan)));
  }

  function modeLabel(mode) {
    return ({new:'خرید جدید',extend:'تمدید',upgrade:'ارتقا',add_vip:'افزودن VIP',add_auto:'افزودن AutoTrade'})[mode] || mode;
  }

  async function openOrderSummary(code) {
    try {
      showModal('خلاصه سفارش', '<div class="empty-state">در حال محاسبه مبلغ از Pricing Engine...</div>');
      const quote = await api('/quote', { method: 'POST', body: JSON.stringify({ plan_code: code }) });
      const credit = Number(quote.upgrade_credit_usdt || 0);
      const setup = Number(quote.setup_fee_usdt || 0);
      const discount = Number(quote.discount_percent || 0);
      showModal('خلاصه سفارش', `
        <div class="order-v2-head"><div><span class="badge">${h(modeLabel(quote.mode))}</span><h3>${h(quote.plan.title_fa)}</h3></div><b>${h(quote.total_usdt)} USDT</b></div>
        <div class="kv"><span>مدت</span><b>${h(durationLabel(quote.duration_days))}</b></div>
        <div class="kv"><span>قیمت پایه</span><b>${h(quote.base_usdt)} USDT</b></div>
        ${setup > 0 ? `<div class="kv"><span>Setup Fee</span><b>${h(quote.setup_fee_usdt)} USDT</b></div>` : ''}
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
    try {
      const data = await api('/plans');
      planCache = data.plans || [];
      if (!state.bootstrap) state.bootstrap = { plans: planCache, entitlements: {} };
      else state.bootstrap.plans = planCache;
      renderPricing();
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
