document.addEventListener('click', event => {
  const target = event.target.closest?.('[data-route="home"],[data-go="home"]');
  if (!target) return;
  window.setTimeout(() => window.hydrateNexusHome?.(), 0);
}, true);
