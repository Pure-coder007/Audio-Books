'use strict';
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const postJSON = async (url, data) => {
  const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':csrf}, body:JSON.stringify(data), keepalive:true});
  if (!response.ok) throw new Error('Request failed');
  return response.json();
};
const toggle = document.querySelector('.nav-toggle');
toggle?.addEventListener('click', () => {
  const expanded = toggle.getAttribute('aria-expanded') !== 'true';
  toggle.setAttribute('aria-expanded', String(expanded));
  document.getElementById('main-nav').classList.toggle('open', expanded);
});
document.querySelectorAll('[data-dismiss]').forEach(button => button.addEventListener('click', () => button.parentElement.remove()));
const preview = document.getElementById('preview-audio');
const player = document.getElementById('preview-player');
let selectedPreview = null;
document.querySelectorAll('[data-trailer]').forEach(button => button.addEventListener('click', async () => {
  document.getElementById('full-audio')?.pause();
  document.querySelectorAll('audio').forEach(audio => { if (audio !== preview) audio.pause(); });
  selectedPreview?.classList.remove('playing');
  selectedPreview = button;
  player.hidden = false;
  document.body.classList.add('has-player');
  document.getElementById('preview-title').textContent = button.dataset.title;
  document.getElementById('preview-status').textContent = '';
  preview.src = button.dataset.trailer;
  try {
    await preview.play();
    button.classList.add('playing');
    if (!location.pathname.startsWith('/admin')) postJSON(`/books/${button.dataset.bookId}/trailer-play`, {}).catch(() => {});
  } catch {
    document.getElementById('preview-status').textContent = 'Preview unavailable. Please try again.';
  }
}));
document.getElementById('preview-close').addEventListener('click', () => {
  preview.pause(); player.hidden = true; document.body.classList.remove('has-player');
  selectedPreview?.classList.remove('playing'); selectedPreview?.focus();
});
preview.addEventListener('timeupdate', () => { if (preview.currentTime >= 60) preview.pause(); });
preview.addEventListener('ended', () => selectedPreview?.classList.remove('playing'));
document.querySelectorAll('audio').forEach(audio => audio.addEventListener('play', () => {
  document.querySelectorAll('audio').forEach(other => { if (other !== audio) other.pause(); });
}));
const fullPlayer = document.getElementById('full-player');
if (fullPlayer) {
  const audio = document.getElementById('full-audio');
  const tracks = [...document.querySelectorAll('[data-track]')];
  const status = document.getElementById('progress-status');
  let current = null, lastSaved = 0, refreshing = false, currentSeconds = 0;
  async function save() {
    if (!current || !audio.src) return;
    try {
      await postJSON(fullPlayer.dataset.progressUrl, {media_id:current.dataset.track, seconds:audio.currentTime});
      status.textContent = 'Your listening progress is saved.';
    } catch { status.textContent = 'Progress could not be saved. Check your connection or open a fresh purchase link.'; }
  }
  function select(track, position=0, play=false) {
    current = track;
    tracks.forEach(t => t.classList.toggle('active', t === track));
    audio.src = track.dataset.src;
    audio.addEventListener('loadedmetadata', () => {
      audio.currentTime = Math.min(position, Number.isFinite(audio.duration) ? audio.duration : position);
      if (play) audio.play().catch(() => {status.textContent='Press play to start listening.';});
    }, {once:true});
  }
  tracks.forEach(track => track.addEventListener('click', async () => {await save(); select(track,0,true);}));
  const resume = tracks.find(t => t.dataset.track === fullPlayer.dataset.resumeMedia) || tracks[0];
  if (resume) select(resume, Number(fullPlayer.dataset.resumeSeconds) || 0);
  document.getElementById('playback-speed').addEventListener('change', e => {audio.playbackRate=Number(e.target.value);});
  document.getElementById('skip-back').addEventListener('click', () => {audio.currentTime=Math.max(0,audio.currentTime-15);});
  document.getElementById('skip-forward').addEventListener('click', () => {audio.currentTime=Math.min(audio.duration || 0,audio.currentTime+15);});
  audio.addEventListener('timeupdate', () => {
    currentSeconds = audio.currentTime;
    if (Date.now()-lastSaved > 15000 && !audio.paused) {lastSaved=Date.now(); save();}
  });
  audio.addEventListener('pause', save);
  audio.addEventListener('ended', async () => {
    await save(); const next=tracks[tracks.indexOf(current)+1]; if (next) select(next,0,true);
  });
  audio.addEventListener('error', async () => {
    if (refreshing || !current) {status.textContent='Audio could not be loaded. Reopen your purchase link to continue.';return;}
    refreshing=true;
    try {
      const response=await fetch(`/library/media-url/${current.dataset.track}`);
      if (!response.ok) throw new Error();
      const result=await response.json(); current.dataset.src=result.url;
      select(current,currentSeconds,false);
      status.textContent='Listening link refreshed. Press play to continue.';
    } catch {status.textContent='Audio is unavailable. Please reopen your purchase link or try again later.';}
  });
  audio.addEventListener('playing',()=>{refreshing=false;});
  window.addEventListener('pagehide',save);
}
if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches && 'IntersectionObserver' in window) {
  const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('reveal');observer.unobserve(entry.target);}}),{threshold:0.08});
  document.querySelectorAll('.shelf-section,.genre-section,.behind-section').forEach(section=>observer.observe(section));
}

// Reserve the actual fixed header height, including an expanded mobile menu.
const fixedHeader = document.querySelector('.site-header');
const syncHeaderHeight = () => document.documentElement.style.setProperty('--nav-height', `${fixedHeader.offsetHeight}px`);
syncHeaderHeight();
if ('ResizeObserver' in window) new ResizeObserver(syncHeaderHeight).observe(fixedHeader);
else window.addEventListener('resize', syncHeaderHeight);




// Only animate visible covers; use a transform layer separate from their images.
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
const coverTargets = [...document.querySelectorAll('.cover-wrap,.hero-art,.detail-cover,.immersive-covers a,.listening-cover')];
if ('IntersectionObserver' in window) {
  const coverObserver = new IntersectionObserver(entries => entries.forEach(entry => {
    entry.target.classList.toggle('cover-visible', entry.isIntersecting);
  }), {threshold:0.08});
  coverTargets.forEach((cover, index) => {
    cover.style.setProperty('--cover-delay', `${-(index % 7) * 0.85}s`);
    coverObserver.observe(cover);
  });
}
if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
  document.querySelectorAll('.cover-wrap,.detail-cover').forEach(cover => {
    let frame;
    cover.addEventListener('pointermove', event => {
      if (motionPreference.matches) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rect = cover.getBoundingClientRect();
        cover.style.setProperty('--tilt-x', `${((event.clientY-rect.top)/rect.height-.5)*-10}deg`);
        cover.style.setProperty('--tilt-y', `${((event.clientX-rect.left)/rect.width-.5)*12}deg`);
      });
    });
    cover.addEventListener('pointerleave', () => {
      cancelAnimationFrame(frame);
      cover.style.setProperty('--tilt-x', '0deg');
      cover.style.setProperty('--tilt-y', '0deg');
    });
  });
}

// Add to cart in place, keeping the visitor on the shelf they are browsing.
const cartFeedback = document.getElementById('cart-feedback');
let feedbackTimer;
let cartAddQueue = Promise.resolve();
document.querySelectorAll('[data-cart-add]').forEach(form => form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  if (button.disabled) return;
  button.disabled = true;
  const previousAddition = cartAddQueue;
  let releaseAddition;
  cartAddQueue = new Promise(resolve => {releaseAddition = resolve;});
  try {
    await previousAddition;
    const tokenResponse = await fetch('/session/csrf', {credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
    if(!tokenResponse.ok)throw new Error('Could not refresh your session. Please try again.');
    const token = (await tokenResponse.json()).csrf_token;
    const payload = new FormData(form);payload.set('csrf_token',token);
    const response = await fetch(form.action, {method:'POST',credentials:'same-origin',headers:{Accept:'application/json','X-CSRFToken':token},body:payload});
    const result = response.headers.get('content-type')?.includes('application/json') ? await response.json() : {error:'Could not add this title. Refresh the page and try again.'};
    if (!response.ok) throw new Error(result.error || 'Could not add this title. Please try again.');
    document.querySelectorAll('.cart-count').forEach(count => count.textContent = result.count);
    document.querySelector('.cart-link').setAttribute('aria-label', `Shopping cart, ${result.count} audiobooks`);
    button.classList.add('cart-added');
    button.setAttribute('aria-label', `${result.title} is in your cart`);
    const card = form.closest('.book-card');
    card?.classList.remove('book-celebrate');
    if (card) {void card.offsetWidth;card.classList.add('book-celebrate');}
    cartFeedback.replaceChildren();
    const message = document.createElement('span');
    message.textContent = result.added ? `“${result.title}” added to your cart.` : `“${result.title}” is already in your cart.`;
    const link = document.createElement('a');link.href='/cart';link.textContent='View cart →';
    const close = document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Dismiss cart notification');close.onclick=()=>{cartFeedback.hidden=true;};
    cartFeedback.append(message,link,close);cartFeedback.hidden=false;
    clearTimeout(feedbackTimer);feedbackTimer=setTimeout(()=>{cartFeedback.hidden=true;},7000);
  } catch(error) {
    cartFeedback.textContent = error.message || 'Could not add this title. Please try again.';
    cartFeedback.hidden=false;
  } finally {button.disabled=false;releaseAddition();}
}));

// Pointer feedback for book cards.
document.querySelectorAll('.cover-wrap,.cart-cover,.immersive-covers a').forEach(cover => {
  cover.addEventListener('pointerdown', () => {cover.classList.add('cover-pressed');});
  ['pointerup','pointercancel','pointerleave'].forEach(name => cover.addEventListener(name, () => cover.classList.remove('cover-pressed')));
  cover.addEventListener('pointerenter', () => {
    const card = cover.closest('.book-card');
    card?.classList.add('book-engaged');
  });
  cover.addEventListener('pointerleave', () => cover.closest('.book-card')?.classList.remove('book-engaged'));
});

// A hinged jacket over a paper block; the image and its alt text remain intact.
const openingBooks = [...document.querySelectorAll('.cover-wrap,.cart-cover,.hero-art,.detail-cover,.immersive-covers a')];
openingBooks.forEach(host => {
  const image = host.querySelector('img');
  if (!image || host.querySelector('.book-opening')) return;
  const book = document.createElement('span');book.className='book-opening';
  const paper = document.createElement('span');paper.className='book-paper';paper.setAttribute('aria-hidden','true');
  const caption=document.createElement('span');caption.className='paper-caption';caption.textContent='A story awaits.';
  paper.append(caption);
  for(let i=0;i<5;i++){const line=document.createElement('span');line.className='paper-line';paper.append(line);}
  const jacket=document.createElement('span');jacket.className='book-jacket';
  image.before(book);jacket.append(image);book.append(paper,jacket);
  host.addEventListener('pointerenter',event=>{
    if(event.pointerType==='touch')return;
    host.classList.add('book-is-open');playBookSound();
  });
  host.addEventListener('pointerleave',()=>host.classList.remove('book-is-open','book-opening-wide'));
  host.addEventListener('focusin',()=>host.classList.add('book-is-open'));
  host.addEventListener('focusout',()=>host.classList.remove('book-is-open','book-opening-wide'));
  host.addEventListener('pointerdown',()=>{host.classList.add('book-is-open','book-opening-wide');playBookSound(true);});
  host.addEventListener('pointercancel',()=>host.classList.remove('book-is-open','book-opening-wide'));
  const link=host.matches('a')?host:null;
  if(link)link.addEventListener('click',event=>{
    if(event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||link.target==='_blank')return;
    host.classList.add('book-is-open','book-opening-wide');playBookSound(true);
    if(motionPreference.matches)return;
    event.preventDefault();
    if(host.dataset.navigating)return;
    host.dataset.navigating='true';
    setTimeout(()=>{window.location.assign(link.href);},340);
  });
});

// Browser autoplay rules require a click/tap before hover audio can be enabled.
let bookAudioContext=null,bookSoundMuted=false,lastBookSound=0;
try{bookSoundMuted=localStorage.getItem('myaudioshelf-book-sound')==='muted';}catch{}
const soundToggle=document.querySelector('.book-sound-toggle');
function updateSoundButton(){
  soundToggle.setAttribute('aria-pressed',String(!bookSoundMuted));
  soundToggle.setAttribute('aria-label',bookSoundMuted?'Enable book-opening sounds':'Mute book-opening sounds');
  soundToggle.title=bookSoundMuted?'Book sounds off':'Book sounds on · hover audio starts after your first click';
  soundToggle.classList.toggle('sound-muted',bookSoundMuted);
}
function unlockBookAudio(){
  if(bookSoundMuted)return;
  const AudioContext=window.AudioContext||window.webkitAudioContext;
  if(!AudioContext)return;
  try{bookAudioContext ||= new AudioContext();bookAudioContext.resume().catch(()=>{});}catch{}
}
function playBookSound(fromGesture=false){
  if(bookSoundMuted||[...document.querySelectorAll('audio')].some(audio=>!audio.paused))return;
  if(fromGesture)unlockBookAudio();
  if(!bookAudioContext)return;
  if(bookAudioContext.state!=='running'){
    if(fromGesture)bookAudioContext.resume().then(()=>playBookSound()).catch(()=>{});
    return;
  }
  if(performance.now()-lastBookSound<450)return;
  lastBookSound=performance.now();
  // A quiet filtered paper rustle, generated locally.
  const context=bookAudioContext,duration=.32;
  const buffer=context.createBuffer(1,Math.ceil(context.sampleRate*duration),context.sampleRate);
  const samples=buffer.getChannelData(0);
  for(let i=0;i<samples.length;i++){
    const t=i/context.sampleRate;
    const envelope=Math.pow(Math.sin(Math.PI*t/duration),1.8);
    samples[i]=(Math.random()*2-1)*envelope;
  }
  const source=context.createBufferSource();source.buffer=buffer;
  const filter=context.createBiquadFilter();filter.type='bandpass';filter.frequency.value=1800;filter.Q.value=.55;
  const gain=context.createGain();gain.gain.value=.075;
  source.connect(filter);filter.connect(gain);gain.connect(context.destination);source.start();
  source.onended=()=>{source.disconnect();filter.disconnect();gain.disconnect();};
}
updateSoundButton();
document.addEventListener('pointerdown',unlockBookAudio,{capture:true});
document.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' ')unlockBookAudio();},{capture:true});
soundToggle.addEventListener('click',()=>{
  bookSoundMuted=!bookSoundMuted;
  try{localStorage.setItem('myaudioshelf-book-sound',bookSoundMuted?'muted':'enabled');}catch{}
  updateSoundButton();if(!bookSoundMuted){unlockBookAudio();playBookSound(true);}
});

const themeButton=document.querySelector('.theme-toggle');
function updateThemeButton(){const dark=document.documentElement.dataset.colorMode==='dark';document.querySelector('meta[name="theme-color"]').content=dark?'#111813':'#f9f8f3';themeButton.textContent=dark?'☀':'☾';themeButton.setAttribute('aria-label',dark?'Switch to light theme':'Switch to dark theme');themeButton.title=themeButton.getAttribute('aria-label');}
updateThemeButton();
themeButton.addEventListener('click',()=>{const mode=document.documentElement.dataset.colorMode==='dark'?'light':'dark';document.documentElement.dataset.colorMode=mode;try{localStorage.setItem('myaudioshelf-theme',mode);}catch{}updateThemeButton();});

// A small, nonblocking spinner for normal page navigation.
let loaderTimeout;
function showPageLoader(){
  document.documentElement.classList.add('page-loading');
  clearTimeout(loaderTimeout);
  loaderTimeout=setTimeout(()=>document.documentElement.classList.remove('page-loading'),15000);
}
document.addEventListener('click',event=>{
  const link=event.target.closest('a[href]');
  if(!link||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||link.hasAttribute('download')||(link.target&&link.target!=='_self'))return;
  const destination=new URL(link.href,location.href);
  if(destination.origin!==location.origin||(destination.pathname===location.pathname&&destination.search===location.search&&destination.hash))return;
  if(event.defaultPrevented&&!link.dataset.navigating)return;
  showPageLoader();
});
document.addEventListener('submit',event=>{
  if(!event.defaultPrevented&&!event.target.matches('[data-cart-add]'))showPageLoader();
});

// Keep discovery navigation accessible without adding another navigation bar.
const discoverMenu=document.querySelector('.nav-discover');
document.addEventListener('click',event=>{if(discoverMenu&&!discoverMenu.contains(event.target))discoverMenu.open=false;});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&discoverMenu?.open){discoverMenu.open=false;discoverMenu.querySelector('summary').focus();}});
// Native demonstration players share playback focus with previews.
document.addEventListener('play',event=>{if(event.target.tagName==='AUDIO')document.querySelectorAll('audio').forEach(audio=>{if(audio!==event.target)audio.pause();});},true);

// Aggregate listening events: no identity, country or fingerprint collection.
document.querySelectorAll('audio').forEach(audio=>{
  audio.addEventListener('emptied',()=>delete audio.dataset.engagementStarted);
  audio.addEventListener('play',()=>{if(!audio.dataset.engagementStarted){audio.dataset.engagementStarted='true';postJSON('/engagement',{kind:'audio_start'}).catch(()=>{});}});
  audio.addEventListener('ended',()=>{postJSON('/engagement',{kind:'audio_complete'}).catch(()=>{});delete audio.dataset.engagementStarted;});
});
