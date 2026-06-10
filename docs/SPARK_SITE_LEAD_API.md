# `POST /api/site/lead` — Spark ingest (reference)

Marketing forwards leads with `app/spark_backend.py` when `SPARK_BACKEND_URL` and `SPARK_SITE_INGEST_SECRET` are set. Spark implements the route; this doc describes the contract for tests and field mapping.

## Headers

| Header | Value |
|--------|--------|
| `Content-Type` | `application/json` |
| `X-Spark-Site-Secret` | Same as Spark’s `SPARK_SITE_INGEST_SECRET` |

## Body (JSON)

Merge rules (Spark): optional nested `params` is merged first; **top-level keys override** `params`.

| Param | Required | Notes |
|--------|----------|--------|
| **`email`** | **Yes** | Valid address; upserts `contact`. |
| **`fname`** | No | First name (also: `first_name`, `name`). |
| **`submission_type`** | No | e.g. `audit`, `cro_scan`, `contact`. Nurture row only for types in Spark’s `SUBMISSION_TYPES_ENROLLING_NURTURE` (typically **`cro_scan`**) plus store/site URL + automation enabled. |
| **`lead_origin`** | No | Alias: **`origin`**. |
| **`resource_slug`** | No | |
| **`business_stage`** | No | |
| **`website_url`** | No | Aliases: **`store_url`**, **`lead_website_url`**. Store/site URL (not the form page). |
| **`form_page_url`** | No | **Page where the form was submitted.** Aliases: **`page_url`**, **`submission_url`** (first non-empty wins). |
| **`orders_per_month`** | No | Passed into nurture payload when nurture is created. |
| **`enroll_nurture`** | No | Boolean: whether this ingest should **start** nurture email automation. The Sparksmetrics app sets this from **`SPARK_NURTURE_ENROLLMENT_TYPES`** (comma-separated `submission_type` list, default `cro_scan` only). **Spark must honor this flag** (and may still apply its own guards). |
| **`report`** | No | Object; attaches scan JSON when a store URL is present. |
| **`report_view_url`** | No | Public HTTPS link to the on-site report viewer (e.g. sparksmetrics.com/cro-scan/report/&lt;token&gt;). Included on attach when Sparksmetrics finishes a background scan (funnel and lead-magnet enrich). |
| **`params`** | No | Nested object; merged with top-level as above. |
| *anything else* | No | Stored in full JSON on **`contact.site_ingest_payload`** in Spark. |

## Copy-paste `curl` (SSH on droplet, after `source .env`)

**Minimal**

```bash
curl -sS -w "\nHTTP %{http_code}\n" -X POST "${SPARK_BACKEND_URL}/api/site/lead" \
  -H "Content-Type: application/json" \
  -H "X-Spark-Site-Secret: ${SPARK_SITE_INGEST_SECRET}" \
  -d '{"email":"test+params@example.com","fname":"Param test","submission_type":"audit"}'
```

**With form page + store URL + origin**

```bash
curl -sS -w "\nHTTP %{http_code}\n" -X POST "${SPARK_BACKEND_URL}/api/site/lead" \
  -H "Content-Type: application/json" \
  -H "X-Spark-Site-Secret: ${SPARK_SITE_INGEST_SECRET}" \
  -d '{
    "email":"test+full@example.com",
    "fname":"Full test",
    "submission_type":"cro_scan",
    "lead_origin":"sparksmetrics.com",
    "website_url":"https://example-store.com",
    "form_page_url":"https://sparksmetrics.com/cro-scan?utm=test",
    "resource_slug":"some-resource",
    "business_stage":"growth",
    "orders_per_month":"100-500"
  }'
```

**Nested `params` (overridable from top level)**

```bash
curl -sS -w "\nHTTP %{http_code}\n" -X POST "${SPARK_BACKEND_URL}/api/site/lead" \
  -H "Content-Type: application/json" \
  -H "X-Spark-Site-Secret: ${SPARK_SITE_INGEST_SECRET}" \
  -d '{
    "email":"test+params2@example.com",
    "params": {
      "fname": "From params",
      "page_url": "https://sparksmetrics.com/page-a"
    },
    "fname": "Top level wins",
    "submission_type": "audit"
  }'
```

After a successful run, check Spark **Clients → Form page** for `form_page_url` / `page_url` / `submission_url`, and **`contact.site_ingest_payload`** for the full snapshot.

## Sparksmetrics: which forms enroll in nurture

In the marketing app `.env`:

- **`SPARK_NURTURE_ENROLLMENT_TYPES`** — comma-separated `submission_type` strings that send **`enroll_nurture: true`** to Spark.

Examples:

- `cro_scan` only (default if unset): CRO scan thank-you enrolls; audit/resource do not.
- `cro_scan,audit`: audit requests also request enrollment.
- Empty value: no form sends `enroll_nurture: true` (all false).

Form → `submission_type`: **`/cro-scan/submit-email`** → `cro_scan`; **`/cro-cost-roi/submit`** → `cro_cost_roi`; **`/request-audit`** → `audit`; **`/download-resource`** → `resource`; **`/strategy-session-step`** (steps 4–6 when email present) → `strategy_session`; Calendly webhook → `calendly`.

**Strategy session funnel** (`/30-minute-strategy-session/`): each step POSTs to **`/strategy-session-step`** with `funnel_session_id`, `step` (2–6), and any answers so far. Steps **2–3** (revenue, name only) log to `app/strategy_session_logs/steps.jsonl` + Slack; from **step 4** onward (valid email), Spark/Postgres upsert runs as `strategy_session` with extra fields `funnel_session_id`, `strategy_session_step`, `funnel_completed` on `site_ingest_payload`.

### CRO cost / ROI calculator (`cro_cost_roi`)

After a successful Spark ingest, the marketing app starts the same **CRO scan pipeline** as the public scan (`POST /api/site/cro-scan/run`, `delivery_mode=funnel`, `submission_type` attach **`cro_cost_roi`**) so the report can attach to the lead on Spark. It does **not** enqueue the generic “lead magnet enrich” background scan (that path is skipped for this type to avoid duplicate runs).

Transactional email to the lead is always the **Sparksmetrics “calculator snapshot”** message (not the CRO scan nurture copy). Spark-side nurture for `cro_cost_roi` is requested by default (`enroll_nurture: true` unless `SPARK_CRO_COST_ROI_ENROLL_NURTURE=0`). Spark should use a **sequence keyed off `submission_type`** (or equivalent) so these contacts do not receive the **CRO scan drip** wording meant for `/cro-scan` signups.

## Silent background CRO scan (all URL leads → Spark)

When **`SPARK_BACKEND_URL`** is set and **`SPARK_BACKGROUND_CRO_SCAN=1`** (default in code: on unless set to `0` / `false` / `no` / `off`):

1. **`_save_lead`** calls `post_form_lead` as before.
2. On **success**, if the payload had a non-empty **`website_url`**, the app enqueues **`run_scan`** with **`delivery_mode=lead_magnet_enrich`** (same as audit/resource): full CRO pipeline on Sparksmetrics, **no** report email to the lead; **`attach_nurture_scan`** sends **`report`** + **`report_view_url`** to Spark.

So **every** form that hits Spark with a store URL gets a scan (except **`cro_scan`**, which is handled only from **`/cro-scan/submit-email`** — register + separate funnel scan — to avoid duplicate work).

**Calendly** and other paths **without** a URL do not enqueue a scan.

Spark: if **`report`** arrives and no nurture row matched, ingest **creates** a **`cro_nurture_lead`** then attaches so **`full_report`** is stored. Nurture drip still follows **`enroll_nurture`** / Spark rules from the first touch; expand **`SPARK_NURTURE_ENROLLMENT_TYPES`** if you want more `submission_type` values to start the sequence, not only scan storage.
