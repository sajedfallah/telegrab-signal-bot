(() => {
  const entry = document.getElementById('entry');
  const setupButtons = [...document.querySelectorAll('.setup-mode button')];
  const panel = document.getElementById('autoSetupPanel');
  if (!entry || !setupButtons.length) return;

  function isAuto() {
    return setupButtons.some(b => b.dataset.mode === 'AUTO' && b.classList.contains('selected'));
  }

  function keepEntryEditable() {
    if (!isAuto()) return;
    entry.disabled = false;
    entry.readOnly = false;
    entry.removeAttribute('readonly');
    entry.removeAttribute('disabled');
    entry.required = true;
    entry.setAttribute('inputmode', 'decimal');
    entry.setAttribute('autocomplete', 'off');
    entry.style.pointerEvents = 'auto';
    entry.style.userSelect = 'text';
    entry.style.webkitUserSelect = 'text';
    entry.tabIndex = 0;
    panel?.classList.add('entry-required');
  }

  setupButtons.forEach(button => button.addEventListener('click', () => setTimeout(keepEntryEditable, 0)));
  entry.addEventListener('pointerdown', keepEntryEditable);
  entry.addEventListener('touchstart', keepEntryEditable, {passive:true});
  entry.addEventListener('focus', keepEntryEditable);
  keepEntryEditable();
})();
