(() => {
  const icons = {
    home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10.5V20h14v-9.5"/><path d="M9 20v-6h6v6"/>',
    signals: '<path d="M4 18h2"/><path d="M8 14h2"/><path d="M12 10h2"/><path d="M16 6h4"/><path d="m4 18 4-4 4-4 4-4"/>',
    trades: '<path d="M4 19V9"/><path d="M4 14h4"/><path d="M8 16V7"/><path d="M8 10h4"/><path d="M12 20V11"/><path d="M12 15h4"/><path d="M16 13V5"/><path d="M16 8h4"/>',
    plans: '<path d="M4 5h16v14H4z"/><path d="M4 9h16"/><path d="M8 13h4"/><path d="M8 16h7"/>',
    account: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20c1.2-4 3.7-6 7.5-6s6.3 2 7.5 6"/>',
    lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    arrowUpRight: '<path d="M7 17 17 7"/><path d="M8 7h9v9"/>',
    chart: '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
    community: '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3.5 19c.8-3.7 2.6-5.5 5.5-5.5s4.7 1.8 5.5 5.5"/><path d="M14 15c1-.9 2-1.3 3.2-1.3 2.2 0 3.6 1.4 4.3 4.3"/>',
    shield: '<path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6z"/><path d="m9 12 2 2 4-5"/>',
    support: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.7 2.7 0 1 1 4.2 2.3c-1 .7-1.7 1.1-1.7 2.7"/><path d="M12 17h.01"/>',
    wallet: '<path d="M4 6h14a2 2 0 0 1 2 2v10H4z"/><path d="M4 6a2 2 0 0 1 2-2h11"/><path d="M15 11h5v4h-5a2 2 0 1 1 0-4z"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    sparkle: '<path d="M12 3l1.4 3.6L17 8l-3.6 1.4L12 13l-1.4-3.6L7 8l3.6-1.4z"/><path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8z"/>',
  };

  function svg(name, className = 'nexus-icon') {
    const body = icons[name] || icons.sparkle;
    return `<svg class="${String(className).replace(/[^a-zA-Z0-9 _-]/g, '')}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  }

  function mount(root = document) {
    root.querySelectorAll?.('[data-nexus-icon]').forEach(node => {
      node.innerHTML = svg(node.dataset.nexusIcon || 'sparkle');
    });
  }

  window.NexusIcons = { svg, mount };
  document.addEventListener('DOMContentLoaded', () => mount(document));
})();
