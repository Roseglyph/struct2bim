const application = document.querySelector("#application");
const form = document.querySelector("#generator-form");
const message = document.querySelector("#message");
const drawingImage = document.querySelector("#drawing-image");
const annotationImage = document.querySelector("#annotation-image");
const imageStage = document.querySelector("#image-stage");
const viewport = document.querySelector("#viewport");
const ifcCanvas = document.querySelector("#ifc-canvas");
const ifcHelp = document.querySelector("#ifc-help");
const tabButtons = [...document.querySelectorAll("[data-view]")];
const submitButtons = [...document.querySelectorAll("button[type=submit]")];
const zoomLevel = document.querySelector("#zoom-level");

let currentView = "drawing";
let imageZoom = 1;
let imagePan = { x: 0, y: 0 };
let currentModel = { columns: [], grids: [], units: "mm" };
let orbit = { azimuth: -0.72, elevation: 0.68, zoom: 1, panX: 0, panY: 0 };

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
    building_outline: form.elements.building_outline.value,
    foundation_type: form.elements.foundation_type.value,
    footing_bottom_m: number("footing_bottom_m"),
    column_embedment_m: number("column_embedment_m"),
    footing_thickness_m: number("footing_thickness_m"),
    tie_beam_width_m: number("tie_beam_width_m"),
    tie_beam_depth_m: number("tie_beam_depth_m"),
    concrete_cover_m: number("concrete_cover_m"),
    design_code: form.elements.design_code.value,
    soil_bearing_capacity_kpa: number("soil_bearing_capacity_kpa"),
    column_load_variation: number("column_load_variation"),
    footing_size_variation: number("footing_size_variation"),
    hatch_density: number("hatch_density"),
    lineweight_variation: number("lineweight_variation"),
    dimension_jitter_mm: number("dimension_jitter_mm"),
    extra_dimension_probability: number("extra_dimension_probability"),
    leader_note_probability: number("leader_note_probability"),
    revision_cloud_probability: number("revision_cloud_probability"),
    section_callout_probability: number("section_callout_probability"),
  };
}

function updateRangeOutput(input) {
  const output = form.querySelector(`output[data-for="${input.name}"]`);
  if (output) output.textContent = `${Math.round(Number(input.value) * 100)}%`;
}

function updateEnvelopeReadout() {
  const columns = number("columns_x");
  const rows = number("columns_y");
  document.querySelector("#grid-x-summary").textContent = `${columns} @ ${(number("spacing_x_mm") / 1000).toFixed(2)} m`;
  document.querySelector("#grid-y-summary").textContent = `${rows} @ ${(number("spacing_y_mm") / 1000).toFixed(2)} m`;
}

form.querySelectorAll('input[type="range"]').forEach((input) => {
  updateRangeOutput(input);
  input.addEventListener("input", () => updateRangeOutput(input));
});
["columns_x", "columns_y", "spacing_x_mm", "spacing_y_mm"].forEach((name) => {
  form.elements[name].addEventListener("input", updateEnvelopeReadout);
});

function setBusy(busy, action) {
  submitButtons.forEach((button) => button.disabled = busy);
  document.querySelector("#preview-button").textContent = busy && action === "preview" ? "Generating…" : "Quick Preview";
}

function resetImageTransform() {
  imageZoom = 1;
  imagePan = { x: 0, y: 0 };
  applyImageTransform();
}

function applyImageTransform() {
  imageStage.style.transform = `translate(${imagePan.x}px, ${imagePan.y}px) scale(${imageZoom})`;
  zoomLevel.textContent = `${Math.round((currentView === "ifc" ? orbit.zoom : imageZoom) * 100)}%`;
}

function selectView(view) {
  currentView = view;
  tabButtons.forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  const isIfc = view === "ifc";
  imageStage.hidden = isIfc;
  ifcCanvas.hidden = !isIfc;
  ifcHelp.hidden = !isIfc;
  drawingImage.hidden = view !== "drawing";
  annotationImage.hidden = view !== "annotations";
  message.hidden = isIfc;
  if (isIfc) {
    resizeIfcCanvas();
    drawIfc();
    zoomLevel.textContent = `${Math.round(orbit.zoom * 100)}%`;
  } else {
    applyImageTransform();
  }
}

tabButtons.forEach((button) => button.addEventListener("click", () => selectView(button.dataset.view)));

function modelBounds() {
  const points = [];
  currentModel.grids.forEach((grid) => points.push(grid.start, grid.end));
  currentModel.columns.forEach((column) => points.push([column.x, column.y]));
  if (!points.length) return { minX: -5000, maxX: 5000, minY: -5000, maxY: 5000 };
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

function projectionContext() {
  const bounds = modelBounds();
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerY = (bounds.minY + bounds.maxY) / 2;
  const span = Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY, 1000);
  const width = ifcCanvas.clientWidth;
  const height = ifcCanvas.clientHeight;
  const scale = Math.min(width, height) / span * 0.72 * orbit.zoom;
  const cosA = Math.cos(orbit.azimuth);
  const sinA = Math.sin(orbit.azimuth);
  const sinE = Math.sin(orbit.elevation);
  const cosE = Math.cos(orbit.elevation);
  function project(point) {
    const dx = point[0] - centerX;
    const dy = point[1] - centerY;
    const rotatedX = cosA * dx - sinA * dy;
    const rotatedY = sinA * dx + cosA * dy;
    return [
      width / 2 + orbit.panX + rotatedX * scale,
      height * 0.56 + orbit.panY - rotatedY * sinE * scale - point[2] * cosE * scale,
    ];
  }
  function depth(point) {
    const dx = point[0] - centerX;
    const dy = point[1] - centerY;
    return Math.sin(orbit.azimuth) * dx + Math.cos(orbit.azimuth) * dy;
  }
  return { project, depth, span };
}

function cuboidVertices(column, footing = false) {
  const multiplier = footing ? 4.6 : 1;
  const width = column.width * multiplier;
  const depth = column.depth * (footing ? 4.1 : 1);
  const bottom = footing ? -Math.max(350, column.height * 0.13) : 0;
  const top = footing ? 0 : column.height;
  const angle = column.rotation * Math.PI / 180;
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  const vertices = [];
  for (const z of [bottom, top]) {
    for (const [x, y] of [[-width / 2, -depth / 2], [width / 2, -depth / 2], [width / 2, depth / 2], [-width / 2, depth / 2]]) {
      vertices.push([column.x + x * cosine - y * sine, column.y + x * sine + y * cosine, z]);
    }
  }
  return vertices;
}

function drawFace(context, points, fill, stroke) {
  context.beginPath();
  points.forEach((point, index) => index ? context.lineTo(point[0], point[1]) : context.moveTo(point[0], point[1]));
  context.closePath();
  context.fillStyle = fill;
  context.fill();
  context.strokeStyle = stroke;
  context.lineWidth = 1;
  context.stroke();
}

function drawCuboid(context, vertices, project, palette) {
  const points = vertices.map(project);
  drawFace(context, [points[0], points[1], points[2], points[3]], palette.bottom, palette.edge);
  drawFace(context, [points[0], points[1], points[5], points[4]], palette.sideA, palette.edge);
  drawFace(context, [points[1], points[2], points[6], points[5]], palette.sideB, palette.edge);
  drawFace(context, [points[2], points[3], points[7], points[6]], palette.sideA, palette.edge);
  drawFace(context, [points[3], points[0], points[4], points[7]], palette.sideB, palette.edge);
  drawFace(context, [points[4], points[5], points[6], points[7]], palette.top, palette.edge);
}

function drawCylinder(context, column, project, palette) {
  const segments = 14;
  const radius = column.width / 2;
  const bottom = [];
  const top = [];
  for (let index = 0; index < segments; index += 1) {
    const angle = index / segments * Math.PI * 2;
    bottom.push(project([column.x + Math.cos(angle) * radius, column.y + Math.sin(angle) * radius, 0]));
    top.push(project([column.x + Math.cos(angle) * radius, column.y + Math.sin(angle) * radius, column.height]));
  }
  for (let index = 0; index < segments; index += 1) {
    const next = (index + 1) % segments;
    drawFace(context, [bottom[index], bottom[next], top[next], top[index]], index % 2 ? palette.sideA : palette.sideB, palette.edge);
  }
  drawFace(context, top, palette.top, palette.edge);
}

function resizeIfcCanvas() {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.floor(ifcCanvas.clientWidth * ratio));
  const height = Math.max(1, Math.floor(ifcCanvas.clientHeight * ratio));
  if (ifcCanvas.width !== width || ifcCanvas.height !== height) {
    ifcCanvas.width = width;
    ifcCanvas.height = height;
  }
}

function drawIfc() {
  if (ifcCanvas.hidden) return;
  resizeIfcCanvas();
  const context = ifcCanvas.getContext("2d");
  const ratio = ifcCanvas.width / Math.max(ifcCanvas.clientWidth, 1);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, ifcCanvas.clientWidth, ifcCanvas.clientHeight);
  const { project, depth } = projectionContext();

  context.strokeStyle = "#9eabb5";
  context.lineWidth = 1;
  context.setLineDash([5, 5]);
  currentModel.grids.forEach((grid) => {
    const first = project([grid.start[0], grid.start[1], 0]);
    const second = project([grid.end[0], grid.end[1], 0]);
    context.beginPath();
    context.moveTo(first[0], first[1]);
    context.lineTo(second[0], second[1]);
    context.stroke();
  });
  context.setLineDash([]);

  const ordered = [...currentModel.columns].sort((first, second) => depth(second) - depth(first));
  ordered.forEach((column) => {
    drawCuboid(context, cuboidVertices(column, true), project, {
      bottom: "#cbd5dd", sideA: "#d5dee5", sideB: "#bcc8d1", top: "#e4ebf0", edge: "#82929e",
    });
    const columnPalette = {
      bottom: "#5c91b8", sideA: "#397da9", sideB: "#2b678d", top: "#69a9d0", edge: "#1d5578",
    };
    if (column.shape === "circular") drawCylinder(context, column, project, columnPalette);
    else drawCuboid(context, cuboidVertices(column, false), project, columnPalette);
  });

  if (!ordered.length) {
    context.fillStyle = "#6f7d88";
    context.font = "12px Segoe UI";
    context.textAlign = "center";
    context.fillText("Generate a preview to load the interactive model", ifcCanvas.clientWidth / 2, ifcCanvas.clientHeight / 2);
  }
}

function changeZoom(direction) {
  if (currentView === "ifc") {
    orbit.zoom = Math.min(3.5, Math.max(0.35, orbit.zoom * direction));
    zoomLevel.textContent = `${Math.round(orbit.zoom * 100)}%`;
    drawIfc();
  } else {
    imageZoom = Math.min(4, Math.max(0.35, imageZoom * direction));
    applyImageTransform();
  }
}

document.querySelector("#zoom-in").addEventListener("click", () => changeZoom(1.2));
document.querySelector("#zoom-out").addEventListener("click", () => changeZoom(1 / 1.2));
document.querySelector("#fit-view").addEventListener("click", () => {
  if (currentView === "ifc") {
    orbit = { azimuth: -0.72, elevation: 0.68, zoom: 1, panX: 0, panY: 0 };
    drawIfc();
    zoomLevel.textContent = "100%";
  } else resetImageTransform();
});

viewport.addEventListener("wheel", (event) => {
  event.preventDefault();
  changeZoom(event.deltaY < 0 ? 1.1 : 1 / 1.1);
}, { passive: false });

let dragState = null;
viewport.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  dragState = { x: event.clientX, y: event.clientY, panX: imagePan.x, panY: imagePan.y, azimuth: orbit.azimuth, elevation: orbit.elevation };
  viewport.setPointerCapture(event.pointerId);
  (currentView === "ifc" ? ifcCanvas : imageStage).classList.add("dragging");
});
viewport.addEventListener("pointermove", (event) => {
  if (!dragState) return;
  const dx = event.clientX - dragState.x;
  const dy = event.clientY - dragState.y;
  if (currentView === "ifc") {
    orbit.azimuth = dragState.azimuth + dx * 0.008;
    orbit.elevation = Math.min(1.35, Math.max(0.18, dragState.elevation - dy * 0.006));
    drawIfc();
  } else {
    imagePan = { x: dragState.panX + dx, y: dragState.panY + dy };
    applyImageTransform();
  }
});
viewport.addEventListener("pointerup", (event) => {
  dragState = null;
  viewport.releasePointerCapture(event.pointerId);
  imageStage.classList.remove("dragging");
  ifcCanvas.classList.remove("dragging");
});
ifcCanvas.addEventListener("dblclick", () => {
  orbit = { azimuth: -0.72, elevation: 0.68, zoom: 1, panX: 0, panY: 0 };
  drawIfc();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const action = event.submitter.dataset.action;
  if (action === "preview") {
    form.elements.seed.value = number("seed") + 1;
  }
  const request = payload();
  message.hidden = false;
  message.classList.remove("error");
  message.textContent = action === "preview" ? `Generating a new scene from seed ${request.seed}…` : "Running the full Blender dataset build…";
  setBusy(true, action);
  const started = performance.now();
  try {
    const response = await fetch(`/api/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const text = await response.text();
    let result;
    try { result = JSON.parse(text); } catch { throw new Error(text || "The operation failed"); }
    if (!response.ok) throw new Error(result.detail || "The operation failed");
    const elapsed = ((performance.now() - started) / 1000).toFixed(2);
    if (action === "preview") {
      const stamp = Date.now();
      drawingImage.src = `${result.drawing}?t=${stamp}`;
      annotationImage.src = `${result.labels}?t=${stamp}`;
      currentModel = result.model;
      document.querySelector("#scene-label").textContent = `Seed ${result.seed}`;
      document.querySelector("#entity-label").textContent = `${result.entities} columns · automatic irregular layout`;
      message.textContent = `New drawing generated in ${elapsed}s`;
      resetImageTransform();
      if (currentView === "ifc") drawIfc();
    } else {
      message.textContent = `Dataset generated and validated in ${elapsed}s`;
    }
  } catch (error) {
    message.classList.add("error");
    message.textContent = error.message;
  } finally {
    setBusy(false, action);
  }
});

const splitter = document.querySelector("#inspector-splitter");
let inspectorWidth = 370;
splitter.addEventListener("pointerdown", (event) => {
  if (application.classList.contains("inspector-collapsed")) return;
  event.preventDefault();
  splitter.classList.add("dragging");
  const startX = event.clientX;
  const startWidth = document.querySelector("#inspector").getBoundingClientRect().width;
  const move = (pointer) => {
    inspectorWidth = Math.min(560, Math.max(280, startWidth + pointer.clientX - startX));
    document.documentElement.style.setProperty("--inspector-width", `${inspectorWidth}px`);
  };
  const stop = () => {
    splitter.classList.remove("dragging");
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", stop);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", stop, { once: true });
});

document.querySelector("#collapse-inspector").addEventListener("click", () => {
  inspectorWidth = document.querySelector("#inspector").getBoundingClientRect().width;
  application.classList.add("inspector-collapsed");
  requestAnimationFrame(() => currentView === "ifc" && drawIfc());
});
document.querySelector("#expand-inspector").addEventListener("click", () => {
  document.documentElement.style.setProperty("--inspector-width", `${inspectorWidth}px`);
  application.classList.remove("inspector-collapsed");
  requestAnimationFrame(() => currentView === "ifc" && drawIfc());
});

new ResizeObserver(() => currentView === "ifc" && drawIfc()).observe(viewport);
updateEnvelopeReadout();
selectView("drawing");
