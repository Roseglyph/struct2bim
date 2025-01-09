const form = document.querySelector("#generator-form");
const message = document.querySelector("#message");
const state = document.querySelector("#result-state");
const drawingImage = document.querySelector("#preview-image");
const annotationImage = document.querySelector("#annotation-image");
const ifcPreview = document.querySelector("#ifc-preview");
const metrics = document.querySelector("#result-metrics");
const buttons = [...document.querySelectorAll("button[type=submit]")];

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
    canvas_width_px: number("canvas_width_px"),
    canvas_height_px: number("canvas_height_px"),
    pixels_per_mm: number("pixels_per_mm"),
    columns_x: number("columns_x"),
    columns_y: number("columns_y"),
    spacing_x_mm: number("spacing_x_mm"),
    spacing_y_mm: number("spacing_y_mm"),
    storey_height_mm: number("storey_height_mm"),
    irregularity_ratio: number("irregularity_ratio"),
    drawing_complexity: number("drawing_complexity"),
    rotation_probability: number("rotation_probability"),
    hatch_probability: number("hatch_probability"),
    footing_overlap_probability: number("footing_overlap_probability"),
    diagonal_beam_probability: number("diagonal_beam_probability"),
    occupancy_probability: number("occupancy_probability"),
  };
}

function setBusy(busy, label = "Working") {
  buttons.forEach((button) => button.disabled = busy);
  state.lastChild.textContent = busy ? label : "Ready";
  state.style.color = busy ? "#d18a48" : "#65b894";
}

function showMetrics(items) {
  metrics.innerHTML = items.map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");
  metrics.insertAdjacentHTML("beforeend", '<div class="status-spacer"></div><div><span>Exchange</span><strong>IFC4 + DXF</strong></div>');
}

function updateRangeOutput(input) {
  const output = form.querySelector(`output[data-for="${input.name}"]`);
  if (output) output.textContent = `${Math.round(Number(input.value) * 100)}%`;
}

form.querySelectorAll('input[type="range"]').forEach((input) => {
  updateRangeOutput(input);
  input.addEventListener("input", () => updateRangeOutput(input));
});

for (const [field, readout] of [["project_name", "project-readout"], ["seed", "seed-readout"]]) {
  form.elements[field].addEventListener("input", (event) => {
    document.querySelector(`#${readout}`).textContent = event.target.value;
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const action = event.submitter.dataset.action;
  message.classList.remove("error");
  message.textContent = action === "preview" ? "Building a fast 2D recipe preview." : "Running Blender and validating the complete dataset.";
  setBusy(true, action === "preview" ? "Previewing" : "Generating");
  const started = performance.now();
  try {
    const response = await fetch(`/api/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload()),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "The operation failed");
    const elapsed = ((performance.now() - started) / 1000).toFixed(2);
    if (action === "preview") {
      const stamp = Date.now();
      drawingImage.src = `${result.drawing}?t=${stamp}`;
      annotationImage.src = `${result.labels}?t=${stamp}`;
      ifcPreview.src = result.ifc_render;
      showMetrics([
        ["Layout", "automatic"],
        ["Columns", result.entities],
        ["Preview", `${elapsed}s`],
        ["IFC / DXF", "on generation"],
      ]);
    } else {
      showMetrics([
        ["Samples", result.sample_count],
        ["Train / val / test", `${result.split_counts.train} / ${result.split_counts.validation} / ${result.split_counts.test}`],
        ["Dataset", "validated"],
      ]);
    }
    message.textContent = `${result.message} in ${elapsed}s`;
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
    const field = form.elements[name];
    if (!field || Array.isArray(value)) continue;
    field.value = value;
    if (field.type === "range") updateRangeOutput(field);
  }
  document.querySelector("#project-readout").textContent = defaults.project_name;
  document.querySelector("#seed-readout").textContent = defaults.seed;
  message.classList.remove("error");
  message.textContent = "Default automatic recipe restored.";
});

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

document.querySelectorAll("[data-split]").forEach((splitter) => {
  splitter.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    splitter.classList.add("dragging");
    const mode = splitter.dataset.split;
    const studio = document.querySelector(".studio");
    const stack = document.querySelector(".output-stack");
    const move = (pointer) => {
      if (mode === "pipeline") {
        const top = document.querySelector(".workspace").getBoundingClientRect().top;
        document.documentElement.style.setProperty("--pipeline-height", `${clamp(pointer.clientY - top, 86, 240)}px`);
      } else if (mode === "inspector") {
        const left = studio.getBoundingClientRect().left;
        document.documentElement.style.setProperty("--inspector-width", `${clamp(pointer.clientX - left, 220, 430)}px`);
      } else if (mode === "outputs") {
        const right = studio.getBoundingClientRect().right;
        document.documentElement.style.setProperty("--right-width", `${clamp(right - pointer.clientX, 260, 560)}px`);
      } else if (mode === "outputs-height") {
        const box = stack.getBoundingClientRect();
        const percent = clamp((pointer.clientY - box.top) / box.height * 100, 25, 75);
        document.documentElement.style.setProperty("--output-top", `${percent}%`);
      }
    };
    const stop = () => {
      splitter.classList.remove("dragging");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
  });
});
