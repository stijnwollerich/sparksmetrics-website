(function () {
  var CALENDLY_URL =
    "https://calendly.com/stijn-wollerich/free-30-minute-strategy-session?hide_gdpr_banner=1";

  var modal = document.getElementById("lead-modal");
  var form = document.getElementById("lead-form");
  var formState = document.getElementById("lead-form-state");
  var thankYouState = document.getElementById("lead-thankyou-state");
  var downloadBlock = document.getElementById("lead-download-block");
  var downloadLink = document.getElementById("lead-download-link");
  var thankYouMessage = document.getElementById("lead-thankyou-message");
  var calendlyIframe = document.getElementById("lead-calendly-iframe");
  var submitBtn = document.getElementById("lead-submit");
  var titleEl = document.getElementById("lead-modal-title");
  var descriptionEl = document.getElementById("lead-modal-description");
  var submitTextEl = document.getElementById("lead-submit-text");
  var bulletsEl = document.getElementById("lead-modal-bullets");
  var badgesEl = document.getElementById("lead-modal-badges");
  var sidebarBadgeEl = document.getElementById("lead-sidebar-badge");
  var slugInput = document.getElementById("lead-slug");
  var typeInput = document.getElementById("lead-modal-type");
  var leadAuditNextDefaultHtml = "";

  function buildThankYouRedirectUrl(fromParam) {
    var modalEl = document.getElementById("lead-modal");
    var explicit =
      modalEl && modalEl.getAttribute("data-lead-thank-you-redirect");
    var ref = encodeURIComponent(window.location.pathname || "");
    var qs = "from=" + encodeURIComponent(fromParam) + "&ref=" + ref;
    if (explicit) {
      var base = (explicit || "").trim().split("#")[0].replace(/\/$/, "");
      if (base) {
        return base.indexOf("?") >= 0 ? base + "&" + qs : base + "?" + qs;
      }
    }
    var origin = (window.location && window.location.origin) || "";
    return origin + "/thank-you/?" + qs;
  }

  function vslSimpleRedirectUrl() {
    return "/free-cro-audit";
  }

  function leadVslSimpleEnabled() {
    return modal && modal.getAttribute("data-lead-vsl-simple") === "1";
  }

  function vslSimpleDefaults() {
    return {
      resource: "vsl-free-cro-video",
      title: "Watch the free CRO walkthrough",
      description: "Enter your name and email to watch the full walkthrough.",
      buttonText: "Continue free",
    };
  }

  function leadSubmitIcon(modalType) {
    if (leadVslSimpleEnabled()) return "play_arrow";
    return modalType === "audit" ? "schedule" : "download";
  }

  function leadAuditMultistepEnabled() {
    return modal && modal.getAttribute("data-lead-audit-multistep") === "1";
  }

  function clearLeadAuditStep1Error() {
    var err = document.getElementById("lead-audit-step1-error");
    if (err) {
      err.textContent = "";
      err.classList.add("hidden");
    }
  }

  function showLeadAuditStep1Error(msg) {
    var err = document.getElementById("lead-audit-step1-error");
    if (!err) {
      window.alert(msg || "Something went wrong. Please try again.");
      return;
    }
    err.textContent = msg || "Something went wrong. Please try again.";
    err.classList.remove("hidden");
  }

  function resetLeadAuditMultistepUi() {
    clearLeadAuditStep1Error();
    var primary = document.getElementById("lead-form-primary-fields");
    var nextBtn = document.getElementById("lead-audit-btn-next");
    var s2 = document.getElementById("lead-audit-step-2-fields");
    if (primary) primary.classList.remove("hidden");
    if (nextBtn) {
      nextBtn.classList.remove("hidden");
      nextBtn.disabled = false;
      nextBtn.innerHTML = leadAuditNextDefaultHtml || "Continue";
    }
    if (s2) {
      s2.classList.add("hidden");
      s2.setAttribute("aria-hidden", "true");
    }
    if (submitBtn && leadAuditMultistepEnabled()) submitBtn.disabled = true;
  }

  function maskEmailForDataLayer(e) {
    try {
      if (!e) return null;
      var parts = e.split("@");
      if (parts.length !== 2) return null;
      return parts[0].charAt(0) + "***@" + parts[1];
    } catch (err) {
      return null;
    }
  }

  function maskNameInitial(n) {
    try {
      return n ? n.charAt(0) : null;
    } catch (err) {
      return null;
    }
  }

  function showLeadAuditStep2() {
    var primary = document.getElementById("lead-form-primary-fields");
    var nextBtn = document.getElementById("lead-audit-btn-next");
    var s2 = document.getElementById("lead-audit-step-2-fields");
    if (primary) primary.classList.add("hidden");
    if (nextBtn) nextBtn.classList.add("hidden");
    if (s2) {
      s2.classList.remove("hidden");
      s2.setAttribute("aria-hidden", "false");
    }
    if (submitBtn) submitBtn.disabled = false;
    var pick = s2 && (s2.querySelector("select") || s2.querySelector("input"));
    if (pick) pick.focus();
  }

  var defaultBullets = bulletsEl ? bulletsEl.innerHTML : "";
  var currentButtonText = "Send me the resource";
  var currentModalType = "resource";

  function openModal(trigger) {
    if (!modal) return;
    var modalType =
      trigger.getAttribute("data-modal-type") ||
      (trigger.getAttribute("data-resource") ? "resource" : "audit");
    currentModalType = modalType;
    var resource = trigger.getAttribute("data-resource") || "";
    var auditMinimal = trigger.getAttribute("data-audit-minimal") === "1";
    var title =
      trigger.getAttribute("data-title") ||
      (modalType === "audit"
        ? "Get a free CRO audit on your funnel"
        : "Free Resource");
    var description =
      trigger.getAttribute("data-description") ||
      (modalType === "audit"
        ? ""
        : "Enter your email and we’ll send you the file.");
    var buttonText =
      trigger.getAttribute("data-button-text") ||
      (modalType === "audit" ? "Request my free audit" : "Send me the resource");
    var bulletsJson = trigger.getAttribute("data-bullets");

    if (typeInput) typeInput.value = modalType;
    if (slugInput) slugInput.value = resource;
    if (titleEl) titleEl.textContent = title;
    if (descriptionEl) {
      var descText = (description || "").trim();
      descriptionEl.textContent = descText;
      if (!descText) descriptionEl.classList.add("hidden");
      else descriptionEl.classList.remove("hidden");
    }
    currentButtonText = buttonText;
    if (submitTextEl) submitTextEl.textContent = buttonText;
    var icon = leadSubmitIcon(modalType);
    var iconClass = leadVslSimpleEnabled()
      ? "material-symbols-outlined play-filled text-lg"
      : "material-symbols-outlined text-lg";
    if (submitBtn)
      submitBtn.innerHTML =
        buttonText +
        ' <span class="' +
        iconClass +
        '">' +
        icon +
        "</span>";

    if (badgesEl) {
      if (leadVslSimpleEnabled()) {
        badgesEl.innerHTML = "";
      } else if (modalType === "audit" && auditMinimal) {
        badgesEl.innerHTML = "";
      } else if (modalType === "audit") {
        badgesEl.innerHTML =
          '<span class="inline-block px-3 py-1.5 bg-primary/10 text-primary text-xs font-black uppercase rounded-full">Free Audit</span><span class="inline-block px-2.5 py-1 border border-primary/30 text-primary text-[10px] font-black uppercase rounded-md">Quick reply</span>';
      } else {
        badgesEl.innerHTML =
          '<span class="inline-block px-3 py-1.5 bg-primary/10 text-primary text-xs font-black uppercase rounded-full">Free Resource</span><span class="inline-block px-2.5 py-1 border border-primary/30 text-primary text-[10px] font-black uppercase rounded-md">Instant access</span>';
      }
    }
    if (sidebarBadgeEl) {
      sidebarBadgeEl.innerHTML =
        modalType === "audit"
          ? '<span class="material-symbols-outlined text-primary text-lg">schedule</span><span class="text-[10px] font-black uppercase tracking-widest text-primary">Quick reply</span>'
          : '<span class="material-symbols-outlined text-primary text-lg">schedule</span><span class="text-[10px] font-black uppercase tracking-widest text-primary">Instant download</span>';
    }

    if (bulletsEl) {
      if (bulletsJson) {
        try {
          var bullets = JSON.parse(bulletsJson);
          bulletsEl.innerHTML = (bullets || [])
            .map(function (b) {
              return (
                '<li class="flex gap-3"><span class="material-symbols-outlined text-primary shrink-0">check_circle</span>' +
                b +
                "</li>"
              );
            })
            .join("");
        } catch (e) {
          bulletsEl.innerHTML = defaultBullets;
        }
      } else if (modalType === "audit" && auditMinimal) {
        bulletsEl.innerHTML = "";
      } else if (modalType === "audit") {
        bulletsEl.innerHTML =
          '<li class="flex gap-3"><span class="material-symbols-outlined text-primary shrink-0">check_circle</span>Data and UI/UX audit of your funnel</li><li class="flex gap-3"><span class="material-symbols-outlined text-primary shrink-0">check_circle</span>Prioritized list of leaks and opportunities</li><li class="flex gap-3"><span class="material-symbols-outlined text-primary shrink-0">check_circle</span>Clear next steps—no obligation</li>';
      } else {
        bulletsEl.innerHTML = defaultBullets;
      }
    }

    if (formState) formState.classList.remove("hidden");
    if (thankYouState) thankYouState.classList.add("hidden");
    if (calendlyIframe) calendlyIframe.src = "about:blank";

    var websiteUrlInputOpen = document.getElementById("lead-website-url");
    var websiteOptionalHint = document.getElementById(
      "lead-website-url-optional-hint",
    );
    var helpRes = document.getElementById("lead-website-url-help-resource");
    var helpAudit = document.getElementById("lead-website-url-help-audit");
    if (websiteUrlInputOpen) {
      if (modalType === "audit") {
        websiteUrlInputOpen.required = true;
        if (websiteOptionalHint) websiteOptionalHint.classList.add("hidden");
        if (helpRes) helpRes.classList.add("hidden");
        if (helpAudit) helpAudit.classList.remove("hidden");
      } else {
        websiteUrlInputOpen.required = false;
        if (websiteOptionalHint) websiteOptionalHint.classList.remove("hidden");
        if (helpRes) helpRes.classList.remove("hidden");
        if (helpAudit) helpAudit.classList.add("hidden");
      }
    }

    if (modalType === "audit" && leadAuditMultistepEnabled()) {
      resetLeadAuditMultistepUi();
    } else if (submitBtn && !leadAuditMultistepEnabled()) {
      submitBtn.disabled = false;
    }

    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    document.getElementById("lead-fname").focus();
    // debug: push modal open event
    try {
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push({
        event: "lead_modal_open",
        modal_type: currentModalType,
        resource: resource || null,
        trigger_text:
          (trigger &&
            trigger.getAttribute &&
            (trigger.getAttribute("data-title") || trigger.textContent)) ||
          null,
        path: window.location.pathname,
        timestamp: new Date().toISOString(),
      });
    } catch (err) {}
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    if (calendlyIframe) calendlyIframe.src = "about:blank";
    if (leadAuditMultistepEnabled()) resetLeadAuditMultistepUi();
  }

  function triggerDownload(url) {
    if (!url || url === "#") return;
    var a = document.createElement("a");
    a.href = url;
    a.download =
      (url.split("/").pop() || "download").split("?")[0] || "download";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function showThankYou(hasDownload, downloadUrl) {
    if (hasDownload && downloadUrl) triggerDownload(downloadUrl);
    if (formState) formState.classList.add("hidden");
    if (thankYouState) thankYouState.classList.remove("hidden");
    if (thankYouMessage) {
      thankYouMessage.textContent = hasDownload
        ? "Your ebook is downloading. Pick a time on the left for a free 30-minute strategy session—we can walk through the strategies and your next steps."
        : "We’ll follow up by email with next steps for your audit request. Or pick a time on the left if you’d rather talk now.";
    }
    if (calendlyIframe) {
      calendlyIframe.src = CALENDLY_URL;
      try {
        var fnameEl = document.getElementById("lead-fname");
        var emailEl = document.getElementById("lead-email");
        var stageEl = document.getElementById("lead-business-stage");
        var calFormAnswer = {
          fname: fnameEl && fnameEl.value ? fnameEl.value.trim() : null,
          email: emailEl && emailEl.value ? emailEl.value.trim() : null,
        };
        if (stageEl && stageEl.value)
          calFormAnswer.business_stage = stageEl.value;
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push({
          event: "calendly_open_from_lead",
          form_id: "lead-form",
          modal_type: currentModalType,
          form_answer: calFormAnswer,
          url: CALENDLY_URL,
          path: window.location.pathname,
          timestamp: new Date().toISOString(),
        });
      } catch (err) {}
    }
  }

  function resetModal() {
    if (form) {
      form.reset();
      if (slugInput) slugInput.value = "";
      if (typeInput) typeInput.value = "resource";
    }
    if (formState) formState.classList.remove("hidden");
    if (thankYouState) thankYouState.classList.add("hidden");
    if (calendlyIframe) calendlyIframe.src = "about:blank";
    if (leadAuditMultistepEnabled()) {
      resetLeadAuditMultistepUi();
    } else if (submitBtn) {
      submitBtn.disabled = false;
    }
    var icon = leadSubmitIcon(currentModalType);
    var iconClass = leadVslSimpleEnabled()
      ? "material-symbols-outlined play-filled text-lg"
      : "material-symbols-outlined text-lg";
    if (submitBtn)
      submitBtn.innerHTML =
        currentButtonText +
        ' <span class="' +
        iconClass +
        '">' +
        icon +
        "</span>";
  }

  function leadCtaClickEvent(triggerModalType, triggerResource) {
    if (triggerModalType === "audit") return "audit_cta_clicked";
    if (
      leadVslSimpleEnabled() ||
      triggerResource === "vsl-free-cro-video"
    ) {
      return "video_cta_clicked";
    }
    return "ebook_cta_clicked";
  }

  function bindTrigger(el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      resetModal();
      // Push a datalayer event when CTA is clicked to open lead modal
      try {
        var triggerModalType =
          el.getAttribute("data-modal-type") ||
          (el.getAttribute("data-resource") ? "resource" : "audit");
        var triggerResource = el.getAttribute("data-resource") || null;
        var triggerPayload = {
          event: leadCtaClickEvent(triggerModalType, triggerResource),
          trigger_text:
            el.getAttribute("data-title") ||
            (el.textContent || "").trim().slice(0, 120),
          modal_type: triggerModalType,
          resource: triggerResource,
          path: window.location.pathname,
          timestamp: new Date().toISOString(),
        };
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push(triggerPayload);
      } catch (err) {}
      if (
        el.getAttribute("data-checklist-modal") !== null &&
        !el.getAttribute("data-resource")
      ) {
        if (leadVslSimpleEnabled()) {
          var vslDefaults = vslSimpleDefaults();
          el.setAttribute("data-resource", vslDefaults.resource);
          el.setAttribute("data-title", vslDefaults.title);
          el.setAttribute("data-description", vslDefaults.description);
          el.setAttribute("data-button-text", vslDefaults.buttonText);
        } else {
          el.setAttribute("data-resource", "13-bulletproof-strategies");
          el.setAttribute(
            "data-title",
            "13 Bulletproof Strategies to Skyrocket Conversions",
          );
          el.setAttribute(
            "data-description",
            "Enter your email and get the free ebook right away — 13 actionable CRO strategies used by $10M+ brands.",
          );
          el.setAttribute("data-button-text", "Send me the ebook");
        }
      }
      openModal(el);
    });
  }
  document.querySelectorAll("[data-download-modal]").forEach(bindTrigger);
  document.querySelectorAll("[data-checklist-modal]").forEach(bindTrigger);
  document.querySelectorAll("[data-audit-modal]").forEach(bindTrigger);

  document.querySelectorAll("[data-lead-close]").forEach(function (el) {
    el.addEventListener("click", closeModal);
  });

  var leadAuditNext = document.getElementById("lead-audit-btn-next");
  if (leadAuditNext) {
    leadAuditNextDefaultHtml = leadAuditNext.innerHTML;
    leadAuditNext.addEventListener("click", function () {
      if (!leadAuditMultistepEnabled()) return;
      var f = document.getElementById("lead-form");
      if (f && f.checkValidity && !f.checkValidity()) {
        f.reportValidity();
        return;
      }
      clearLeadAuditStep1Error();
      var fnameInput = document.getElementById("lead-fname");
      var emailInput = document.getElementById("lead-email");
      var websiteUrlInput = document.getElementById("lead-website-url");
      var fname = fnameInput && fnameInput.value ? fnameInput.value.trim() : "";
      var email = emailInput && emailInput.value ? emailInput.value.trim() : "";
      var websiteUrlOpt =
        websiteUrlInput && websiteUrlInput.value
          ? websiteUrlInput.value.trim()
          : "";
      if (!fname || !email || !websiteUrlOpt) return;

      leadAuditNext.disabled = true;
      leadAuditNext.innerHTML = "Saving…";

      fetch("/request-audit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          audit_multistep_step: 1,
          fname: fname,
          email: email,
          website_url: websiteUrlOpt,
          form_page_url: window.location.href || "",
        }),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { ok: res.ok, data: data };
          });
        })
        .then(function (pack) {
          if (!pack.data || !pack.data.success) {
            showLeadAuditStep1Error(
              (pack.data && pack.data.error) || "Please try again.",
            );
            leadAuditNext.disabled = false;
            leadAuditNext.innerHTML = leadAuditNextDefaultHtml;
            return;
          }
          try {
            window.dataLayer = window.dataLayer || [];
            window.dataLayer.push({
              event: "audit_multistep_primary_saved",
              form_id: "lead-form",
              modal_type: "audit",
              form_answer: {
                fname: fname,
                email: email,
                website_url: websiteUrlOpt,
              },
              path: window.location.pathname,
              timestamp: new Date().toISOString(),
            });
          } catch (err) {}
          leadAuditNext.disabled = false;
          leadAuditNext.innerHTML = leadAuditNextDefaultHtml;
          showLeadAuditStep2();
        })
        .catch(function () {
          showLeadAuditStep1Error("Network error. Please try again.");
          leadAuditNext.disabled = false;
          leadAuditNext.innerHTML = leadAuditNextDefaultHtml;
        });
    });
  }
  var leadAuditBack = document.getElementById("lead-audit-btn-back");
  if (leadAuditBack) {
    leadAuditBack.addEventListener("click", function () {
      resetLeadAuditMultistepUi();
      var fn = document.getElementById("lead-fname");
      if (fn) fn.focus();
    });
  }

  if (modal)
    modal.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeModal();
    });

  if (form)
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var fnameInput = document.getElementById("lead-fname");
      var emailInput = document.getElementById("lead-email");
      var websiteUrlInput = document.getElementById("lead-website-url");
      var businessStageEl = document.getElementById("lead-business-stage");
      var fname = fnameInput && fnameInput.value ? fnameInput.value.trim() : "";
      var email = emailInput && emailInput.value ? emailInput.value.trim() : "";
      var websiteUrlOpt =
        websiteUrlInput && websiteUrlInput.value
          ? websiteUrlInput.value.trim()
          : "";
      var businessStage =
        businessStageEl && businessStageEl.value
          ? businessStageEl.value.trim()
          : null;
      var resource = slugInput && slugInput.value ? slugInput.value.trim() : "";
      var modalType =
        typeInput && typeInput.value ? typeInput.value : "resource";
      if (!fname) return;
      if (!email) return;
      if (
        modalType !== "audit" &&
        businessStageEl &&
        !businessStage &&
        !leadVslSimpleEnabled()
      ) {
        businessStageEl.focus();
        businessStageEl.reportValidity && businessStageEl.reportValidity();
        return;
      }
      if (modalType === "audit" && websiteUrlInput) {
        if (!websiteUrlOpt) {
          websiteUrlInput.reportValidity &&
            websiteUrlInput.reportValidity();
          return;
        }
      }
      if (modalType === "audit" && leadAuditMultistepEnabled()) {
        var s2el = document.getElementById("lead-audit-step-2-fields");
        if (s2el && s2el.classList.contains("hidden")) {
          return;
        }
        var omEl = document.getElementById("lead-audit-orders-per-month");
        var cvrEl = document.getElementById("lead-audit-conversion-rate");
        var aovEl = document.getElementById("lead-audit-aov");
        var omv = omEl && omEl.value ? omEl.value.trim() : "";
        var cvrV = cvrEl && cvrEl.value ? cvrEl.value.trim() : "";
        var aovV = aovEl && aovEl.value ? aovEl.value.trim() : "";
        if (!omv) {
          if (omEl) omEl.focus();
          return;
        }
        if (!cvrV) {
          if (cvrEl) cvrEl.focus();
          return;
        }
        if (!aovV) {
          if (aovEl) aovEl.focus();
          return;
        }
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = "Sending…";
      }

      var formAnswer;
      if (modalType === "audit" && leadAuditMultistepEnabled()) {
        var omAns = document.getElementById("lead-audit-orders-per-month");
        var cvrAns = document.getElementById("lead-audit-conversion-rate");
        var aovAns = document.getElementById("lead-audit-aov");
        formAnswer = {
          fname: fname,
          email: email,
          website_url: websiteUrlOpt,
          orders_per_month:
            omAns && omAns.value ? omAns.value.trim() : "",
          conversion_rate:
            cvrAns && cvrAns.value ? cvrAns.value.trim() : "",
          average_order_value:
            aovAns && aovAns.value ? aovAns.value.trim() : "",
        };
      } else {
        formAnswer = {
          fname: fname,
          email: email,
        };
        if (businessStage) formAnswer.business_stage = businessStage;
      }

      // Push a datalayer event with form answers (useful for GTM)
      try {
        window.dataLayer = window.dataLayer || [];
        var submittedPayload = {
          event: "lead_form_submitted",
          form_id: "lead-form",
          modal_type: modalType,
          resource: resource,
          form_answer: formAnswer,
          path: window.location.pathname,
          timestamp: new Date().toISOString(),
        };
        window.dataLayer.push(submittedPayload);
      } catch (err) {
        // ignore
      }

      var url = modalType === "audit" ? "/request-audit" : "/download-resource";
      var body =
        modalType === "audit"
          ? {
              fname: fname,
              email: email,
              website_url: websiteUrlOpt,
              form_page_url: window.location.href || "",
            }
          : { resource: resource, fname: fname, email: email };
      if (modalType === "resource" && leadVslSimpleEnabled()) {
        body.form_page_url = window.location.href || "";
      }
      if (modalType === "resource" && businessStage)
        body.business_stage = businessStage;
      if (modalType === "resource" && websiteUrlOpt)
        body.website_url = websiteUrlOpt;
      if (modalType === "audit" && leadAuditMultistepEnabled()) {
        body.audit_multistep_step = 2;
        var omB = document.getElementById("lead-audit-orders-per-month");
        var cvrB = document.getElementById("lead-audit-conversion-rate");
        var aovB = document.getElementById("lead-audit-aov");
        body.orders_per_month =
          omB && omB.value ? omB.value.trim() : "";
        body.conversion_rate =
          cvrB && cvrB.value ? cvrB.value.trim() : "";
        body.average_order_value =
          aovB && aovB.value ? aovB.value.trim() : "";
      }

      fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify(body),
      })
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          var hasDownload =
            modalType === "resource" &&
            data.success &&
            data.download_url &&
            !leadVslSimpleEnabled();
          // Push success event with server response and form answers
          try {
            window.dataLayer = window.dataLayer || [];
            var successPayload = {
              event: "lead_form_success",
              form_id: "lead-form",
              modal_type: modalType,
              resource: resource,
              form_answer: formAnswer,
              success: !!data.success,
              download_url: data.download_url || null,
              path: window.location.pathname,
              timestamp: new Date().toISOString(),
            };
            window.dataLayer.push(successPayload);
          } catch (err) {}
          if (leadVslSimpleEnabled()) {
            if (data && data.success) {
              closeModal();
              window.location.href =
                (data.redirect_url && String(data.redirect_url)) ||
                vslSimpleRedirectUrl();
            } else if (submitBtn) {
              submitBtn.innerHTML = "Try again";
            }
            return;
          }
          // Redirect to thank-you page with source (from) and referring page (ref)
          var fromParam =
            modalType === "audit" ? "audit" : resource || "ebook";
          var thankYouUrl = buildThankYouRedirectUrl(fromParam);
          if (hasDownload && data.download_url) {
            triggerDownload(data.download_url);
          }
          window.location.href = thankYouUrl;
        })
        .catch(function () {
          // Push error event with form answers
          try {
            window.dataLayer = window.dataLayer || [];
            var errorPayload = {
              event: "lead_form_error",
              form_id: "lead-form",
              modal_type: modalType,
              resource: resource,
              form_answer: formAnswer,
              path: window.location.pathname,
              timestamp: new Date().toISOString(),
            };
            window.dataLayer.push(errorPayload);
          } catch (err) {}
          if (leadVslSimpleEnabled()) {
            if (submitBtn) submitBtn.innerHTML = "Try again";
            return;
          }
          // On error still redirect to thank-you so user can book
          var fromParam =
            modalType === "audit" ? "audit" : resource || "ebook";
          var thankYouUrl = buildThankYouRedirectUrl(fromParam);
          window.location.href = thankYouUrl;
        })
        .finally(function () {
          if (!submitBtn) return;
          submitBtn.disabled = false;
          var icon = leadSubmitIcon(currentModalType);
          var iconClass = leadVslSimpleEnabled()
            ? "material-symbols-outlined play-filled text-lg"
            : "material-symbols-outlined text-lg";
          submitBtn.innerHTML =
            currentButtonText +
            ' <span class="' +
            iconClass +
            '">' +
            icon +
            "</span>";
        });
    });

  window.LeadModal = {
    openFrom: function (el) {
      if (!el) return;
      resetModal();
      openModal(el);
    },
    close: closeModal,
  };
})();
