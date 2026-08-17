"use strict";

document.querySelectorAll("[data-ai-form]").forEach((form) => {
  const button = form.querySelector("[data-ai-submit]");
  const label = form.querySelector("[data-ai-label]");
  form.addEventListener("submit", (event) => {
    if (form.dataset.submitting === "true") {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = "true";
    form.setAttribute("aria-busy", "true");
    if (button) button.disabled = true;
    if (label) label.textContent = "Generating...";
  });
});
