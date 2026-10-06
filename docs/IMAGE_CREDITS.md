# Background imagery

The platform uses photographs found through web search and downloaded locally from Pexels. No paid audiobook cover art was copied. The horror treatment uses a misty Gothic castle as a Dracula-inspired atmosphere, rather than implying this platform sells Dracula.

| Use | Source |
| --- | --- |
| Platform / default library | [Library with shelves full of books](https://www.pexels.com/photo/library-with-shelves-full-of-books-5360440/) |
| Fiction | [Path in forest in sunlight](https://www.pexels.com/photo/path-in-forest-in-sunlight-24706137/) |
| Horror | [Castle on a foggy day](https://www.pexels.com/photo/castle-on-a-foggy-day-5970156/) |
| Romance | [Pink flowers at sunset](https://www.pexels.com/photo/pink-flowers-at-sunset-18368364/) |
| Non-fiction | [Compass on a map](https://www.pexels.com/photo/compass-on-a-map-14436272/) |
| Children’s | [Kid holding color pencils](https://www.pexels.com/photo/kid-holding-color-pencils-8363564/) |
| Educational | [Open book on desk](https://www.pexels.com/photo/open-book-on-desk-19561464/) |
| Drama | [Red theater curtain drapes on stage](https://www.pexels.com/photo/red-theater-curtain-drapes-on-stage-35962860/) |
| Originals | [Microphone in a recording studio](https://www.pexels.com/photo/photo-of-a-microphone-in-a-recording-studio-10942517/) |

Source pages describe these photographs as free to use. See the [Pexels license](https://www.pexels.com/license/) for the provider’s terms. Files live in `app/static/images/genres/`; visitors do not load images from third-party servers.

The user-provided logo was copied unchanged from `aud_logo.png` to `app/static/images/brand/aud-logo.png` and retains its transparency. It is used in the navbar and footer.

The full-page background opacity is 19% in light mode and 28% in dark mode. Genre headers and discovery tiles use stronger imagery, with readable foreground text. Additional admin-created genres fall back to the library theme until a matching asset and entry are added to `app/genre_themes.py`.
