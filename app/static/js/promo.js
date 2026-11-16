// Homepage announcement: translated audiobooks. Shown on two homepage visits at most, never over another dialog.
(() => {
  const dialog = document.querySelector('[data-translation-promo]');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  const KEY = 'translation-promo-views';
  const LIMIT = 2;
  let views;
  try { views = Number(localStorage.getItem(KEY)) || 0; } catch { return; }
  if (views >= LIMIT) return;

  const show = () => {
    if (document.hidden || document.querySelector('dialog[open], .consent-card')) return setTimeout(show, 4000);
    try { localStorage.setItem(KEY, String(views + 1)); } catch { /* still show it this once */ }
    dialog.showModal();
    requestAnimationFrame(() => dialog.classList.add('is-visible'));
    dialog.querySelector('.promo-card').focus({ preventScroll: true });
  };
  const close = () => {
    dialog.classList.remove('is-visible');
    setTimeout(() => dialog.close(), window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 260);
  };
  // Anywhere on the card goes to the translated books, except the close buttons.
  dialog.addEventListener('click', event => {
    if (event.target === dialog || event.target.closest('[data-promo-dismiss]')) return close();
    if (!event.target.closest('a')) location.href = dialog.dataset.href;
  });
  dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
  if (document.readyState === 'complete') setTimeout(show, 1500);
  else window.addEventListener('load', () => setTimeout(show, 1500), { once: true });
})();
