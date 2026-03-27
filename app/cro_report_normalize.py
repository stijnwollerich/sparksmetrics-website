"""Normalize CRO report dict for HTML template rendering (no scan pipeline; Sparksmetrics-only)."""


def _empty_page_dict() -> dict:
    """Return a minimal page dict so the report always has something to render for each page."""
    anatomy_keys = (
        "promise",
        "offer",
        "pain_point",
        "solution",
        "social_proof",
        "trust_signals",
        "cta",
        "visual_hierarchy",
    )
    return {
        "score": None,
        "motivation": "",
        "friction": [],
        "clarity": "",
        "page_anatomy": {k: "" for k in anatomy_keys},
        "page_summary": "",
        "ui_ux_notes": [],
        "testing_ideas": [],
        "above_the_fold": "",
        "below_the_fold": "",
    }


def _normalize_report(report: dict) -> dict:
    """Ensure required keys exist and types are correct."""
    if "pages" not in report:
        report["pages"] = {}
    for key in ("homepage", "collection", "product"):
        if key not in report["pages"] or report["pages"][key] is None:
            report["pages"][key] = _empty_page_dict()
        elif not isinstance(report["pages"][key], dict):
            report["pages"][key] = _empty_page_dict()
    anatomy_keys = (
        "promise",
        "offer",
        "pain_point",
        "solution",
        "social_proof",
        "trust_signals",
        "cta",
        "visual_hierarchy",
    )
    for key in ("homepage", "collection", "product"):
        page = report["pages"].get(key)
        if isinstance(page, dict):
            for list_key in ("testing_ideas", "friction", "ui_ux_notes"):
                if list_key not in page or not isinstance(page[list_key], list):
                    page[list_key] = page.get(list_key) if isinstance(page.get(list_key), list) else []
            if key == "product":
                if "above_the_fold" not in page:
                    page["above_the_fold"] = page.get("above_the_fold") or ""
                if "below_the_fold" not in page:
                    page["below_the_fold"] = page.get("below_the_fold") or ""
            if "page_anatomy" not in page or not isinstance(page.get("page_anatomy"), dict):
                page["page_anatomy"] = page.get("page_anatomy") if isinstance(page.get("page_anatomy"), dict) else {}
            for anat_key in anatomy_keys:
                if anat_key not in page["page_anatomy"]:
                    page["page_anatomy"][anat_key] = ""
            if "page_summary" not in page:
                page["page_summary"] = page.get("page_summary") or ""
    if "overall_score" not in report:
        report["overall_score"] = 0
    if "store_name" not in report:
        report["store_name"] = "Store"
    if "score_components" not in report or not isinstance(report.get("score_components"), str):
        report["score_components"] = (
            (report.get("score_components") or "Score reflects: Clarity, Motivation, Trust, Friction, Mobile usability.")
            if isinstance(report.get("score_components"), str)
            else "Score reflects: Clarity, Motivation, Trust, Friction, Mobile usability."
        )
    if "biggest_conversion_leaks" not in report or not isinstance(report.get("biggest_conversion_leaks"), list):
        report["biggest_conversion_leaks"] = (
            report.get("biggest_conversion_leaks") if isinstance(report.get("biggest_conversion_leaks"), list) else []
        )
    for i, leak in enumerate(report["biggest_conversion_leaks"]):
        if not isinstance(leak, dict):
            report["biggest_conversion_leaks"][i] = {"title": "", "explanation": ""}
        else:
            if "title" not in leak:
                leak["title"] = ""
            if "explanation" not in leak:
                leak["explanation"] = ""
    if "executive_summary" not in report or not isinstance(report.get("executive_summary"), dict):
        report["executive_summary"] = (
            report.get("executive_summary") if isinstance(report.get("executive_summary"), dict) else {}
        )
    for k in ("what_is_working", "what_is_hurting", "biggest_opportunity"):
        if k not in report["executive_summary"]:
            report["executive_summary"][k] = ""
    if "customer_research" not in report or not isinstance(report.get("customer_research"), dict):
        report["customer_research"] = (
            report.get("customer_research") if isinstance(report.get("customer_research"), dict) else {}
        )
    for k in ("target_audience_hypothesis", "customer_motivations", "customer_fears_frustrations", "desired_outcomes"):
        if k not in report["customer_research"]:
            report["customer_research"][k] = ""
    if "ugly_truth" not in report:
        report["ugly_truth"] = ""
    if "biggest_opportunity" not in report or not isinstance(report["biggest_opportunity"], dict):
        report["biggest_opportunity"] = (
            report.get("biggest_opportunity") if isinstance(report.get("biggest_opportunity"), dict) else {}
        )
    for k in ("title", "explanation", "why_it_matters", "example_tests"):
        if k not in report["biggest_opportunity"]:
            report["biggest_opportunity"][k] = "" if k != "example_tests" else []
    if not isinstance(report["biggest_opportunity"].get("example_tests"), list):
        report["biggest_opportunity"]["example_tests"] = report["biggest_opportunity"].get("example_tests") or []
    if "fast_wins" not in report or not isinstance(report["fast_wins"], list):
        report["fast_wins"] = report.get("fast_wins") if isinstance(report.get("fast_wins"), list) else []
    if "roadmap_90_days" not in report or not isinstance(report["roadmap_90_days"], dict):
        report["roadmap_90_days"] = report.get("roadmap_90_days") if isinstance(report.get("roadmap_90_days"), dict) else {}
    for m in ("month1", "month2", "month3"):
        if report["roadmap_90_days"].get(m) is None or not isinstance(report["roadmap_90_days"].get(m), list):
            report["roadmap_90_days"][m] = (
                report["roadmap_90_days"].get(m) if isinstance(report["roadmap_90_days"].get(m), list) else []
            )
    backlog = report.get("experiment_backlog") or report.get("potential_tests_backlog")
    if not isinstance(backlog, list):
        backlog = []
    report["experiment_backlog"] = backlog
    if "what_good_looks_like" not in report:
        report["what_good_looks_like"] = ""
    if "next_steps" not in report:
        report["next_steps"] = ""
    if "report_date" not in report:
        from datetime import datetime

        report["report_date"] = datetime.utcnow().strftime("%B %d, %Y")
    return report
