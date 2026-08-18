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
  document.querySelectorAll("[data-pdf-form]").forEach(resetPdfForm);
});

function resetPdfForm(form) {
  const button = form.querySelector("[data-pdf-submit]");
  const label = form.querySelector("[data-pdf-label]");
  form.dataset.submitting = "false";
  form.setAttribute("aria-busy", "false");
  if (button) button.disabled = false;
  if (label) label.textContent = "Download PDF Report";
}

document.querySelectorAll("[data-pdf-form]").forEach((form) => {
  const button = form.querySelector("[data-pdf-submit]");
  const label = form.querySelector("[data-pdf-label]");
  let resetTimer;

  resetPdfForm(form);
  form.addEventListener("submit", (event) => {
    if (form.dataset.submitting === "true") {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = "true";
    form.setAttribute("aria-busy", "true");
    if (button) button.disabled = true;
    if (label) label.textContent = "Generating PDF...";
    window.clearTimeout(resetTimer);
    resetTimer = window.setTimeout(() => resetPdfForm(form), 10000);
  });
});
