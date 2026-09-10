(() => {
  const ownerLabels = new Set(['صاحب حساب', 'نام صاحب حساب', 'Account Owner', 'Owner']);
  const bidiMarks = /[\u200E\u200F\u202A-\u202E\u2066-\u2069]/g;

  function normalize(value) {
    return String(value ?? '').replace(bidiMarks, '').replace(/\s+/g, ' ').trim();
  }

  function cleanNode(node, {rtl = true} = {}) {
    if (!node || typeof node.textContent !== 'string') return;
    const cleaned = normalize(node.textContent);
    if (cleaned !== node.textContent) node.textContent = cleaned;
    node.classList.add('bidi-safe');
    node.setAttribute('dir', rtl ? 'rtl' : 'ltr');
  }

  function applyBidi(root = document) {
    root.querySelectorAll?.('.kv').forEach(row => {
      const label = normalize(row.querySelector('span')?.textContent || '');
      if (!ownerLabels.has(label)) return;
      const value = row.querySelector('b');
      if (!value) return;
      value.classList.add('payment-owner');
      cleanNode(value, {rtl: true});
    });
    root.querySelectorAll?.('#userName,.account-profile-copy h2,.profile-card h2,.account-owner-name,[data-bidi-safe]').forEach(node => cleanNode(node, {rtl: true}));
    window.NexusIcons?.mount?.(root);
  }

  const observer = new MutationObserver(records => {
    records.forEach(record => record.addedNodes.forEach(node => {
      if (node.nodeType === 1) applyBidi(node);
    }));
  });

  function boot() {
    applyBidi(document);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
