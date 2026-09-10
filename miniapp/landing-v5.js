(() => {
  const landing = document.getElementById('nexusLanding');
  const enterButton = document.getElementById('enterNexus');
  const appShell = document.querySelector('.app-shell');

  if (!landing || !enterButton || !appShell) {
    document.body.classList.remove('landing-active');
    return;
  }

  let entered = false;

  const showLanding = () => {
    entered = false;
    enterButton.disabled = false;
    landing.hidden = false;
    landing.classList.remove('is-leaving');
    appShell.setAttribute('aria-hidden', 'true');
    document.body.classList.add('landing-active');
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  };

  const enterApp = () => {
    if (entered || enterButton.disabled) return;

    entered = true;
    enterButton.disabled = true;
    landing.classList.add('is-leaving');

    try {
      window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
    } catch (_) {}

    window.setTimeout(() => {
      if (!entered) return;
      landing.hidden = true;
      appShell.removeAttribute('aria-hidden');
      document.body.classList.remove('landing-active');
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
    }, 220);
  };

  // Telegram can keep its WebView alive after the Mini App is closed. Reset
  // the gate whenever the document leaves the foreground so every reopen
  // starts on the landing page, even when the same WebView is reused.
  const resetForNextOpen = () => {
    if (entered || landing.hidden) showLanding();
  };

  enterButton.addEventListener('click', enterApp);

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') resetForNextOpen();
  });

  window.addEventListener('pagehide', resetForNextOpen);
  window.addEventListener('pageshow', showLanding);

  // The navigation layer calls the exact same landing lifecycle when the
  // in-app Back button returns from Home to the entry screen.
  window.NexusLanding = {
    show: showLanding,
    enter: enterApp,
    reset: resetForNextOpen,
  };

  showLanding();
})();
