let shelfTheme='dark';
try{shelfTheme=localStorage.getItem('myaudioshelf-theme')==='light'?'light':'dark';}catch{}
document.documentElement.dataset.colorMode=shelfTheme;

document.documentElement.classList.add('page-loading');
window.addEventListener('load',()=>document.documentElement.classList.remove('page-loading'),{once:true});
window.addEventListener('pageshow',()=>document.documentElement.classList.remove('page-loading'));
setTimeout(()=>document.documentElement.classList.remove('page-loading'),15000);
