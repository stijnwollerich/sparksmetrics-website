# CRO Scan Pipeline

End-to-end flow after a user submits their email on the cro-scan thank-you page:

1. **User flow**: User enters store URL → thank-you page → submits email (company only).
2. **Background job** (runs in a daemon thread right after the API responds):
   - **Screenshots**: Discover homepage, one collection page, one product page. If `BROWSERLESS_API_TOKEN` is set, use [Browserless](https://www.browserless.io/) /unblock (Cloudflare bypass, 1000 free/mo); else if `SCRAPFLY_API_KEY` is set, use [Scrapfly](https://scrapfly.io/screenshot-api); otherwise use [thum.io](https://image.thum.io/).
   - **AI analysis**: Send screenshot image URLs to OpenAI Vision (e.g. `gpt-4o-mini`); prompt returns structured JSON (motivation, friction, clarity, page anatomy, top issues, recommendations).
   - **Report**: Render `app/templates/cro_scan_report.html` with the JSON → HTML → PDF via [WeasyPrint](https://weasyprint.org/).
   - **Email**: Send the PDF as an attachment via [Brevo transactional API](https://developers.brevo.com/reference/send-transac-email).

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | For AI analysis | OpenAI API key; if missing, report uses a placeholder and still sends a PDF. |
| `BREVO_API_KEY` | For email | Brevo API key. |
| `BREVO_SENDER_EMAIL` | For email | Verified sender email in Brevo (transactional). |
| `BREVO_SENDER_NAME` | Optional | Sender name (default: Sparksmetrics). |
| `OPENAI_BASE_URL` | Optional | Default `https://api.openai.com/v1`. |
| `BROWSERLESS_API_TOKEN` | Optional | When set, screenshots use Browserless /unblock (Cloudflare bypass). 1000 free requests/mo. Takes precedence over Scrapfly. |
| `SCRAPFLY_API_KEY` | Optional | When set (and no Browserless), screenshots use Scrapfly. ~60 credits/screenshot. |

## Report JSON shape

The AI is prompted to return JSON like:

```json
{
  "overall_score": 72,
  "store_name": "Store Name",
  "pages": {
    "homepage": { "score": 72, "motivation": "...", "friction": [], "clarity": "...", "anatomy": "..." },
    "collection": { ... },
    "product": { ... }
  },
  "top_issues": [ { "priority": 1, "page": "homepage", "title": "...", "description": "..." } ],
  "recommendations": [ "..." ]
}
```

You can extend the prompt and schema in `app/cro_scan/ai_analysis.py` (e.g. more dimensions, scores per section) and add sections in `app/templates/cro_scan_report.html`.

## PDF generation

WeasyPrint is used for HTML → PDF. On Linux servers you may need system libraries, e.g.:

- Ubuntu/Debian: `apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info`
- macOS: `brew install pango gdk-pixbuf libffi`

See [WeasyPrint install](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).

## Running the scan manually

From a Python shell with app context:

```python
from app import create_app
from app.cro_scan import run_scan
app = create_app()
with app.app_context():
    run_scan(store_url="https://yourstore.com", email="you@company.com", fname="You")
```
