SEO Guidelines for blog content (AI / writers)
=============================================

Purpose
-------
Provide a consistent set of requirements and examples so automated processes (AI or humans) produce rich, SEO-friendly articles that match Sparksmetrics' style.

Required structural elements for every article
--------------------------------------------
- Title: human-friendly, includes primary keyword (60–70 chars ideally).
- Meta description: 140–160 characters, includes primary keyword and a clear value proposition.
- H1 (page title) & clear H2/H3 hierarchy.
- Table of contents (anchor links) near the top for long pieces.
- Lead / intro paragraph: 40–80 words summarizing the article and its value.
- "Why this matters" section near the top or for each major section.
- "Implementation checklist" near the end with concrete, actionable steps.
- Strong CTAs: at least one primary CTA (Schedule a call / Audit) and one secondary CTA (Download resource / Learn more).
- JSON-LD Article schema with headline and description.
- Internal links to related pages (case studies, services, other blog posts).
- Image(s) with descriptive alt text and 1200x630 OG-friendly variants.
- Reading time estimate and published_date metadata.

Voice & tone
----------
- Authoritative but practical. Use active voice and short paragraphs.
- Focus on outcomes and tests, not buzzwords.
- Include specific examples, numbers, or micro-case-studies where possible.

SEO & formatting best practices
-----------------------------
- Use the primary keyword in title, first paragraph, one H2, and meta description.
- Keep sentences under 20 words where practical.
- Use lists, bolding (sparingly), and callout boxes for "Why this matters" and "Quick actions".
- Add internal links to relevant service pages (e.g., /schedule-a-call/, /cro/).
- Ensure meta_description and og_description are present and not template placeholders.
- Provide canonical if content exists in multiple forms.

Guidance for AI article generation
---------------------------------
When an AI generates or rewrites an article, require the following output structure:

1) Frontmatter dict (JSON) with keys:
   - title
   - meta_description
   - published_date (DD Mon YYYY)
   - reading_time (e.g., "8 min read")
   - category
   - featured_image (optional)

2) HTML content body including:
   - Table of contents (anchors)
   - Intro paragraph
   - 3–8 H2 sections with meaningful content
   - Per-section "Why this matters" callout and 2–3 Quick actions
   - Implementation checklist at the end
   - CTA callout with Schedule a call link

3) JSON-LD block for Article schema:
   - @context, @type, headline, description, author

Example short template for an article (AI should follow):

```html
<nav id="toc">...</nav>
<h1>{{ title }}</h1>
<p class="lead">Intro — why readers should keep reading.</p>
<h2>Section 1</h2>
<p>...analysis, examples...</p>
<div class="callout"><p class="callout-title">Why this matters</p><p>Short explanation</p><ul><li>Quick action 1</li><li>Quick action 2</li></ul></div>
...
<section class="implementation-checklist"><h3>Implementation checklist</h3><ul><li>Action 1</li>...</ul></section>
<div class="callout">Want us to run the audit? <a href="/schedule-a-call/">Book a call</a></div>
```

Prompt hints for AI
-------------------
- Ask for examples, numbers, and small experiments where possible.
- Prefer specific actionable steps (what to measure, how to set up the test, expected output).
- Avoid placeholder variables like `{{ post.title }}` inside extracted text; if using templates, ensure the metadata source is present.

Versioning
----------
Update this file when you add new CTAs, change page structure, or adjust recommended lengths.

