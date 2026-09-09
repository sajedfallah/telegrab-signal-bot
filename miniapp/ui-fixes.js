(() => {
  function applyBidi(root = document) {
    root.querySelectorAll?.('.kv').forEach(row => {
      const label = row.querySelector('span')?.textContent?.trim() || '';
      if (label === 'صاحب حساب' || label === 'نام صاحب حساب') {
        const value = row.querySelector('b');
        if (value) {
          value.classList.add('bidi-auto', 'payment-owner');
          value.setAttribute('dir', 'auto');
        }
      }
    });
    root.querySelectorAll?.('#userName,.account-profile-copy h2,.profile-card h2').forEach(node => {
      node.classList.add('bidi-auto');
      node.setAttribute('dir', 'auto');
    });
    window.NexusIcons?.mount?.(root);
  }

  const observer = new MutationObserver(records => {
    records.forEach(record => record.addedNodes.forEach(node => {
      if (node.nodeType === 1) applyBidi(node);
    }));
  });

  document.addEventListener('DOMContentLoaded', () => {
    applyBidi(document);
    observer.observe(document.body, { childList: true, subtree: true });
  });
})();
