// Shelf studio guided tour: spotlights each part of a page with a short explanation.
(() => {
  const source = document.getElementById('tour-data');
  if (!source) return;
  const tour = JSON.parse(source.textContent);
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const ns = 'http://www.w3.org/2000/svg';
  let steps = [], index = 0, auto = false, root, spotlight, card, lastFocus, frame;

  const report = action => fetch(tour.endpoint, {method: 'POST', credentials: 'same-origin', keepalive: true,
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
    body: JSON.stringify({action, page: tour.page})}).catch(() => {});
  const target = key => key ? document.querySelector(`[data-tour="${key}"]`) : null;
  const shown = element => element && element.getClientRects().length > 0;
  const clamp = (value, min, max) => Math.min(Math.max(value, min), Math.max(min, max));
  const wait = ms => new Promise(resolve => setTimeout(resolve, reducedMotion.matches ? 0 : ms));

  function icon(paths, className) {
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    if (className) svg.setAttribute('class', className);
    paths.forEach(d => { const path = document.createElementNS(ns, 'path'); path.setAttribute('d', d); svg.append(path); });
    return svg;
  }

  function node(tag, className, attributes = {}) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
    return element;
  }

  function build() {
    root = node('div', 'tour-root');
    const blocker = node('div', 'tour-blocker');
    blocker.addEventListener('click', () => {
      card.classList.remove('tour-nudge'); void card.offsetWidth; card.classList.add('tour-nudge');
    });
    spotlight = node('div', 'tour-spotlight', {'aria-hidden': 'true'});
    card = node('section', 'tour-card', {role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'tour-title', 'aria-describedby': 'tour-text'});

    const arrow = node('span', 'tour-arrow', {'aria-hidden': 'true'});
    const head = node('div', 'tour-head');
    const chip = node('span', 'tour-chip');
    chip.append(node('span', 'tour-chip-dot'), node('span', '', {'data-count': ''}));
    const close = node('button', 'tour-close', {type: 'button', 'aria-label': 'Skip the guided tour'});
    close.append(icon(['M6 6l12 12', 'M18 6 6 18']));
    head.append(chip, close);

    const hero = node('div', 'tour-hero', {'data-hero': '', 'aria-hidden': 'true'});
    hero.append(illustration());
    const title = node('h2', 'tour-title', {id: 'tour-title'});
    const text = node('p', 'tour-text', {id: 'tour-text'});
    const note = node('p', 'tour-note', {'data-note': ''});
    const progress = node('div', 'tour-progress', {'aria-hidden': 'true'});

    const foot = node('div', 'tour-foot');
    const skip = node('button', 'tour-skip', {type: 'button', 'data-skip': ''});
    skip.textContent = 'Skip tour';
    const navigation = node('div', 'tour-nav');
    const back = node('button', 'tour-back', {type: 'button', 'data-back': ''});
    back.append(icon(['M15 18l-6-6 6-6']), document.createTextNode('Back'));
    const next = node('button', 'tour-next', {type: 'button', 'data-next': ''});
    next.append(node('span', '', {'data-next-label': ''}), icon(['M9 6l6 6-6 6'], 'tour-next-arrow'), icon(['M5 12.5l4.2 4.2L19 7'], 'tour-next-check'));
    navigation.append(back, next);
    foot.append(skip, navigation);
    const never = node('button', 'tour-never', {type: 'button', 'data-never': ''});
    never.textContent = 'Don’t show this guide again';
    const live = node('p', 'sr-only', {'aria-live': 'polite', 'data-live': ''});

    card.append(arrow, head, hero, title, text, note, progress, foot, never, live);
    root.append(blocker, spotlight, card);
    document.body.append(root);

    close.addEventListener('click', () => finish('skip'));
    skip.addEventListener('click', () => finish('skip'));
    never.addEventListener('click', () => finish('never'));
    back.addEventListener('click', () => index > 0 && go(index - 1));
    next.addEventListener('click', () => index < steps.length - 1 ? go(index + 1) : finish('seen'));
  }

  // Open book with rising sound waves, drawn in the brand palette.
  function illustration() {
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 220 120');
    const parts = [
      ['circle', {cx: 110, cy: 64, r: 52, class: 'tour-art-glow'}],
      ['path', {d: 'M38 86c22-10 46-10 72 2V40c-26-12-50-12-72-2Z', class: 'tour-art-page'}],
      ['path', {d: 'M182 86c-22-10-46-10-72 2V40c26-12 50-12 72-2Z', class: 'tour-art-page tour-art-page-right'}],
      ['path', {d: 'M110 40v48', class: 'tour-art-spine'}],
      ['path', {d: 'M50 52c16-5 32-5 48 1M50 63c16-5 32-5 48 1M50 74c16-5 32-5 48 1', class: 'tour-art-line'}],
      ['path', {d: 'M122 53c16-6 32-6 48-1M122 64c16-6 32-6 48-1', class: 'tour-art-line'}],
      ['path', {d: 'M98 26c4-6 20-6 24 0M90 17c9-11 31-11 40 0M82 8c14-15 42-15 56 0', class: 'tour-art-wave'}],
      ['circle', {cx: 168, cy: 30, r: 4, class: 'tour-art-spark'}],
      ['circle', {cx: 52, cy: 28, r: 3, class: 'tour-art-spark tour-art-spark-late'}],
    ];
    parts.forEach(([tag, attributes]) => {
      const element = document.createElementNS(ns, tag);
      Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
      svg.append(element);
    });
    return svg;
  }

  function fill(step) {
    const last = index === steps.length - 1;
    const welcome = step.kind === 'welcome';
    card.dataset.kind = welcome ? 'welcome' : last ? 'finish' : 'step';
    card.querySelector('[data-count]').textContent = welcome ? 'Quick tour' : `Step ${index + 1} of ${steps.length}`;
    card.querySelector('#tour-title').textContent = step.title;
    card.querySelector('#tour-text').textContent = step.text;
    card.querySelector('[data-hero]').hidden = !welcome;
    const note = card.querySelector('[data-note]');
    note.hidden = !(welcome && auto && tour.sign_in);
    note.textContent = `Sign-in ${tour.sign_in} of ${tour.sign_ins}. This guide opens on your first ${tour.sign_ins} sign-ins.`;
    card.querySelector('[data-back]').hidden = index === 0;
    card.querySelector('[data-skip]').hidden = last;
    card.querySelector('[data-next-label]').textContent = welcome ? 'Show me around' : last ? 'Finish' : 'Next';
    card.querySelector('[data-never]').hidden = !(auto && (welcome || last));
    card.querySelector('[data-live]').textContent = `${step.title} ${step.text}`;
    const progress = card.querySelector('.tour-progress');
    progress.replaceChildren(...steps.map((_, i) => node('span', i < index ? 'done' : i === index ? 'current' : '')));
  }

  function place() {
    if (!root) return;
    const step = steps[index];
    const element = step.element;
    const vw = window.innerWidth, vh = window.innerHeight;
    const sheet = vw < 720;
    card.classList.toggle('tour-sheet', sheet && !!element);
    if (!element) {
      root.classList.add('tour-centered');
      Object.assign(card.style, {top: '', left: ''});
      return;
    }
    root.classList.remove('tour-centered');
    const rect = element.getBoundingClientRect(), pad = 8, edge = 6;
    const top = clamp(rect.top - pad, edge, vh - edge), bottom = clamp(rect.bottom + pad, edge, vh - edge);
    const left = clamp(rect.left - pad, edge, vw - edge), right = clamp(rect.right + pad, edge, vw - edge);
    const box = {top, left, width: right - left, height: Math.max(bottom - top, 24)};
    Object.assign(spotlight.style, {top: `${box.top}px`, left: `${box.left}px`, width: `${box.width}px`, height: `${box.height}px`});
    if (sheet) {
      Object.assign(card.style, {top: '', left: ''});
      return;
    }
    const cw = card.offsetWidth, ch = card.offsetHeight, gap = 20, margin = 14;
    const space = {right: vw - box.left - box.width, left: box.left, bottom: vh - box.top - box.height, top: box.top};
    const fits = side => (side === 'left' || side === 'right') ? space[side] >= cw + gap + margin : space[side] >= ch + gap + margin;
    const side = ['right', 'bottom', 'left', 'top'].find(fits) || 'inside';
    const midY = box.top + box.height / 2, midX = box.left + box.width / 2;
    let x, y;
    if (side === 'right') { x = box.left + box.width + gap; y = clamp(midY - ch / 2, margin, vh - ch - margin); }
    else if (side === 'left') { x = box.left - gap - cw; y = clamp(midY - ch / 2, margin, vh - ch - margin); }
    else if (side === 'bottom') { y = box.top + box.height + gap; x = clamp(midX - cw / 2, margin, vw - cw - margin); }
    else if (side === 'top') { y = box.top - gap - ch; x = clamp(midX - cw / 2, margin, vw - cw - margin); }
    else { x = clamp(midX - cw / 2, margin, vw - cw - margin); y = vh - ch - margin; }
    card.dataset.side = side;
    const offset = side === 'right' || side === 'left' ? clamp(midY - y, 26, ch - 26) : clamp(midX - x, 26, cw - 26);
    card.style.setProperty('--arrow', `${offset}px`);
    Object.assign(card.style, {top: `${y}px`, left: `${x}px`});
  }

  async function go(next) {
    index = next;
    const step = steps[index];
    card.classList.add('tour-swapping');
    if (step.element) {
      const rect = step.element.getBoundingClientRect();
      const header = document.querySelector('.site-header')?.offsetHeight || 0;
      if (rect.top < header + 12 || rect.bottom > window.innerHeight - 12) {
        step.element.scrollIntoView({block: rect.height > window.innerHeight * 0.6 ? 'start' : 'center', behavior: reducedMotion.matches ? 'auto' : 'smooth'});
        await wait(450);
      }
    }
    await wait(140);
    fill(step);
    place();
    card.classList.remove('tour-swapping');
    card.querySelector('[data-next]').focus({preventScroll: true});
  }

  function start(automatic) {
    if (root) return;
    steps = tour.steps.map(step => ({...step, element: target(step.target)}))
      .filter(step => !step.target || shown(step.element) || step.kind === 'finish')
      .map(step => ({...step, element: shown(step.element) ? step.element : null}));
    if (!steps.length) return;
    auto = automatic;
    index = 0;
    lastFocus = document.activeElement;
    build();
    document.body.classList.add('tour-open');
    requestAnimationFrame(() => root.classList.add('tour-visible'));
    go(0);
    window.addEventListener('resize', schedule);
    window.addEventListener('scroll', schedule, {passive: true});
    document.addEventListener('keydown', keys, true);
  }

  function finish(action) {
    if (!root) return;
    if (auto || action === 'never') report(action);
    const closing = root;
    root = null;
    closing.classList.remove('tour-visible');
    document.body.classList.remove('tour-open');
    window.removeEventListener('resize', schedule);
    window.removeEventListener('scroll', schedule);
    document.removeEventListener('keydown', keys, true);
    setTimeout(() => closing.remove(), reducedMotion.matches ? 0 : 320);
    if (lastFocus && lastFocus.focus) lastFocus.focus({preventScroll: true});
    if (action === 'skip') toast('Tour skipped. Open “Guided tour” in the sidebar whenever you need it.');
    if (action === 'never') toast('The guide won’t open automatically again. “Guided tour” is always in the sidebar.');
    if (action === 'seen' && auto) toast('Nice work. Each studio page has its own short guide the first time you visit.');
  }

  function toast(message) {
    const note = node('div', 'tour-toast', {role: 'status'});
    note.append(icon(['M5 12.5l4.2 4.2L19 7']), document.createTextNode(message));
    document.body.append(note);
    requestAnimationFrame(() => note.classList.add('tour-toast-in'));
    setTimeout(() => { note.classList.remove('tour-toast-in'); setTimeout(() => note.remove(), 400); }, 4200);
  }

  function schedule() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(place);
  }

  function keys(event) {
    if (!root) return;
    if (event.key === 'Escape') { event.preventDefault(); finish('skip'); }
    else if (event.key === 'ArrowRight') { event.preventDefault(); card.querySelector('[data-next]').click(); }
    else if (event.key === 'ArrowLeft' && index > 0) { event.preventDefault(); go(index - 1); }
    else if (event.key === 'Tab') {
      const focusable = [...card.querySelectorAll('button')].filter(button => !button.hidden);
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (!card.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  }

  document.querySelectorAll('[data-tour-start]').forEach(button => button.addEventListener('click', () => start(false)));
  if (tour.auto) {
    const begin = () => setTimeout(() => start(true), reducedMotion.matches ? 0 : 450);
    document.readyState === 'complete' ? begin() : window.addEventListener('load', begin, {once: true});
  }
})();
