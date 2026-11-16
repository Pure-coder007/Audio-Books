// Site languages: the visitor picks a language and Google Translate shows the whole site in it.
// Google's script loads only after a choice; English visitors never contact Google.
(() => {
  const COOKIE = 'googtrans';
  const chosen = (document.cookie.match(/(?:^|;\s*)googtrans=\/(?:auto|en)\/([^;]+)/) || [])[1];

  // The cookie is set for this host and its parent domain, since Google Translate may read either.
  const domains = () => {
    const parent = location.hostname.replace(/^www\./, '');
    return /^[\d.]+$/.test(parent) || !parent.includes('.') ? [null] : [null, '.' + parent];
  };
  const remember = code => {
    for (const domain of domains()) {
      const scope = '; path=/' + (domain ? '; domain=' + domain : '') + '; SameSite=Lax';
      document.cookie = code ? `${COOKIE}=/en/${code}${scope}; max-age=31536000` : `${COOKIE}=${scope}; max-age=0`;
    }
  };

  if (chosen && chosen !== 'en' && !location.pathname.startsWith('/admin')) {
    window.myAudioShelfTranslate = () => {
      new window.google.translate.TranslateElement({ pageLanguage: 'en', autoDisplay: false }, 'google-translate-element');
    };
    const script = document.createElement('script');
    script.src = 'https://translate.google.com/translate_a/element.js?cb=myAudioShelfTranslate';
    script.async = true;
    script.onerror = () => document.documentElement.classList.add('translation-unavailable');
    document.head.append(script);
  }

  const dialog = document.querySelector('[data-site-language-dialog]');
  if (!dialog) return;
  const search = dialog.querySelector('[data-language-search]');
  const options = [...dialog.querySelectorAll('[data-language]')];
  const empty = dialog.querySelector('[data-language-empty]');

  const open = () => {
    if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
    document.documentElement.classList.add('language-dialog-open');
    if (window.matchMedia('(min-width: 700px)').matches) search?.focus();
  };
  const close = () => {
    if (typeof dialog.close === 'function') dialog.close(); else dialog.removeAttribute('open');
  };
  dialog.addEventListener('close', () => document.documentElement.classList.remove('language-dialog-open'));
  document.querySelectorAll('[data-site-language-open]').forEach(button => button.addEventListener('click', open));
  dialog.querySelectorAll('[data-site-language-close]').forEach(button => button.addEventListener('click', close));
  dialog.addEventListener('click', event => { if (event.target === dialog) close(); });

  // Matches the English name, the language's own name or its code, ignoring accents.
  const plain = text => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  search?.addEventListener('input', () => {
    const term = plain(search.value.trim());
    let shown = 0;
    for (const option of options) {
      const match = !term || plain(option.dataset.search).includes(term);
      option.hidden = !match;
      shown += match;
    }
    dialog.querySelectorAll('[data-language-group]').forEach(group => {
      group.hidden = !group.querySelector('[data-language]:not([hidden])');
    });
    if (empty) empty.hidden = shown > 0;
  });

  for (const option of options) {
    option.addEventListener('click', () => {
      const code = option.dataset.language;
      if ((code === 'en' && !chosen) || code === chosen) return close();
      remember(code === 'en' ? null : code);
      dialog.classList.add('is-switching');
      location.reload();
    });
  }
})();
