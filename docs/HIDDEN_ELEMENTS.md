# Temporarily hidden elements

Control visibility by editing `temporarily_hidden` in `app/templates/base.html`. Child templates (e.g. `landing_alt.html`) use this list to show/hide sections.

## Keys and where they live

| Key                 | Location      | Description |
|---------------------|---------------|-------------|
| `primary_bar`       | base.html     | Top orange bar: "Only accepting 2 more partners for Q3…" |
| `audit_bar`         | base.html     | Bottom audit bar: "Get a FREE 24-HOUR CRO AUDIT" |
| `homepage_video`    | landing_alt.html | Homepage hero video: "Watch: How we find and fix conversion leaks" |
| `video_testimonials`| landing_alt.html | Video testimonials (3 cards) + YouTube gallery section |
| `cro_checklist`     | landing_alt.html | "The 57-Point CRO Checklist" section |
| `results_section`  | landing_alt.html | "The Results of Relentless Optimization" section + video cards |
| `cro_video_testimonials` | cro.html | CRO page: "The Results of Relentless Optimization" video testimonial cards (3 cards) |
| `analytics_video_testimonials` | analytics.html | Analytics page: "The Results of Accurate Tracking" video testimonial cards (3 cards) |

**Currently hidden:** `homepage_video`, `video_testimonials`, `cro_checklist`, `results_section`, `cro_video_testimonials`, `analytics_video_testimonials`  
**Currently visible:** `primary_bar`, `audit_bar`

## How to change visibility

In `app/templates/base.html`, find:

```jinja2
{% set temporarily_hidden = ['homepage_video', 'video_testimonials', 'cro_checklist'] %}
```

- To **show everything**: set to empty: `{% set temporarily_hidden = [] %}`
- To **hide primary or audit bar again**: add `'primary_bar'` and/or `'audit_bar'` to the list.
- To **show video, checklist, results section, or CRO video testimonials again**: remove the corresponding key from the list (e.g. `'cro_video_testimonials'` for the CRO page video cards).
