(() => {
  const table = {
    BTC: ['crypto', '₿'], ETH: ['crypto', 'Ξ'], SOL: ['crypto', '◎'], XRP: ['crypto', 'X'], BNB: ['crypto', 'B'],
    XAU: ['metal', 'Au'], XAG: ['metal', 'Ag'],
    US30: ['index', '30'], US100: ['index', '100'], NAS100: ['index', '100'], SPX500: ['index', '500'], GER40: ['index', '40'], UK100: ['index', '100'],
  };
  const forex = /^[A-Z]{6}$/;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  function mark(symbol) {
    const normalized = String(symbol || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
    const key = Object.keys(table).find(prefix => normalized.startsWith(prefix));
    const [category, glyph] = key ? table[key] : forex.test(normalized) ? ['forex', normalized.slice(0, 2)] : ['other', normalized.slice(0, 2) || 'N'];
    return `<span class="nexus-symbol-mark ${category}" aria-hidden="true">${escape(glyph)}</span>`;
  }
  window.NexusSymbolVisuals = Object.freeze({mark});
})();
