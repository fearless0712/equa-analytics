"use strict";

document.documentElement.dataset.javascript = "enabled";

function resetUploadForm(form) {
  const button = form.querySelector("[data-submit-button]");
  const label = form.querySelector("[data-button-label]");
  form.dataset.submitting = "false";
  form.setAttribute("aria-busy", "false");
  if (button) button.disabled = false;
  if (label) label.textContent = "Analyze Data";
}

document.querySelectorAll("[data-upload-form]").forEach((form) => {
  const input = form.querySelector("[data-file-input]");
  const fileName = form.querySelector("[data-file-name]");
  const button = form.querySelector("[data-submit-button]");
  const label = form.querySelector("[data-button-label]");

  resetUploadForm(form);
  input?.addEventListener("change", () => {
    fileName.textContent = input.files?.[0]?.name || "No file selected";
  });
  form.addEventListener("submit", (event) => {
    if (form.dataset.submitting === "true") {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = "true";
    form.setAttribute("aria-busy", "true");
    button.disabled = true;
    label.textContent = "Analyzing...";
  });
});

window.addEventListener("pageshow", () => {
  document.querySelectorAll("[data-upload-form]").forEach(resetUploadForm);
  document.querySelectorAll("[data-report-form]").forEach(resetReportForm);
});

const BUSINESS_REPORT_ACTIONS = Object.freeze({
  "pdf,false": "/reports/pdf",
  "pdf,true": "/reports/pdf/ai",
  "html,false": "/reports/html",
  "html,true": "/reports/html/ai",
});

function getBusinessReportAction(format, includeAi) {
  return BUSINESS_REPORT_ACTIONS[`${format},${includeAi}`] || null;
}

function resetReportForm(form) {
  const button = form.querySelector("[data-report-submit]");
  const label = form.querySelector("[data-report-label]");
  form.dataset.submitting = "false";
  form.setAttribute("aria-busy", "false");
  if (button) button.disabled = false;
  if (label) label.textContent = "Download Report";
}

document.querySelectorAll("[data-report-form]").forEach((form) => {
  const button = form.querySelector("[data-report-submit]");
  const label = form.querySelector("[data-report-label]");
  const aiToggle = form.querySelector("[name='include_ai']");
  const aiHelp = form.querySelector("[data-report-ai-help]");
  let resetTimer;

  const updateAiHelp = () => {
    if (!aiHelp) return;
    aiHelp.textContent = aiToggle?.checked
      ? "Adds AI interpretation and recommendations to the deterministic analysis."
      : "Uses deterministic analysis only.";
  };

  resetReportForm(form);
  updateAiHelp();
  aiToggle?.addEventListener("change", updateAiHelp);
  form.addEventListener("submit", (event) => {
    if (form.dataset.submitting === "true") {
      event.preventDefault();
      return;
    }
    const format = form.querySelector("[name='report_format']:checked")?.value;
    const action = getBusinessReportAction(format, Boolean(aiToggle?.checked));
    if (!action) {
      event.preventDefault();
      return;
    }
    form.action = action;
    form.dataset.submitting = "true";
    form.setAttribute("aria-busy", "true");
    if (button) button.disabled = true;
    if (label) label.textContent = "Generating Report...";
    window.clearTimeout(resetTimer);
    resetTimer = window.setTimeout(() => resetReportForm(form), 10000);
  });
});
