(() => {
  let selectedPeriod = '30';

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

  function summaryGrid(data) {
    return `<div class="track-stat-grid">
      <div><b>${h(data.total)}</b><span>کل سیگنال‌ها</span></div>
      <div class="metric-primary"><b>${h(data.win_rate)}%</b><span>Win Rate</span></div>
      <div><b>${h(data.wins)}</b><span>WIN</span></div>
      <div><b>${h(data.losses)}</b><span>LOSS</span></div>
      <div><b>${h(data.be)}</b><span>BE</span></div>
    </div>`;
  }

  function symbols(rows) {
    if (!rows?.length) return '<div class="empty-state">داده کافی برای تفکیک نمادها وجود ندارد.</div>';
    return `<div class="track-table">${rows.map(row => `<article>
      <div class="track-symbol-copy"><b>${h(row.symbol)}</b><span>${h(row.total)} سیگنال</span></div>
      <div class="track-winbar" aria-label="Win Rate ${h(row.win_rate)}%"><i style="width:${Math.max(0, Math.min(100, Number(row.win_rate || 0)))}%"></i></div>
      <span class="win">${h(row.wins)} W</span><span class="loss">${h(row.losses)} L</span><span>${h(row.be)} BE</span><em>${h(row.win_rate)}%</em>
    </article>`).join('')}</div>`;
  }

  function channels(data) {
    if (!data) return '';
    return `<div class="track-channel-grid">${Object.entries(data).map(([name, row]) => `<article><span class="badge ${name === 'VIP' ? 'vip-badge' : ''}">${h(name)}</span>${summaryGrid(row)}</article>`).join('')}</div>`;
  }

  async function load(period = selectedPeriod) {
    selectedPeriod = period;
    const body = document.getElementById('trackRecordBody');
    if (!body) return;
    body.innerHTML = window.NexusProduct?.skeleton?.('performance', 4) || '<div class="empty-state">در حال محاسبه عملکرد از دیتابیس...</div>';
    try {
      const data = await api(`/performance/details?period=${encodeURIComponent(period)}`);
      document.querySelectorAll('[data-track-period]').forEach(btn => btn.classList.toggle('active', btn.dataset.trackPeriod === period));
      body.innerHTML = `
        <section class="track-summary">${summaryGrid(data.summary)}<p>${h(data.methodology?.message_fa || '')}</p></section>
        <section class="track-section"><div class="section-head"><h2>تفکیک نمادها</h2></div>${symbols(data.symbols)}</section>
        <section class="track-section"><div class="section-head"><h2>رایگان / VIP</h2></div>${channels(data.channels)}</section>
        <section class="track-integrity"><span>${icon('shield')}</span><div><b>شفافیت نتایج</b><span>LOSS و BE از گزارش حذف نمی‌شوند. این صفحه عملکرد سیگنال‌های منتشرشده را نشان می‌دهد، نه بازده حساب معاملاتی شما.</span></div></section>`;
      track('performance_view', { period, source: 'track_record' });
    } catch (err) {
      body.innerHTML = `<div class="empty-state">دریافت عملکرد NEXUS با مشکل مواجه شد.<br><button class="btn ghost" id="retryTrackRecord">تلاش مجدد</button></div>`;
      document.getElementById('retryTrackRecord')?.addEventListener('click', () => load(period));
    }
  }

  function openTrackRecord() {
    state.route = 'performance';
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
    view.innerHTML = `<section class="page-head"><div><div class="eyebrow">TRACK RECORD</div><h1>عملکرد NEXUS</h1><p class="modal-muted">نتایج ثبت‌شده سیگنال‌ها؛ نه بازده حساب معاملاتی.</p></div><button class="text-btn" id="trackBack">بازگشت</button></section>
      <div class="track-periods">${['7','30','90','all'].map(key => `<button class="tab ${key === selectedPeriod ? 'active' : ''}" data-track-period="${key}">${key === 'all' ? 'ALL' : key + 'D'}</button>`).join('')}</div>
      <div id="trackRecordBody">${window.NexusProduct?.skeleton?.('performance', 4) || '<div class="empty-state">در حال دریافت...</div>'}</div>`;
    document.querySelectorAll('[data-track-period]').forEach(btn => btn.addEventListener('click', () => load(btn.dataset.trackPeriod)));
    document.getElementById('trackBack')?.addEventListener('click', () => render('home'));
    load(selectedPeriod);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  window.NexusTrackRecord = { open: openTrackRecord, load };

  document.addEventListener('click', event => {
    const target = event.target.closest?.('[data-home-go="performance"],[data-open-track-record]');
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openTrackRecord();
  }, true);
})();
