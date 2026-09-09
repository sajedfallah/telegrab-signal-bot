(() => {
  const cssHref = './account-v2.css';
  if (!document.querySelector(`link[href="${cssHref}"]`)) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = cssHref;
    document.head.appendChild(link);
  }

  if (!document.querySelector('script[data-nexus-account-v2]')) {
    const script = document.createElement('script');
    script.src = './account-v2.js';
    script.dataset.nexusAccountV2 = '1';
    document.body.appendChild(script);
  }
})();

document.addEventListener('click', event => {
  const target = event.target.closest?.('[data-route="home"],[data-go="home"]');
  if (!target) return;
  window.setTimeout(() => window.hydrateNexusHome?.(), 0);
}, true);
