(() => {
  const panel = document.getElementById('autoSetupPanel');
  const timeframe = document.getElementById('timeframe');
  const trailing = document.getElementById('trailing');
  const volumeModeButtons = document.querySelectorAll('.volume-mode button');
  const setupButtons = document.querySelectorAll('.setup-mode button');
  if (!panel || !setupButtons.length) return;

  const setText = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };

  function syncAutoPanel() {
    const autoButton = [...setupButtons].find(b => b.classList.contains('selected'));
    const auto = autoButton?.dataset.mode === 'AUTO';
    panel.hidden = !auto;
    if (!auto) return;
    setText('autoTimeframeValue', timeframe?.value || 'M5');
    setText('autoTrailingValue', trailing?.selectedOptions?.[0]?.textContent || trailing?.value || '—');
    const volumeButton = [...volumeModeButtons].find(b => b.classList.contains('selected'));
    setText('autoVolumeValue', volumeButton?.dataset.volume || 'RISK');
  }

  setupButtons.forEach(button => button.addEventListener('click', () => queueMicrotask(syncAutoPanel)));
  timeframe?.addEventListener('change', syncAutoPanel);
  trailing?.addEventListener('change', syncAutoPanel);
  volumeModeButtons.forEach(button => button.addEventListener('click', () => queueMicrotask(syncAutoPanel)));
  syncAutoPanel();
})();
