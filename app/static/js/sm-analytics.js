(function (global) {
  "use strict";

  var SESSION_KEY = "sm_funnel_session_id";
  var FORM_START_SENT = "data-sm-form-start";

  var RESOURCE_LABELS = {
    "13-bulletproof-strategies": "CRO Ebook — 13 Bulletproof Strategies",
    "7-questions-cro-agency": "CRO Ebook — 7 Questions for a CRO Agency",
    "vsl-free-cro-video": "Free CRO Video (VSL Gate)",
  };

  var USER_DATA_KEYS = [
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
  ];

  function emptyUserData() {
    var data = {};
    USER_DATA_KEYS.forEach(function (key) {
      data[key] = null;
    });
    return data;
  }

  function mergeUserData(partial) {
    var base = emptyUserData();
    if (!partial) return base;
    USER_DATA_KEYS.forEach(function (key) {
      if (partial[key] !== undefined && partial[key] !== null && partial[key] !== "") {
        base[key] = partial[key];
      }
    });
    return base;
  }

  function uuid() {
    return "evt_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
  }

  function getFunnelSessionId() {
    try {
      var id = sessionStorage.getItem(SESSION_KEY);
      if (!id) {
        id =
          "fs_" +
          Date.now().toString(36) +
          "_" +
          Math.random().toString(36).slice(2, 10);
        sessionStorage.setItem(SESSION_KEY, id);
      }
      return id;
    } catch (err) {
      return "fs_anon";
    }
  }

  function inferPageType() {
    if (global.smPageType) return String(global.smPageType);
    var path = (global.location && global.location.pathname) || "";
    if (path.indexOf("/do-i-qualify") >= 0) return "qualify_quiz";
    if (path.indexOf("/30-minute-strategy-session") >= 0) return "strategy_session";
    if (path.indexOf("/cro-scan") >= 0) return "cro_scan";
    if (path.indexOf("/cro-cost-roi") >= 0 || path.indexOf("/cost-roi") >= 0)
      return "cro_cost_roi";
    if (path.indexOf("/free-cro-audit") >= 0) return "free_cro_audit";
    if (path.indexOf("/thank-you") >= 0) return "thank_you";
    if (path.indexOf("/schedule-a-call") >= 0) return "schedule_a_call";
    if (path.indexOf("/cro-ebook") >= 0) return "cro_ebook";
    return path.replace(/^\/|\/$/g, "").replace(/\//g, "_") || "home";
  }

  function isAuditQualified(userData) {
    var orders =
      userData && userData.orders_per_month
        ? String(userData.orders_per_month)
        : "";
    if (!orders) return false;
    return orders.indexOf("~100/month") < 0;
  }

  function isCcrQualified(userData) {
    var tpm = userData && userData.transactions_per_month;
    if (tpm === null || tpm === undefined || tpm === "") return false;
    var n = parseInt(String(tpm).replace(/[^0-9]/g, ""), 10);
    return !isNaN(n) && n >= 500;
  }

  function resolveLeadType(modalOrLeadType, resourceSlug, userData) {
    var t = modalOrLeadType || "resource";
    if (t === "audit") {
      return isAuditQualified(userData) ? "audit_qualified" : "audit";
    }
    if (t === "cro_scan") return "cro_scan";
    if (t === "cro_cost_roi") {
      return isCcrQualified(userData) ? "cro_cost_roi_qualified" : "cro_cost_roi";
    }
    if (t === "qualify_quiz") return "qualify_quiz";
    if (t === "strategy_session") return "strategy_session";
    if (resourceSlug === "vsl-free-cro-video") return "vsl";
    if (t === "resource" || t === "ebook") return "ebook";
    return t;
  }

  function resolveFormName(formId, leadType, resourceSlug, explicitName) {
    if (explicitName) return explicitName;
    if (formId === "qualify-quiz") return "CRO Qualify Quiz";
    if (formId === "mss-funnel") return "30 Minute Strategy Session";
    if (formId === "cro-scan-form") return "CRO Scan";
    if (formId === "cro-scan-email-form") return "CRO Scan — Email Follow-up";
    if (formId === "ccr-lead-form") return "CRO Cost / ROI Calculator";
    if (formId === "schedule-modal") return "Schedule a Call (Header Modal)";
    if (formId === "calendly-inline") return "Calendly Inline";
    if (leadType === "audit" || leadType === "audit_qualified") return "Free CRO Audit";
    if (resourceSlug && RESOURCE_LABELS[resourceSlug]) return RESOURCE_LABELS[resourceSlug];
    if (leadType === "vsl") return "Free CRO Video (VSL Gate)";
    if (leadType === "ebook") return "Resource Download";
    return formId || "Form";
  }

  function normalizeCroScanFormId(formId) {
    if (!formId) return "cro-scan-form";
    if (formId.indexOf("cro-scan-form") === 0) return "cro-scan-form";
    return formId;
  }

  function isQualifiedLeadType(leadType) {
    return (
      leadType === "audit_qualified" || leadType === "cro_cost_roi_qualified"
    );
  }

  function conversionType(leadType) {
    if (!leadType) return null;
    if (leadType === "qualify_quiz") return "qualify_quiz";
    // Every lead form (including qualified) is a Lead. Qualified is an extra flag.
    if (
      leadType === "ebook" ||
      leadType === "vsl" ||
      leadType === "audit" ||
      leadType === "audit_qualified" ||
      leadType === "cro_scan" ||
      leadType === "cro_cost_roi" ||
      leadType === "cro_cost_roi_qualified" ||
      leadType === "strategy_session"
    ) {
      return "lead";
    }
    return "lead";
  }

  var GADS_LABEL_BY_LEAD_TYPE = {
    ebook: "4yqYCKvn0ocaEJHd0OQ9",
    vsl: "4yqYCKvn0ocaEJHd0OQ9",
    cro_scan: "ecdbCNLgroIcEJHd0OQ9",
  };

  var GADS_SCHEDULE_LABEL = "KO_0CPODpskZEJHd0OQ9";

  function resolveGadsLabel(leadType, eventName) {
    if (eventName === "schedule_booked") return GADS_SCHEDULE_LABEL;
    return GADS_LABEL_BY_LEAD_TYPE[leadType] || null;
  }

  function buildPayload(eventName, data) {
    data = data || {};
    var userData = mergeUserData(data.user_data);
    var formId = data.form_id || null;
    if (formId && formId.indexOf("cro-scan-form") === 0) {
      formId = normalizeCroScanFormId(formId);
    }
    var resourceSlug = data.resource_slug || data.resource || null;
    var leadType =
      data.lead_type ||
      resolveLeadType(data.modal_type || data.lead_type_hint, resourceSlug, userData);

    var payload = {
      event: eventName,
      form_id: formId,
      form_name: resolveFormName(formId, leadType, resourceSlug, data.form_name),
      lead_type: leadType,
      conversion_type: leadType ? conversionType(leadType) : null,
      is_qualified: "false",
      gads_conversion_label: null,
      resource_slug: resourceSlug,
      form_step: data.form_step != null ? data.form_step : null,
      form_step_total: data.form_step_total != null ? data.form_step_total : null,
      form_step_name: data.form_step_name || null,
      user_data: userData,
      page_type: data.page_type || inferPageType(),
      page_path: (global.location && global.location.pathname) || "",
      page_location: (global.location && global.location.href) || "",
      funnel_session_id: data.funnel_session_id || getFunnelSessionId(),
      event_id: data.event_id || null,
      video_id: data.video_id || null,
      video_provider: data.video_provider || null,
      video_url: data.video_url || null,
      video_title: data.video_title || null,
      video_duration: data.video_duration != null ? data.video_duration : null,
      video_current_time:
        data.video_current_time != null ? data.video_current_time : null,
      video_percent: data.video_percent != null ? data.video_percent : null,
      scroll_percent: data.scroll_percent != null ? data.scroll_percent : null,
      click_label: data.click_label || null,
      click_text: data.click_text || null,
      click_url: data.click_url || null,
      schedule_action: data.schedule_action || null,
      calendly_event: data.calendly_event || null,
      calendly_url: data.calendly_url || null,
      trigger_text: data.trigger_text || null,
      trigger_location: data.trigger_location || null,
      question_id: data.question_id || null,
      question: data.question || null,
      answer: data.answer != null ? String(data.answer) : null,
      answer_label: data.answer_label || null,
      timestamp: new Date().toISOString(),
    };

    if (eventName === "schedule_booked") {
      payload.conversion_type = "schedule";
    }

    if (eventName === "form_success" || eventName === "schedule_booked") {
      if (!payload.event_id) payload.event_id = uuid();
      payload.is_qualified =
        eventName === "form_success" && isQualifiedLeadType(leadType)
          ? "true"
          : "false";
      payload.gads_conversion_label = resolveGadsLabel(leadType, eventName);
    }

    return payload;
  }

  function pushPayload(payload) {
    try {
      global.dataLayer = global.dataLayer || [];
      global.dataLayer.push(payload);
    } catch (err) {}
  }

  function push(eventName, data) {
    pushPayload(buildPayload(eventName, data));
  }

  function formStart(data) {
    push("form_start", data);
  }

  function formSubmit(data) {
    push("form_submit", data);
  }

  function formSuccess(data) {
    pushPayload(buildPayload("form_success", data));
  }

  function formError(data) {
    push("form_error", data);
  }

  function formStep(data) {
    push("form_step", data);
  }

  function scheduleOpen(data) {
    var d = data || {};
    if (!d.schedule_action) d.schedule_action = "open";
    push("schedule_open", d);
  }

  function scheduleBooked(data) {
    var d = data || {};
    d.schedule_action = "booked";
    pushPayload(buildPayload("schedule_booked", d));
  }

  function videoEvent(action, data) {
    var d = data || {};
    push(action, d);
  }

  function click(data) {
    push("click", data);
  }

  function scroll(data) {
    push("scroll", data);
  }

  function initFormStart() {
    document.addEventListener(
      "focusin",
      function (e) {
        try {
          var form = e.target && e.target.closest && e.target.closest("form");
          if (!form || form.getAttribute(FORM_START_SENT) === "1") return;
          if (form.id === "lead-form" && window.LeadModal) return;
          form.setAttribute(FORM_START_SENT, "1");
          var ud = collectUserDataFromForm(form);
          formStart({
            form_id: form.id || null,
            form_name: form.getAttribute("data-form-name") || null,
            user_data: ud,
          });
        } catch (err) {}
      },
      true,
    );
  }

  function collectUserDataFromForm(form) {
    var ud = emptyUserData();
    if (!form) return ud;
    var els = form.elements || [];
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (!el.name || !el.value) continue;
      var v = String(el.value).trim();
      if (!v) continue;
      if (el.name === "fname" || el.name === "first_name") ud.fname = v;
      if (el.type === "email" || el.name === "email") ud.email = v;
      if (el.name === "website_url" || el.name === "url" || el.name === "store_url")
        ud.website_url = v;
      if (el.name === "business_stage") ud.business_stage = v;
      if (el.name === "orders_per_month") ud.orders_per_month = v;
      if (el.name === "conversion_rate") ud.conversion_rate = v;
      if (el.name === "average_order_value") ud.average_order_value = v;
      if (el.name === "annual_revenue") ud.annual_revenue = v;
      if (el.name === "monthly_revenue_usd") ud.monthly_revenue_usd = v;
      if (el.name === "transactions_per_month") ud.transactions_per_month = v;
    }
    return ud;
  }

  function initDataTrackClicks() {
    document.addEventListener("click", function (e) {
      try {
        var el = e.target.closest("[data-track]");
        if (!el) return;
        click({
          click_label: el.getAttribute("data-track") || null,
          click_text: (el.textContent || "").trim().slice(0, 120),
          click_url: el.getAttribute("href") || null,
        });
      } catch (err) {}
    });
  }

  function initScrollDepth() {
    var sent = {};
    var thresholds = [25, 50, 75, 90];
    function check() {
      var doc = document.documentElement;
      var scrollTop = global.pageYOffset || doc.scrollTop || 0;
      var height = Math.max(doc.scrollHeight - global.innerHeight, 1);
      var pct = Math.min(100, Math.round((scrollTop / height) * 100));
      for (var i = 0; i < thresholds.length; i++) {
        var t = thresholds[i];
        if (pct >= t && !sent[t]) {
          sent[t] = true;
          scroll({ scroll_percent: t });
        }
      }
    }
    global.addEventListener("scroll", check, { passive: true });
    check();
  }

  function mapCalendlyToSchedule(eventName) {
    if (!eventName) return null;
    var e = String(eventName).toLowerCase();
    if (e === "event_scheduled" || e === "invitee_meeting_scheduled") {
      return "booked";
    }
    if (e === "event_type_viewed" || e === "profile_page_viewed") return "open";
    if (e.indexOf("date") >= 0 && e.indexOf("select") >= 0) return "date_selected";
    return "open";
  }

  function initCalendlyListener() {
    function isCalendlyOrigin(origin) {
      if (!origin) return false;
      return (
        origin.indexOf("calendly.com") !== -1 ||
        origin.indexOf("assets.calendly.com") !== -1
      );
    }
    global.addEventListener(
      "message",
      function (e) {
        try {
          if (!isCalendlyOrigin(e.origin)) return;
          if (!e.data) return;
          var payload = e.data;
          if (typeof payload === "string") {
            if (payload.indexOf("calendly") !== 0) return;
          } else if (payload && payload.event) {
            payload = payload.event;
          } else {
            return;
          }
          if (typeof payload !== "string" || payload.indexOf("calendly") !== 0) return;
          var parts = payload.split(".");
          var calEvent = parts.length > 1 ? parts.slice(1).join(".") : payload;
          var scheduleAction = mapCalendlyToSchedule(calEvent);
          if (scheduleAction === "booked") {
            scheduleBooked({
              form_id: global.smScheduleFormId || null,
              form_name: global.smScheduleFormName || null,
              lead_type: global.smScheduleLeadType || null,
              calendly_event: calEvent,
              calendly_url: global.smScheduleCalendlyUrl || null,
            });
          } else {
            scheduleOpen({
              form_id: global.smScheduleFormId || "calendly-inline",
              form_name: global.smScheduleFormName || "Calendly",
              schedule_action: scheduleAction,
              calendly_event: calEvent,
              calendly_url: global.smScheduleCalendlyUrl || null,
            });
          }
        } catch (err) {}
      },
      false,
    );
  }

  function init() {
    initCalendlyListener();
    initFormStart();
    initDataTrackClicks();
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initScrollDepth);
    } else {
      initScrollDepth();
    }
  }

  var api = {
    push: push,
    buildPayload: buildPayload,
    emptyUserData: emptyUserData,
    mergeUserData: mergeUserData,
    getFunnelSessionId: getFunnelSessionId,
    resolveLeadType: resolveLeadType,
    resolveFormName: resolveFormName,
    collectUserDataFromForm: collectUserDataFromForm,
    formStart: formStart,
    formSubmit: formSubmit,
    formSuccess: formSuccess,
    formError: formError,
    formStep: formStep,
    scheduleOpen: scheduleOpen,
    scheduleBooked: scheduleBooked,
    videoEvent: videoEvent,
    click: click,
    scroll: scroll,
    init: init,
    USER_DATA_KEYS: USER_DATA_KEYS,
    RESOURCE_LABELS: RESOURCE_LABELS,
  };

  global.SmAnalytics = api;
  init();
})(window);
