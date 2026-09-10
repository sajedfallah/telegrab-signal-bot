(() => {
  const landing = document.getElementById('nexusLanding');
  const enterButton = document.getElementById('enterNexus');
  const appShell = document.querySelector('.app-shell');

  if (!landing || !enterButton || !appShell) {
    document.body.classList.remove('landing-active');
    return;
  }

  appShell.setAttribute('aria-hidden', 'true');

  const enterApp = () => {
    if (enterButton.disabled) return;

    enterButton.disabled = true;
    landing.classList.add('is-leaving');

    try {
      window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
    } catch (_) {}

    window.setTimeout(() => {
      landing.hidden = true;
      appShell.removeAttribute('aria-hidden');
      document.body.classList.remove('landing-active');
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
    }, 220);
  };

  enterButton.addEventListener('click', enterApp, { once: true });
})();
