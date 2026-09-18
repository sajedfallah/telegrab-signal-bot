(() => {
  'use strict';

  const tg = window.Telegram?.WebApp;
  const root = document.documentElement;

  const px = value => {
    const n = Number(value);
    return Number.isFinite(n) && n > 0 ? `${n}px` : '0px';
  };

  function setInsetVars(prefix, inset = {}) {
    root.style.setProperty(`--nx-${prefix}-top`, px(inset.top));
    root.style.setProperty(`--nx-${prefix}-right`, px(inset.right));
    root.style.setProperty(`--nx-${prefix}-bottom`, px(inset.bottom));
    root.style.setProperty(`--nx-${prefix}-left`, px(inset.left));
  }

  function applyInsets() {
    const safe = tg?.safeAreaInset || {};
    const content = tg?.contentSafeAreaInset || safe;
    setInsetVars('safe', safe);
    setInsetVars('content-safe', content);
  }

  function applyTheme() {
    const theme = tg?.themeParams || {};
    root.dataset.telegramColorScheme = tg?.colorScheme || 'dark';

    root.style.setProperty('--nx-tg-bg', theme.bg_color || '#07111d');
    root.style.setProperty('--nx-tg-secondary-bg', theme.secondary_bg_color || '#0d1723');
    root.style.setProperty('--nx-tg-text', theme.text_color || '#edf3f8');
    root.style.setProperty('--nx-tg-hint', theme.hint_color || '#8fa0b2');
    root.style.setProperty('--nx-tg-link', theme.link_color || '#22d3ee');
    root.style.setProperty('--nx-tg-button', theme.button_color || '#27cdb9');
    root.style.setProperty('--nx-tg-button-text', theme.button_text_color || '#041411');

    if (!tg) return;
    const chrome = theme.secondary_bg_color || theme.bg_color || '#07111d';
    try { tg.setHeaderColor?.(chrome); } catch (_) {}
    try { tg.setBackgroundColor?.(theme.bg_color || '#07111d'); } catch (_) {}
    try { tg.setBottomBarColor?.(chrome); } catch (_) {}
  }

  function haptic(kind = 'selection') {
    const feedback = tg?.HapticFeedback;
    if (!feedback) return;
    try {
      if (kind === 'selection') feedback.selectionChanged?.();
      else if (kind === 'success' || kind === 'warning' || kind === 'error') feedback.notificationOccurred?.(kind);
      else feedback.impactOccurred?.(kind);
    } catch (_) {}
  }

  function setVerticalSwipes(enabled) {
    if (!tg) return;
    try {
      if (enabled) tg.enableVerticalSwipes?.();
      else tg.disableVerticalSwipes?.();
    } catch (_) {}
  }

  function refresh() {
    applyInsets();
    applyTheme();
  }

  if (tg) {
    try { tg.ready?.(); } catch (_) {}
    try { tg.expand?.(); } catch (_) {}
    refresh();

    ['themeChanged', 'safeAreaChanged', 'contentSafeAreaChanged', 'viewportChanged'].forEach(eventName => {
      try { tg.onEvent?.(eventName, refresh); } catch (_) {}
    });
  } else {
    refresh();
  }

  window.NexusTelegramShell = {
    refresh,
    haptic,
    disableVerticalSwipes: () => setVerticalSwipes(false),
    enableVerticalSwipes: () => setVerticalSwipes(true),
  };
})();
