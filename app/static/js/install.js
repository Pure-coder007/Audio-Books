// Install prompt: offers MyAudioShelf as an app on phones, tablets and computers.
// Chrome, Edge and Samsung Internet open their own install window; Safari and
// Firefox, which have none, get two short steps instead.
(() => {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});

  const KEY = 'myaudioshelf-install';
  const VISIT_KEY = 'myaudioshelf-visit-start';
  const SNOOZE = 7 * 24 * 60 * 60 * 1000;
  const DELAY = 12000;
  const QUIET = ['/admin', '/checkout', '/library/access'];
  const ns = 'http://www.w3.org/2000/svg';
  const ua = navigator.userAgent;
  const preview = new URLSearchParams(location.search).get('install-preview');
  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const touch = window.matchMedia('(pointer: coarse)').matches;
  const ios = /iphone|ipad|ipod/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const macSafari = !ios && /Macintosh/.test(ua) && /Version\/(1[7-9]|[2-9]\d)[.\d]* Safari/.test(ua) && !/Chrome|Chromium|Edg|OPR|Firefox/.test(ua);
  const androidFirefox = /Android/.test(ua) && /Firefox/.test(ua);
  // Browsers inside social apps cannot add to the Home Screen, so the steps would mislead.
  const inApp = /FBAN|FBAV|Instagram|Line\/|Snapchat|TikTok|musical_ly|BytedanceWebview|Twitter/i.test(ua);
  // Safari 26 on iPhone tucks Share under the ••• button.
  const compactSafari = /iPhone/.test(ua) && /Version\/(2[6-9]|[3-9]\d)/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);

  const ICONS = {
    close: ['M6 6l12 12', 'M18 6 6 18'],
    check: ['M20 6 9 17l-5-5'],
    download: ['M12 4v11', 'm7 10 5 5 5-5', 'M5 20h14'],
    share: ['M12 15V3', 'm8 7 4-4 4 4', 'M8 10H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-2'],
    add: ['M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z', 'M12 8v8', 'M8 12h8'],
    more: ['M5 12h.01', 'M12 12h.01', 'M19 12h.01'],
    menu: ['M12 5h.01', 'M12 12h.01', 'M12 19h.01'],
    done: ['M22 11.1V12a10 10 0 1 1-5.9-9.1', 'M22 4 12 14l-3-3'],
    info: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'M12 16v-4', 'M12 8h.01']
  };
  // Steps for browsers without an install window; [text] is shown in bold.
  const GUIDES = {
    ios: {text: 'Add it to your Home Screen to listen like an app.', steps: [
      compactSafari ? [['Tap ', ['•••'], ', then ', ['Share']], 'more'] : [['Tap ', ['Share'], ' in your browser bar'], 'share'],
      [['Choose ', ['Add to Home Screen']], 'add']]},
    mac: {text: 'Add it to your Dock to listen like an app, in its own window.', steps: [
      [['Click ', ['Share'], ' in the Safari toolbar'], 'share'],
      [['Choose ', ['Add to Dock']], 'add']]},
    firefox: {text: 'Add it to your home screen to listen like an app.', steps: [
      [['Tap the ', ['⋮'], ' menu'], 'menu'],
      [['Choose ', ['Add to Home screen']], 'add']]}
  };

  let deferred = null, variant = null, stack, card, timer = 0;

  const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch { return {}; } };
  const save = state => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch {} };
  const quiet = () => QUIET.some(path => location.pathname === path || location.pathname.startsWith(`${path}/`));
  const snoozed = () => { const state = read(); return state.installed || state.snoozedUntil > Date.now(); };
  const footerButtons = () => document.querySelectorAll('[data-install-open]');

  function icon(name, className) {
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    if (className) svg.setAttribute('class', className);
    ICONS[name].forEach(d => { const path = document.createElementNS(ns, 'path'); path.setAttribute('d', d); svg.append(path); });
    return svg;
  }

  function node(tag, className, attributes = {}, ...children) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
    element.append(...children);
    return element;
  }

  const rich = parts => parts.map(part => Array.isArray(part) ? node('b', '', {}, part[0]) : part);

  function root() {
    if (!stack) {
      stack = node('div', 'install-stack');
      document.body.append(stack);
    }
    return stack;
  }

  function build() {
    const guide = GUIDES[variant];
    const title = node('p', 'install-title', {id: 'install-title'}, 'Install MyAudioShelf');
    const text = node('p', 'install-text', {id: 'install-text'}, guide ? guide.text
      : touch ? 'Your stories on your home screen, one tap away.' : 'Open it from your dock, taskbar or Start menu, in its own window.');
    const close = node('button', 'install-close', {type: 'button', 'aria-label': 'Dismiss install offer'}, icon('close'));
    const head = node('div', 'install-head', {},
      node('span', 'install-icon', {}, node('img', '', {src: '/static/icons/app-192.png', alt: '', width: '52', height: '52'})),
      node('div', 'install-copy', {}, title, text), close);

    const list = guide
      ? node('ol', 'install-steps', {}, ...guide.steps.map(([parts, name], index) =>
          node('li', '', {}, node('span', 'install-step-number', {'aria-hidden': 'true'}, String(index + 1)), node('span', 'install-step-text', {}, ...rich(parts)), icon(name))))
      : node('ul', 'install-perks', {}, ...(touch ? ['Opens in one tap', 'Full-screen listening', 'Light on data'] : ['Its own window', 'Opens in one click', 'Light on data'])
          .map(perk => node('li', '', {}, icon('check'), perk)));

    const primary = guide
      ? node('button', 'install-primary', {type: 'button'}, 'Got it')
      : node('button', 'install-primary', {type: 'button'}, node('span', 'install-shine', {'aria-hidden': 'true'}), icon('download'), node('span', 'install-label', {}, 'Install app'));
    const later = node('button', 'install-later', {type: 'button'}, 'Not now');
    const actions = node('div', 'install-actions', {}, primary, later, node('span', 'install-note', {}, 'Free · no app store'));

    const section = node('section', `install-card${guide ? ' install-guide' : ''}`, {'aria-labelledby': 'install-title', 'aria-describedby': 'install-text'},
      node('span', 'install-accent', {'aria-hidden': 'true'}), node('span', 'install-glow', {'aria-hidden': 'true'}),
      node('div', 'install-body', {}, head, list, actions));
    close.addEventListener('click', dismiss);
    later.addEventListener('click', dismiss);
    primary.addEventListener('click', guide ? dismiss : install);
    section.addEventListener('keydown', event => { if (event.key === 'Escape') dismiss(); });
    return section;
  }

  function enter(element) {
    root().append(element);
    requestAnimationFrame(() => requestAnimationFrame(() => element.classList.add('install-in')));
  }

  function leave(element) {
    if (!element) return;
    element.classList.remove('install-in');
    element.classList.add('install-out');
    setTimeout(() => element.remove(), 260);
  }

  function show(focus = false) {
    clearTimeout(timer);
    if (card || !variant) return;
    card = build();
    enter(card);
    if (focus) card.querySelector('.install-primary').focus({preventScroll: true});
  }

  function hide() {
    leave(card);
    card = null;
  }

  function dismiss() {
    hide();
    if (!preview) save({snoozedUntil: Date.now() + SNOOZE});
  }

  function toast(kind, title, text) {
    const element = node('div', `install-toast install-toast-${kind}`, {role: 'status', 'aria-live': 'polite'},
      node('span', 'install-accent', {'aria-hidden': 'true'}),
      node('div', 'install-body', {},
        node('span', 'install-toast-icon', {}, icon(kind === 'success' ? 'done' : 'info')),
        node('div', 'install-copy', {}, node('p', 'install-title', {}, title), node('p', 'install-text', {}, text))),
      node('span', 'install-timer', {'aria-hidden': 'true'}));
    enter(element);
    setTimeout(() => leave(element), 5200);
  }

  async function install() {
    if (preview || !deferred) {
      hide();
      toast('info', 'Install preview', 'On a real visit, your browser’s install window opens here.');
      return;
    }
    const button = card.querySelector('.install-primary');
    button.disabled = true;
    card.querySelector('.install-label').textContent = 'Opening…';
    try {
      await deferred.prompt();
      const {outcome} = await deferred.userChoice;
      deferred = null;
      footerButtons().forEach(item => { item.hidden = true; });
      hide();
      if (outcome === 'accepted') {
        save({installed: true});
        toast('success', 'MyAudioShelf is installed', 'Open it from your home screen or app list any time.');
      } else {
        save({snoozedUntil: Date.now() + SNOOZE});
      }
    } catch {
      hide();
    }
  }

  // Wait until the visitor has spent a little time on the site, across pages.
  function schedule() {
    let start = Date.now();
    try {
      start = Number(sessionStorage.getItem(VISIT_KEY)) || start;
      sessionStorage.setItem(VISIT_KEY, String(start));
    } catch {}
    clearTimeout(timer);
    timer = setTimeout(attempt, preview ? 600 : Math.max(DELAY - (Date.now() - start), 2500));
  }

  // Never interrupt an open menu, a form being filled in or a hidden tab.
  function attempt() {
    const typing = document.activeElement?.matches('input, textarea, select');
    const menuOpen = document.querySelector('#main-nav.open, .nav-discover[open]');
    if (document.hidden || typing || menuOpen) timer = setTimeout(attempt, 5000);
    else show();
  }

  function offer(kind) {
    variant = kind;
    footerButtons().forEach(item => { item.hidden = false; });
    if (preview || (!snoozed() && !quiet())) schedule();
  }

  footerButtons().forEach(item => item.addEventListener('click', () => {
    if (deferred && !preview) {
      show();
      install();
    } else {
      show(true);
    }
  }));

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    deferred = event;
    if (!standalone && !preview) offer('app');
  });

  window.addEventListener('appinstalled', () => {
    save({installed: true});
    deferred = null;
    hide();
    footerButtons().forEach(item => { item.hidden = true; });
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    fetch('/engagement', {method: 'POST', credentials: 'same-origin', keepalive: true,
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify({kind: 'app_install'})}).catch(() => {});
  });

  if (preview) offer({ios: 'ios', mac: 'mac', firefox: 'firefox'}[preview] || 'app');
  else if (!standalone && !inApp) {
    if (ios) offer('ios');
    else if (macSafari) offer('mac');
    else if (androidFirefox) offer('firefox');
  }
})();
