# Do not use this folder for site assets

Flask serves static files from **`app/static/`** (URLs like `/static/images/...`).

Nurture email images belong under:

- `app/static/images/cro_nurture/`
- `app/static/images/youtube_thumbnails/`

Files here are **not** exposed by the app unless copied into `app/static/`.
