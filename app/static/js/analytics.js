// Google Analytics 4, loaded only after the visitor accepts analytics cookies.
// Declining, or not choosing, sets nothing; the choice can be changed from "Cookie settings" in the footer.
(() => {
  const id = document.querySelector('meta[name="analytics-id"]')?.content;
  if (!id) return;

  const KEY = 'myaudioshelf-analytics-consent';
  const read = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
  const save = value => { try { localStorage.setItem(KEY, value); } catch {} };
  let loaded = false, card = null;

  window.dataLayer = window.dataLayer || [];
  // gtag.js reads the arguments object itself, so this must stay a plain function.
  function gtag() { window.dataLayer.push(arguments); }

  function load() {
    if (loaded) return;
    loaded = true;
    gtag('js', new Date());
    gtag('config', id);
    const script = document.createElement('script');
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`;
    document.head.append(script);
    // Events the server marked on this page: purchases, enquiries and newsletter sign-ups.
    document.querySelectorAll('meta[name="analytics-event"]').forEach(meta => {
      let params = {};
      try { params = JSON.parse(meta.dataset.params || '{}'); } catch {}
      if (Array.isArray(params.items)) params.items = params.items.map(name => ({item_name: name}));
      gtag('event', meta.content, params);
    });
  }

  document.addEventListener('click', event => {
    const trailer = event.target.closest('[data-trailer]');
    if (trailer && loaded) gtag('event', 'preview_play', {item_name: trailer.dataset.title || ''});
  });

  function node(tag, className, attributes = {}, ...children) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
    element.append(...children);
    return element;
  }

  function close() {
    if (!card) return;
    const leaving = card;
    card = null;
    leaving.classList.remove('consent-in');
    setTimeout(() => leaving.remove(), 260);
  }

  function choose(value) {
    save(value);
    close();
    if (value === 'granted') load();
    // Withdrawing consent stops collection on the next page, once gtag.js is no longer loaded.
    else if (loaded) window[`ga-disable-${id}`] = true;
  }

  function open(focus = false) {
    if (card) return;
    const accept = node('button', 'button', {type: 'button'}, 'Accept analytics');
    const decline = node('button', 'button secondary', {type: 'button'}, 'Decline');
    card = node('section', 'consent-card', {'aria-labelledby': 'consent-title', 'aria-describedby': 'consent-text'},
      node('p', 'consent-title', {id: 'consent-title'}, 'Cookies, only with your permission'),
      node('p', 'consent-text', {id: 'consent-text'}, 'We’d like to use Google Analytics cookies to learn which pages and previews people enjoy. They’re optional, and nothing is set unless you accept. ',
        node('a', '', {href: '/cookies'}, 'Cookie policy')),
      node('div', 'consent-actions', {}, accept, decline));
    accept.addEventListener('click', () => choose('granted'));
    decline.addEventListener('click', () => choose('denied'));
    card.addEventListener('keydown', event => { if (event.key === 'Escape') choose('denied'); });
    document.body.append(card);
    requestAnimationFrame(() => requestAnimationFrame(() => card?.classList.add('consent-in')));
    if (focus) accept.focus({preventScroll: true});
  }

  document.querySelectorAll('[data-consent-open]').forEach(button => button.addEventListener('click', () => open(true)));
  const choice = read();
  if (choice === 'granted') load();
  else if (choice !== 'denied') open();
})();
