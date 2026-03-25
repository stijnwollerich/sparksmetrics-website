# CRO nurture (on sparksmetrics-website)

AI-assisted drip emails for **free CRO scan** signups. Lives in this repo next to `/cro-scan`.

## What emails send, and when

**Production:** The transactional **CRO scan results email** (PDF / link) always sends when the scan finishes. The **first nurture email** is scheduled **only after** `full_report` is stored on the lead, after **`sequence_schedule` step 1 `delay_after_previous_seconds`** (default **2 hours** from that moment). Later steps use their own delays after each send. Cron must run enrichment + dispatch regularly.

**Why two identical-looking emails?** You likely had **two `cro_nurture_lead` rows** (same email + site, e.g. double submit). Dispatch used to send step 1 for **each** due row. **Now:** when an older row is superseded by a **newer** active row with the same `email` + `site_url`, the older row is **auto-paused** and skipped (see `dispatch.py`). You can still unpause or delete stray rows in the DB if needed.

**Why only one nurture step per cron in production?** Delays between steps live in the DB (`sequence_schedule` → sync). Each cron run sends **at most one step per due lead**. **Local testing — all 10 emails in one go:** set **`CRO_NURTURE_TEST_ZERO_DELAYS=1`** and **`FLASK_DEBUG=1`**. Then step delays are treated as **0**, and the DEBUG post-scan kick (and `/api/cron/run` / `dispatch`) **loops** until no more sends (see `run_dispatch_batch_until_quiet`). **Production:** leave that unset; real 2h / multi-day gaps apply. Alternative burst path: `CRO_NURTURE_TEST_INSTANT_SEQUENCE=1` (separate flow, 2 min wait — below).

**Enrichment:** Logs like `enrich={'processed': 1, 'ok': 1, 'failed': 0}` mean the profile model ran successfully (`business_profile` JSON on the lead). `attach ... enrich=pending` means the scan was merged and enrichment was queued/reset to pick up `full_report`.

Edit **`app/cro_nurture/sequence_schedule.py`** (`STEPS`: delays + `instruction_prompt`). Apply to the DB:

**Where to run commands:** the directory that contains **`run.py`** (repo root, often named `sparksmetrics-website`). Your shell prompt already shows that name when you are in the right place — then you **only** run Flask, no extra `cd`:

```bash
flask --app run cro-nurture-sync-sequence --force
```

If you are somewhere else, use **one** path on its own line (no trailing comment on the same line — some copy/paste turns that into extra words and you get `cd: too many arguments`):

```bash
cd /Users/stijnwollerich/Coding/Sparksmetrics/sparksmetrics-website
flask --app run cro-nurture-sync-sequence --force
```

Do **not** run `cd sparksmetrics-website` when you are already inside that folder (there is no nested `sparksmetrics-website` folder → `no such file or directory`).

(`--force` overwrites existing step rows; without it, only empty sequences get seeded—e.g. first deploy.)

## Inspect / re-run enrichment from the terminal

No form submit needed. From the project root (with venv + `.env` loaded, `CRO_NURTURE_ENABLED=1`):

```bash
# Latest lead by id (or pass an id: cro-nurture-lead-show 4)
flask --app run cro-nurture-lead-show

# Re-fetch homepage + rebuild business_profile (OpenAI) for that lead
flask --app run cro-nurture-lead-enrich 4
```

Check JSON: `enrichment_status` should be `ok`, `has_full_report` true if the scan finished, `business_profile` should list `industry`, `cro_audit_themes`, `hooks_for_email`, etc. There is also `scripts/inspect_cro_nurture_leads.py` for a quick text dump of recent rows.

## Test nurture emails from the terminal

Requires **`BREVO_API_KEY`**, a verified **`BREVO_SENDER_EMAIL`**, and **`OPEN_AI_KEY`** (emails are real sends unless you point Brevo at a sandbox — there is no dry-run).

**1. Fast local drip (all steps back-to-back)** — `.env`:

- `FLASK_DEBUG=1`
- `CRO_NURTURE_TEST_ZERO_DELAYS=1`

**2. Make the next step due** (overrides `next_send_at` for one lead; default id = latest):

```bash
flask --app run cro-nurture-lead-due-now
flask --app run cro-nurture-lead-due-now 4
```

**3a. One command — all remaining steps for one lead** (recommended for “send me the full drip now”):

Requires **`FLASK_DEBUG=1`** (or `true`) **and** either **`CRO_NURTURE_TEST_ZERO_DELAYS=1`** or **`CRO_NURTURE_CLI_BURST=1`**:

```bash
flask --app run cro-nurture-lead-burst 4
```

This **ignores** multi-day DB delays and sends step after step until the sequence ends (cap `--max-steps`, default 15).

**Reset and test the full drip again** (same lead id; dev gate same as burst — deletes `cro_nurture_email_send` rows, sets `next_step_order=1`, clears unsub/pause):

```bash
flask --app run cro-nurture-lead-reset-sequence 4
flask --app run cro-nurture-lead-burst 4
```

**3b. Run dispatch** (batch + optional multi-round loop when zero-delay mode works):

```bash
flask --app run cro-nurture-dispatch
```

**4. Optional — enrich then dispatch** (like the HTTP cron):

```bash
flask --app run cro-nurture-cron
```

**Without** `CRO_NURTURE_TEST_ZERO_DELAYS`, only **one** step sends per `cro-nurture-dispatch` run; repeat `due-now` + `dispatch` after each send, or wait for real `next_send_at`.

**Reading dispatch JSON:** **`sent`** is how many emails actually went out in that command. **`rounds`** is how many internal dispatch passes ran (with zero-delay mode, it keeps going while each pass sends something). If `sent` is **1** and `rounds` is **2**, the second pass had nothing due — usually the next step was scheduled **days** ahead because zero-delay was off or `FLASK_DEBUG` was not effective for the CLI; ensure `.env` has `FLASK_DEBUG=1` and `CRO_NURTURE_TEST_ZERO_DELAYS=1`, then run `cro-nurture-lead-due-now 4` again and `cro-nurture-dispatch` again.

**Alternative (HTTP):** start the app, then  
`curl -X POST "http://localhost:5001/cro-nurture/api/cron/run?token=YOUR_CRO_NURTURE_CRON_TOKEN"`.

**Internal dashboard (HTML):** in the browser, open  
`/cro-nurture/internal/leads?token=YOUR_CRO_NURTURE_CRON_TOKEN`  
Auth: `?token=` (same value as `CRO_NURTURE_CRON_TOKEN`, or `CRO_NURTURE_INTERNAL_DASHBOARD_TOKEN` if set), or header `X-Cron-Token` / `Authorization: Bearer …`. If you see “Unauthorized” with no token in `.env` on the **deployed** host, set `CRO_NURTURE_CRON_TOKEN` there and restart. **By default** loads **all** nurture + form rows on **one page**. Optional caps: `?limit=` / `?form_limit=` (max 100000 each).

## Localhost testing

- **App + DB**: With **`FLASK_DEBUG=1`**, after each scan finishes the app runs enrich + **multi-round** dispatch in a background thread when **`CRO_NURTURE_TEST_ZERO_DELAYS=1`** (otherwise a single dispatch round). The first nurture email after attach still respects **`CRO_NURTURE_LOCAL_FIRST_EMAIL_SECONDS`** in DEBUG (default **`0`**). In production (`DEBUG` off), `CRO_NURTURE_TEST_ZERO_DELAYS` is ignored and cron uses normal DB delays.
- **Manual cron** (optional): `curl -X POST "http://localhost:5001/cro-nurture/api/cron/run?token=YOUR_TOKEN"`. Use `SITE_URL=http://localhost:5001` in `.env` for unsubscribe links in test emails.

### Instant full sequence (dev only)

To test **all nurture emails** in one go **after the scan JSON exists**, with a short pause (default **2 minutes**) so timing resembles prod:

1. `CRO_NURTURE_ENABLED=1`
2. `CRO_NURTURE_TEST_INSTANT_SEQUENCE=1`
3. **`FLASK_DEBUG=1`** so `current_app.debug` is True (hook does **not** run when `DEBUG` is False).

Submit the CRO form: you still get the **normal CRO scan results email** when the pipeline finishes. A background thread **waits until `full_report` is on the lead** (poll, max `CRO_NURTURE_TEST_WAIT_FOR_SCAN_MAX_SECONDS`, default 900s), then sleeps **`CRO_NURTURE_TEST_WAIT_BEFORE_NURTURE_SECONDS`** (default **120**), **re-enriches** with the full scan, then sends every nurture step back-to-back. **Do not** enable on production.

**Second submit (same work email + same store URL)** reuses the **same** `cro_nurture_lead` row (instant-test only): previous `full_report` is kept until a new scan overwrites it.

- **Brevo sending**: Works from localhost if `BREVO_API_KEY` and a verified sender are set (Brevo’s servers call their API; your IP does not need to be public).
- **Webhooks (opens/clicks)**: Brevo **POSTs event JSON to your URL**. `http://localhost:...` is **not** reachable from the internet, so webhooks will **not** hit your machine unless you use **ngrok**, **Cloudflare Tunnel**, etc., or test on a deployed URL. Nurture emails still **send** without webhooks; you just won’t update `open_count` / `click_count` locally.

## Webhook direction (why it exists)

You configured an **outgoing / transactional webhook** in Brevo: when someone **opens** or **clicks** an email, **Brevo’s servers send an HTTP POST** to **your** endpoint (`/cro-nurture/api/webhooks/brevo`). So **Brevo is pushing data to you**—you are not “calling” the webhook; your route **receives** notifications. That is separate from Brevo **“Inbound parsing”** (paid) which processes email *received at* your domain—different product.

## Intake (no Zapier)

When someone completes **`POST /cro-scan/submit-email`**, the app:

1. Saves the usual `Lead` row and syncs Brevo (existing behavior).
2. If **`CRO_NURTURE_ENABLED=1`**, creates a **`cro_nurture_lead`** row (server-side — no public secret in the browser).
3. When the background scan finishes, **`attach_cro_scan_report_to_lead`** merges the report JSON (`full_report`) into the lead, resets enrichment to **pending** if it had already run without the scan, and schedules the **first nurture send** (step 1 delay after attach, default 2h in `sequence_schedule`).

Optional **`POST /cro-nurture/api/ingest`** remains for external systems; use `CRO_NURTURE_INGEST_SECRET`.

## Enable

1. Set **`CRO_NURTURE_ENABLED=1`** in `.env`.
2. Deploy / restart so `db.create_all()` creates `cro_nurture_*` tables and seeds the default sequence.
3. Set secrets and Brevo/OpenAI (see env list below).
4. Schedule **`GET/POST /cro-nurture/api/cron/run?token=…`** every few minutes (see `tasks/Marketing/cro_nurture_cron.py`).
5. Point the Brevo **transactional** webhook at  
   `{SITE_URL}/cro-nurture/api/webhooks/brevo?token={CRO_NURTURE_BREVO_WEBHOOK_TOKEN}`.

## Env (typical)

| Variable | Purpose |
|----------|---------|
| `CRO_NURTURE_ENABLED=1` | Turn on blueprint + hooks |
| `CRO_NURTURE_TEST_ZERO_DELAYS=1` | **Dev only** (requires `FLASK_DEBUG=1`): treat all step delays as 0; one post-scan kick or cron `run` can send **all 10** steps in a loop |
| `CRO_NURTURE_TEST_INSTANT_SEQUENCE=1` | Dev only: alternate burst — wait for scan JSON, pause 2 min (configurable), re-enrich, burst (requires `FLASK_DEBUG=1`) |
| `CRO_NURTURE_TEST_WAIT_BEFORE_NURTURE_SECONDS` | Default `120` — delay after `full_report` exists before instant-test burst |
| `CRO_NURTURE_TEST_WAIT_FOR_SCAN_MAX_SECONDS` | Default `900` — max poll time for `full_report` before burst anyway |
| `CRO_NURTURE_LOCAL_FIRST_EMAIL_SECONDS` | With `FLASK_DEBUG=1`, seconds after scan attach before nurture #1 (default `0`; set `7200` to mimic prod) |
| `CRO_NURTURE_CRON_TOKEN` | Cron endpoints + internal HTML dashboard (unless overridden below) |
| `CRO_NURTURE_INTERNAL_DASHBOARD_TOKEN` | Optional: use this instead of `CRO_NURTURE_CRON_TOKEN` for `/cro-nurture/internal/leads?token=…` only |
| `CRO_NURTURE_INGEST_SECRET` | Optional `/api/ingest` auth |
| `CRO_NURTURE_BREVO_WEBHOOK_TOKEN` | Webhook query token |
| `CRO_NURTURE_BREVO_LIST_IDS` | Extra Brevo lists for nurture contacts (comma-separated) |
| `BREVO_API_KEY` | Already used site-wide |
| `BREVO_SENDER_EMAIL` / `BREVO_SENDER_NAME` | Transactional sender (or `CRO_NURTURE_BREVO_SENDER_*`) |
| `OPEN_AI_KEY` or `OPENAI_API_KEY` | Enrichment + copy |
| `SITE_URL` | Unsubscribe links + defaults (e.g. `https://sparksmetrics.com`) |
| `CRO_NURTURE_DEFAULT_SOURCE_TAG` | Stored on leads from `/cro-scan` (default `sparksmetrics.com/cro-scan`) |
| `CRO_NURTURE_PROFILE_HOMEPAGE_CHARS` | Max chars of homepage text sent to the profile summarizer (default `3500`; not stored on the lead) |
| `CRO_NURTURE_PROFILE_AUDIT_JSON_MAX` | Max JSON size for condensed audit in that call (default `6000`) |
| `CRO_NURTURE_PROFILE_INPUT_MAX_CHARS` | Hard cap on the profile model’s input JSON (default `12000`) |
| `CRO_NURTURE_EMAIL_INPUT_MAX_CHARS` | Max chars for serialized `{ lead, step_instructions }` on each nurture email call (default `20000`) |
| `CRO_NURTURE_EMAIL_AUDIT_JSON_MAX` | Starting cap for condensed audit inside that slim lead; tightened automatically if the total is still too big (default `7000`) |
| `CRO_NURTURE_EMAIL_PROFILE_JSON_MAX` | Max chars for `business_profile` inside the slim email lead (default `3200`) |
| `CRO_NURTURE_EMAIL_MAX_COMPLETION_TOKENS` | Completion budget for subject + html + text JSON (default `2800`) |
| `CRO_NURTURE_EMAIL_STATIC_ORIGIN` | Public `https` origin for `/static/…` images in nurture HTML (default `https://sparksmetrics.com`). Use this so step 5 screenshots load when the app runs on localhost/staging; unsubscribe links still use `SITE_URL`. |

**Enrichment:** One OpenAI call builds `business_profile` JSON on the lead (industry, business type, summary, products/services, value prop / “why”, CRO themes, email hooks, etc.). Raw homepage text is only used in that call; the DB keeps the summary plus `fetched_pages` meta/`text_len`. Full scan JSON remains on `cro_scan_payload.full_report` for the report viewer and nurture (nurture **does not** send the raw blob to the model—it uses a condensed copy + caps).

**Nurture emails:** Each step sends a **slim** lead (condensed audit + capped `business_profile`) plus `step_instructions`, bounded by `CRO_NURTURE_EMAIL_INPUT_MAX_CHARS`, so cost skews toward **writing** (completion tokens), not megabyte-scale inputs.

**Step 5 image:** Commit and deploy under **`app/static/`** (Flask’s static root): `app/static/images/cro_nurture/test_aov_variants_client.png` → public URL `{CRO_NURTURE_EMAIL_STATIC_ORIGIN}/static/images/cro_nurture/test_aov_variants_client.png` (default origin `https://sparksmetrics.com`). A repo-root `static/` folder is **not** served by Flask.

**Step 2 / 7 YouTube thumbnails:** `app/static/images/youtube_thumbnails/audit_walkthrough_wxnd.jpg` and `feastables_conversion_lessons.jpg` (same origin as step 5 — avoids `img.youtube.com` being blocked). Replace files as needed; keep filenames or update `dispatch.py`.

## Remove

1. Unset `CRO_NURTURE_ENABLED`.
2. Delete `app/cro_nurture/`.
3. Remove the `CRO_NURTURE_*` block from `app/__init__.py` and `CRO_NURTURE_ENABLED` from `config.py`.
4. Remove hooks in `app/routes/main.py` and `app/cro_scan/runner.py`.
5. Remove the `cro-nurture-sync-sequence` CLI block from `app/__init__.py` if you want a clean uninstall.
6. Drop `cro_nurture_*` tables in SQL if desired.
