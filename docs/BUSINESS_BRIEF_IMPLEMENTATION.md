# Business brief integration

The existing Flask storefront, purchase library, cart, staff CMS, dark/light theme controls and book-opening animations remain in place. Public registration remains disabled.

## Public pages

- `/`: revised business positioning, production formats, audio comparison, children and innovation introductions, existing book shelves and newsletter.
- `/about`: company purpose, vision and values.
- `/services`: eight production service areas.
- `/immersive-audio`: production formats and two accessible audio demonstrations.
- `/children`: developing Kids programme, families, schools and children's shelf.
- `/originals`: original IP direction and existing collection.
- `/innovation`: StoryDNA Engine, persistent Story Intelligence Profile, Sound Recommendation Engine, Audio Continuity Engine and Author Control Layer, presented as live production technology. The engines run in the production pipeline, outside this web application.
- `/production`: author/publisher form, project metadata, optional private manuscript and six-stage process.
- `/contact`: general, author, children, partnership, creative, innovation/investment and accessibility enquiries.
- `/privacy`, `/terms`, `/accessibility`: public platform information. Business-specific legal review and company/contact particulars remain owner tasks before commercial launch.

Home, Bookshelf, Discover, Authors & Publishers and Contact keep the fixed navbar compact. Discover exposes the six company/content pages. Footer links expose policies and staff access. Social URLs are omitted until official accounts are provided.

## Working submissions and files

Contact and project submissions persist in the existing admin enquiries inbox. Staff see enquiry type and project metadata. Manuscripts support PDF, UTF-8 TXT and non-macro DOCX, with a 10 MB upload cap, basic file validation and random storage filenames. Files are served as attachments only to owner/editor staff; they are not publicly addressable. Media cleanup retains enquiry attachments. No automatic manuscript analysis is claimed or performed.

Newsletter first names are stored alongside consent-based email registration. The existing durable email outbox handles listening-access emails; enquiry auto-replies and newsletter campaigns are not enabled without mail/content setup.

## Audio and analytics

Available production comparison assets take priority; otherwise the bundled demonstration recordings are explicitly labelled. Native comparison players are shown only for actual paired production assets. Bundled synthetic demonstrations and transcript blocks are no longer shown on public pages. The existing listening player retains speed, chapters and progress.

First-party aggregate page views, starts/completions, author submissions and contact submissions are recorded without introducing advertising cookies. Dashboard counts show page views, completions and contacts. These are event counts, not unique visitors or verified conversion rates. Geographic reporting, comprehensive device reporting and an external analytics dashboard remain future integrations. Static demonstration audio is counted in aggregate events.

## Future work, as described in the brief

The StoryDNA, sound recommendation and continuity engines run in MyAudioShelf's production pipeline rather than in this web application. Interactive/adaptive audio, subscriptions, parental controls and personalised listening remain proposed capabilities.

Production imagery uses the established genre photograph assets; no stock photograph is claimed as the company's staff or studio. Verified behind-the-scenes photographs, licensed production recordings, official social links and business contact particulars can be added when provided.

## Deployment

Run `flask --app wsgi db upgrade` to add enquiry and newsletter fields. Render's existing startup migration hook applies this migration automatically. Existing enquiry rows receive the `author` type, preserving their contents. Manuscripts require the same persistent private media storage as uploaded audio.
