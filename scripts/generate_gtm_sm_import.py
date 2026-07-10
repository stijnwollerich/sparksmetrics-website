#!/usr/bin/env python3
"""Generate GTM workspace overwrite JSON from the live container export shell."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path

ACCOUNT_ID = "6197865940"
CONTAINER_ID = "166824053"
FP = str(int(time.time() * 1000))
SOURCE_EXPORT = Path.home() / "Downloads" / "GTM-ML2ZDNH2_workspace51.json"

KEEP_TAGS = {
    "GA4 - Tracking ID",
    "Gads - Conversion Linker",
    "FB - Tracking ID",
    "GA4 - Scroll Depth",
    "GA4 - Social Media Link",
    "GA4 - Phone Number Click",
    "GA4 - Email Link Click",
    "GA4 - PDF Click",
    "GA4 - Blog Internal Link Click",
    "GA4 - Button Click",
    "Hotjar - Tracking ID",
    "Microsoft Clarity - Base Tag",
    "Sparksmetrics - Tracking Script",
    "Twitter - Tracking ID",
}

KEEP_TRIGGERS = {
    "Scroll Depth",
    "Social Media Link",
    "Phone Number Click",
    "Blog Internal Link Click",
    "PDF Link Click",
    "Email Link Click",
    "Button Click",
    "Main site (not app)",
}

KEEP_VARIABLES = {
    "Measurement ID",
    "FB - Pixel ID",
    "GA4 - Tracking ID",
    "lt - Content Group",
    "User Provided Data",
    "cjs - Last Click URL Path",
}

TID: dict[str, str] = {}
_id = 9000


def next_id() -> str:
    global _id
    _id += 1
    return str(_id)


def find_item(items: list[dict], name: str) -> dict:
    for item in items:
        if item.get("name") == name:
            return item
    raise KeyError(name)


def dlv(name: str, dl_key: str) -> dict:
    return {
        "accountId": ACCOUNT_ID,
        "containerId": CONTAINER_ID,
        "variableId": next_id(),
        "name": name,
        "type": "v",
        "parameter": [
            {"type": "INTEGER", "key": "dataLayerVersion", "value": "2"},
            {"type": "BOOLEAN", "key": "setDefaultValue", "value": "false"},
            {"type": "TEMPLATE", "key": "name", "value": dl_key},
        ],
        "fingerprint": FP,
        "formatValue": {},
    }


def trigger_condition(match_type: str, variable: str, value: str) -> dict:
    return {
        "type": match_type,
        "parameter": [
            {"type": "TEMPLATE", "key": "arg0", "value": variable},
            {"type": "TEMPLATE", "key": "arg1", "value": value},
        ],
    }


def clone_trigger(
    source: dict,
    template_name: str,
    *,
    name: str,
    event: str,
    conditions: list[dict] | None = None,
    regex_event: bool = False,
) -> dict:
    trigger = deepcopy(find_item(source["trigger"], template_name))
    trigger["triggerId"] = next_id()
    trigger["name"] = name
    trigger["fingerprint"] = FP
    trigger["customEventFilter"] = [
        {
            "type": "MATCH_REGEX" if regex_event else "EQUALS",
            "parameter": [
                {"type": "TEMPLATE", "key": "arg0", "value": "{{_event}}"},
                {"type": "TEMPLATE", "key": "arg1", "value": event},
            ],
        }
    ]
    if conditions:
        trigger["filter"] = conditions
    else:
        trigger.pop("filter", None)
    TID[name] = trigger["triggerId"]
    return trigger


def clone_tag(
    source: dict,
    template_name: str,
    *,
    name: str,
    trigger_name: str | list[str],
) -> dict:
    tag = deepcopy(find_item(source["tag"], template_name))
    tag["tagId"] = next_id()
    tag["name"] = name
    tag["fingerprint"] = FP
    trigger_names = trigger_name if isinstance(trigger_name, list) else [trigger_name]
    tag["firingTriggerId"] = [TID[t] for t in trigger_names]
    tag.pop("blockingTriggerId", None)
    tag.pop("paused", None)
    return tag


def set_tag_param(tag: dict, key: str, value: str) -> None:
    for param in tag["parameter"]:
        if param.get("key") == key:
            param["value"] = value
            return
    raise KeyError(key)


def set_ga4_event_name(tag: dict, event_name: str) -> None:
    set_tag_param(tag, "eventName", event_name)


def set_ga4_params(tag: dict, params: list[tuple[str, str]]) -> None:
    settings = [
        {
            "type": "MAP",
            "map": [
                {"type": "TEMPLATE", "key": "parameter", "value": p},
                {"type": "TEMPLATE", "key": "parameterValue", "value": v},
            ],
        }
        for p, v in params
    ]
    for param in tag["parameter"]:
        if param.get("key") == "eventSettingsTable":
            param["list"] = settings
            return
    tag["parameter"].insert(
        1,
        {"type": "LIST", "key": "eventSettingsTable", "list": settings},
    )


def set_gads_label(tag: dict, label: str) -> None:
    set_tag_param(tag, "conversionLabel", label)


def replace_in_obj(obj, old: str, new: str):
    if isinstance(obj, str):
        return obj.replace(old, new)
    if isinstance(obj, list):
        return [replace_in_obj(item, old, new) for item in obj]
    if isinstance(obj, dict):
        return {key: replace_in_obj(value, old, new) for key, value in obj.items()}
    return obj


def patch_legacy_variable_refs(tag: dict) -> dict:
    return replace_in_obj(tag, "dlv - form_answers.", "dlv - user_data.")


def build_new_variables() -> list[dict]:
    variables: list[dict] = []
    for key in [
        "fname",
        "email",
        "phone",
        "website_url",
        "business_stage",
        "orders_per_month",
        "conversion_rate",
        "average_order_value",
        "annual_revenue",
        "monthly_revenue_usd",
        "transactions_per_month",
        "qualify_score",
        "qualify_tier",
    ]:
        variables.append(dlv(f"dlv - user_data.{key}", f"user_data.{key}"))

    for name, key in [
        ("dlv - lead_type", "lead_type"),
        ("dlv - conversion_type", "conversion_type"),
        ("dlv - is_qualified", "is_qualified"),
        ("dlv - resource_slug", "resource_slug"),
        ("dlv - event_id", "event_id"),
        ("dlv - funnel_session_id", "funnel_session_id"),
        ("dlv - page_type", "page_type"),
        ("dlv - page_path", "page_path"),
        ("dlv - form_id", "form_id"),
        ("dlv - form_name", "form_name"),
        ("dlv - form_step", "form_step"),
        ("dlv - form_step_total", "form_step_total"),
        ("dlv - form_step_name", "form_step_name"),
        ("dlv - gads_conversion_label", "gads_conversion_label"),
        ("dlv - video_id", "video_id"),
        ("dlv - video_percent", "video_percent"),
        ("dlv - video_provider", "video_provider"),
        ("dlv - video_url", "video_url"),
        ("dlv - video_title", "video_title"),
        ("dlv - video_duration", "video_duration"),
        ("dlv - video_current_time", "video_current_time"),
        ("dlv - click_label", "click_label"),
        ("dlv - click_text", "click_text"),
        ("dlv - click_url", "click_url"),
        ("dlv - scroll_percent", "scroll_percent"),
        ("dlv - calendly_event", "calendly_event"),
        ("dlv - calendly_url", "calendly_url"),
        ("dlv - schedule_action", "schedule_action"),
        ("dlv - question", "question"),
        ("dlv - answer", "answer"),
        ("dlv - trigger_location", "trigger_location"),
    ]:
        variables.append(dlv(name, key))
    return variables


def build_new_triggers(source: dict) -> list[dict]:
    """One dataLayer event per action; GTM filters on conversion_type / gads_conversion_label."""
    base = "CE - CRO Lead Form Success"
    triggers = [
        clone_trigger(source, base, name="CE - form_success", event="form_success"),
        clone_trigger(source, base, name="CE - form_step", event="form_step"),
        clone_trigger(source, base, name="CE - form_start", event="form_start"),
        clone_trigger(source, base, name="CE - schedule_booked", event="schedule_booked"),
        clone_trigger(source, base, name="CE - schedule_open", event="schedule_open"),
        clone_trigger(
            source,
            base,
            name="CE - form_success - lead",
            event="form_success",
            conditions=[trigger_condition("EQUALS", "{{dlv - conversion_type}}", "lead")],
        ),
        clone_trigger(
            source,
            base,
            name="CE - form_success - qualified_lead",
            event="form_success",
            conditions=[
                trigger_condition("EQUALS", "{{dlv - is_qualified}}", "true")
            ],
        ),
        clone_trigger(
            source,
            base,
            name="CE - form_success - qualify_quiz",
            event="form_success",
            conditions=[
                trigger_condition("EQUALS", "{{dlv - conversion_type}}", "qualify_quiz")
            ],
        ),
        clone_trigger(
            source,
            base,
            name="CE - schedule_booked - schedule",
            event="schedule_booked",
            conditions=[trigger_condition("EQUALS", "{{dlv - conversion_type}}", "schedule")],
        ),
        clone_trigger(
            source,
            base,
            name="CE - conversion - Gads",
            event="form_success",
            conditions=[
                trigger_condition("MATCH_REGEX", "{{dlv - gads_conversion_label}}", ".+")
            ],
        ),
        clone_trigger(
            source,
            base,
            name="CE - schedule_booked - Gads",
            event="schedule_booked",
            conditions=[
                trigger_condition("MATCH_REGEX", "{{dlv - gads_conversion_label}}", ".+")
            ],
        ),
        clone_trigger(
            source,
            "Video Engagement",
            name="CE - engagement",
            event="video_|^scroll$|^click$",
            regex_event=True,
        ),
    ]
    return triggers


def build_new_tags(source: dict) -> list[dict]:
    common_form_params = [
        ("form_id", "{{dlv - form_id}}"),
        ("form_name", "{{dlv - form_name}}"),
        ("lead_type", "{{dlv - lead_type}}"),
        ("conversion_type", "{{dlv - conversion_type}}"),
        ("is_qualified", "{{dlv - is_qualified}}"),
        ("resource_slug", "{{dlv - resource_slug}}"),
        ("page_type", "{{dlv - page_type}}"),
        ("funnel_session_id", "{{dlv - funnel_session_id}}"),
        ("event_id", "{{dlv - event_id}}"),
    ]

    ga4_success = clone_tag(
        source,
        "GA4 - CRO Lead Form Success",
        name="GA4 - Form Success",
        trigger_name="CE - form_success",
    )
    set_ga4_event_name(ga4_success, "generate_lead")
    set_ga4_params(ga4_success, common_form_params)

    ga4_step = clone_tag(
        source,
        "GA4 - CRO Lead Form Success",
        name="GA4 - Form Step",
        trigger_name="CE - form_step",
    )
    set_ga4_event_name(ga4_step, "form_step")
    set_ga4_params(
        ga4_step,
        common_form_params
        + [
            ("form_step", "{{dlv - form_step}}"),
            ("form_step_total", "{{dlv - form_step_total}}"),
            ("form_step_name", "{{dlv - form_step_name}}"),
            ("question", "{{dlv - question}}"),
            ("answer", "{{dlv - answer}}"),
        ],
    )

    ga4_schedule = clone_tag(
        source,
        "GA4 - CRO Lead Form Success",
        name="GA4 - Schedule Booked",
        trigger_name="CE - schedule_booked",
    )
    set_ga4_event_name(ga4_schedule, "schedule")
    set_ga4_params(
        ga4_schedule,
        [
            ("form_id", "{{dlv - form_id}}"),
            ("form_name", "{{dlv - form_name}}"),
            ("lead_type", "{{dlv - lead_type}}"),
            ("conversion_type", "{{dlv - conversion_type}}"),
            ("calendly_event", "{{dlv - calendly_event}}"),
            ("event_id", "{{dlv - event_id}}"),
        ],
    )

    ga4_schedule_step = clone_tag(
        source,
        "GA4 - CRO Lead Form Success",
        name="GA4 - Schedule Step",
        trigger_name="CE - schedule_open",
    )
    set_ga4_event_name(ga4_schedule_step, "schedule_step")
    set_ga4_params(
        ga4_schedule_step,
        [
            ("form_id", "{{dlv - form_id}}"),
            ("form_name", "{{dlv - form_name}}"),
            ("lead_type", "{{dlv - lead_type}}"),
            ("schedule_action", "{{dlv - schedule_action}}"),
            ("calendly_event", "{{dlv - calendly_event}}"),
            ("calendly_url", "{{dlv - calendly_url}}"),
            ("page_type", "{{dlv - page_type}}"),
            ("funnel_session_id", "{{dlv - funnel_session_id}}"),
        ],
    )

    ga4_engagement = clone_tag(
        source,
        "GA4 - Video Engagement",
        name="GA4 - Engagement",
        trigger_name="CE - engagement",
    )
    set_ga4_params(
        ga4_engagement,
        [
            ("video_id", "{{dlv - video_id}}"),
            ("video_percent", "{{dlv - video_percent}}"),
            ("video_provider", "{{dlv - video_provider}}"),
            ("video_url", "{{dlv - video_url}}"),
            ("video_title", "{{dlv - video_title}}"),
            ("video_duration", "{{dlv - video_duration}}"),
            ("video_current_time", "{{dlv - video_current_time}}"),
            ("click_label", "{{dlv - click_label}}"),
            ("click_text", "{{dlv - click_text}}"),
            ("click_url", "{{dlv - click_url}}"),
            ("scroll_percent", "{{dlv - scroll_percent}}"),
            ("page_type", "{{dlv - page_type}}"),
        ],
    )

    fb_lead = clone_tag(
        source,
        "FB - Lead - Lead Form Success",
        name="FB - Lead",
        trigger_name="CE - form_success - lead",
    )

    fb_quiz = clone_tag(
        source,
        "FB - CRO Qualify Quiz Complete - SubmitApplication",
        name="FB - Qualify Quiz Complete",
        trigger_name="CE - form_success - qualify_quiz",
    )

    fb_qualified = clone_tag(
        source,
        "FB - Custom - Qualified Lead- Free CRO Audit",
        name="FB - Qualified Lead",
        trigger_name="CE - form_success - qualified_lead",
    )
    fb_qualified = patch_legacy_variable_refs(fb_qualified)

    fb_schedule = clone_tag(
        source,
        "FB - Schedule - Calendly Event Schedule",
        name="FB - Schedule",
        trigger_name="CE - schedule_booked - schedule",
    )

    gads_conversion = clone_tag(
        source,
        "Gads - CRO Ebook Submit",
        name="Gads - Conversion",
        trigger_name=["CE - conversion - Gads", "CE - schedule_booked - Gads"],
    )
    set_gads_label(gads_conversion, "{{dlv - gads_conversion_label}}")

    return [
        ga4_success,
        ga4_step,
        ga4_schedule,
        ga4_schedule_step,
        ga4_engagement,
        fb_lead,
        fb_quiz,
        fb_qualified,
        fb_schedule,
        gads_conversion,
    ]


def patch_button_click_trigger(trigger: dict) -> dict:
    trigger["filter"] = [
        {
            "type": "MATCH_REGEX",
            "parameter": [
                {"type": "TEMPLATE", "key": "arg0", "value": "{{Click Classes}}"},
                {"type": "TEMPLATE", "key": "arg1", "value": "(btn|button)"},
            ],
        }
    ]
    trigger["fingerprint"] = FP
    return trigger


def load_source() -> dict:
    if not SOURCE_EXPORT.exists():
        raise FileNotFoundError(
            f"Missing source export: {SOURCE_EXPORT}\n"
            "Export the current GTM workspace and save it to Downloads first."
        )
    return json.loads(SOURCE_EXPORT.read_text())


def build() -> dict:
    source_export = load_source()
    source = source_export["containerVersion"]

    kept_tags = [deepcopy(t) for t in source["tag"] if t["name"] in KEEP_TAGS]
    for tag in kept_tags:
        tag.pop("paused", None)

    kept_triggers = []
    for trigger in source["trigger"]:
        if trigger["name"] not in KEEP_TRIGGERS:
            continue
        item = deepcopy(trigger)
        if item["name"] == "Button Click":
            item = patch_button_click_trigger(item)
        kept_triggers.append(item)

    kept_variables = [deepcopy(v) for v in source["variable"] if v["name"] in KEEP_VARIABLES]

    new_triggers = build_new_triggers(source)
    new_tags = build_new_tags(source)

    out = deepcopy(source_export)
    cv = out["containerVersion"]
    cv["tag"] = kept_tags + new_tags
    cv["trigger"] = kept_triggers + new_triggers
    cv["variable"] = kept_variables + build_new_variables()
    out["exportTime"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return out


def main() -> None:
    out = build()
    cv = out["containerVersion"]
    repo = Path(__file__).resolve().parents[1]
    paths = [
        repo / "docs" / "gtm-import-sm-analytics.json",
        Path.home() / "Downloads" / "gtm-import-sm-analytics-GTM-ML2ZDNH2-OVERWRITE.json",
    ]
    for path in paths:
        path.write_text(json.dumps(out, indent=4), encoding="utf-8")
        print(f"Wrote {path}")
    print(
        f"Overwrite container: {len(cv['tag'])} tags, "
        f"{len(cv['trigger'])} triggers, {len(cv['variable'])} variables, "
        f"{len(cv.get('builtInVariable', []))} built-ins, "
        f"{len(cv.get('customTemplate', []))} templates"
    )


if __name__ == "__main__":
    main()
