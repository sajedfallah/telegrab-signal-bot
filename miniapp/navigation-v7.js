(() => {
  const backButton = document.getElementById('nexusBackBtn');
  const viewEl = document.getElementById('view');
  const enterButton = document.getElementById('enterNexus');

  if (!backButton || !viewEl) return;

  const routeStack = ['landing'];
  let currentRoute = document.body.classList.contains('landing-active') ? 'landing' : routeName();
  let suppressRecord = false;

  function routeName() {
    try {
      return String(state?.route || 'home');
    } catch (_) {
      return 'home';
    }
  }

  function landingVisible() {
    const landing = document.getElementById('nexusLanding');
    return Boolean(document.body.classList.contains('landing-active') || (landing && !landing.hidden));
  }

  function modalVisible() {
    const modal = document.getElementById('modalRoot');
    return Boolean(modal && !modal.hidden);
  }

  function updateBackButton() {
    backButton.dataset.currentRoute = currentRoute;
    backButton.setAttribute('aria-label', currentRoute === 'home' ? 'بازگشت به صفحه ورود' : 'بازگشت به صفحه قبلی');
  }

  function applyHomeAnalysisLabel(root = document) {
    root.querySelectorAll?.('.home-v2-actions [data-enter-nexus] span').forEach(label => {
      if (label.textContent !== 'اتاق تحلیل') label.textContent = 'اتاق تحلیل';
    });
  }

  function rememberRouteChange() {
    applyHomeAnalysisLabel(viewEl);

    if (landingVisible()) {
      currentRoute = 'landing';
      updateBackButton();
      return;
    }

    const nextRoute = routeName();
    if (!nextRoute || nextRoute === currentRoute) {
      updateBackButton();
      return;
    }

    if (!suppressRecord && currentRoute !== 'landing') {
      if (routeStack[routeStack.length - 1] !== currentRoute) routeStack.push(currentRoute);
    }

    currentRoute = nextRoute;
    updateBackButton();
  }

  function openRoute(route) {
    suppressRecord = true;
    currentRoute = route;

    try {
      if (route === 'landing') {
        if (window.NexusLanding?.show) {
          window.NexusLanding.show();
        } else {
          render('home');
        }
      } else if (route === 'performance' && window.NexusTrackRecord?.open) {
        window.NexusTrackRecord.open();
      } else if (route === 'trades' && window.NexusTrades?.open) {
        window.NexusTrades.open();
      } else {
        render(route);
      }
    } finally {
      window.setTimeout(() => {
        suppressRecord = false;
        applyHomeAnalysisLabel(viewEl);
        updateBackButton();
      }, 0);
    }
  }

  function goBack() {
    if (modalVisible()) {
      try { closeModal(); } catch (_) {}
      return;
    }

    let previous = routeStack.length ? routeStack.pop() : null;
    if (!previous || previous === currentRoute) {
      previous = currentRoute === 'home' ? 'landing' : 'home';
    }
    openRoute(previous);
  }

  backButton.addEventListener('click', goBack);

  enterButton?.addEventListener('click', () => {
    routeStack.length = 0;
    routeStack.push('landing');
    window.setTimeout(() => {
      currentRoute = routeName();
      applyHomeAnalysisLabel(viewEl);
      updateBackButton();
    }, 240);
  }, true);

  const observer = new MutationObserver(rememberRouteChange);
  observer.observe(viewEl, { childList: true, subtree: true });

  document.addEventListener('click', event => {
    const target = event.target.closest?.('[data-route],[data-go],[data-home-go],[data-open-track-record]');
    if (!target) return;
    window.setTimeout(rememberRouteChange, 0);
  }, true);

  applyHomeAnalysisLabel(viewEl);
  updateBackButton();

  window.NexusNavigation = {
    back: goBack,
    stack: routeStack,
    current: () => currentRoute,
  };
})();
