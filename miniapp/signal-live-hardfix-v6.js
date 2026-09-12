(() => {
  function forceDarkLivePanel(root = document) {
    root.querySelectorAll?.('.signal-live-panel').forEach(panel => {
      panel.style.setProperty('background', 'linear-gradient(155deg,#111821,#0b1017)', 'important');
      panel.style.setProperty('background-color', '#0b1118', 'important');
      panel.style.setProperty('background-image', 'linear-gradient(155deg,#111821,#0b1017)', 'important');
      panel.style.setProperty('border-color', 'rgba(57,215,196,.18)', 'important');
      panel.style.setProperty('box-shadow', 'none', 'important');
      panel.style.setProperty('color', '#f4f7fb', 'important');
      panel.querySelectorAll('.signal-live-grid > div').forEach(cell => {
        cell.style.setProperty('background', '#0f151d', 'important');
        cell.style.setProperty('background-color', '#0f151d', 'important');
        cell.style.setProperty('border-color', 'rgba(255,255,255,.075)', 'important');
      });
      panel.querySelectorAll('.signal-live-grid span').forEach(el => el.style.setProperty('color', '#8995a7', 'important'));
      panel.querySelectorAll('.signal-live-grid b').forEach(el => el.style.setProperty('color', '#f4f7fb', 'important'));
      panel.querySelectorAll('.signal-live-grid .pnl.in_profit').forEach(el => el.style.setProperty('color', '#77e5bd', 'important'));
      panel.querySelectorAll('.signal-live-grid .pnl.in_loss').forEach(el => el.style.setProperty('color', '#ff8c96', 'important'));
      panel.querySelectorAll('.signal-live-grid .pnl.be').forEach(el => el.style.setProperty('color', '#c7d0dc', 'important'));
    });
  }

  forceDarkLivePanel();
  const observer = new MutationObserver(records => {
    for (const record of records) {
      record.addedNodes.forEach(node => {
        if (node.nodeType !== 1) return;
        if (node.matches?.('.signal-live-panel')) forceDarkLivePanel(node.parentElement || document);
        else if (node.querySelector?.('.signal-live-panel')) forceDarkLivePanel(node);
      });
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('pageshow', () => forceDarkLivePanel());
})();
