/**
 * PDP redesign landing — sticky CTA, ROI math, tracking, UTMs.
 * Proof pair is static (no slider) so the point survives without interaction.
 */
(function () {
  "use strict";

  var UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id"];

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function readParams() {
    var out = {};
    try {
      var sp = new URLSearchParams(window.location.search);
      sp.forEach(function (v, k) {
        if (v) out[k] = v;
      });
    } catch (e) {}
    return out;
  }

  function persistUtms(params) {
    try {
      var store = {};
      UTM_KEYS.forEach(function (k) {
        if (params[k]) store[k] = params[k];
      });
      if (params.v) store.v = params.v;
      if (Object.keys(store).length) {
        sessionStorage.setItem("pdp_redesign_attrs", JSON.stringify(store));
      }
    } catch (e) {}
  }

  function loadPersisted() {
    try {
      var raw = sessionStorage.getItem("pdp_redesign_attrs");
      return raw ? JSON.parse(raw) : {};
    } catch (e) {
      return {};
    }
  }

  function mergeAttrs() {
    var fromUrl = readParams();
    persistUtms(fromUrl);
    var stored = loadPersisted();
    var merged = {};
    UTM_KEYS.concat(["v"]).forEach(function (k) {
      if (fromUrl[k]) merged[k] = fromUrl[k];
      else if (stored[k]) merged[k] = stored[k];
    });
    return merged;
  }

  function appendAttrs(url, attrs) {
    try {
      var u = new URL(url, window.location.origin);
      Object.keys(attrs || {}).forEach(function (k) {
        if (attrs[k] && !u.searchParams.get(k)) u.searchParams.set(k, attrs[k]);
      });
      return u.pathname + u.search + u.hash;
    } catch (e) {
      return url;
    }
  }

  function dlPush(payload) {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push(payload);
  }

  function fireMeta(eventName, params) {
    try {
      if (typeof window.fbq === "function") {
        window.fbq("track", eventName, params || {});
      }
    } catch (e) {}
  }

  dlPush({ event: "lp_view", offer: "pdp_redesign" });

  var scrollMarks = { 50: false, 90: false };
  function onScrollDepth() {
    var doc = document.documentElement;
    var scrollTop = window.scrollY || doc.scrollTop || 0;
    var height = (doc.scrollHeight || 0) - (window.innerHeight || 0);
    if (height <= 0) return;
    var pct = (scrollTop / height) * 100;
    if (!scrollMarks[50] && pct >= 50) {
      scrollMarks[50] = true;
      dlPush({ event: "scroll_50", offer: "pdp_redesign" });
    }
    if (!scrollMarks[90] && pct >= 90) {
      scrollMarks[90] = true;
      dlPush({ event: "scroll_90", offer: "pdp_redesign" });
    }
  }

  var attrs = mergeAttrs();

  qsa(".js-pdp-buy").forEach(function (el) {
    var href = el.getAttribute("href") || "";
    var position = el.getAttribute("data-position") || "hero";
    el.setAttribute("href", appendAttrs(href, Object.assign({}, attrs, { position: position })));
    el.addEventListener("click", function () {
      dlPush({ event: "cta_click_buy", position: position, offer: "pdp_redesign" });
      dlPush({ event: "checkout_started", position: position, offer: "pdp_redesign", value: 500, currency: "USD" });
      fireMeta("InitiateCheckout", { value: 500, currency: "USD", content_name: "PDP Redesign" });
    });
  });

  qsa(".js-pdp-call").forEach(function (el) {
    el.addEventListener("click", function () {
      var position = el.getAttribute("data-position") || "hero";
      dlPush({ event: "cta_click_call", position: position, offer: "pdp_redesign" });
    });
  });

  var primary = qs("#pdp-primary-cta");
  var sticky = qs("#pdp-sticky-cta");
  function updateSticky() {
    if (!primary || !sticky) return;
    var passed = primary.getBoundingClientRect().bottom < 0;
    sticky.classList.toggle("is-visible", passed);
    sticky.setAttribute("aria-hidden", passed ? "false" : "true");
  }

  /* ROI: monthly is primary; annual is secondary only */
  var revenue = qs("#pdp-revenue");
  var revenueLabel = qs("#pdp-revenue-label");
  var roiValue = qs("#pdp-roi-value");
  var roiAnnual = qs("#pdp-roi-annual");
  var roiMath = qs("#pdp-roi-math");

  function formatMoney(n) {
    var abs = Math.round(n);
    if (abs >= 1000000) {
      var m = abs / 1000000;
      return "$" + (Math.round(m * 10) / 10) + "M";
    }
    if (abs >= 1000) {
      var k = abs / 1000;
      var rounded = Math.round(k * 10) / 10;
      return "$" + (Number.isInteger(rounded) ? rounded : rounded.toFixed(1)) + "K";
    }
    return "$" + abs;
  }

  function updateRoi() {
    if (!revenue || !roiValue) return;
    var monthly = parseInt(revenue.value, 10) || 150000;
    var monthlyUpside = monthly * (0.003 / 0.02); // 2% → 2.3%
    var annualUpside = monthlyUpside * 12;
    if (revenueLabel) revenueLabel.textContent = formatMoney(monthly) + "/mo";
    // Force monthly unit on the big number — never write /year here
    roiValue.textContent = "~" + formatMoney(monthlyUpside) + "/mo";
    roiValue.setAttribute("data-unit", "month");
    if (roiAnnual) roiAnnual.textContent = "that’s ~" + formatMoney(annualUpside) + "/year";
    if (roiMath) {
      roiMath.textContent =
        "2% → 2.3% CVR on " + formatMoney(monthly) + "/mo = ~" + formatMoney(monthlyUpside) + " more per month.";
    }
  }
  if (revenue) {
    revenue.addEventListener("input", updateRoi);
    updateRoi();
  }

  var lightbox = qs("#pdp-lightbox");
  var lightboxImg = qs("#pdp-lightbox-img");
  function openLightbox(src) {
    if (!lightbox || !lightboxImg) return;
    lightboxImg.src = src;
    lightbox.hidden = false;
    lightbox.classList.add("is-open");
  }
  function closeLightbox() {
    if (!lightbox) return;
    lightbox.classList.remove("is-open");
    lightbox.hidden = true;
  }
  qsa(".js-pdp-zoom").forEach(function (el) {
    el.addEventListener("click", function () {
      openLightbox(el.getAttribute("data-full") || (el.querySelector("img") || {}).src);
    });
  });
  var closeBtn = qs("#pdp-lightbox-close");
  if (closeBtn) closeBtn.addEventListener("click", closeLightbox);
  if (lightbox) {
    lightbox.addEventListener("click", function (e) {
      if (e.target === lightbox) closeLightbox();
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeLightbox();
  });

  window.addEventListener(
    "scroll",
    function () {
      updateSticky();
      onScrollDepth();
    },
    { passive: true }
  );
  window.addEventListener("resize", updateSticky);
  updateSticky();
  onScrollDepth();
})();
