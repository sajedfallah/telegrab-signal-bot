(() => {
  const landing = document.getElementById('nexusLanding');
  const enterButton = document.getElementById('enterNexus');
  const appShell = document.querySelector('.app-shell');
  const poster = landing?.querySelector('.nexus-landing-poster');

  if (!landing || !enterButton || !appShell || !poster) {
    document.body.classList.remove('landing-active');
    return;
  }

  let entered = false;
  let posterObjectUrl = null;
  let posterHydrated = false;

  const embeddedSource = poster.dataset.directWebpSource || '';

  const extractEmbeddedWebp = async () => {
    if (posterHydrated || !embeddedSource) return;

    try {
      const response = await fetch(embeddedSource, {
        cache: 'no-store',
        credentials: 'same-origin',
      });
      if (!response.ok) throw new Error(`landing asset HTTP ${response.status}`);

      const svg = await response.text();
      const match = svg.match(/data:image\/webp;base64,([^"']+)/i);
      if (!match?.[1]) throw new Error('embedded WebP payload not found');

      const binary = atob(match[1]);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);

      const blob = new Blob([bytes], { type: 'image/webp' });
      posterObjectUrl = URL.createObjectURL(blob);
      poster.src = posterObjectUrl;

      if (typeof poster.decode === 'function') {
        try { await poster.decode(); } catch (_) {}
      }

      poster.classList.remove('is-fallback');
      poster.classList.add('is-ready');
      posterHydrated = true;
    } catch (error) {
      console.error('NEXUS landing direct image decode failed', error);
      poster.src = embeddedSource;
      poster.classList.remove('is-ready');
      poster.classList.add('is-fallback');
      posterHydrated = true;
    }
  };

  const showLanding = () => {
    entered = false;
    enterButton.disabled = false;
    landing.hidden = false;
    landing.classList.remove('is-leaving');
    appShell.setAttribute('aria-hidden', 'true');
    document.body.classList.add('landing-active');
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
    extractEmbeddedWebp();
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

  const resetForNextOpen = () => {
    if (entered || landing.hidden) showLanding();
  };

  enterButton.addEventListener('click', enterApp);

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') resetForNextOpen();
  });

  window.addEventListener('pagehide', resetForNextOpen);
  window.addEventListener('pageshow', showLanding);
  window.addEventListener('beforeunload', () => {
    if (posterObjectUrl) URL.revokeObjectURL(posterObjectUrl);
  });

  window.NexusLanding = {
    show: showLanding,
    enter: enterApp,
    reset: resetForNextOpen,
  };

  showLanding();
})();
