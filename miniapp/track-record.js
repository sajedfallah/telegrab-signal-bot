(() => {
  let selectedPeriod = '30';

  function h(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  }

  function summaryGrid(data) {
    return `<div class="track-stat-grid">
      <div><b>${h(data.total)}</b><span>Total</span></div>
      <div><b>${h(data.wins)}</b><span>WIN</span></div>
      <div><b>${h(data.losses)}</b><span>LOSS</span></div>
      <div><b>${h(data.be)}</b><span>BE</span></div>
      <div><b>${h(data.win_rate)}%</b><span>Win Rate</span></div>
    </div>`;
  }

  function symbols(rows) {
    if (!rows?.length) return '<div class="empty-state">داده کافی برای تفکیک نمادها وجود ندارد.</div>';
    return `<div class="track-table">${rows.map(row => `<article><b>${h(row.symbol)}</b><span>${h(row.total)} Signals</span><span class="win">${h(row.wins)} W</span><span class="loss">${h(row.losses)} L</span><span>${h(row.be)} BE</span><em>${h(row.win_rate)}%</em></article>`).join('')}</div>`;
  }

  function channels(data) {
    if (!data) return '';
    return `<div class="track-channel-grid">${Object.entries(data).map(([name, row]) => `<article><span class="badge ${name === 'VIP' ? 'vip-badge' : ''}">${h(name)}</span>${summaryGrid(row)}</article>`).join('')}</div>`;
  }

  async function load(period = selectedPeriod) {
    selectedPeriod = period;
    const body = document.getElementById('trackRecordBody');
    if (!body) return;
    body.innerHTML = '<div class="empty-state">در حال محاسبه Track Record از دیتابیس...</div>';
    try {
      const data = await api(`/performance/details?period=${encodeURIComponent(period)}`);
      document.querySelectorAll('[data-track-period]').forEach(btn => btn.classList.toggle('active', btn.dataset.trackPeriod === period));
      body.innerHTML = `
        <section class="track-summary">${summaryGrid(data.summary)}<p>${h(data.methodology?.message_fa || '')}</p></section>
        <section class="track-section"><div class="section-head"><h2>تفکیک نمادها</h2></div>${symbols(data.symbols)}</section>
        <section class="track-section"><div class="section-head"><h2>FREE / VIP</h2></div>${channels(data.channels)}</section>
        <section class="track-integrity"><b>شفافیت نتایج</b><span>LOSS و BE از گزارش حذف نمی‌شوند. این صفحه عملکرد سیگنال‌های منتشرشده را نشان می‌دهد، نه بازده حساب شما.</span></section>`;
    } catch (err) {
      body.innerHTML = `<div class="empty-state">دریافت Track Record با مشکل مواجه شد.<br><button class="btn ghost" id="retryTrackRecord">تلاش مجدد</button></div>`;
      document.getElementById('retryTrackRecord')?.addEventListener('click', () => load(period));
    }
  }

  function openTrackRecord() {
    state.route = 'performance';
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
    view.innerHTML = `<section class="page-head"><div><div class="eyebrow">TRACK RECORD</div><h1>عملکرد NEXUS</h1></div><button class="text-btn" id="trackBack">بازگشت</button></section>
      <div class="track-periods">${['7','30','90','all'].map(key => `<button class="tab ${key === selectedPeriod ? 'active' : ''}" data-track-period="${key}">${key === 'all' ? 'ALL' : key + 'D'}</button>`).join('')}</div>
      <div id="trackRecordBody"><div class="empty-state">در حال دریافت...</div></div>`;
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

  const observer = new MutationObserver(() => {
    if (state.route !== 'signals') return;
    const head = view.querySelector('.page-head');
    if (!head || head.querySelector('[data-open-track-record]')) return;
    const button = document.createElement('button');
    button.className = 'text-btn';
    button.dataset.openTrackRecord = '1';
    button.textContent = 'Track Record';
    head.appendChild(button);
  });
  observer.observe(view, { childList: true, subtree: true });
})();
