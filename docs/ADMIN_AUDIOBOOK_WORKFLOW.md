# Adding an audiobook

1. Sign in at `/admin/login` as an owner or editor. Support staff cannot create or edit books.
2. Open Audiobooks and choose Add audiobook.
3. Start in Draft. Enter the title, author, narrator/cast, synopsis, language, production style and total duration in minutes. Add the publisher, biography, credits, notes and transcript when available.
4. Upload cover artwork (JPG/PNG/WebP; up to 10 MB; at least 200 × 200 pixels), a dedicated trailer (up to 60 seconds), and either full audio or chapters. Audio formats: MP3, M4A, WAV, OGG and FLAC, up to 500 MB per file; the form request also has a 512 MB total cap, so upload large assets across separate saves.
5. For chapters, enter a chapter title, upload its audio and save. Repeat for each chapter. Use the chapter management controls to move or remove chapters. If chapters exist, the player uses chapters rather than the full-audio file.
6. Enter a positive price in major currency units, choose currency and select at least one genre. Keep Available for sale checked for public catalogue visibility. Show on homepage controls home shelves; Featured, Hero, Original and Children select their corresponding collections. Only one published hero title is active.
7. Save the draft and use Preview. Check cover, trailer, description, price, genre and credits. Staff can preview draft media; purchased full audio remains private.
8. Select Published and save. Publication validates metadata, cover, trailer, full audio or at least one chapter, positive price and duration. Fix any displayed validation message. Create your own title for real publication; seeded fictional titles cannot be republished for real sales.
9. Check `/books` and the book detail page. For listening access, complete an eligible purchase; publication alone does not grant a staff account a customer purchase entitlement.
10. To unpublish a title, select Draft or Archived and save.

# Neon database

The application reads `DATABASE_URL` from `.env` locally and from host environment variables in deployment. Standard PostgreSQL URLs are automatically adapted to the installed psycopg 3 driver, preserving SSL and other query parameters. Connections use pool pre-ping to detect stale connections.

Use `pip install -r requirements-production.txt` for PostgreSQL support. Run `python -m flask --app wsgi db upgrade` for migrations and `create-admin` to provision staff in a new database. SQLite records are not automatically transferred to Neon; the original SQLite file is retained. Seed initialization only adds missing sample catalogue records.

For Render, set the web service's `DATABASE_URL` to the same Neon connection string in the dashboard. Local `.env` is ignored by Git and is not uploaded to Render. Database startup migrations remain automatic. Neon stores records, not uploaded audio or manuscripts: retain the persistent media disk or configure separate private object storage before replacing file storage.

## Updating prices and genres

Open Audiobooks → Edit beside the title. In Price & discovery, enter the price in major currency units (for example 15.00 GBP, not 1500), select the currency and check the desired genres. Available for sale enables purchases. Save audiobook applies the changes. Create additional genres in Genres → Add genre, then return to the book and select them. A Published save also validates all required publication fields; if the supplied prelaunch book lacks narrator/cast or a positive price, complete those fields before enabling sales.

## Customer downloads

Verified paid purchases show Download audiobook in My purchases and Download complete audiobook in the listening room. The purchase email leads to this library; it does not attach large recordings. A chapter-based book downloads as one ZIP with numbered files, an included cover when available, and a contents list. A full-file book downloads its original audio format. A new request checks both active entitlement and paid order status. Refunded/revoked access cannot start another download, but copies already saved to the customer's device cannot be recalled.

The archive is created on temporary disk and streamed; allow adequate temporary disk space for large audiobooks. All full/chapter files must exist on the deployed server's private storage. Missing chapters produce an availability message rather than a partial archive.
