(() => {
  'use strict';

  const source = document.getElementById('entry');
  const autoEntry = document.getElementById('autoEntry');
  const autoField = document.getElementById('autoEntryStatic');
  const setupButtons = [...document.querySelectorAll('.setup-mode button')];

  if (!source || !autoEntry || !autoField || !setupButtons.length) return;

  function isAuto() {
    return setupButtons.some((button) => button.dataset.mode === 'AUTO' && button.classList.contains('selected'));
  }

  function normalizeDecimal(value) {
    return String(value ?? '')
      .replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
      .replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
      .replace(/,/g, '.')
      .replace(/[^0-9.\-]/g, '');
  }

  function dispatchSourceInput() {
    source.dispatchEvent(new Event('input', { bubbles: true }));
    source.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function syncAutoToSource() {
    const clean = normalizeDecimal(autoEntry.value);
    if (autoEntry.value !== clean) autoEntry.value = clean;
    source.value = clean;
    dispatchSourceInput();
  }

  function syncSourceToAuto() {
    if (document.activeElement === autoEntry) return;
    autoEntry.value = normalizeDecimal(source.value);
  }

  function syncMode() {
    const auto = isAuto();
    autoField.hidden = !auto;
    source.disabled = false;
    source.readOnly = false;
    source.removeAttribute('disabled');
    source.removeAttribute('readonly');
    source.style.pointerEvents = 'auto';
    source.tabIndex = 0;

    if (auto) {
      syncSourceToAuto();
      requestAnimationFrame(() => {
        autoEntry.disabled = false;
        autoEntry.readOnly = false;
        autoEntry.removeAttribute('disabled');
        autoEntry.removeAttribute('readonly');
        autoEntry.style.pointerEvents = 'auto';
        autoEntry.tabIndex = 0;
      });
    }
  }

  autoEntry.addEventListener('input', syncAutoToSource);
  autoEntry.addEventListener('change', syncAutoToSource);
  source.addEventListener('input', syncSourceToAuto);
  source.addEventListener('change', syncSourceToAuto);
  setupButtons.forEach((button) => button.addEventListener('click', () => setTimeout(syncMode, 0)));

  syncMode();
})();
