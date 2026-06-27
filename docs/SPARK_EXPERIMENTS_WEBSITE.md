# Spark experiments on sparksmetrics.com

Public A/B test cards (before/after screenshots + results) on **`/free-cro-audit/`** are loaded from **Spark** at **`https://spark.sparksmetrics.com`**.

## Architecture

| Piece | Host | Role |
|-------|------|------|
| Page HTML | `sparksmetrics.com` | Renders cards when Spark returns experiments |
| List API | `spark.sparksmetrics.com` | `GET /api/site/experiments` (secret auth) |
| Images | `sparksmetrics.com` | `GET /spark-experiments/image?path=…` proxies to Spark |
| Image bytes | `spark.sparksmetrics.com` | `GET /api/site/experiments/image` (secret + allowlist) |
| Source of truth | Spark Postgres | `experiment` rows + `variant_groups` JSON |

No browser calls Spark directly; the marketing app uses server-side `requests` with **`X-Spark-Site-Secret`**.

## Open API on Spark, filter on sparksmetrics.com

| Layer | What it does |
|-------|----------------|
| **Spark** `GET /api/site/experiments` | Returns **all** experiments (marketing-safe JSON: no company name). Includes `published_channels`, stats, variant images. Auth: `X-Spark-Site-Secret` only — not a public browser API. |
| **Spark** `GET /api/site/experiments/image` | Serves any experiment screenshot path (same secret + allowlist of upload paths). |
| **Marketing** `app/services/spark_experiments.py` | **Only place** that decides what appears on `/free-cro-audit/`. Edit this file to change rules; redeploy marketing only. |

Default marketing rule (`spark_experiments.py`): **variant winner** with **positive lift** (conv, revenue, PSV, or AOV) and control/challenger images. Completed tests where control won or metrics are flat/negative are excluded. The Spark **website** checkbox is **not** required.

Company names are **not** exposed from Spark. Prefer **replica** mockups on client tests.

## Production environment (sparksmetrics.com server)

In the marketing app `.env` on the droplet (same values you already use for lead ingest):

```bash
SPARK_BACKEND_URL=https://spark.sparksmetrics.com
SPARK_SITE_INGEST_SECRET=<same string as on Spark>
```

`SPARK_SITE_INGEST_SECRET` must match Spark’s `SPARK_SITE_INGEST_SECRET` byte-for-byte (copy from Spark `.env` / password manager).

After changing `.env`:

```bash
sudo systemctl restart sparksmetrics
```

Verify:

```bash
# From the server (substitute your real secret)
curl -sS -H "X-Spark-Site-Secret: YOUR_SECRET" \
  https://spark.sparksmetrics.com/api/site/experiments | head -c 400
# Expect: {"ok":true,"experiments":[...]}

curl -sS https://sparksmetrics.com/free-cro-audit/ | grep -o 'id="ab-tests"'
# Expect: id="ab-tests"
```

## Production deploy checklist

### 1. Deploy Spark first (`spark.sparksmetrics.com`)

Push and deploy the Spark repo that includes:

- `app/sparksmetrics_website/experiments_public.py`
- `GET /api/site/experiments` and `GET /api/site/experiments/image` in `app/sparksmetrics_website/routes.py`
- `app/experiment_image_serve.py`
- `website` in **Published / shared** UI (`experiment_variants.PUBLICATION_CHANNEL_KEYS`)

On the Spark server: `git pull`, restart gunicorn/uwsgi (e.g. `sudo systemctl restart spark`).

Confirm the route exists (404 today means this deploy is still pending):

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "X-Spark-Site-Secret: YOUR_SECRET" \
  https://spark.sparksmetrics.com/api/site/experiments
# Target: 200
```

### 2. Deploy sparksmetrics.com

Push and deploy **sparksmetrics-website** with:

- `app/services/spark_experiments.py`
- `app/spark_backend.fetch_website_experiments` / `fetch_experiment_image`
- `/free-cro-audit/` passes `spark_experiments`
- `/spark-experiments/image` proxy route

Restart the marketing systemd service.

### 3. Mark experiments on production Spark

On **https://spark.sparksmetrics.com** (production DB), enable **Sparksmetrics website** for each test you want live. Production data is separate from your local Postgres.

## Local development

- Spark: `PORT=5002` (macOS uses `:5000` for AirPlay).
- Marketing: `SPARK_BACKEND_URL=http://127.0.0.1:5002`

See `context/spark-experiments-api.md` in the sparksmetrics workspace for upload API details.

## Caching

The marketing app caches the experiment list for **5 minutes** (`app/services/spark_experiments.py`). After publishing a new test in Spark, wait up to 5 minutes or restart the marketing app to see it immediately.

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| No section on `/free-cro-audit/` | `SPARK_BACKEND_URL` / secret unset on marketing server, or fetch failed |
| Section + “No tests are published yet” | Spark reachable but no `published_channels.website` experiments with images |
| Broken images | Spark not deployed with `/api/site/experiments/image`, or path not in allowlist |
| `401` from Spark | `SPARK_SITE_INGEST_SECRET` mismatch between apps |
| `404` on `/api/site/experiments` | Spark code not deployed to production yet |
