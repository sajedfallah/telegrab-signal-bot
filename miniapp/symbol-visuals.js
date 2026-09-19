(() => {
  const table = {
    BTC: ['crypto', '₿'], ETH: ['crypto', 'Ξ'], SOL: ['crypto', '◎'], XRP: ['crypto', 'X'], BNB: ['crypto', 'B'],
    XAU: ['metal', 'Au'], XAG: ['metal', 'Ag'],
    US30: ['index', '30'], US100: ['index', '100'], NAS100: ['index', '100'], SPX500: ['index', '500'], GER40: ['index', '40'], UK100: ['index', '100'],
  };
  const forex = /^[A-Z]{6}$/;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

  function normalize(symbol) {
    return String(symbol || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  }

  function keyFor(symbol) {
    const normalized = normalize(symbol);
    return Object.keys(table).find(prefix => normalized.startsWith(prefix)) || '';
  }

  function mark(symbol) {
    const normalized = normalize(symbol);
    const key = keyFor(normalized);
    const [category, glyph] = key ? table[key] : forex.test(normalized) ? ['forex', normalized.slice(0, 2)] : ['other', normalized.slice(0, 2) || 'N'];
    return `<span class="nexus-symbol-mark ${category}" aria-hidden="true">${escape(glyph)}</span>`;
  }

  function svgWrap(body, label, extraClass = '') {
    return `<span class="nexus-symbol-svg ${extraClass}" role="img" aria-label="${escape(label)}"><svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" focusable="false">${body}</svg></span>`;
  }

  function icon(symbol) {
    const normalized = normalize(symbol);
    const key = keyFor(normalized);

    if (key === 'BTC') return svgWrap(
      '<circle cx="16" cy="16" r="15" fill="#F7931A"/><path d="M20.8 13.1c.3-2-1.2-3.1-3.3-3.8l.7-2.6-1.6-.4-.6 2.5-1.3-.3.7-2.6-1.6-.4-.7 2.6-3.2-.8-.4 1.7 1.7.4c.9.2 1.1.8 1 1.2l-.8 3.1.3.1-.3-.1-1.1 4.4c-.1.3-.4.8-1 .6l-1.7-.4-.8 1.8 3.2.8-.7 2.7 1.6.4.7-2.6 1.3.3-.7 2.7 1.6.4.7-2.7c2.8.5 4.9.3 5.8-2.2.7-2-.1-3.2-1.7-4 1.2-.3 2.1-1.2 2.4-2.7Zm-4.3 5.9c-.5 2-4 1-5.1.8l.9-3.5c1.1.3 4.7.8 4.2 2.7Zm.5-5.9c-.5 1.8-3.4.9-4.3.7l.8-3.2c.9.2 4 .7 3.5 2.5Z" fill="#fff"/>',
      'Bitcoin', 'btc'
    );

    if (key === 'ETH') return svgWrap(
      '<circle cx="16" cy="16" r="15" fill="#1A2235"/><path d="M16 4.3 9.2 16l6.8 4 6.8-4L16 4.3Z" fill="#8C8CFF"/><path d="m16 21.2-6.8-4 6.8 10.5 6.8-10.5-6.8 4Z" fill="#627EEA"/><path d="M16 4.3V20l6.8-4L16 4.3Z" fill="#B8B8FF"/>',
      'Ethereum', 'eth'
    );

    if (key === 'SOL') return svgWrap(
      '<circle cx="16" cy="16" r="15" fill="#101018"/><path d="M9 8.5h13.8l-3 3H6l3-3Z" fill="#8C5CFF"/><path d="M9.2 14.5H23l-3 3H6.2l3-3Z" fill="#20E7B7"/><path d="M9 20.5h13.8l-3 3H6l3-3Z" fill="#47D7FF"/>',
      'Solana', 'sol'
    );

    if (key === 'BNB') return svgWrap(
      '<circle cx="16" cy="16" r="15" fill="#F3BA2F"/><path d="m16 7.2 3.1 3.1-3.1 3.1-3.1-3.1L16 7.2Zm-5.3 5.3 3.1 3.1-3.1 3.1-3.1-3.1 3.1-3.1Zm10.6 0 3.1 3.1-3.1 3.1-3.1-3.1 3.1-3.1ZM16 17.8l3.1 3.1L16 24l-3.1-3.1 3.1-3.1Zm0-4.1 1.9 1.9-1.9 1.9-1.9-1.9 1.9-1.9Z" fill="#111820"/>',
      'BNB', 'bnb'
    );

    if (key === 'XRP') return svgWrap(
      '<circle cx="16" cy="16" r="15" fill="#151C24"/><path d="M9 9h3.1c1 0 1.5.3 2.2 1l1.7 1.8 1.7-1.8c.7-.7 1.2-1 2.2-1H23l-5.4 5.5c-.9.9-2.3.9-3.2 0L9 9Zm14 14h-3.1c-1 0-1.5-.3-2.2-1L16 20.2 14.3 22c-.7.7-1.2 1-2.2 1H9l5.4-5.5c.9-.9 2.3-.9 3.2 0L23 23Z" fill="#fff"/>',
      'XRP', 'xrp'
    );

    if (key === 'XAU') return svgWrap(
      '<circle cx="16" cy="16" r="15" fill="#C99A2E"/><circle cx="16" cy="16" r="11.7" fill="#151B24" stroke="#F1C75B" stroke-width="1.2"/><text x="16" y="19.3" text-anchor="middle" font-family="Arial,sans-serif" font-size="9.2" font-weight="700" fill="#F1C75B">Au</text>',
      'Gold', 'xau'
    );

    if (forex.test(normalized)) {
      const base = escape(normalized.slice(0, 3));
      return svgWrap(
        `<circle cx="16" cy="16" r="15" fill="#142333"/><circle cx="16" cy="16" r="11.5" fill="none" stroke="#34D4C2" stroke-width="1"/><text x="16" y="19" text-anchor="middle" font-family="Arial,sans-serif" font-size="7" font-weight="700" fill="#D8F7F3">${base}</text>`,
        normalized, 'forex'
      );
    }

    const fallback = escape((normalized.slice(0, 2) || 'NX'));
    return svgWrap(
      `<circle cx="16" cy="16" r="15" fill="#172433"/><text x="16" y="19" text-anchor="middle" font-family="Arial,sans-serif" font-size="8" font-weight="700" fill="#C7D7E5">${fallback}</text>`,
      normalized || 'Symbol', 'other'
    );
  }

  window.NexusSymbolVisuals = Object.freeze({mark, icon});
})();
