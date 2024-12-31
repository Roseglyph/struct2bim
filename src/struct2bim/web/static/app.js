const form = document.querySelector("#generator-form");
const message = document.querySelector("#message");
const state = document.querySelector("#result-state");
const image = document.querySelector("#preview-image");
const metrics = document.querySelector("#result-metrics");
const buttons = [...form.querySelectorAll("button[type=submit]")];

function selected(name) {
  return [...form.querySelectorAll(`input[name=${name}]:checked`)].map((item) => item.value);
}

function number(name) {
  return Number(form.elements[name].value);
}

function payload() {
  return {
    project_name: form.elements.project_name.value,
    output_name: form.elements.output_name.value,
    seed: number("seed"),
    scene_seed_start: number("scene_seed_start"),
    scene_count: number("scene_count"),
    layout_modes: selected("layout_modes"),
    variants: selected("variants"),
    canvas_width_px: number("canvas_width_px"),
    canvas_height_px: number("canvas_height_px"),
    pixels_per_mm: number("pixels_per_mm"),
    columns_x: number("columns_x"),
    columns_y: number("columns_y"),
    spacing_x_mm: number("spacing_x_mm"),
    spacing_y_mm: number("spacing_y_mm"),
    storey_height_mm: number("storey_height_mm"),
    irregularity_ratio: number("irregularity_ratio"),
  };
}

function setBusy(busy, label = "Working") {
  buttons.forEach((button) => button.disabled = busy);
  state.textContent = busy ? label : "Ready";
  state.style.background = busy ? "#fff4e6" : "#edf7f4";
  state.style.color = busy ? "#9b5d13" : "#26725a";
}

function showMetrics(items) {
  metrics.innerHTML = items.map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const action = event.submitter.dataset.action;
  message.classList.remove("error");
  message.textContent = action === "preview" ? "Rendering a preview in Blender and checking IFC and DXF." : "Building and validating the configured dataset.";
  setBusy(true, action === "preview" ? "Rendering" : "Generating");
  try {
    const response = await fetch(`/api/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload()),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "The operation failed");
    if (action === "preview") {
      image.src = `${result.pipeline}?t=${Date.now()}`;
      showMetrics([
        ["Layout", result.layout],
        ["Columns", result.entities],
        ["Exchange checks", result.ifc_valid && result.dxf_valid ? "Passed" : "Failed"],
      ]);
    } else {
      showMetrics([
        ["Samples", result.sample_count],
        ["Train / val / test", `${result.split_counts.train} / ${result.split_counts.validation} / ${result.split_counts.test}`],
        ["Validation", "Passed"],
      ]);
    }
    message.textContent = result.message;
  } catch (error) {
    message.classList.add("error");
    message.textContent = error.message;
  } finally {
    setBusy(false);
  }
});

document.querySelector("#reset-button").addEventListener("click", async () => {
  const defaults = await fetch("/api/defaults").then((response) => response.json());
  for (const [name, value] of Object.entries(defaults)) {
    const fields = [...form.querySelectorAll(`[name=${name}]`)];
    if (!fields.length) continue;
    if (Array.isArray(value)) fields.forEach((field) => field.checked = value.includes(field.value));
    else fields[0].value = value;
  }
  message.classList.remove("error");
  message.textContent = "Default reference parameters restored.";
});
