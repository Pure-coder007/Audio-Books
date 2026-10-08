# MyAudioShelf MVP

A working Flask/Jinja audiobook storefront, guest commerce flow, protected listening library and operational staff CMS. The UI uses the provided blueprint’s warm surfaces, flat editorial layout, full-width navigation and lemon-green accent. The supplied MyAudioShelf logo is used in the fixed navigation and footer. Visible library imagery and distinct genre photographs add atmosphere while keeping content readable. The navbar theme control switches between dark and light appearances and remembers the preference. The logo stays transparent. The public navbar contains Home, Bookshelf, Discover, Authors & Publishers and Contact, plus purchase/cart access and sound/theme controls. The customer `/login` route remains available directly. Public customer registration is disabled; existing purchase email links remain available. Book covers hinge open on hover, keyboard focus and press, revealing a paper interior. A short synthesized paper-opening sound plays after the first browser interaction, with a navbar mute control that remembers its setting. Sounds pause while audiobook audio is playing, and reduced-motion preferences are respected.

## Open the MVP on this Mac

Double-click **start.command**, then open **http://127.0.0.1:5000**. Keep the Terminal window open while using the app. Stop the server with Ctrl+C.

The database and twelve fictional demo titles have already been prepared in this workspace. This demo has playable sample narration and cover artwork. Demo checkout takes no money and grants no purchase entitlements.

Admin: **http://127.0.0.1:5000/admin/**. The initial local credentials are in `instance/LOCAL_ADMIN.txt` (private, ignored by Git). Use `reset-admin-password` below to change the password.

## Fresh installation

Python 3.11+ recommended (built and tested with Python 3.13).

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m flask --app wsgi db upgrade
.venv/bin/python -m flask --app wsgi seed-demo
.venv/bin/python -m flask --app wsgi create-admin
.venv/bin/python -m flask --app wsgi run --host 127.0.0.1 --port 5000
```

`create-admin` prompts for your email and a password of at least 12 characters. There is no hard-coded admin password. Development generates a private local secret if `SECRET_KEY` is empty. Set your own strong secret in production.

```sh
.venv/bin/python -m flask --app wsgi reset-admin-password
.venv/bin/python -m pytest -q
```

## What’s implemented

- Responsive, book-led homepage: hero, featured titles, catalogue, new releases, previews, audio comparisons, children’s shelf, originals, genre discovery, immersive titles, authors’ production services, credits and newsletter signup. Empty shelves have honest empty states. Collections follow the database and admin flags.
- Search titles, authors, narration and synopsis; filter genre, language, production, age range, duration, price and collections; sort new, featured, title and price. Genre and author pages are server-rendered.
- Book details with portrait covers, dedicated trailers, metadata, transcript when supplied, production notes, credits, synopsis, chapters and related titles.
- Signed-session cart, one copy per title, and previews from the cart. Checkout snapshots authoritative database prices in a pending internal order and redirects to Stripe Checkout. Mixed currencies require separate checkouts.
- Signed, idempotent Stripe webhooks create entitlements only for paid, matching sessions and totals. Asynchronous payment, failure and expiration events are handled. Full refunds revoke access, including refunds received before payment events. Another paid purchase can preserve access. Partial refunds require staff review in Stripe and the CMS.
- Single-use email magic links; scanner-safe confirmation; purchase library; private, expiring audio URLs tied to the listening session and current entitlement. HTTP range requests, native seek/volume, playback speed, chapters and remembered progress. Expired audio links can refresh during listening.
- Admin dashboard, draft/edit/preview/publish/unpublish/archive workflow, image/audio uploads, chapter ordering/removal, collections and hero curation, genre creation, author bios, order inspection, access revoke/restore/reissue, enquiries, staff roles and audit history.
- Newsletter consent records; book-view, preview-play and listening activity records; basic dashboard metrics. Newsletter campaigns, attribution funnels and advanced reporting are later work.
- CSRF, rate limits, validated uploads, hashed passwords, disabled-session invalidation, secure production cookies, CSP and security headers, sitemap, robots, canonical/social metadata, accessible controls and reduced motion support.
- Database migrations, test coverage, Docker build definition and an email outbox with retries.

## Publish your first real title

1. Sign in to Shelf studio and choose **Add audiobook**.
2. Enter title, author and biography, narrator/cast, language, duration, synopsis and any credits.
3. Upload a cover (JPG/PNG/WebP), a dedicated trailer of at most 60 seconds, and a full audio file or chapter files. Audio accepts MP3/M4A/WAV/OGG/FLAC. Total request limit is 512 MB; upload chapters one at a time.
4. Choose a genre, price and currency. Set your homepage/featured/original/children/hero flags.
5. Save as Draft and preview. Select Published and save when ready. Missing required fields or assets block publication.
6. Optionally upload both comparison clips to show a real plain-narration-versus-immersive section on the homepage. Comparison clips are public and limited to 60 seconds each.

Replacements invalidate old media references and reset progress for replaced files. Removing chapters requires unpublishing first. Choose Draft to unpublish, or Archived to archive. Existing paid entitlements continue listening to retained private media even when a title is unlisted.

Samples can be browsed only with `DEMO_MODE=true`; they cannot be sold through Stripe or promoted into real titles. Create your own titles. Production always forces demo mode off.

## Stripe and access emails

Set `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` and `BASE_URL` in `.env` or deployment environment. Use test credentials first. Register `/checkout/webhook` for:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `checkout.session.expired`
- `charge.refunded`

For local Stripe testing, use Stripe CLI:

```sh
stripe listen --forward-to http://127.0.0.1:5000/checkout/webhook
```

Use the printed webhook signing secret in your local configuration and restart Flask. Purchase a real uploaded test title with Stripe test mode. Demo titles intentionally do not enter Stripe. Browser success-page arrival alone never grants access.

Configure SMTP with the `MAIL_*` variables and run:

```sh
.venv/bin/python -m flask --app wsgi deliver-emails
```

Schedule that command every minute using a **single** scheduler job. The durable outbox avoids coupling payment confirmation to SMTP availability. Delayed messages receive fresh access links before delivery. Without SMTP, queued emails can be inspected by the owner in the development outbox at `/admin/outbox`; that screen is disabled in production. No real Stripe payment or external email has been sent during this build.

[Stripe webhook documentation](https://docs.stripe.com/webhooks) explains signature verification and delivery retries. [Flask application factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) informs the modular app structure. The visual reference was [NaijaHub](https://www.naijahub.ai/), adapted without its content, sidebar or section numbering.

## Production deployment

Use a Python host or VPS that supports persistent storage and scheduled jobs. This Flask app cannot run on Cloudflare Workers / Sites.

- Set `APP_ENV=production`, a strong `SECRET_KEY` of at least 32 characters, `BASE_URL=https://your-domain`, `DEMO_MODE=false`, real Stripe and SMTP credentials.
- Redis is optional. For now, use `RATELIMIT_STORAGE_URI=memory://` with one Gunicorn worker and one web instance. Rate-limit counters reset on restart. Use shared Redis storage before running multiple workers or instances. Production still requires an HTTPS base URL.
- Install `requirements-production.txt` and set `DATABASE_URL` to a PostgreSQL SQLAlchemy URL such as `postgresql+psycopg://...`. SQLite remains suitable for the local demo.
- Run `python -m flask --app wsgi db upgrade` as the release step, then `create-admin` interactively.
- Start with `python -m gunicorn --bind 0.0.0.0:8000 --workers 1 --timeout 120 wsgi:app`.
- Terminate TLS at your reverse proxy, forward requests to Gunicorn, permit the required upload size and hide access-token URL paths from proxy access logs. The app does not blindly trust forwarded headers. `BASE_URL` is authoritative for email and payment links.
- Persist and back up `instance/media` and the database. Full audio is served by Flask after current entitlement checks; do not expose the media directory through the web server. For larger catalogues, replace the media service with private object storage and equivalent entitlement/expiring URL behavior.
- Schedule one `deliver-emails` worker each minute and `cleanup-access` / `cleanup-media` daily. Cleanup has a 24-hour grace period for unreferenced upload files. Monitor queued emails, webhook failures, disk space and `/health`.
- Complete a Stripe test purchase, receive its email, listen on desktop/mobile, confirm a refund revokes access, and replace fictional/demo content before real sales.

Docker: `docker build -t myaudioshelf .`. Run with environment variables and a persistent volume mounted at `/app/instance`; provide PostgreSQL separately; Redis is optional for a single worker. The Docker image is prepared but has not been built here.

## Scope and verification

**64 automated tests pass.** Automated tests cover guest checkout price snapshots, payment signatures and idempotency, refunds and event order, magic-link expiry/single use, private range streaming, revoked access, progress validation, admin roles, publishing, upload checks, CSRF and page rendering. Desktop/mobile Chrome checks cover preview playback, demo cart checkout, menu behavior, failed requests and horizontal overflow. A separate isolated browser fixture verifies staff sign-in, draft creation, email-link redemption, private chapter playback, playback speed, saved resume and entitlement revocation. Preview screenshots are in `docs/`.

Live Stripe checkout and SMTP delivery still need your service credentials and an integration test. This workspace has not been deployed publicly. Background photograph sources are documented in `docs/IMAGE_CREDITS.md`. Detailed cast profile management, discounts, newsletter delivery campaigns, advanced analytics and dynamic section ordering are beyond this initial MVP.

The **Narrative Audio Map** remains a future module as requested in the blueprint; its proposed extension is recorded in `docs/NARRATIVE_AUDIO_MAP.md` and is not marketed as a completed feature.

Cart additions on book cards update the cart count in place and show a View cart notification. Server-rendered forms remain available when JavaScript is disabled. Fictional seed titles remain identified on their detail pages and during checkout; removing the global demo banner does not enable real sales of those samples.

### Customer sign-in

Open `http://localhost:5000/login` for existing customer email/password sign-in. Public sign-up is disabled and `/register` is not available. Customers can also access their purchases using a secure email link from `/library`. Staff accounts created with `create-admin` sign in separately at `/admin/login`.

The admin studio includes a refreshed sidebar, dashboard metrics, cover thumbnails beside book details, title search, and a crimson sign-out button. Catalogue and admin list pages use 10 items per page. “Search all books” clears previous filters; “Apply filters” combines the selected filters with the search term. Public sign-up remains disabled.
# Audio-Books

Render without Redis: set `RATELIMIT_STORAGE_URI=memory://` and use start command `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`.

### Render database initialization

Set the Render start command to `sh render-start.sh`. This runs migrations against the runtime database before Gunicorn starts, using a single worker without Redis. An error such as `no such table: category` means the configured database has not been migrated.

For durable SQLite storage, attach a persistent disk at `/opt/render/project/src/instance` and set `DATABASE_URL=sqlite:////opt/render/project/src/instance/myaudioshelf.db`. Without a disk, SQLite data and uploaded audio are lost when Render replaces the instance. PostgreSQL is the other supported durable database option. Run `python -m flask --app wsgi create-admin` in the Render Shell after deployment to create the staff account in the deployed database.

On Render, the repository's default `gunicorn.conf.py` also runs migrations once in the master process before workers start. This supports the existing `gunicorn wsgi:app ...` start command without a dashboard change. Local Gunicorn runs do not migrate automatically. Render disks and other service settings must still be configured in the dashboard.

Render automatically restores the original 12 sample titles, authors, genres and available preview audio after migrations. Seeding skips existing titles. `SAMPLE_CATALOG=true` permits sample visibility without enabling real Stripe purchases of fictional books. Set `SAMPLE_CATALOG=false` in Render when replacing the sample catalogue with licensed titles.

## Company and production brief

The business plan is integrated into the existing storefront with About, Services, Immersive Audio, Children, Originals, Innovation and Contact pages. Discover groups the company navigation; the existing library, cart and admin routes remain intact. The homepage introduces production formats, comparison audio and the proposed narrative-aware Story Engine. Research capabilities are explicitly described as under development.

Author enquiries include project information, optional private PDF/TXT/DOCX manuscripts (10 MB), and consent. Contact enquiries share the staff inbox with a recorded enquiry type. Staff owners/editors can download manuscripts; public visitors cannot. Run `db upgrade` when updating an installation; Render applies it automatically at startup.

See [business brief implementation notes](docs/BUSINESS_BRIEF_IMPLEMENTATION.md) for implemented functionality, data handling, analytics scope and future work.

## Adding audiobooks and Neon configuration

See [the admin audiobook workflow](docs/ADMIN_AUDIOBOOK_WORKFLOW.md) for the Draft → upload → preview → publish flow, file limits, chapter management and discovery options. Standard Neon PostgreSQL URLs in `DATABASE_URL` are supported without manually changing the URL scheme. PostgreSQL needs `requirements-production.txt`. Local `.env` does not update Render environment variables; configure the deployed `DATABASE_URL` separately.

## Supplied catalogue

The fictional seed titles are archived and hidden. Render now restores the supplied “5000 Names of God” artwork and 52-second preview instead of seeding fictional titles. The supplied book appears as Coming soon until its price and sales readiness are confirmed. Full recordings are private files, excluded from Git; the 23 tracks imported locally need to be uploaded to the deployed persistent media storage before full listening on Render. Neon stores metadata and file references, not the recordings themselves. Existing historical references to archived sample titles are preserved.

Paid customers can now download their audiobook from the purchase library: full-file titles download directly, while chapter-based titles download as an ordered ZIP with cover and contents. Every request checks a verified paid order and active entitlement. Full recordings must be available in the deployed private media storage. See the admin workflow guide for price/genre editing.
