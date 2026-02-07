Add your resource files here. Each resource is registered in app/routes/main.py (RESOURCE_DOWNLOADS).

Current:
- 57-point-cro-checklist.pdf (slug: cro-checklist)

To add a new resource:
1. Add the PDF/file to this folder.
2. In main.py, add an entry to RESOURCE_DOWNLOADS: "your-slug": {"filename": "your-file.pdf"}
3. On any page, add a button: data-download-modal data-resource="your-slug" data-title="Your Title" data-description="..." data-button-text="Send me the guide"
