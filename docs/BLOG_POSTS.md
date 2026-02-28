# How to create a blog post

This doc describes how to add a new blog post to the site using the latest setup (one HTML template per post + metadata in `blog_posts.json`).

## Overview

- **One HTML template per post** in `app/templates/blog/`.
- **One metadata entry** per post in `app/blog_posts.json` (title, description, slug, dates, optional video, etc.).
- The blog index at `/blog` is built by scanning `app/templates/blog/*.html` and merging with `blog_posts.json` by slug. Posts are **sorted newest first** by `published_date`.
- The sitemap includes all posts listed in `blog_posts.json`. The footer links to the blog index.

## Step 1: Add the post to `app/blog_posts.json`

Add an object to the `posts` array with at least:

| Key | Example | Notes |
|-----|---------|--------|
| `slug` | `"allbirds-conversion-strategy-shopify-cro"` | URL path: `/blog/<slug>`. Use lowercase and hyphens. |
| `title` | `"Allbirds Conversion Strategy: 7 Shopify CRO Lessons to Steal"` | Meta title / index card title. |
| `description` | `"A fun, data-driven teardown…"` | Meta description; keep 140–160 chars for SEO. |
| `published_date` | `"16 Feb 2026"` | Format: `DD Mon YYYY`. Used for sorting (newest first) and display. |
| `updated_date` | `"16 Feb 2026"` | Same format as `published_date`. |
| `reading_time` | `"14 min read"` | Shown in header and index. |
| `category` | `"CRO"` | Shown in header and index. |
| `template` | `"blog_allbirds-conversion-strategy-shopify-cro.html"` | Filename only (no `blog/` prefix). Must match the file you create. |

Optional (e.g. for video posts):

- `video_id` — YouTube video ID (e.g. `"06bAhn_pMUI"`).
- `youtube_url` — Full URL (e.g. `"https://youtu.be/06bAhn_pMUI"`).

**Slug and filename:** The slug in JSON must match the slug derived from the template filename: `blog_<slug>.html` → slug is `<slug>`. So for slug `allbirds-conversion-strategy-shopify-cro`, the file must be named `blog_allbirds-conversion-strategy-shopify-cro.html` (hyphens in the filename give hyphens in the URL).

## Step 2: Create the template in `app/templates/blog/`

Create a file named `blog_<slug>.html` (e.g. `blog_allbirds-conversion-strategy-shopify-cro.html`).

### Template structure

1. **Extend base and set meta**
   - `{% extends "base.html" %}`
   - Blocks: `title`, `meta_description`, `og_title`, `twitter_title`, `og_description`, `twitter_description`, `content`.

2. **Header section** (above the fold)
   - “Back to blog” link: `{{ url_for('main.blog_index') }}`
   - Category, H1 (post title), description (`{{ post.description }}`), published date and reading time (`{{ post.published_date }}`, `{{ post.reading_time }}`).

3. **Video** (optional)
   - If the post has a video, embed it right after the header with an iframe using `https://www.youtube.com/embed/{{ post.video_id }}`. Fallback: `{{ post.video_id or 'YOUR_DEFAULT_ID' }}`.

4. **Article body** (`<article class="blog-prose">`)
   - JSON-LD script for Article (headline, description).
   - **Short on-page summary** (recommended for SEO): a `<p class="lead">` and/or a bullet list so the value is indexable without watching a video.
   - **CTAs:** Include `{% include 'blog/includes/hero_cta_buttons.html' %}` once near the top (Schedule a call + Download free ebook).
   - **Table of contents:** `<nav id="toc">` with `<strong>Contents</strong>` and a `<ul>` of anchor links to each major section (use `id="section-slug"` on each `h2`).
   - **Body:** H2s with `id="..."` for anchors, H3s, paragraphs, `ul`/`ol`, and callouts.
   - **Callouts:** Use `<div class="callout">` and `<p class="callout-title">…</p>` for “CRO takeaway”, “Why this matters”, etc.
   - **Mid/end CTAs:** e.g. `{% include 'blog/includes/cta_audit.html' %}` before or after the closing CTA section.

### Typography and spacing (don’t override)

- **Body and lists:** `.blog-prose` sets paragraph and list font size and line-height; lists use the same size as body for consistency.
- **Lead:** Use `<p class="lead">` for the intro; it gets larger size and spacing automatically.
- **TOC:** Use `<nav id="toc">` and a `<ul>` inside; font size and spacing are set in `base.html` so the TOC doesn’t look cramped.
- **Callouts:** Use `.callout` and `.callout-title`; title size is tuned in `base.html`.

So: use the classes above and avoid adding extra font-size or spacing utilities unless needed for a one-off.

### Example snippet (after the video)

```html
<article class="blog-prose mt-10">
  <script type="application/ld+json">{{ { "@context": "https://schema.org", "@type": "Article", "headline": post.title, "description": post.description } | tojson }}</script>

  <p class="lead">Short intro so the value is clear without watching a video.</p>
  <ul class="mb-6">
    <li><strong>First takeaway</strong></li>
    <li>Second takeaway</li>
  </ul>

  {% include 'blog/includes/hero_cta_buttons.html' %}

  <nav id="toc" class="mb-6 p-4 bg-primary/5 rounded-lg">
    <strong>Contents</strong>
    <ul class="ml-4 mt-2">
      <li><a href="#section-1">Section 1</a></li>
      <li><a href="#section-2">Section 2</a></li>
    </ul>
  </nav>

  <h2 id="section-1">Section 1</h2>
  <p>…</p>
  <div class="callout mt-6 p-4 bg-primary/5 rounded-lg border border-primary/20">
    <p class="callout-title font-semibold mb-2">CRO takeaway</p>
    <p>…</p>
  </div>

  <h2 id="section-2">Section 2</h2>
  …

  {% include 'blog/includes/cta_audit.html' %}
</article>
```

## Checklist

- [ ] Entry in `app/blog_posts.json` with correct `slug`, `template`, `published_date`, and optional `video_id`.
- [ ] File `app/templates/blog/blog_<slug>.html` created with the same slug (hyphens in slug → hyphens in filename).
- [ ] Template extends `base.html`, sets meta blocks, header, optional video, and `<article class="blog-prose">` with JSON-LD, lead/summary, TOC, and body.
- [ ] At least one primary CTA (hero buttons and/or audit) and one secondary (ebook) as per `app/SEO_GUIDELINES.md`.
- [ ] H2s have `id` attributes matching the TOC links.

## References

- **Content and CTAs:** `app/SEO_GUIDELINES.md` — required structure, voice, and reusable includes (`hero_cta_buttons`, `cta_audit`, `cta_ebook`, `banner_schedule`).
- **Blog automation:** `README.md` — YouTube → blog post script and cron.
- **Discovery:** Blog index uses `_scan_blog_templates()` (then falls back to `_load_blog_posts()`), sorts by `published_date` newest first; sitemap uses `_load_blog_posts()`; footer link to blog is in `base.html`.
