(() => {
  const BRAND = './assets/brand/nexus-mark.svg?v=20260910-1215';

  function repair(root = document) {
    root.querySelectorAll?.('img[src*="nexus-logo.svg"]').forEach(img => {
      if (img.getAttribute('src') !== BRAND) img.setAttribute('src', BRAND);
    });
    root.querySelectorAll?.('.payment-owner,.account-owner-name,.bidi-safe,.bidi-auto').forEach(node => {
      if (node.children.length === 0 && window.NexusLocale?.repairMojibake) {
        node.textContent = window.NexusLocale.repairMojibake(node.textContent);
      }
      node.setAttribute('dir', 'rtl');
    });
  }

  function install() {
    if (window.NexusProduct && window.NexusLocale) {
      window.NexusProduct.humanDate = (value, withTime = false) => withTime
        ? window.NexusLocale.formatDateTime(value)
        : window.NexusLocale.formatDate(value);
      window.NexusProduct.normalizeBidi = value => window.NexusLocale.repairMojibake(value);
    }
    try { window.formatDate = value => window.NexusLocale?.formatDateTime?.(value) || '—'; } catch (_) {}
    try { window.shortDate = value => window.NexusLocale?.formatDate?.(value) || '—'; } catch (_) {}
    repair(document);
    new MutationObserver(records => {
      records.forEach(record => record.addedNodes.forEach(node => {
        if (node.nodeType === Node.ELEMENT_NODE) repair(node);
      }));
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();
