# Private audiobook storage on Bunny

Create a **Storage Zone** in your Bunny dashboard. Open **FTP & API Access** and copy the zone name, storage password and regional HTTP endpoint into your private `.env`:

```dotenv
BUNNY_STORAGE_ZONE=your-zone-name
BUNNY_STORAGE_ACCESS_KEY=your-storage-zone-password
BUNNY_STORAGE_ENDPOINT=https://storage.bunnycdn.com
```

Use the regional endpoint shown by Bunny (for example `https://uk.storage.bunnycdn.com`). The credential is the **Storage Zone password**, rather than your account API key or a Stream library key. [Bunny's Storage API explanation](https://bunny.net/faq/).

Keep full recordings in this private zone without an unrestricted connected Pull Zone. The application fetches them with the server-side storage credential. Customers receive only app download/streaming URLs; each private request checks their paid purchase. No Bunny key or unrestricted recording URL is sent to the browser.

## Move the current recordings

Run this on the computer that contains the existing `instance/media` files:

```sh
.venv/bin/python -m flask --app wsgi sync-media-to-bunny
```

The command uploads every referenced media file and manuscript, preserving storage keys and chapter order. It reports missing local files and exits unsuccessfully if any remain. It does not delete source recordings. Uploads automatically retry interrupted network transfers up to three times, reopening the file from the beginning. Run the command again safely if a connection still fails.

Add the same three Bunny environment variables to your **Render web service → Environment**, then redeploy. `.env` is private and is not pushed to GitHub. Render and your local app must also use the same Neon `DATABASE_URL` so their file references agree.

## New uploads and downloads

Upload a cover, trailer, full recording or chapter files from the admin book editor as usual. When Bunny is configured, the app uploads the validated file to private storage before saving its database reference. Failed storage uploads produce an error so the editor can retry.

Files are cached locally on demand for audio range playback and complete chapter ZIP downloads. After a Render restart, missing cached files are fetched again from Bunny. Covers and trailers can be served publicly through the existing app routes; complete recordings and manuscripts retain their existing access checks.

The application checks recording availability before creating Stripe Checkout. Once verified payment unlocks a purchase, the customer can immediately download the full file or an ordered chapter ZIP without creating an account. Keep `STRIPE_WEBHOOK_SECRET` configured for delayed payment confirmations and refunds.

Bunny setup is active only when both the zone name and storage password are present. With both blank, the app continues using local storage. A partially configured zone or invalid endpoint prevents startup with a clear configuration error.
