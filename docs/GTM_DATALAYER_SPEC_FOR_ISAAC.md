# Sparksmetrics — GTM & dataLayer Spec

**For:** Isaac (GTM setup)  
**Site:** sparksmetrics.com  
**GTM container:** `GTM-ML2ZDNH2`  
**GA4:** `G-LHY1QG6J5T`  
**Last updated:** July 2026

---

## Overview

All tracking is pushed from one JavaScript module: `app/static/js/sm-analytics.js`.

**Principles:**

1. **Same `event` name** for the same action across all forms (e.g. every successful lead = `form_success`).
2. **Params distinguish the form** — `form_id`, `form_name`, `lead_type`, `resource_slug`, `conversion_type`.
3. **`user_data` is always the same object** with the same keys — GTM variables like `{{dlv - user_data.email}}` work on every push.
4. **One dataLayer push per action** — e.g. a single `form_success` push. Platform tags (FB, GAds, GA4) all listen to the same event; GTM filters on semantic fields like `conversion_type`, not platform-specific event names.
5. **Routing logic lives in code** — `sm-analytics.js` sets `conversion_type` and `gads_conversion_label`. GTM uses simple equals filters on those fields — never `lead_type` regex.

**Do not push manual `page_view` events** — let GTM handle pageviews.

---

## Event names (complete list)

### Forms

| `event`       | When                                      | GA4 mapping (suggested) |
|---------------|-------------------------------------------|-------------------------|
| `form_start`  | User opens or first interacts with a form | `form_start`            |
| `form_step`   | Multi-step funnel: user on step N         | `form_step`             |
| `form_submit` | Submit clicked (before server response)   | `form_submit`           |
| `form_success`| Server confirmed lead saved               | `generate_lead`         |
| `form_error`  | Server/network error                      | `form_error`            |

### Schedule (Calendly)

| `event`           | When                              | GA4 mapping (suggested) |
|-------------------|-----------------------------------|-------------------------|
| `schedule_open`   | Calendly widget/modal loads or funnel step | `schedule_step`         |
| `schedule_booked` | Calendly `event_scheduled` fires  | `schedule`              |

**`schedule_action` on `schedule_open`:** `open` (widget viewed) | `date_selected` (time slot picked)

### Engagement

| `event`           | When                          | GA4 mapping (suggested) |
|-------------------|-------------------------------|-------------------------|
| `video_start`     | Video plays                   | `video_start`           |
| `video_progress`  | 10/25/50/75/90% milestone     | `video_progress`        |
| `video_complete`  | Video ends                    | `video_complete`        |
| `video_pause`     | User pauses                   | `video_pause`           |
| `scroll`          | 25/50/75/90% page scroll      | `scroll`                |
| `click`           | Tracked CTA / button click    | `click`                 |

### Conversion fields (on `form_success` and `schedule_booked` only)

One push carries everything. GTM tags filter on these fields:

| Field | Values | Used by |
|-------|--------|---------|
| `conversion_type` | `lead`, `qualify_quiz`, `schedule` | FB Lead / Quiz / Schedule |
| `is_qualified` | `"true"` / `"false"` | FB Qualified Lead (extra) |
| `gads_conversion_label` | GAds label string, or `null` | GAds tag (fires when label is set) |

**Every lead form fires `conversion_type: "lead"`** — including qualified audits. Qualified is an additional flag, not a replacement.

| `lead_type` | `conversion_type` | `is_qualified` |
|-------------|-------------------|----------------|
| `ebook`, `vsl`, `audit`, `cro_scan`, `cro_cost_roi`, `strategy_session` | `lead` | `false` |
| `audit_qualified`, `cro_cost_roi_qualified` | `lead` | `true` |
| `qualify_quiz` | `qualify_quiz` | `false` |
| *(schedule_booked event)* | `schedule` | `false` |

**GAds labels** (set in code as `gads_conversion_label`):

| `lead_type` / event | Label |
|---------------------|-------|
| `ebook`, `vsl` | `4yqYCKvn0ocaEJHd0OQ9` |
| `cro_scan` | `ecdbCNLgroIcEJHd0OQ9` |
| `schedule_booked` | `KO_0CPODpskZEJHd0OQ9` |

---

## Standard payload structure

Every `dataLayer.push()` uses this shape. Keys that don't apply are `null` or omitted.

```javascript
{
  // ── Trigger (what happened) ──
  event: "form_success",

  // ── Form identity (which form) ──
  form_id: "lead-form",
  form_name: "CRO Ebook — 13 Bulletproof Strategies",
  lead_type: "ebook",
  conversion_type: "lead",
  resource_slug: "13-bulletproof-strategies",

  // ── Multi-step (null on single-step forms) ──
  form_step: null,
  form_step_total: null,
  form_step_name: null,

  // ── User data — ALWAYS this object, ALWAYS these keys ──
  user_data: {
    fname: "Stijn",
    email: "stijn@example.com",
    phone: null,
    website_url: null,
    business_stage: "scaling",
    orders_per_month: null,
    conversion_rate: null,
    average_order_value: null,
    annual_revenue: null,
    monthly_revenue_usd: null,
    transactions_per_month: null,
    qualify_score: null,
    qualify_tier: null
  },

  // ── Page context (auto-filled by sm-analytics.js) ──
  page_type: "cro_ebook",
  page_path: "/cro-ebook/",
  page_location: "https://sparksmetrics.com/cro-ebook/",

  // ── Session (auto-filled) ──
  funnel_session_id: "fs_abc123",
  event_id: "evt_xyz789",              // UUID on form_success + schedule_booked (dedup)

  // ── Video (null on non-video events) ──
  video_id: null,
  video_provider: null,
  video_url: null,
  video_title: null,
  video_duration: null,
  video_current_time: null,
  video_percent: null,

  // ── Click (null on non-click events) ──
  click_label: null,
  click_text: null,
  click_url: null,

  // ── Schedule (null on non-schedule events) ──
  schedule_action: null,               // open | booked | date_selected
  calendly_event: null,
  calendly_url: null,

  // ── Quiz step context (null when N/A) ──
  question_id: null,
  question: null,
  answer: null,
  answer_label: null,

  // ── Optional trigger context ──
  trigger_text: null,
  trigger_location: null,                // hero | header | modal | cta | inline

  timestamp: "2026-07-09T14:44:00Z"
}
```

---

## Form registry

| `form_id`              | `form_name`                          | `lead_type` values                          |
|------------------------|--------------------------------------|---------------------------------------------|
| `lead-form`            | Varies (see resource slugs below)    | `ebook`, `vsl`, `audit`, `audit_qualified`  |
| `qualify-quiz`         | CRO Qualify Quiz                     | `qualify_quiz`                              |
| `mss-funnel`           | 30 Minute Strategy Session           | `strategy_session`                          |
| `cro-scan-form`        | CRO Scan                             | `cro_scan`                                  |
| `cro-scan-email-form`  | CRO Scan — Email Follow-up           | `cro_scan`                                  |
| `ccr-lead-form`        | CRO Cost / ROI Calculator            | `cro_cost_roi`, `cro_cost_roi_qualified`    |
| `schedule-modal`       | Schedule a Call (Header Modal)       | `strategy_session`                          |
| `calendly-inline`      | Calendly Inline                        | `strategy_session`                          |

### `lead_type` values

| `lead_type`               | Meaning                                      | FB event (suggested)     |
|---------------------------|----------------------------------------------|--------------------------|
| `ebook`                   | Ebook / resource download                    | Lead                     |
| `vsl`                     | VSL video gate                               | Lead                     |
| `audit`                   | Free CRO audit                               | Lead                     |
| `audit_qualified`         | Audit + orders NOT `~100/month`              | Custom: Qualified Lead   |
| `cro_scan`                | CRO scan funnel                              | Lead                     |
| `cro_cost_roi`            | Cost ROI calculator                          | Lead                     |
| `cro_cost_roi_qualified`  | CCR + 500+ orders/month                      | Custom: Qualified Lead   |
| `qualify_quiz`            | Qualify quiz                                 | SubmitApplication (book) |
| `strategy_session`        | Strategy session funnel                      | —                        |

### Resource slugs (`resource_slug`)

| Slug                        | `form_name`                              | `lead_type` |
|-----------------------------|------------------------------------------|-------------|
| `13-bulletproof-strategies` | CRO Ebook — 13 Bulletproof Strategies    | `ebook`     |
| `7-questions-cro-agency`    | CRO Ebook — 7 Questions for a CRO Agency | `ebook`     |
| `vsl-free-cro-video`        | Free CRO Video (VSL Gate)                | `vsl`       |

---

## Example payloads by scenario

### Ebook download — `form_success` (single push)

```javascript
{
  event: "form_success",
  form_id: "lead-form",
  form_name: "CRO Ebook — 13 Bulletproof Strategies",
  lead_type: "ebook",
  conversion_type: "lead",
  gads_conversion_label: "4yqYCKvn0ocaEJHd0OQ9",
  resource_slug: "13-bulletproof-strategies",
  user_data: { fname: "Stijn", email: "stijn@example.com" },
  event_id: "evt_xyz789"
}
```

GTM fires on this **one push**:
- `GA4 - Form Success` → `CE - form_success`
- `FB - Lead` → `CE - form_success - lead` (`conversion_type` = `lead`)
- `Gads - Conversion` → `CE - conversion - Gads` (`gads_conversion_label` is set)

### VSL gate — `form_success`

```javascript
{
  event: "form_success",
  form_id: "lead-form",
  form_name: "Free CRO Video (VSL Gate)",
  lead_type: "vsl",
  resource_slug: "vsl-free-cro-video",
  user_data: {
    fname: "Stijn",
    email: "stijn@example.com"
    // remaining keys null
  }
}
```

### Free CRO audit (qualified) — `form_success`

```javascript
{
  event: "form_success",
  form_id: "lead-form",
  form_name: "Free CRO Audit",
  lead_type: "audit_qualified",
  resource_slug: null,
  user_data: {
    fname: "Stijn",
    email: "stijn@example.com",
    website_url: "https://store.com",
    orders_per_month: "500-1000",
    conversion_rate: "2.5%",
    average_order_value: "85"
  }
}
```

### Qualify quiz — `form_step`

```javascript
{
  event: "form_step",
  form_id: "qualify-quiz",
  form_name: "CRO Qualify Quiz",
  lead_type: "qualify_quiz",
  form_step: 5,
  form_step_total: 9,
  form_step_name: "monthly_traffic",
  question_id: "q4",
  question: "How many visitors does your store get per month?",
  answer: "50k-100k",
  answer_label: "50,000 – 100,000",
  user_data: {
    qualify_score: 45
  }
}
```

### Strategy session — `form_step`

```javascript
{
  event: "form_step",
  form_id: "mss-funnel",
  form_name: "30 Minute Strategy Session",
  lead_type: "strategy_session",
  form_step: 4,
  form_step_total: 6,
  form_step_name: "email",
  question: "What's your email?",
  answer: "stijn@example.com",
  user_data: {
    fname: "Stijn",
    email: "stijn@example.com",
    annual_revenue: "1m-5m"
  }
}
```

### CRO scan — `form_submit`

```javascript
{
  event: "form_submit",
  form_id: "cro-scan-form",
  form_name: "CRO Scan",
  lead_type: "cro_scan",
  user_data: {
    website_url: "https://store.myshopify.com"
  }
}
```

### CRO cost ROI — `form_success`

```javascript
{
  event: "form_success",
  form_id: "ccr-lead-form",
  form_name: "CRO Cost / ROI Calculator",
  lead_type: "cro_cost_roi_qualified",
  user_data: {
    fname: "Stijn",
    email: "stijn@example.com",
    website_url: "https://store.com",
    monthly_revenue_usd: "150000",
    transactions_per_month: "600"
  }
}
```

### Calendly booked — `schedule_booked`

```javascript
{
  event: "schedule_booked",
  form_id: "lead-form",
  form_name: "CRO Ebook — 13 Bulletproof Strategies",
  lead_type: "ebook",
  schedule_action: "booked",
  calendly_event: "event_scheduled",
  calendly_url: "https://calendly.com/stijn-wollerich/free-30-minute-strategy-session",
  user_data: {
    fname: "Stijn",
    email: "stijn@example.com"
  },
  event_id: "evt_def456"
}
```

### Video progress — `video_progress`

```javascript
{
  event: "video_progress",
  form_id: null,
  form_name: null,
  lead_type: null,
  video_id: "vsl-hero",
  video_provider: "youtube",
  video_url: "https://www.youtube.com/watch?v=VIDEO_ID",
  video_title: "Free CRO Walkthrough",
  video_duration: 312,
  video_current_time: 156,
  video_percent: 50,
  user_data: {
    // all null
  }
}
```

### Calculator completed — `click`

```javascript
{
  event: "click",
  click_label: "cro_cost_roi_calculated",
  click_text: "Calculator completed",
  page_type: "cro_cost_roi_landing"
}
```

### CTA opens lead modal — `click`

```javascript
{
  event: "click",
  form_id: "lead-form",
  form_name: "CRO Ebook — 13 Bulletproof Strategies",
  lead_type: "ebook",
  resource_slug: "13-bulletproof-strategies",
  click_text: "Download free ebook",
  trigger_location: "cta"
}
```

---

## GTM setup instructions

### Quick start — import JSON (recommended)

A **full workspace overwrite** file is ready — it replaces the entire workspace (deletes all ~77 old tags) with a clean setup.

**File:** `docs/gtm-import-sm-analytics.json` (also copied to Downloads as `gtm-import-sm-analytics-GTM-ML2ZDNH2-OVERWRITE.json`)

**Regenerate after changes:** `python3 scripts/generate_gtm_sm_import.py` (requires `~/Downloads/GTM-ML2ZDNH2_workspace51.json` as source for foundation tags)

**Import steps:**

1. **Export a backup first** — Admin → Export Container → save current workspace
2. GTM → Admin → **Import Container**
3. Choose the JSON file
4. Select workspace: **Default** (or create a fresh test workspace first)
5. Import option: **Overwrite** — this replaces the whole workspace
6. **Confirm** → review the diff → **Preview** on site → **Publish**

**What's kept from the old container (14 tags):**

- GA4 config, Gads conversion linker, FB PageView
- Hotjar, Clarity, Twitter, Sparksmetrics script
- Native GA4 tags: scroll depth, social/phone/email/PDF/blog/button clicks

**What's new (9 SM tags, 12 CE triggers, 46 variables):**

| Tag | Trigger | Condition |
|-----|---------|-----------|
| `GA4 - Form Success` | `CE - form_success` | — |
| `GA4 - Form Step` | `CE - form_step` | — |
| `GA4 - Schedule Step` | `CE - schedule_open` | `schedule_step` + `schedule_action` |
| `GA4 - Schedule Booked` | `CE - schedule_booked` | `schedule` |
| `GA4 - Engagement` | `CE - engagement` | — |
| `FB - Lead` | `CE - form_success - lead` | `conversion_type` = `lead` |
| `FB - Qualified Lead` | `CE - form_success - qualified_lead` | `is_qualified` = `true` |
| `FB - Qualify Quiz Complete` | `CE - form_success - qualify_quiz` | `conversion_type` = `qualify_quiz` |
| `FB - Schedule` | `CE - schedule_booked - schedule` | `conversion_type` = `schedule` |
| `Gads - Conversion` | `CE - conversion - Gads` + `CE - schedule_booked - Gads` | `gads_conversion_label` is set |

**No platform-specific event names.** Same `form_success` push powers GA4, FB, and GAds.

---

### Manual setup (if not importing)

### Step 1 — Create Data Layer Variables

Create these as **Data Layer Variable** (version 2) in GTM:

| Variable name                      | Data Layer Variable Name           |
|------------------------------------|------------------------------------|
| `dlv - event`                      | `event`                            |
| `dlv - form_id`                    | `form_id`                          |
| `dlv - form_name`                  | `form_name`                        |
| `dlv - lead_type`                  | `lead_type`                        |
| `dlv - conversion_type`            | `conversion_type`                    |
| `dlv - is_qualified`               | `is_qualified`                       |
| `dlv - gads_conversion_label`      | `gads_conversion_label`              |
| `dlv - resource_slug`              | `resource_slug`                    |
| `dlv - form_step`                  | `form_step`                        |
| `dlv - form_step_total`            | `form_step_total`                  |
| `dlv - form_step_name`             | `form_step_name`                   |
| `dlv - user_data.fname`            | `user_data.fname`                  |
| `dlv - user_data.email`            | `user_data.email`                  |
| `dlv - user_data.phone`             | `user_data.phone`                  |
| `dlv - user_data.website_url`      | `user_data.website_url`            |
| `dlv - user_data.business_stage`   | `user_data.business_stage`         |
| `dlv - user_data.orders_per_month`   | `user_data.orders_per_month`       |
| `dlv - user_data.conversion_rate`   | `user_data.conversion_rate`        |
| `dlv - user_data.average_order_value` | `user_data.average_order_value` |
| `dlv - user_data.annual_revenue`   | `user_data.annual_revenue`         |
| `dlv - user_data.monthly_revenue_usd` | `user_data.monthly_revenue_usd` |
| `dlv - user_data.transactions_per_month` | `user_data.transactions_per_month` |
| `dlv - user_data.qualify_score`    | `user_data.qualify_score`          |
| `dlv - user_data.qualify_tier`     | `user_data.qualify_tier`           |
| `dlv - funnel_session_id`          | `funnel_session_id`                |
| `dlv - event_id`                   | `event_id`                         |
| `dlv - page_type`                  | `page_type`                        |
| `dlv - page_path`                  | `page_path`                        |
| `dlv - video_id`                   | `video_id`                         |
| `dlv - video_percent`              | `video_percent`                    |
| `dlv - video_provider`             | `video_provider`                   |
| `dlv - video_url`                  | `video_url`                        |
| `dlv - video_title`                | `video_title`                      |
| `dlv - video_duration`             | `video_duration`                   |
| `dlv - video_current_time`         | `video_current_time`               |
| `dlv - click_label`                | `click_label`                      |
| `dlv - click_text`                 | `click_text`                       |
| `dlv - scroll_percent`             | `scroll_percent`                   |
| `dlv - calendly_event`             | `calendly_event`                   |
| `dlv - calendly_url`               | `calendly_url`                     |
| `dlv - question`                   | `question`                         |
| `dlv - answer`                     | `answer`                           |
| `dlv - trigger_location`           | `trigger_location`                 |

**Delete or stop using old variables:**

- `dlv - form_answers.*` (replaced by `user_data.*`)
- `dlv - data.*` (replaced by `user_data.*`)
- `dlv - anwer` (typo — use `dlv - answer`)
- Top-level `dlv - fname` / `dlv - email` (use `user_data.fname` / `user_data.email`)

---

### Step 2 — Create triggers

| Trigger name               | Type          | Condition                                              |
|----------------------------|---------------|--------------------------------------------------------|
| `CE - form_success`                | Custom Event  | `event` equals `form_success`                          |
| `CE - form_success - lead`         | Custom Event  | `form_success` + `conversion_type` equals `lead`       |
| `CE - form_success - qualified_lead` | Custom Event | `form_success` + `is_qualified` equals `true`          |
| `CE - form_success - qualify_quiz` | Custom Event  | `form_success` + `conversion_type` equals `qualify_quiz` |
| `CE - conversion - Gads`           | Custom Event  | `form_success` + `gads_conversion_label` is set        |
| `CE - schedule_booked - schedule`  | Custom Event  | `schedule_booked` + `conversion_type` equals `schedule` |
| `CE - schedule_booked - Gads`      | Custom Event  | `schedule_booked` + `gads_conversion_label` is set     |
| `CE - form_step`                   | Custom Event  | `event` equals `form_step`                             |
| `CE - form_start`                  | Custom Event  | `event` equals `form_start`                            |
| `CE - schedule_booked`             | Custom Event  | `event` equals `schedule_booked`                       |
| `CE - schedule_open`               | Custom Event  | `event` equals `schedule_open`                         |
| `CE - engagement`                  | Custom Event  | `event` matches RegEx `video_|^scroll$|^click$`         |

**Do not filter on `lead_type` in GTM** — use `conversion_type` instead.

**Keep existing native GTM triggers** (no code changes needed):

- Scroll Depth
- Social media link clicks
- Phone / email link clicks
- PDF clicks
- Blog internal link clicks

---

### Step 3 — Create consolidated tags

#### GA4 - Form Success

- **Type:** Google Analytics: GA4 Event
- **Trigger:** `CE - form_success`
- **Event name:** `generate_lead`
- **Event parameters:**

| Parameter           | Value                        |
|---------------------|------------------------------|
| `form_id`           | `{{dlv - form_id}}`          |
| `form_name`         | `{{dlv - form_name}}`        |
| `lead_type`         | `{{dlv - lead_type}}`        |
| `resource_slug`     | `{{dlv - resource_slug}}`    |
| `page_type`         | `{{dlv - page_type}}`        |
| `funnel_session_id` | `{{dlv - funnel_session_id}}`|
| `event_id`          | `{{dlv - event_id}}`         |

- **User properties (optional):** map `lead_type`, `page_type` as needed.

#### GA4 - Form Submit

- **Trigger:** `CE - form_submit`
- **Event name:** `form_submit`
- Same parameters as Form Success.

#### GA4 - Form Step

- **Trigger:** `CE - form_step`
- **Event name:** `form_step`
- Additional parameters: `form_step`, `form_step_total`, `form_step_name`, `question`, `answer`, `answer_label`.

#### GA4 - Schedule Step

- **Trigger:** `CE - schedule_open`
- **Event name:** `schedule_step`
- Parameters: `form_id`, `form_name`, `lead_type`, `schedule_action`, `calendly_event`, `calendly_url`, `page_type`, `funnel_session_id`

#### GA4 - Schedule Booked

- **Trigger:** `CE - schedule_booked`
- **Event name:** `schedule`
- Parameters: `form_id`, `form_name`, `lead_type`, `calendly_event`, `funnel_session_id`, `event_id`.

#### GA4 - Engagement

- **Trigger:** `CE - engagement`
- **Event name:** `{{Event}}` (pass-through: `video_start`, `video_progress`, `click`, `scroll`, etc.)
- Parameters: `video_id`, `video_percent`, `video_provider`, `video_url`, `video_title`, `video_duration`, `video_current_time`, `click_label`, `click_text`, `scroll_percent`.

#### FB conversions

Each FB tag fires on `form_success` or `schedule_booked` with a `conversion_type` filter:

| GTM tag | Trigger | Condition |
|---------|---------|-----------|
| `FB - Lead` | `CE - form_success - lead` | `conversion_type` = `lead` (all lead forms) |
| `FB - Qualified Lead` | `CE - form_success - qualified_lead` | `is_qualified` = `true` |
| `FB - Qualify Quiz Complete` | `CE - form_success - qualify_quiz` | `conversion_type` = `qualify_quiz` |
| `FB - Schedule` | `CE - schedule_booked - schedule` | `conversion_type` = `schedule` |

#### Gads - Conversion

- **Triggers:** `CE - conversion - Gads` (form) + `CE - schedule_booked - Gads`
- **Conversion label:** `{{dlv - gads_conversion_label}}`
- Fires only when code sets a label (null = no GAds conversion for that form)

---

### Step 4 — Enhanced conversions

GA4 enhanced conversions / Google Ads user-provided data:

- Email: `{{dlv - user_data.email}}`
- First name: `{{dlv - user_data.fname}}`

Use the **User-Provided Data** variable in GTM set to automatic mode, or map manually from the variables above.

For Meta CAPI (if using sGTM): hash `user_data.email` and `user_data.fname` server-side. Pass `event_id` for deduplication on `form_success` and `schedule_booked`.

---

### Step 5 — Archive old tags

Once validated in GTM Preview, **pause then archive** these old patterns:

- Per-event GA4 tags (`GA4 - EBook CTA Clicked`, `GA4 - Audit CTA Clicked`, `GA4 - Lead Modal Open`, etc.)
- Per-event CE triggers (`CE - lead_form_success - Free CRO Audit - 500+ Orders`, etc.)
- Duplicate Calendly tags (consolidate to schedule tags above)
- Legacy pageview-based ebook conversion trigger (`CRO Lead Form Submit` on `/thank-you/` + referrer)

Run **old and new tags in parallel** for 1–2 weeks before fully removing old ones.

---

## Testing checklist

Use GTM Preview + GA4 DebugView. Confirm each row fires the correct `event` and parameters.

| # | Action                              | Expected `event`   | Key params to verify                                      |
|---|-------------------------------------|--------------------|-----------------------------------------------------------|
| 1 | Click ebook CTA                     | `click`            | `form_id=lead-form`, `lead_type=ebook`, `resource_slug`   |
| 2 | Open lead modal                     | `form_start`       | `form_id`, `form_name`, `lead_type`                       |
| 3 | Submit ebook form                   | `form_submit` then `form_success` | `user_data.email`, `event_id` on success      |
| 4 | Submit VSL gate                     | `form_success`     | `lead_type=vsl`, `resource_slug=vsl-free-cro-video`       |
| 5 | Submit audit (qualified)            | `form_success`     | `lead_type=audit_qualified`, `user_data.orders_per_month` |
| 6 | Book Calendly after ebook           | `schedule_booked`  | `user_data.email`, `event_id`                             |
| 7 | Qualify quiz step                   | `form_step`        | `form_id=qualify-quiz`, `form_step`, `question`           |
| 8 | Strategy session step               | `form_step`        | `form_id=mss-funnel`, `user_data.annual_revenue`          |
| 9 | CRO scan URL submit                 | `form_submit`      | `form_id=cro-scan-form`                                   |
| 10| CRO cost ROI lead                   | `form_success`     | `form_id=ccr-lead-form`, `lead_type`                      |
| 11| Play VSL video                      | `video_start`      | `video_id`, `video_provider`                              |
| 12| Video 50%                           | `video_progress`   | `video_percent=50`                                        |
| 13| Scroll 50%                          | `scroll`           | `scroll_percent=50`                                       |
| 14| Header schedule link                | `schedule_open`    | `form_id=schedule-modal`                                  |

---

## Adding a new form

In code:

```javascript
SmAnalytics.formSuccess({
  form_id: "webinar-signup",
  form_name: "Webinar Signup",
  lead_type: "webinar",
  user_data: {
    fname: "Jane",
    email: "jane@example.com"
  }
});
```

GTM: `CE - form_success` fires GA4 automatically. For FB/GAds, update `conversionType()` and `GADS_LABEL_BY_LEAD_TYPE` in `sm-analytics.js`. Only add a new GTM tag if you need a new `conversion_type` value.

---

## Old event → new event mapping

| Old dataLayer `event`              | New `event`        |
|------------------------------------|--------------------|
| `lead_modal_open`                  | `form_start`       |
| `lead_form_submitted`              | `form_submit`      |
| `lead_form_success`                | `form_success`     |
| `lead_form_error`                  | `form_error`       |
| `ebook_cta_clicked` / `audit_cta_clicked` / `video_cta_clicked` | `click` |
| `cro_qualify_quiz`                 | `form_step`        |
| `strategy_session_form`            | `form_step` / `form_submit` |
| `calendly_open_from_lead`          | `schedule_open`    |
| `calendly.event_scheduled`         | `schedule_booked`  |
| `schedule_modal_open`              | `schedule_open`    |
| `generic_form_submitted`           | `form_submit`      |
| `cro_cost_roi_calculated`          | `click` (`click_label=cro_cost_roi_calculated`) |
| `cro_cost_roi_lead`                | `form_success`     |
| `cro_scan_email_submitted`         | `form_success`     |
| Manual `page_view`                 | **Removed** — use GTM pageview |

---

## Code reference

| File | Role |
|------|------|
| `app/static/js/sm-analytics.js` | **Only file that calls `dataLayer.push()`** |
| `app/static/js/checklist-modal.js` | Lead modal (ebook, VSL, audit) |
| `app/static/js/qualify-quiz-gtm.js` | Qualify quiz tracking |
| `app/static/js/strategy-session-funnel.js` | Strategy session funnel |
| `app/static/js/vsl-video-analytics.js` | Video engagement |
| `app/templates/base.html` | Loads `sm-analytics.js`, generic form submit listener |

---

## Questions?

Contact Stijn if payloads in GTM Preview don't match this doc.
