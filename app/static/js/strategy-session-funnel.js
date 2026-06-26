(function () {
  var funnel = document.getElementById("mss-funnel");
  if (!funnel) return;

  var CALENDLY_URL =
    "https://calendly.com/stijn-wollerich/conversion-rate-optimization?hide_gdpr_banner=1";
  var TOTAL = 6;
  var EMBED = funnel.getAttribute("data-embed") === "1";
  var START_STEP = parseInt(funnel.getAttribute("data-start-step") || "1", 10) || 1;
  var DISABLE_EXIT = funnel.getAttribute("data-disable-exit") === "1";
  var FORM_NAME =
    funnel.getAttribute("data-form-name") || "30 Minute Strategy Session";
  var PAGE_TYPE = EMBED ? "strategy_session_embed" : "strategy_session_funnel";
  var CALENDLY_HEIGHT_EMBED = 640;

  var current = START_STEP;
  var annualRevenue = "";
  var calendlyMounted = false;
  var lastSyncedStep = {};

  var progressRoot = funnel.querySelector("#mss-progress");
  var progressLabel = funnel.querySelector("#mss-progress-label");
  var geoLine = funnel.querySelector("#mss-geo-line");
  var submitBtn = funnel.querySelector("#mss-submit");
  var calendlyInline = funnel.querySelector("#mss-calendly-inline");
  var exitModal = document.getElementById("mss-exit-modal");
  var exitProgressFill = document.getElementById("mss-exit-progress-fill");
  var exitStorageKey = "mss_exit_popup_shown";
  var pageReadyAt = Date.now();
  var exitEnabled = !DISABLE_EXIT;

  var COUNTRY_META = {
    US: { name: "the United States", flag: "🇺🇸" },
    GB: { name: "the United Kingdom", flag: "🇬🇧" },
    UK: { name: "the United Kingdom", flag: "🇬🇧" },
    NL: { name: "the Netherlands", flag: "🇳🇱" },
    AU: { name: "Australia", flag: "🇦🇺" },
    CA: { name: "Canada", flag: "🇨🇦" },
    DE: { name: "Germany", flag: "🇩🇪" },
    FR: { name: "France", flag: "🇫🇷" },
    BE: { name: "Belgium", flag: "🇧🇪" },
    IE: { name: "Ireland", flag: "🇮🇪" },
    SE: { name: "Sweden", flag: "🇸🇪" },
    DK: { name: "Denmark", flag: "🇩🇰" },
    NO: { name: "Norway", flag: "🇳🇴" },
    ES: { name: "Spain", flag: "🇪🇸" },
    IT: { name: "Italy", flag: "🇮🇹" },
    AT: { name: "Austria", flag: "🇦🇹" },
    CH: { name: "Switzerland", flag: "🇨🇭" },
    NZ: { name: "New Zealand", flag: "🇳🇿" },
    SG: { name: "Singapore", flag: "🇸🇬" },
  };

  function buildProgressDots() {
    if (!progressRoot) return;
    progressRoot.innerHTML = "";
    for (var i = 1; i <= TOTAL; i++) {
      if (i > 1) {
        var line = document.createElement("div");
        line.className = "mss-progress-line";
        progressRoot.appendChild(line);
      }
      var dot = document.createElement("div");
      dot.className = "mss-progress-dot";
      dot.setAttribute("data-progress-dot", String(i));
      progressRoot.appendChild(dot);
    }
  }

  function setGeoLine(code) {
    if (!geoLine) return;
    var c = (code || "").toUpperCase();
    var meta = COUNTRY_META[c];
    if (meta) {
      geoLine.textContent =
        "Working with ecommerce brands in " + meta.name + " " + meta.flag;
    } else if (c) {
      geoLine.textContent =
        "Working with ecommerce brands in your region \uD83C\uDF0D";
    }
  }

  function resolveVisitorCountry() {
    if (funnel.getAttribute("data-geo-lookup-needed") !== "1") return;
    fetch("https://ipapi.co/country_code/", { credentials: "omit" })
      .then(function (r) {
        return r.text();
      })
      .then(function (code) {
        if (code && code.trim().length === 2) setGeoLine(code.trim());
      })
      .catch(function () {
        var lang = (navigator.language || "").split("-")[1];
        if (lang && lang.length === 2) setGeoLine(lang);
      });
  }

  function getFormAnswersSnapshot() {
    var fnameEl = funnel.querySelector("#mss-fname");
    var emailEl = funnel.querySelector("#mss-email");
    var websiteEl = funnel.querySelector("#mss-website");
    return {
      annual_revenue: annualRevenue || "",
      fname: fnameEl && fnameEl.value.trim() ? fnameEl.value.trim() : "",
      email: emailEl && emailEl.value.trim() ? emailEl.value.trim() : "",
      website_url:
        websiteEl && websiteEl.value.trim() ? websiteEl.value.trim() : "",
    };
  }

  var STEP_META = {
    1: {
      key: "intro",
      question: "Free 30-minute CRO strategy session",
      field_name: null,
    },
    2: {
      key: "annual_revenue",
      question: "What's your store's annual revenue?",
      field_name: "annual_revenue",
    },
    3: {
      key: "fname",
      question: "What's your first name?",
      field_name: "fname",
    },
    4: {
      key: "email",
      question: "What's your email?",
      field_name: "email",
    },
    5: {
      key: "website_url",
      question: "What's your store URL?",
      field_name: "website_url",
    },
    6: {
      key: "schedule",
      question: "Schedule your call",
      field_name: null,
    },
  };

  function pushStrategySessionGtm(formAction, step, fieldValue, extra) {
    extra = extra || {};
    try {
      var meta = STEP_META[step] || {};
      var answers = getFormAnswersSnapshot();
      var payload = {
        event: "strategy_session_form",
        form_action: formAction,
        form_id: "mss-funnel",
        form_name: FORM_NAME,
        form_step: step,
        form_step_total: TOTAL,
        form_step_name: meta.key || "",
        form_step_question: meta.question || "",
        form_progress_pct: Math.min(
          100,
          Math.max(0, Math.round((step / TOTAL) * 100)),
        ),
        funnel_session_id: getFunnelSessionId(),
        page_type: PAGE_TYPE,
        page_path: window.location.pathname,
        page_location: window.location.href,
        timestamp: new Date().toISOString(),
        form_answers: {
          annual_revenue: answers.annual_revenue,
          fname: answers.fname,
          email: answers.email,
          website_url: answers.website_url,
        },
        annual_revenue: answers.annual_revenue,
        fname: answers.fname,
        email: answers.email,
        website_url: answers.website_url,
        field_name: meta.field_name || "",
        field_value: "",
      };
      if (fieldValue !== undefined && fieldValue !== null) {
        payload.field_value = String(fieldValue);
      }
      var country = funnel.getAttribute("data-visitor-country");
      if (country) payload.visitor_country = country;
      Object.keys(extra).forEach(function (key) {
        payload[key] = extra[key];
      });
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push(payload);
    } catch (err) {}
  }

  function pushStepView(step) {
    pushStrategySessionGtm("step_view", step);
  }

  function pushStepCompleted(step, stepAnswer) {
    pushStrategySessionGtm("step_complete", step, stepAnswer);
  }

  function getFunnelSessionId() {
    try {
      var id = sessionStorage.getItem("mss_funnel_session_id");
      if (!id) {
        id =
          "mss_" +
          Date.now().toString(36) +
          "_" +
          Math.random().toString(36).slice(2, 10);
        sessionStorage.setItem("mss_funnel_session_id", id);
      }
      return id;
    } catch (err) {
      return "mss_anon";
    }
  }

  function syncStrategyStep(step) {
    var payload = {
      step: step,
      funnel_session_id: getFunnelSessionId(),
      form_page_url: window.location.href,
    };
    if (annualRevenue) payload.annual_revenue = annualRevenue;
    var country = funnel.getAttribute("data-visitor-country");
    if (country) payload.visitor_country = country;
    var fnameEl = funnel.querySelector("#mss-fname");
    var emailEl = funnel.querySelector("#mss-email");
    var websiteEl = funnel.querySelector("#mss-website");
    if (fnameEl && fnameEl.value.trim()) payload.fname = fnameEl.value.trim();
    if (emailEl && emailEl.value.trim()) payload.email = emailEl.value.trim();
    if (websiteEl && websiteEl.value.trim()) {
      payload.website_url = websiteEl.value.trim();
    }

    var snapshot =
      step +
      "|" +
      (payload.annual_revenue || "") +
      "|" +
      (payload.fname || "") +
      "|" +
      (payload.email || "") +
      "|" +
      (payload.website_url || "");
    if (lastSyncedStep[step] === snapshot) return;
    lastSyncedStep[step] = snapshot;

    fetch("/strategy-session-step", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      keepalive: true,
      body: JSON.stringify(payload),
    }).catch(function () {});
  }

  function buildCalendlyUrl(fname, email) {
    var url = CALENDLY_URL;
    if (fname) url += "&name=" + encodeURIComponent(fname);
    if (email) url += "&email=" + encodeURIComponent(email);
    return url;
  }

  function sizeCalendlyViewport() {
    if (!calendlyInline || !funnel.classList.contains("is-calendly-step")) {
      return;
    }
    if (EMBED) {
      calendlyInline.style.height = CALENDLY_HEIGHT_EMBED + "px";
      calendlyInline.style.minHeight = CALENDLY_HEIGHT_EMBED + "px";
      return;
    }
    var copy = funnel.querySelector(".mss-step-calendly-copy");
    var copyHeight = copy ? copy.offsetHeight : 0;
    var height = Math.max(320, window.innerHeight - copyHeight);
    calendlyInline.style.height = height + "px";
    calendlyInline.style.minWidth = "100%";
  }

  function mountCalendly() {
    if (calendlyMounted || !calendlyInline) return;
    calendlyMounted = true;

    var fnameEl = funnel.querySelector("#mss-fname");
    var emailEl = funnel.querySelector("#mss-email");
    var fname = fnameEl ? fnameEl.value.trim() : "";
    var email = emailEl ? emailEl.value.trim() : "";
    var widgetUrl = buildCalendlyUrl(fname, email);

    calendlyInline.setAttribute("data-url", widgetUrl);
    calendlyInline.innerHTML = "";
    calendlyInline.removeAttribute("data-processed");
    sizeCalendlyViewport();

    var attempts = 0;
    function initWidget() {
      if (window.Calendly && window.Calendly.initInlineWidget) {
        window.Calendly.initInlineWidget({
          url: widgetUrl,
          parentElement: calendlyInline,
          prefill: { name: fname, email: email },
          resize: true,
        });
        window.setTimeout(sizeCalendlyViewport, 120);
        return;
      }
      if (++attempts > 160) return;
      window.setTimeout(initWidget, 50);
    }
    initWidget();
    syncStrategyStep(6);
    pushStrategySessionGtm("calendly_open", 6, "", {
      calendly_url: widgetUrl,
    });
  }

  function steps() {
    return funnel.querySelectorAll(".mss-step");
  }

  function dots() {
    return funnel.querySelectorAll("[data-progress-dot]");
  }

  function scrollToFunnelStep() {
    if (EMBED) {
      funnel.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function setProgress(n) {
    current = n;
    if (progressLabel) {
      progressLabel.textContent = "Step " + n + " of " + TOTAL;
    }
    dots().forEach(function (dot) {
      var idx = parseInt(dot.getAttribute("data-progress-dot"), 10);
      dot.classList.remove("is-active", "is-done");
      if (idx < n) dot.classList.add("is-done");
      else if (idx === n) dot.classList.add("is-active");
    });
    steps().forEach(function (el) {
      var s = parseInt(el.getAttribute("data-step"), 10);
      el.classList.toggle("is-active", s === n);
    });
    funnel.classList.toggle("is-calendly-step", n === 6);
    if (!EMBED) {
      document.body.classList.toggle("mss-calendly-active", n === 6);
    }
    if (n === 6) {
      window.setTimeout(sizeCalendlyViewport, 0);
    }
    var focusId =
      n === 3 ? "mss-fname" : n === 4 ? "mss-email" : n === 5 ? "mss-website" : null;
    scrollToFunnelStep();
    if (focusId) {
      window.setTimeout(function () {
        var el = funnel.querySelector("#" + focusId);
        if (el) el.focus();
      }, 320);
    }
    try {
      pushStepView(n);
    } catch (err) {}
  }

  function goNext() {
    if (current < TOTAL) setProgress(current + 1);
  }

  function goBack() {
    if (current > START_STEP) setProgress(current - 1);
  }

  function validateField(id) {
    var el = funnel.querySelector("#" + id);
    if (!el) return false;
    if (!el.value || !el.value.trim()) {
      el.focus();
      el.reportValidity && el.reportValidity();
      return false;
    }
    if (el.type === "email" && !el.checkValidity()) {
      el.focus();
      el.reportValidity && el.reportValidity();
      return false;
    }
    return true;
  }

  function submitLead() {
    if (
      !validateField("mss-fname") ||
      !validateField("mss-email") ||
      !validateField("mss-website")
    ) {
      var fnameEl = funnel.querySelector("#mss-fname");
      var emailEl = funnel.querySelector("#mss-email");
      if (!fnameEl || !fnameEl.value.trim()) setProgress(3);
      else if (!emailEl || !emailEl.value.trim()) setProgress(4);
      return;
    }
    var websiteEl = funnel.querySelector("#mss-website");
    var website = websiteEl ? websiteEl.value.trim() : "";

    exitEnabled = false;
    syncStrategyStep(5);
    pushStepCompleted(5, website);
    pushStrategySessionGtm("form_submit", 5, website);
    setProgress(6);
    mountCalendly();
  }

  buildProgressDots();
  resolveVisitorCountry();
  pushStrategySessionGtm("page_load", START_STEP);
  setProgress(START_STEP);
  window.addEventListener("resize", sizeCalendlyViewport);

  funnel.querySelectorAll("[data-mss-next]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (current === 1) {
        pushStepCompleted(1, "started");
      }
      goNext();
    });
  });
  funnel.querySelectorAll("[data-mss-back]").forEach(function (btn) {
    btn.addEventListener("click", goBack);
  });

  function advanceAfterField(id) {
    if (!validateField(id)) return;
    if (id === "mss-fname") {
      var fnameVal = funnel.querySelector("#mss-fname").value.trim();
      syncStrategyStep(3);
      pushStepCompleted(3, fnameVal);
    }
    if (id === "mss-email") {
      var emailVal = funnel.querySelector("#mss-email").value.trim();
      syncStrategyStep(4);
      pushStepCompleted(4, emailVal);
    }
    goNext();
  }

  funnel.querySelectorAll("[data-mss-next-field]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      advanceAfterField(btn.getAttribute("data-mss-next-field"));
    });
  });

  ["mss-fname", "mss-email", "mss-website"].forEach(function (id) {
    var el = funnel.querySelector("#" + id);
    if (!el) return;
    el.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      if (id === "mss-website") submitLead();
      else advanceAfterField(id);
    });
  });

  funnel.querySelectorAll("[data-revenue]").forEach(function (tile) {
    tile.addEventListener("click", function () {
      funnel.querySelectorAll("[data-revenue]").forEach(function (t) {
        t.classList.remove("is-selected");
      });
      tile.classList.add("is-selected");
      annualRevenue = tile.getAttribute("data-revenue") || "";
      syncStrategyStep(2);
      pushStepCompleted(2, annualRevenue);
      window.setTimeout(goNext, 200);
    });
  });

  if (submitBtn) submitBtn.addEventListener("click", submitLead);

  if (!DISABLE_EXIT && exitModal) {
    function updateExitProgressBar() {
      if (exitProgressFill) {
        exitProgressFill.style.width =
          Math.min(100, Math.round((current / TOTAL) * 100)) + "%";
      }
    }

    function closeExitModal() {
      exitModal.classList.remove("is-open");
      exitModal.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
    }

    function openExitModal() {
      if (!exitEnabled || current >= TOTAL) return;
      try {
        if (sessionStorage.getItem(exitStorageKey) === "1") return;
        sessionStorage.setItem(exitStorageKey, "1");
      } catch (err) {}
      updateExitProgressBar();
      exitModal.classList.add("is-open");
      exitModal.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    }

    function maybeShowExitIntent(e) {
      if (!exitEnabled || current >= TOTAL) return;
      if (Date.now() - pageReadyAt < 4000) return;
      if (e && typeof e.clientY === "number" && e.clientY > 12) return;
      openExitModal();
    }

    document.addEventListener("mouseout", function (e) {
      if (!e.relatedTarget && !e.toElement) maybeShowExitIntent(e);
    });
    document.addEventListener("mouseleave", maybeShowExitIntent);
    document.querySelectorAll("[data-mss-exit-close]").forEach(function (el) {
      el.addEventListener("click", closeExitModal);
    });
    var exitCta = document.getElementById("mss-exit-cta");
    if (exitCta) exitCta.addEventListener("click", closeExitModal);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && exitModal.classList.contains("is-open")) {
        closeExitModal();
      }
    });
  }
})();
