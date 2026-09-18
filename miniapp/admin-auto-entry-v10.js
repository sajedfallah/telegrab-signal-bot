(() => {
  const source = document.getElementById('entry');
  const panel = document.getElementById('autoSetupPanel');
  const setupButtons = [...document.querySelectorAll('.setup-mode button')];
  if (!source || !panel || !setupButtons.length) return;

  const host = document.createElement('div');
  host.className = 'auto-entry-field';
  host.id = 'autoEntryField';
  host.innerHTML = `
    <label for="autoEntryInput">قیمت ورود</label>
    <div class="auto-entry-wrap">
      <input id="autoEntryInput" type="text" inputmode="decimal" autocomplete="off" placeholder="3650.00" aria-label="قیمت ورود Auto Setup">
      <span>ENTRY</span>
    </div>
    <div class="auto-entry-hint">قیمت ورود را دستی وارد کنید؛ SL و TP فقط پس از اتصال Structure Engine محاسبه می‌شوند.</div>`;
  panel.insertBefore(host, panel.querySelector('.auto-setup-grid'));

  const autoInput = document.getElementById('autoEntryInput');
  const sourceLabel = source.closest('label');

  function isAuto() {
    return setupButtons.some(b => b.dataset.mode === 'AUTO' && b.classList.contains('selected'));
  }

  function cleanDecimal(value) {
    return String(value ?? '').replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/,/g, '.').replace(/[^0-9.\-]/g, '');
  }

  function syncFromAuto() {
    const value = cleanDecimal(autoInput.value);
    if (autoInput.value !== value) autoInput.value = value;
    source.value = value;
    source.dispatchEvent(new Event('input', { bubbles: true }));
    const valid = Number.isFinite(Number(value)) && Number(value) > 0;
    host.classList.toggle('auto-entry-invalid', !!value && !valid);
  }

  function syncFromSource() {
    if (document.activeElement !== autoInput) autoInput.value = source.value || '';
  }

  function syncMode() {
    const auto = isAuto();
    host.classList.toggle('is-visible', auto);
    if (sourceLabel) sourceLabel.hidden = auto;
    if (auto) {
      source.disabled = false;
      source.readOnly = false;
      source.required = true;
      syncFromSource();
      setTimeout(() => autoInput.focus({ preventScroll: true }), 0);
    } else if (sourceLabel) {
      sourceLabel.hidden = false;
    }
  }

  autoInput.addEventListener('input', syncFromAuto);
  autoInput.addEventListener('change', syncFromAuto);
  source.addEventListener('input', syncFromSource);
  setupButtons.forEach(button => button.addEventListener('click', () => setTimeout(syncMode, 0)));
  syncMode();
})();
