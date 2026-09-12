(() => {
  const host = document.getElementById('positionList');
  if (!host) return;

  function enhance(card) {
    if (!card || card.dataset.compactV7 === '1') return;
    card.dataset.compactV7 = '1';
    card.classList.add('admin-position-card-v7');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'admin-position-more';
    button.textContent = 'جزئیات پوزیشن';
    button.setAttribute('aria-expanded', 'false');
    button.addEventListener('click', event => {
      event.stopPropagation();
      const expanded = card.classList.toggle('expanded');
      button.textContent = expanded ? 'بستن جزئیات' : 'جزئیات پوزیشن';
      button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });
    card.appendChild(button);
  }

  function scan() {
    host.querySelectorAll('.card').forEach(enhance);
  }

  const observer = new MutationObserver(scan);
  observer.observe(host, {childList:true, subtree:true});
  scan();
})();
