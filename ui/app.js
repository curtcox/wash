import { canonicalizeInput, currentTarget, displayInput, framedPath, rawPath } from "./modules/router.js";
import { fetchResource, getCommands, getNames, getRootInfo, postTerm } from "./modules/api.js";
import { renderResource } from "./modules/render.js";
import { setDefinitionList, setStatus } from "./modules/chrome.js";

const els = {
  backing: document.querySelector("#backing-panel"),
  commands: document.querySelector("#commands-panel"),
  content: document.querySelector("#content"),
  form: document.querySelector("#goto-form"),
  input: document.querySelector("#goto-input"),
  names: document.querySelector("#names-panel"),
  options: document.querySelector("#path-options"),
  preview: document.querySelector("#canonical-preview"),
  raw: document.querySelector("#raw-link"),
  reload: document.querySelector("#reload-button"),
  root: document.querySelector("#root-panel"),
  run: document.querySelector("#run-panel"),
  shell: document.querySelector("#shell-button"),
  status: document.querySelector("#status"),
};

async function boot() {
  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    location.href = framedPath(canonicalizeInput(els.input.value));
  });
  els.input.addEventListener("input", updatePreview);
  els.reload.addEventListener("click", () => load());
  els.shell.addEventListener("click", async () => {
    const result = await postTerm(currentTarget());
    window.alert(result.message || result.command || "No terminal launcher is configured.");
  });
  await loadChrome();
  await load();
}

async function loadChrome() {
  const root = await getRootInfo().catch((error) => ({ error: error.message }));
  setDefinitionList(els.root, {
    path: root.root || "unknown",
    origin: location.origin,
    status: root.error || "ready",
  });
  const [commands, names] = await Promise.all([
    getCommands().catch(() => ({ commands: [] })),
    getNames().catch(() => ({ findings: [] })),
  ]);
  populateAutocomplete(commands, names);
  els.commands.replaceChildren(
    ...commands.commands.map((command) => {
      const a = document.createElement("a");
      a.className = "chip";
      a.href = framedPath(command.name);
      a.textContent = `${command.name}${command.mutates ? " mutates" : ""}`;
      return a;
    }),
  );
  els.names.replaceChildren(
    ...(names.names || []).map((entry) => {
      const div = document.createElement("div");
      div.className = `chip ${entry.inert ? "inert" : ""}`;
      div.textContent = `${entry.scope}:${entry.name} -> ${entry.target}`;
      return div;
    }),
    ...(names.findings || []).map((finding) => {
      const div = document.createElement("div");
      div.className = `chip ${finding.severity === "error" ? "error" : ""}`;
      div.textContent = `${finding.location}: ${finding.message}`;
      return div;
    }),
  );
}

function populateAutocomplete(commands, names) {
  const values = new Set();
  for (const command of commands.commands || []) {
    values.add(`/${command.name}`);
  }
  for (const finding of names.findings || []) {
    const location = finding.location || "";
    const name = location.includes(":") ? location.split(":").pop() : "";
    if (name && !name.includes("/")) {
      values.add(`/${name}`);
    }
  }
  for (const entry of names.names || []) {
    values.add(`/${entry.name}`);
  }
  els.options.replaceChildren(
    ...Array.from(values).sort().map((value) => {
      const option = document.createElement("option");
      option.value = value;
      return option;
    }),
  );
}

async function load() {
  const target = currentTarget();
  els.input.value = displayInput(target);
  updatePreview();
  els.raw.href = rawPath(target);
  setStatus(els.status, "Loading live resource...");
  els.content.replaceChildren();
  try {
    const resource = await fetchResource(target);
    setDefinitionList(els.run, resource.headers);
    setDefinitionList(els.backing, backingFilesFromHeaders(resource.headers));
    setStatus(els.status, `${resource.status} ${resource.contentType || ""}`.trim());
    await renderResource(els.content, resource);
  } catch (error) {
    setStatus(els.status, error.message);
  }
}

function updatePreview() {
  els.preview.value = canonicalizeInput(els.input.value);
  els.preview.textContent = els.preview.value;
}

function backingFilesFromHeaders(headers) {
  const backing = {};
  if (headers.source) {
    backing.source = headers.source;
  }
  if (headers["resolved path"]) {
    backing["resolved path"] = headers["resolved path"];
  }
  if (headers.command) {
    backing.command = headers.command;
  }
  if (headers.pipeline) {
    backing.pipeline = headers.pipeline;
  }
  if (Object.keys(backing).length === 0) {
    backing.status = "No backing files reported";
  }
  return backing;
}

boot();
