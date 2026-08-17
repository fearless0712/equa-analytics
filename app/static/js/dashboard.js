"use strict";

document.querySelectorAll("[data-chart-spec]").forEach((element) => {
  try {
    const spec = JSON.parse(window.atob(element.dataset.chartSpec));
    window.Plotly.newPlot(element, spec.data, spec.layout, {
      displaylogo: false,
      responsive: true,
      scrollZoom: false,
    });
  } catch (_error) {
    element.textContent = "Chart unavailable";
  }
});
