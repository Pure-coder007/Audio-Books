# Business brief integration

MyAudioShelf Ltd (Companies House 17533587) operates this storefront live at https://myaudioshelf.com. The Flask storefront, purchase library, cart, staff CMS, dark/light theme controls and book-opening animations remain in place. Listeners sign in to their library with the email used at checkout; listener self-registration is not offered. Authors and publishers create their own accounts for a subscription plan (see below).

## Public pages

- `/`: revised business positioning, production formats, audio comparison, children and innovation introductions, existing book shelves and newsletter.
- `/about`: company purpose, vision and values.
- `/services`: eight production service areas.
- `/immersive-audio`: production formats and two accessible audio demonstrations.
- `/children`: developing Kids programme, families, schools and children's shelf.
- `/originals`: original IP direction and existing collection.
- `/innovation`: StoryDNA Engine, persistent Story Intelligence Profile, Sound Recommendation Engine, Audio Continuity Engine and Author Control Layer, presented as live production technology. The engines run in the production pipeline, outside this web application.
- `/pricing`: the four author subscription plans (Lite £19, Author £39, Pro Author £79, Publisher from £199 a month) with the 14-day free trial, linked from the main menu.
- `/production`: leads with the subscription plans and free trial; keeps the author/publisher form, project metadata, optional private manuscript and six-stage process as a contact route.
- `/authors/signup`, `/authors/login`, `/authors/account`: author sign-up and login. The account shows the author's plan, trial timeline and the projects they have sent, and lets them change plan or password.
- `/contact`: general, author, children, partnership, creative, innovation/investment and accessibility enquiries.
- `/privacy`, `/terms`, `/cookies`, `/copyright`, `/accessibility`: public policies, naming MyAudioShelf Ltd and its registered office.

The fixed navbar keeps the main shelves and the Discover and Services menus together. Discover exposes the company and content pages, including author submissions and contact. Footer links expose policies, staff access and the official Facebook, Instagram, X and TikTok accounts.

## Working submissions and files

Contact and project submissions persist in the existing admin enquiries inbox. Staff see enquiry type and project metadata. Manuscripts support PDF, UTF-8 TXT and non-macro DOCX, with a 10 MB upload cap, basic file validation and random storage filenames. Files are served as attachments only to owner/editor staff; they are not publicly addressable. Media cleanup retains enquiry attachments. Each manuscript is analysed by the StoryDNA Engine in the production pipeline, and the author approves each resulting production decision through the Author Control Layer. The storefront stores manuscripts securely for the production team, who run them through that pipeline.

Newsletter first names are stored alongside consent-based email registration. The existing durable email outbox handles listening-access emails; enquiry auto-replies and newsletter campaigns are not enabled without mail/content setup.

## Audio and analytics

Available production comparison assets take priority; otherwise the bundled demonstration recordings are explicitly labelled. Native comparison players are shown only for actual paired production assets. Bundled synthetic demonstrations and transcript blocks are no longer shown on public pages. The existing listening player retains speed, chapters and progress.

First-party aggregate page views, starts/completions, author submissions and contact submissions are recorded without introducing advertising cookies. Dashboard counts show page views, completions and contacts. These are event counts, not unique visitors or verified conversion rates. Geographic reporting, comprehensive device reporting and an external analytics dashboard remain future integrations. Static demonstration audio is counted in aggregate events.

## Production technology and roadmap

The StoryDNA, Sound Recommendation and Continuity Engines are part of MyAudioShelf's production pipeline and are maintained separately from this storefront codebase; `/innovation` presents them.

Author subscription plans launch in February 2027: Lite £19, Author £39, Pro Author £79 and Publisher from £199 a month, each with a 14-day free trial. Authors can already create an account and reserve a plan; their trial starts on launch day. The storefront also sells individual audiobooks with free previews, guest checkout and a private listening library. Later roadmap releases are interactive and adaptive audio, parental controls and personalised listening. Each will be documented here as it ships.

Production imagery uses the established genre photograph assets; no stock photograph is claimed as the company's staff or studio. Verified behind-the-scenes photographs, licensed production recordings, official social links and business contact particulars can be added when provided.

## Deployment

Run `flask --app wsgi db upgrade` to add enquiry and newsletter fields. Render's existing startup migration hook applies this migration automatically. Existing enquiry rows receive the `author` type, preserving their contents. Manuscripts require the same persistent private media storage as uploaded audio.
