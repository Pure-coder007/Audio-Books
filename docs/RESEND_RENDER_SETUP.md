# Paid audiobook emails on Render

After Stripe confirms a paid Checkout session, the application commits the order,
purchase access and email queue together. It immediately attempts delivery through
Resend. Provider failures leave the message queued for retry without undoing payment.
Each email includes a receipt, the purchased books and secure download buttons.
Full recordings download as audio files; chapter recordings download in one ZIP.
The email contains links rather than large attachments.

## Resend setup

1. Add your sending domain in Resend and add its supplied DNS records at your DNS
   provider. Wait for domain verification before sending to customers.
2. Create a Resend API key with sending permission for that domain.
3. Set `RESEND_API_KEY` and `RESEND_FROM_EMAIL` in both your local `.env` and Render.
   Example sender: `MyAudioShelf <books@yourdomain.com>`. Replace the example with
   an address on your verified domain. Do not use the `resend.dev` testing sender
   for customer delivery. Optionally set `RESEND_REPLY_TO` to your support mailbox.
4. Run `python -m flask --app wsgi check-email-config` to check local configuration.
   This command does not send email or verify DNS.

Official domain instructions: https://resend.com/docs/dashboard/domains/introduction

## Render environment

Enter values in Render's Environment settings without surrounding quotes.
Copy secrets directly from your private `.env` or the provider dashboard.
Never put them in Git or send them to customers.

| Variable | Value / purpose |
| --- | --- |
| `APP_ENV` | `production` |
| `SECRET_KEY` | Stable random secret, at least 32 characters |
| `DATABASE_URL` | Your persistent PostgreSQL connection URL (Neon or Render) |
| `BASE_URL` | Your public HTTPS website URL, without a trailing slash |
| `STRIPE_SECRET_KEY` | Stripe secret key; use test mode first, live mode for real sales |
| `STRIPE_WEBHOOK_SECRET` | Signing secret for this deployed site's Stripe webhook endpoint |
| `RESEND_API_KEY` | Resend API key with sending permission |
| `RESEND_FROM_EMAIL` | `MyAudioShelf <books@your-verified-domain>` |
| `BUNNY_STORAGE_ZONE` | Private storage zone containing the recordings |
| `BUNNY_STORAGE_ACCESS_KEY` | That zone's Storage password / API access key |
| `BUNNY_STORAGE_ENDPOINT` | Your zone's regional endpoint, e.g. `https://storage.bunnycdn.com` |
| `RATELIMIT_STORAGE_URI` | Redis connection URL for persistent/shared rate limits |
| `DEMO_MODE` | `false` |
| `SAMPLE_CATALOG` | `false` |
| `RESEND_REPLY_TO` | Optional support mailbox |
| `STRIPE_PUBLISHABLE_KEY` | Optional; hosted Stripe Checkout does not require it |

SMTP `MAIL_*` settings are unnecessary when using Resend.
`RESEND_WEBHOOK_SECRET` is not used by this application.
Bunny settings are necessary when your recordings are stored in Bunny; a persistent
media disk is the alternative. Local recordings are not automatically deployed.

Build command: `pip install -r requirements-production.txt`

Web start command: `sh render-start.sh`

The start script runs database migrations, including the email outbox migration.
Deploy the web service before starting the retry job.

## Retry queued mail

Create a Render Cron Job from the same repository and revision, with the same build
command and the same environment settings. It must use the **same PostgreSQL
DATABASE_URL** as the web service, rather than a separate SQLite database.

Schedule: `* * * * *`

Command: `python -m flask --app wsgi deliver-emails`

This retries failed or queued messages every minute. Old links are refreshed before
sending. Successfully submitted emails are not resent. Submission does not prove
inbox delivery; check Resend's dashboard for delivered/bounced events.

Render Cron Job instructions: https://render.com/docs/cronjobs

## Stripe webhook and verification

Register `https://YOUR-SITE/checkout/webhook` in Stripe with these events:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `checkout.session.expired`
- `charge.refunded`

Use the endpoint's signing secret as `STRIPE_WEBHOOK_SECRET`; a local Stripe CLI
secret is different. Match your Stripe key and endpoint's test/live mode.

Purchase an uploaded, published, non-demo book using Stripe test mode and your own
email. Confirm the order is paid in Studio, a message appears in Resend, the message
arrives, and the email download button downloads the complete recording. Repeat
with a chapter book if you sell chapter recordings. Check that refunded purchases
lose access. Email scanner GET requests cannot consume the sign-in token.

Links expire after 15 minutes. The first confirmation signs the buyer into their
purchase library; other book buttons work in that same browser session. A buyer
opening an expired or already-used link in another browser can request a fresh
email through `/library`.
