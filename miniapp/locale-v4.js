(() => {
  const TIME_ZONE = 'Asia/Tehran';
  const BIDI_CONTROL_RE = /[\u200E\u200F\u202A-\u202E\u2066-\u2069]/g;
  const MOJIBAKE_HINT_RE = /[ØÙÛÃÂ]/;
  const PERSIAN_RE = /[\u0600-\u06FF]/;

  function stripControls(value) {
    return String(value ?? '').replace(BIDI_CONTROL_RE, '').replace(/\s+/g, ' ').trim();
  }

  function repairMojibake(value) {
    const original = stripControls(value);
    if (!MOJIBAKE_HINT_RE.test(original)) return original;
    try {
      const bytes = Uint8Array.from(Array.from(original, ch => ch.charCodeAt(0) & 0xff));
      const decoded = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
      if (PERSIAN_RE.test(decoded)) return stripControls(decoded);
    } catch (_) {}
    return original;
  }

  function parseDate(value) {
    if (!value) return null;
    const date = value instanceof Date ? value : new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function formatDate(value) {
    const date = parseDate(value);
    if (!date) return '—';
    return new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
      timeZone: TIME_ZONE,
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }).format(date);
  }

  function formatDateTime(value) {
    const date = parseDate(value);
    if (!date) return '—';
    const day = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
      timeZone: TIME_ZONE,
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }).format(date);
    const clock = new Intl.DateTimeFormat('fa-IR', {
      timeZone: TIME_ZONE,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(date);
    return `${day} · ${clock}`;
  }

  function formatNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString('fa-IR') : repairMojibake(value);
  }

  function normalizeNode(node) {
    if (!node || node.nodeType !== Node.ELEMENT_NODE) return;
    node.querySelectorAll?.('[data-fa-text],.payment-owner,.account-owner-name,.bidi-safe,.bidi-auto').forEach(el => {
      if (el.children.length === 0) el.textContent = repairMojibake(el.textContent);
      el.setAttribute('dir', 'rtl');
    });
  }

  function installGlobalDateOverrides() {
    try { window.formatDate = formatDateTime; } catch (_) {}
    try { window.shortDate = formatDate; } catch (_) {}
  }

  function boot() {
    document.documentElement.lang = 'fa';
    document.documentElement.dir = 'rtl';
    installGlobalDateOverrides();
    normalizeNode(document.body);
    new MutationObserver(records => {
      records.forEach(record => record.addedNodes.forEach(node => {
        if (node.nodeType === Node.ELEMENT_NODE) normalizeNode(node);
      }));
    }).observe(document.body, { childList: true, subtree: true });
  }

  window.NexusLocale = {
    TIME_ZONE,
    repairMojibake,
    stripControls,
    formatDate,
    formatDateTime,
    formatNumber,
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
