(() => {
  const landing = document.getElementById('nexusLanding');
  const enterButton = document.getElementById('enterNexus');
  const appShell = document.querySelector('.app-shell');
  const poster = landing?.querySelector('.nexus-landing-poster');

  if (!landing || !enterButton || !appShell) {
    document.body.classList.remove('landing-active');
    appShell?.removeAttribute('aria-hidden');
    return;
  }

  let entered = false;

  const markFallback = () => {
    landing.classList.add('landing-fallback');
    enterButton.setAttribute('aria-label', 'ورود به NEXUS');
    if (!enterButton.querySelector('.nexus-fallback-cta')) {
      const fallback = document.createElement('span');
      fallback.className = 'nexus-fallback-cta';
      fallback.innerHTML = '<b>NEXUS</b><small>Trading Intelligence</small><em>ورود به پنل</em>';
      enterButton.appendChild(fallback);
    }
  };

  if (poster) {
    poster.addEventListener('error', markFallback, { once: true });
    if (poster.complete && poster.naturalWidth === 0) markFallback();
  } else {
    markFallback();
  }

  const revealApp = () => {
    landing.hidden = true;
    landing.classList.remove('is-leaving');
    appShell.removeAttribute('aria-hidden');
    appShell.style.visibility = '';
    appShell.style.pointerEvents = '';
    document.body.classList.remove('landing-active');
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  };

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
      revealApp();
      try {
        if (typeof window.render === 'function') window.render('home');
        if (typeof window.hydrateNexusHome === 'function') window.hydrateNexusHome();
      } catch (_) {}
    }, 180);
  };

  const resetForNextOpen = () => {
    if (entered || landing.hidden) showLanding();
  };

  enterButton.addEventListener('click', enterApp);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') resetForNextOpen();
  });
  window.addEventListener('pagehide', resetForNextOpen);
  window.addEventListener('pageshow', showLanding);

  window.NexusLanding = {
    show: showLanding,
    enter: enterApp,
    reset: resetForNextOpen,
    reveal: revealApp,
  };

  showLanding();
})();
