(() => {
  'use strict';

  function applySignalState(card) {
    if (!card) return;
    card.classList.remove('pnl-profit', 'pnl-loss', 'pnl-be');
    const pnl = card.querySelector('.signal-live-grid .pnl');
    if (pnl?.classList.contains('in_profit')) card.classList.add('pnl-profit');
    else if (pnl?.classList.contains('in_loss')) card.classList.add('pnl-loss');
    else if (pnl?.classList.contains('be')) card.classList.add('pnl-be');
  }

  function fixPanel(panel) {
    if (!panel) return;

    // Critical: user-theme-option3.css styles every `.live` element cyan.
    // The live panel must never carry this generic class.
    panel.classList.remove('live');
    panel.classList.add('is-live');

    panel.style.setProperty('background', 'linear-gradient(155deg,#111821,#0b1017)', 'important');
    panel.style.setProperty('background-color', '#0b1118', 'important');
    panel.style.setProperty('background-image', 'linear-gradient(155deg,#111821,#0b1017)', 'important');
    panel.style.setProperty('border', '1px solid rgba(57,215,196,.18)', 'important');
    panel.style.setProperty('box-shadow', 'none', 'important');
    panel.style.setProperty('color', '#f4f7fb', 'important');

    panel.querySelectorAll('.signal-live-grid > div').forEach((cell) => {
      cell.style.setProperty('background', '#0f151d', 'important');
      cell.style.setProperty('background-color', '#0f151d', 'important');
      cell.style.setProperty('border-color', 'rgba(255,255,255,.075)', 'important');
    });

    panel.querySelectorAll('.signal-live-grid span').forEach((el) => {
      el.style.setProperty('color', '#8995a7', 'important');
    });
    panel.querySelectorAll('.signal-live-grid b').forEach((el) => {
      el.style.setProperty('color', '#f4f7fb', 'important');
    });
    panel.querySelectorAll('.signal-live-grid .pnl.in_profit').forEach((el) => {
      el.style.setProperty('color', '#77e5bd', 'important');
    });
    panel.querySelectorAll('.signal-live-grid .pnl.in_loss').forEach((el) => {
      el.style.setProperty('color', '#ff8c96', 'important');
    });
    panel.querySelectorAll('.signal-live-grid .pnl.be').forEach((el) => {
      el.style.setProperty('color', '#c7d0dc', 'important');
    });

    applySignalState(panel.closest('.signal-v2-card'));
  }

  function scan(root = document) {
    root.querySelectorAll?.('.signal-live-panel').forEach(fixPanel);
    root.querySelectorAll?.('.signal-v2-card').forEach(applySignalState);
  }

  scan();

  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        if (node.matches?.('.signal-live-panel')) fixPanel(node);
        if (node.matches?.('.signal-v2-card')) applySignalState(node);
        scan(node);
      }
    }
  });

  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('pageshow', () => scan());
})();
