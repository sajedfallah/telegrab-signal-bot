(() => {
  function placePerformanceAfterToday() {
    const home = document.querySelector('.home-v2');
    if (!home) return;

    const today = home.querySelector('.home-v2-today');
    const performance = home.querySelector('.home-v2-performance');
    if (!today || !performance) return;

    if (today.nextElementSibling !== performance) {
      today.insertAdjacentElement('afterend', performance);
    }
  }

  function start() {
    const view = document.getElementById('view');
    if (!view) return;

    placePerformanceAfterToday();
    const observer = new MutationObserver(placePerformanceAfterToday);
    observer.observe(view, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
