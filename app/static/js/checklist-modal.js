(function () {
  var CALENDLY_URL = "https://calendly.com/stijnwherever/free-30-minute-strategy-session?hide_gdpr_banner=1";

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

  var defaultBullets = bulletsEl ? bulletsEl.innerHTML : "";
  var currentButtonText = "Send me the resource";
  var currentModalType = "resource";

  function openModal(trigger) {
    if (!modal) return;
    var modalType = trigger.getAttribute("data-modal-type") || (trigger.getAttribute("data-resource") ? "resource" : "audit");
    currentModalType = modalType;
    var resource = trigger.getAttribute("data-resource") || "";
    var title = trigger.getAttribute("data-title") || (modalType === "audit" ? "Get a FREE 24-Hour CRO Audit" : "Free Resource");
    var description = trigger.getAttribute("data-description") || (modalType === "audit" ? "Enter your email and we’ll get in touch to schedule your free audit. Limited to 3 brands per week." : "Enter your email and we’ll send you the file.");
    var buttonText = trigger.getAttribute("data-button-text") || (modalType === "audit" ? "Claim my free audit" : "Send me the resource");
    var bulletsJson = trigger.getAttribute("data-bullets");

    if (typeInput) typeInput.value = modalType;
    if (slugInput) slugInput.value = resource;
    if (titleEl) titleEl.textContent = title;
    if (descriptionEl) descriptionEl.textContent = description;
    currentButtonText = buttonText;
    if (submitTextEl) submitTextEl.textContent = buttonText;
    var icon = modalType === "audit" ? "schedule" : "download";
    if (submitBtn) submitBtn.innerHTML = buttonText + ' <span class="material-symbols-outlined text-lg">' + icon + "</span>";

    if (badgesEl) {
      if (modalType === "audit") {
        badgesEl.innerHTML = '<span class="inline-block px-3 py-1.5 bg-primary/10 text-primary text-xs font-black uppercase rounded-full">Free Audit</span><span class="inline-block px-2.5 py-1 border border-primary/30 text-primary text-[10px] font-black uppercase rounded-md">24-hour turnaround</span>';
      } else {
        badgesEl.innerHTML = '<span class="inline-block px-3 py-1.5 bg-primary/10 text-primary text-xs font-black uppercase rounded-full">Free Resource</span><span class="inline-block px-2.5 py-1 border border-primary/30 text-primary text-[10px] font-black uppercase rounded-md">Instant access</span>';
      }
    }
    if (sidebarBadgeEl) {
      sidebarBadgeEl.innerHTML = modalType === "audit"
        ? '<span class="material-symbols-outlined text-primary text-lg">schedule</span><span class="text-[10px] font-black uppercase tracking-widest text-primary">24-hour turnaround</span>'
        : '<span class="material-symbols-outlined text-primary text-lg">schedule</span><span class="text-[10px] font-black uppercase tracking-widest text-primary">Instant download</span>';
    }

    if (bulletsEl) {
      if (bulletsJson) {
        try {
          var bullets = JSON.parse(bulletsJson);
          bulletsEl.innerHTML = (bullets || []).map(function (b) {
            return '<li class="flex gap-3"><span class="material-symbols-outlined text-primary shrink-0">check_circle</span>' + b + "</li>";
          }).join("");
        } catch (e) {
          bulletsEl.innerHTML = defaultBullets;
        }
      } else if (modalType === "audit") {
        bulletsEl.innerHTML = '<li class="flex gap-3"><span class="material-symbols-outlined text-primary shrink-0">check_circle</span>Data and UI/UX audit of your funnel</li><li class="flex gap-3"><span class="material-symbols-outlined text-primary shrink-0">check_circle</span>Prioritized list of leaks and opportunities</li><li class="flex gap-3"><span class="material-symbols-outlined text-primary shrink-0">check_circle</span>Clear next steps—no obligation</li>';
      } else {
        bulletsEl.innerHTML = defaultBullets;
      }
    }

    if (formState) formState.classList.remove("hidden");
    if (thankYouState) thankYouState.classList.add("hidden");
    if (calendlyIframe) calendlyIframe.src = "about:blank";

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
          trigger_text: (trigger && (trigger.getAttribute && (trigger.getAttribute('data-title') || trigger.textContent))) || null,
          path: window.location.pathname,
          timestamp: new Date().toISOString()
        });
      } catch (err) {}
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    if (calendlyIframe) calendlyIframe.src = "about:blank";
  }

  function triggerDownload(url) {
    if (!url || url === "#") return;
    var a = document.createElement("a");
    a.href = url;
    a.download = (url.split("/").pop() || "download").split("?")[0] || "download";
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
        : "We’ll be in touch to schedule your free 24-hour CRO audit. Or pick a time on the left to get on the calendar now.";
    }
    if (calendlyIframe) {
      calendlyIframe.src = CALENDLY_URL;
      try {
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push({
          event: "calendly_open_from_lead",
          form_id: "lead-form",
          modal_type: currentModalType,
          fname: (document.getElementById('lead-fname')||{}).value || null,
          email: (document.getElementById('lead-email')||{}).value || null,
          url: CALENDLY_URL,
          path: window.location.pathname,
          timestamp: new Date().toISOString()
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
    var icon = currentModalType === "audit" ? "schedule" : "download";
    if (submitBtn) submitBtn.innerHTML = currentButtonText + ' <span class="material-symbols-outlined text-lg">' + icon + "</span>";
  }

  function bindTrigger(el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      resetModal();
      // Push a datalayer event when CTA is clicked to open lead modal
      try {
        var triggerModalType = el.getAttribute("data-modal-type") || (el.getAttribute("data-resource") ? "resource" : "audit");
        var triggerResource = el.getAttribute("data-resource") || null;
        var triggerPayload = {
          event: triggerModalType === "audit" ? "audit_cta_clicked" : "ebook_cta_clicked",
          trigger_text: el.getAttribute("data-title") || (el.textContent || "").trim().slice(0, 120),
          modal_type: triggerModalType,
          resource: triggerResource,
          path: window.location.pathname,
          timestamp: new Date().toISOString()
        };
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push(triggerPayload);
      } catch (err) {}
      if (el.getAttribute("data-checklist-modal") !== null && !el.getAttribute("data-resource")) {
        el.setAttribute("data-resource", "cro-checklist");
        el.setAttribute("data-title", "13 Bulletproof Strategies to Skyrocket Conversions");
        el.setAttribute("data-description", "Enter your email and we'll send you the free ebook with 13 actionable CRO strategies used by $10M+ brands.");
        el.setAttribute("data-button-text", "Send me the ebook");
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

  if (modal) modal.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeModal();
  });

  if (form) form.addEventListener("submit", function (e) {
    e.preventDefault();
    var fnameInput = document.getElementById("lead-fname");
    var emailInput = document.getElementById("lead-email");
    var fname = fnameInput && fnameInput.value ? fnameInput.value.trim() : "";
    var email = emailInput && emailInput.value ? emailInput.value.trim() : "";
    var resource = slugInput && slugInput.value ? slugInput.value.trim() : "";
    var modalType = typeInput && typeInput.value ? typeInput.value : "resource";
    if (!fname) return;
    if (!email) return;

    submitBtn.disabled = true;
    submitBtn.innerHTML = "Sending…";

    // Mask PII before pushing to dataLayer
    function maskEmail(e) {
      try {
        if (!e) return null;
        var parts = e.split('@');
        if (parts.length !== 2) return null;
        return parts[0].charAt(0) + '***@' + parts[1];
      } catch (err) { return null; }
    }
    function maskName(n) {
      try { return n ? n.charAt(0) : null; } catch (err) { return null; }
    }
    var maskedEmail = maskEmail(email);
    var fnameInitial = maskName(fname);
    // Push a datalayer event with masked submission (useful for GTM)
    try {
      window.dataLayer = window.dataLayer || [];
      var submittedPayload = {
        event: "lead_form_submitted",
        form_id: "lead-form",
        modal_type: modalType,
        resource: resource,
        fname_initial: fnameInitial,
        email_masked: maskedEmail,
        path: window.location.pathname,
        timestamp: new Date().toISOString(),
      };
      window.dataLayer.push(submittedPayload);
    } catch (err) {
      // ignore
    }

    var url = modalType === "audit" ? "/request-audit" : "/download-resource";
    var body = modalType === "audit"
      ? { fname: fname, email: email }
      : { resource: resource, fname: fname, email: email };

    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(body),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var hasDownload = modalType === "resource" && data.success && data.download_url;
        // Push success event with server response
        try {
          window.dataLayer = window.dataLayer || [];
          var successPayload = {
            event: "lead_form_success",
            form_id: "lead-form",
            modal_type: modalType,
            resource: resource,
            fname_initial: fnameInitial,
            email_masked: maskedEmail,
            success: !!data.success,
            download_url: data.download_url || null,
            path: window.location.pathname,
            timestamp: new Date().toISOString(),
          };
          window.dataLayer.push(successPayload);
        } catch (err) {}
        showThankYou(hasDownload, data.download_url || "#");
      })
      .catch(function () {
        // Push error event
        try {
          window.dataLayer = window.dataLayer || [];
          var errorPayload = {
            event: "lead_form_error",
            form_id: "lead-form",
            modal_type: modalType,
            resource: resource,
            fname_initial: fnameInitial,
            email_masked: maskedEmail,
            path: window.location.pathname,
            timestamp: new Date().toISOString(),
          };
          window.dataLayer.push(errorPayload);
        } catch (err) {}
        showThankYou(modalType === "resource", "#");
      })
      .finally(function () {
        submitBtn.disabled = false;
        var icon = currentModalType === "audit" ? "schedule" : "download";
        submitBtn.innerHTML = currentButtonText + ' <span class="material-symbols-outlined text-lg">' + icon + "</span>";
      });
  });
})();
