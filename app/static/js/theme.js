let shelfTheme='dark';
try{shelfTheme=localStorage.getItem('myaudioshelf-theme')==='light'?'light':'dark';}catch{}
document.documentElement.dataset.colorMode=shelfTheme;
