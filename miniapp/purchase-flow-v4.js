(() => {
  const h = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fa = value => window.NexusLocale?.repairMojibake?.(value) ?? String(value ?? '');
  const fdate = value => window.NexusLocale?.formatDateTime?.(value) ?? String(value ?? '—');
  const fday = value => window.NexusLocale?.formatDate?.(value) ?? String(value ?? '—');
  const icon = name => window.NexusIcons?.svg?.(name, 'nexus-inline-icon') || '';
  const statusFa = value => ({pending:'در انتظار بررسی',approved:'تأیید شده',rejected:'رد شده',failed:'ناموفق',cancelled:'لغو شده'})[String(value || '').toLowerCase()] || fa(value || '—');
  let pollTimer = null;

  function stopPoll() {
    if (pollTimer) window.clearTimeout(pollTimer);
    pollTimer = null;
  }

  function readFileDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('خواندن تصویر رسید ناموفق بود.'));
      reader.readAsDataURL(file);
    });
  }

  function licenseCard(license) {
    if (!license) return '';
    const key = license.license_key
      ? `<div class="license-v4-key"><code>${h(license.license_key)}</code><button class="btn ghost" data-copy-license="${h(license.license_key)}">کپی</button></div>`
      : '<div class="purchase-security-note">لایسنس AutoTrade پس از تأیید اتصال MetaTrader صادر می‌شود.</div>';
    return `<section class="license-v4-card">
      <div class="purchase-state-head"><h3>لایسنس NEXUS</h3><span class="status-pill success">${h(license.status || 'active')}</span></div>
      ${key}
      <div class="license-v4-grid">
        <div><span>پلن</span><b>${h(license.plan_code || '—')}</b></div>
        <div><span>انقضا</span><b class="date-fa">${h(fday(license.expires_at))}</b></div>
        ${license.vip_expires_at ? `<div><span>VIP</span><b class="date-fa">${h(fday(license.vip_expires_at))}</b></div>` : ''}
        ${license.autotrade_expires_at ? `<div><span>AutoTrade</span><b class="date-fa">${h(fday(license.autotrade_expires_at))}</b></div>` : ''}
      </div>
    </section>`;
  }

  function progressSteps(ctx) {
    const payment = ctx.payment || {};
    const meta = ctx.meta_account || {};
    const paymentDone = payment.status === 'approved';
    const metaRequired = !!payment.requires_meta_account;
    const metaDone = !metaRequired || meta.status === 'VALID';
    return `<div class="purchase-step-list">
      <div class="purchase-step done"><i>1</i><div><b>ارسال رسید</b><small>رسید پرداخت ثبت شده است.</small></div></div>
      <div class="purchase-step ${paymentDone ? 'done' : 'current'}"><i>2</i><div><b>بررسی ادمین</b><small>${h(statusFa(payment.status))}</small></div></div>
      ${metaRequired ? `<div class="purchase-step ${metaDone ? 'done' : (paymentDone ? 'current' : '')}"><i>3</i><div><b>اعتبارسنجی MetaTrader</b><small>${h(meta.message_fa || 'پس از تأیید پرداخت فعال می‌شود.')}</small></div></div>` : ''}
      <div class="purchase-step ${paymentDone && metaDone ? 'done' : ''}"><i>${metaRequired ? '4' : '3'}</i><div><b>فعال‌سازی دسترسی</b><small>${paymentDone && metaDone ? 'تکمیل شده' : 'در انتظار مراحل قبل'}</small></div></div>
    </div>`;
  }

  function metaForm(ctx) {
    const payment = ctx.payment || {};
    const meta = ctx.meta_account || {};
    return `<form class="purchase-form" id="metaAccountForm">
      <div class="purchase-field"><label>پلتفرم</label><select class="purchase-select" id="metaPlatform"><option value="MT5" ${meta.platform === 'MT5' ? 'selected' : ''}>MetaTrader 5</option><option value="MT4" ${meta.platform === 'MT4' ? 'selected' : ''}>MetaTrader 4</option></select></div>
      <div class="purchase-field"><label>شماره حساب</label><input class="purchase-input" id="metaAccountNumber" data-ltr="1" inputmode="numeric" autocomplete="off" value="${h(meta.account_number || '')}" required /></div>
      <div class="purchase-field"><label>سرور بروکر</label><input class="purchase-input" id="metaServer" data-ltr="1" autocomplete="off" value="${h(meta.server || '')}" placeholder="Broker-Server" required /></div>
      <div class="purchase-field"><label>رمز Investor / Read-only</label><input class="purchase-input" id="metaInvestorPassword" type="password" data-ltr="1" autocomplete="new-password" required /></div>
      <div class="purchase-security-note">فقط رمز Investor / Read-only را وارد کنید. رمز اصلی معامله یا Master Password را در NEXUS وارد نکنید. رمز واردشده در دیتابیس Mini App ذخیره نمی‌شود و فقط برای همان درخواست اعتبارسنجی استفاده می‌شود.</div>
      <button class="btn primary full" type="submit" id="validateMetaBtn">بررسی و اتصال حساب</button>
      <input type="hidden" id="metaPaymentId" value="${h(payment.id)}" />
    </form>`;
  }

  function contextBody(ctx) {
    const payment = ctx.payment;
    if (!payment) return '<div class="empty-state">پرداخت فعالی برای ادامه فرایند وجود ندارد.</div>';
    let body = `<section class="purchase-status-card">
      <div class="purchase-state-head"><h3>${h(payment.plan_code || 'NEXUS')}</h3><span class="status-pill ${h(payment.status)}">${h(statusFa(payment.status))}</span></div>
      ${progressSteps(ctx)}`;
    if (ctx.next_step === 'WAITING_PAYMENT_REVIEW') {
      body += '<div class="purchase-state-copy"><span class="purchase-loader"><i class="purchase-spinner"></i>رسید در صف بررسی ادمین است. این صفحه به‌صورت خودکار بروزرسانی می‌شود.</span></div>';
    } else if (ctx.next_step === 'RESUBMIT_RECEIPT') {
      body += `<div class="status-panel danger">${icon('close')}<b>رسید تأیید نشد</b><p>${h(fa(payment.rejection_reason || 'دلیل رد ثبت نشده است.'))}</p></div><button class="btn primary full" data-retry-payment="${h(payment.id)}">ارسال مجدد رسید</button>`;
    } else if (ctx.next_step === 'META_ACCOUNT') {
      body += metaForm(ctx);
    } else if (ctx.next_step === 'COMPLETE') {
      body += '<div class="status-panel success">فرایند فعال‌سازی با موفقیت تکمیل شده است.</div>';
      if (payment.vip_access) body += '<button class="btn primary full" data-open-vip="1">ورود به VIP</button>';
    } else if (ctx.next_step === 'PAYMENT_ERROR') {
      body += '<div class="status-panel danger">وضعیت پرداخت نیاز به بررسی پشتیبانی دارد.</div>';
    }
    body += '</section>' + licenseCard(ctx.license);
    return body;
  }

  function bindContext(ctx) {
    document.querySelector('[data-retry-payment]')?.addEventListener('click', async event => {
      const id = event.currentTarget.dataset.retryPayment;
      try {
        setModalBusy(true);
        const invoice = await api(`/purchase/payments/${encodeURIComponent(id)}/retry`, { method: 'POST', body: '{}' });
        renderInvoiceV4(invoice);
      } catch (err) { toast(fa(err.message)); }
      finally { setModalBusy(false); }
    });
    document.querySelector('[data-open-vip]')?.addEventListener('click', () => openVip());
    document.querySelectorAll('[data-copy-license]').forEach(btn => btn.addEventListener('click', () => copyText(btn.dataset.copyLicense || '')));
    document.getElementById('metaAccountForm')?.addEventListener('submit', async event => {
      event.preventDefault();
      const btn = document.getElementById('validateMetaBtn');
      const payload = {
        payment_id: Number(document.getElementById('metaPaymentId')?.value || 0),
        platform: document.getElementById('metaPlatform')?.value || 'MT5',
        account_number: String(document.getElementById('metaAccountNumber')?.value || '').trim(),
        server: String(document.getElementById('metaServer')?.value || '').trim(),
        investor_password: String(document.getElementById('metaInvestorPassword')?.value || ''),
      };
      if (!payload.account_number || !payload.server || !payload.investor_password) return toast('همه اطلاعات MetaTrader را کامل کنید.');
      if (btn) { btn.disabled = true; btn.innerHTML = '<span class="purchase-loader"><i class="purchase-spinner"></i>در حال بررسی اتصال...</span>'; }
      try {
        const result = await api('/purchase/meta-account', { method: 'POST', body: JSON.stringify(payload) });
        const next = result.context || await api(`/purchase/status?payment_id=${payload.payment_id}`);
        const modalBody = document.getElementById('modalBody');
        if (modalBody) modalBody.innerHTML = contextBody(next);
        bindContext(next);
        if (!result.ok) toast(fa(result.validation?.message_fa || 'اعتبارسنجی حساب انجام نشد.'));
      } catch (err) {
        toast(fa(err.message));
        if (btn) { btn.disabled = false; btn.textContent = 'بررسی و اتصال حساب'; }
      }
    });
  }

  async function openPurchaseStatus(paymentId = null) {
    stopPoll();
    showModal('وضعیت خرید', '<div class="empty-state"><span class="purchase-loader"><i class="purchase-spinner"></i>در حال دریافت وضعیت...</span></div>');
    async function refresh() {
      try {
        const suffix = paymentId ? `?payment_id=${encodeURIComponent(paymentId)}` : '';
        const ctx = await api(`/purchase/status${suffix}`);
        const body = document.getElementById('modalBody');
        if (!body) return stopPoll();
        body.innerHTML = contextBody(ctx);
        bindContext(ctx);
        if (ctx.next_step === 'WAITING_PAYMENT_REVIEW') pollTimer = window.setTimeout(refresh, 4000);
      } catch (err) {
        const body = document.getElementById('modalBody');
        if (body) body.innerHTML = `<div class="empty-state">${h(fa(err.message))}<br><button class="btn ghost" id="retryPurchaseStatus">تلاش مجدد</button></div>`;
        document.getElementById('retryPurchaseStatus')?.addEventListener('click', refresh);
      }
    }
    await refresh();
  }

  function renderInvoiceV4(inv) {
    const payment = inv.payment || {};
    const instruction = inv.payment_method === 'usdt'
      ? `<div class="kv"><span>مبلغ</span><b class="ltr">${h(inv.total_usdt)} USDT</b></div><div class="kv"><span>شبکه</span><b class="ltr">${h(payment.network || '—')}</b></div><label class="field-label">Wallet</label><div class="copy-box"><code>${h(payment.wallet || '—')}</code><button id="copyPay">کپی</button></div>`
      : `<div class="kv"><span>مبلغ ریالی</span><b>${h(window.NexusLocale?.formatNumber?.(inv.final_amount_rial || 0) || inv.final_amount_rial || 0)} ریال</b></div><div class="kv"><span>صاحب حساب</span><b class="payment-owner bidi-safe" data-fa-text dir="rtl">${h(fa(payment.owner || '—'))}</b></div><label class="field-label">شماره کارت</label><div class="copy-box"><code>${h(payment.card || '—')}</code><button id="copyPay">کپی</button></div>`;
    showModal('فاکتور پرداخت', `${instruction}
      <div class="kv"><span>اعتبار فاکتور</span><b class="date-fa">${h(fdate(inv.expires_at))}</b></div>
      ${inv.payment_method === 'usdt' ? '<input class="text-input" id="txHash" placeholder="TXID / Transaction Hash (اختیاری)" />' : ''}
      <label class="upload-box">تصویر رسید را انتخاب کنید<input type="file" id="receiptFile" accept="image/jpeg,image/png,image/webp" /></label>
      <div class="modal-muted" id="receiptName">فایلی انتخاب نشده است.</div>
      <button class="btn primary full" id="submitReceipt">ارسال رسید برای تأیید</button>`);
    setTimeout(() => {
      document.getElementById('copyPay')?.addEventListener('click', () => copyText(payment.wallet || payment.card || ''));
      const file = document.getElementById('receiptFile');
      file?.addEventListener('change', () => { document.getElementById('receiptName').textContent = file.files?.[0]?.name || 'فایلی انتخاب نشده است.'; });
      document.getElementById('submitReceipt')?.addEventListener('click', () => submitReceiptV4(inv.invoice_id));
    }, 0);
  }

  async function submitReceiptV4(invoiceId) {
    const input = document.getElementById('receiptFile');
    const file = input?.files?.[0];
    if (!file) return toast('ابتدا تصویر رسید را انتخاب کنید.');
    if (file.size > 5_000_000) return toast('حجم رسید باید کمتر از 5MB باشد.');
    try {
      setModalBusy(true);
      const image = await readFileDataUrl(file);
      const tx = String(document.getElementById('txHash')?.value || '').trim();
      const result = await api('/purchase/receipts', { method: 'POST', body: JSON.stringify({ invoice_id: Number(invoiceId), image_data_url: image, transaction_hash: tx || null }) });
      window.NexusProduct?.track?.('checkout_start', { stage: 'receipt_submitted', payment_id: result.payment_id });
      await openPurchaseStatus(result.payment_id);
    } catch (err) { toast(fa(err.message)); }
    finally { setModalBusy(false); }
  }

  async function showPaymentsV4() {
    try {
      const data = await api('/payments');
      const rows = data.payments || [];
      showModal('پرداخت‌های من', rows.length ? rows.map(p => `
        <button class="payment-row" data-payment-status="${h(p.id)}"><div><b>${h(p.plan_code || '—')}</b><small>${h(fdate(p.created_at))}</small></div><span class="status-pill ${h(p.status)}">${h(statusFa(p.status))}</span></button>`).join('') : '<div class="empty-state">هنوز پرداختی ثبت نشده است.</div>');
      document.querySelectorAll('[data-payment-status]').forEach(row => row.addEventListener('click', () => openPurchaseStatus(row.dataset.paymentStatus)));
    } catch (err) { toast(fa(err.message)); }
  }

  async function fetchAdminReceipt(paymentId) {
    const response = await fetch(`${API}/admin/purchase/payments/${encodeURIComponent(paymentId)}/receipt`, { headers: authHeaders() });
    if (!response.ok) return null;
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  }

  async function openAdminPayments() {
    showModal('بررسی رسیدهای پرداخت', '<div class="empty-state"><span class="purchase-loader"><i class="purchase-spinner"></i>در حال دریافت رسیدها...</span></div>');
    try {
      const data = await api('/admin/purchase/payments?status=pending&limit=50');
      const body = document.getElementById('modalBody');
      if (!body) return;
      const items = data.items || [];
      body.innerHTML = items.length ? `<div class="admin-payment-list">${items.map(item => `<article class="admin-payment-card" data-admin-payment="${h(item.id)}">
        <div class="admin-payment-head"><div><h3>${h(item.plan_code || '—')}</h3><small>${h(fdate(item.created_at))}</small></div><span class="status-pill pending">در انتظار بررسی</span></div>
        <div class="admin-meta-grid"><div class="admin-meta-row"><span>کاربر</span><b>${h(fa(item.first_name || item.username || item.telegram_id))}</b></div><div class="admin-meta-row"><span>Telegram ID</span><b class="ltr">${h(item.telegram_id)}</b></div><div class="admin-meta-row"><span>مبلغ</span><b>${h(item.price_label || item.amount_usdt || '—')}</b></div><div class="admin-meta-row"><span>روش</span><b>${h(item.payment_method || '—')}</b></div></div>
        ${item.has_receipt_file ? '<div class="admin-receipt-slot"><span class="purchase-loader"><i class="purchase-spinner"></i>در حال بارگذاری رسید...</span></div>' : '<div class="empty-state">تصویر رسید روی سرور ذخیره نشده است؛ رسید Telegram را بررسی کنید.</div>'}
        <div class="admin-reject-box"><textarea class="purchase-input" rows="2" data-reject-reason placeholder="دلیل رد رسید"></textarea><div class="admin-payment-actions"><button class="btn ghost" data-admin-reject>رد رسید</button><button class="btn primary" data-admin-approve>تأیید پرداخت</button></div></div>
      </article>`).join('')}</div>` : '<div class="empty-state">رسید در انتظار بررسی وجود ندارد.</div>';
      for (const card of body.querySelectorAll('[data-admin-payment]')) {
        const id = card.dataset.adminPayment;
        const slot = card.querySelector('.admin-receipt-slot');
        if (slot) {
          const url = await fetchAdminReceipt(id);
          slot.innerHTML = url ? `<img class="admin-receipt-image" src="${h(url)}" alt="رسید پرداخت" />` : '<div class="empty-state">بارگذاری تصویر رسید ناموفق بود.</div>';
        }
        card.querySelector('[data-admin-approve]')?.addEventListener('click', async event => {
          if (!window.confirm('این پرداخت تأیید و اشتراک کاربر فعال شود؟')) return;
          event.currentTarget.disabled = true;
          try { await api(`/admin/purchase/payments/${id}/approve`, { method: 'POST', body: JSON.stringify({ note: 'Approved from Mini App admin panel' }) }); toast('پرداخت تأیید و دسترسی کاربر فعال شد.'); card.remove(); }
          catch (err) { toast(fa(err.message)); event.currentTarget.disabled = false; }
        });
        card.querySelector('[data-admin-reject]')?.addEventListener('click', async event => {
          const reason = String(card.querySelector('[data-reject-reason]')?.value || '').trim();
          if (reason.length < 3) return toast('دلیل رد رسید را وارد کنید.');
          if (!window.confirm('رسید رد شود؟ دلیل برای کاربر نمایش داده خواهد شد.')) return;
          event.currentTarget.disabled = true;
          try { await api(`/admin/purchase/payments/${id}/reject`, { method: 'POST', body: JSON.stringify({ reason }) }); toast('رسید رد شد و دلیل برای کاربر ثبت گردید.'); card.remove(); }
          catch (err) { toast(fa(err.message)); event.currentTarget.disabled = false; }
        });
      }
    } catch (err) {
      const body = document.getElementById('modalBody');
      if (body) body.innerHTML = `<div class="empty-state">${h(fa(err.message))}<br><button class="btn ghost" id="retryAdminPayments">تلاش مجدد</button></div>`;
      document.getElementById('retryAdminPayments')?.addEventListener('click', openAdminPayments);
    }
  }

  async function enhanceAccount() {
    if (typeof state === 'undefined' || state.route !== 'account') return;
    if (view.querySelector('[data-purchase-v4-enhanced]')) return;
    try {
      const ctx = await api('/purchase/status');
      if (state.route !== 'account') return;
      const marker = document.createElement('div');
      marker.dataset.purchaseV4Enhanced = '1';
      marker.innerHTML = `${ctx.license ? licenseCard(ctx.license) : ''}${ctx.payment && ['pending','rejected'].includes(ctx.payment.status) ? `<button class="menu-card" data-current-purchase><span>${icon('wallet')}</span><div><b>وضعیت خرید</b><small>${h(statusFa(ctx.payment.status))}</small></div></button>` : ''}${ctx.is_admin ? `<button class="menu-card" data-admin-purchases><span>${icon('shield')}</span><div><b>بررسی رسیدهای پرداخت</b><small>پنل مدیریت Mini App</small></div></button>` : ''}`;
      view.appendChild(marker);
      marker.querySelector('[data-current-purchase]')?.addEventListener('click', () => openPurchaseStatus(ctx.payment.id));
      marker.querySelector('[data-admin-purchases]')?.addEventListener('click', openAdminPayments);
      marker.querySelectorAll('[data-copy-license]').forEach(btn => btn.addEventListener('click', () => copyText(btn.dataset.copyLicense || '')));
    } catch (_) {}
  }

  function boot() {
    try { window.renderInvoice = renderInvoiceV4; } catch (_) {}
    try { window.submitReceipt = submitReceiptV4; } catch (_) {}
    try { window.showPayments = showPaymentsV4; } catch (_) {}
    document.addEventListener('click', event => {
      if (event.target.closest?.('[data-route="account"],[data-go="account"]')) window.setTimeout(enhanceAccount, 350);
    }, true);
    new MutationObserver(() => { if (typeof state !== 'undefined' && state.route === 'account') window.setTimeout(enhanceAccount, 0); }).observe(view, { childList: true, subtree: false });
    window.setTimeout(enhanceAccount, 600);
  }

  window.NexusPurchase = { openStatus: openPurchaseStatus, openAdmin: openAdminPayments, renderInvoice: renderInvoiceV4, enhanceAccount };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
