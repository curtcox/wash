import {
  canonicalizeInput,
  currentTarget,
  currentViewMode,
  displayInput,
  framedPath,
  rawPath,
  viewModeHref,
} from "./modules/router.js";
import {
  fetchListing,
  fetchResource,
  fetchText,
  getCommands,
  getNames,
  getRootInfo,
  postTerm,
} from "./modules/api.js";
import { hideFilesBrowser, renderFilesBrowser } from "./modules/files.js";
import { renderResource } from "./modules/render.js";
import {
  buildThreadModel,
  detectNodeKind,
  isThreadContext,
  renderThread,
  shellDirectory,
} from "./modules/thread.js";
import { setDefinitionList, setStatus } from "./modules/chrome.js";

const api = { fetchListing, fetchText };

const els = {
  backing: document.querySelector("#backing-panel"),
  commands: document.querySelector("#commands-panel"),
  content: document.querySelector("#content"),
  files: document.querySelector("#files-panel"),
  form: document.querySelector("#goto-form"),
  input: document.querySelector("#goto-input"),
  kind: document.querySelector("#node-kind"),
  names: document.querySelector("#names-panel"),
  options: document.querySelector("#path-options"),
  preview: document.querySelector("#canonical-preview"),
  raw: document.querySelector("#raw-link"),
  reload: document.querySelector("#reload-button"),
  root: document.querySelector("#root-panel"),
  run: document.querySelector("#run-panel"),
  shell: document.querySelector("#shell-button"),
  status: document.querySelector("#status"),
  thread: document.querySelector("#thread-panel"),
  viewContent: document.querySelector("#content-view-link"),
  viewFiles: document.querySelector("#files-view-link"),
  viewThread: document.querySelector("#thread-view-link"),
};

let commandCatalog = [];

async function boot() {
  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    location.href = framedPath(canonicalizeInput(els.input.value));
  });
  els.input.addEventListener("input", updatePreview);
  els.reload.addEventListener("click", () => load());
  window.addEventListener("hashchange", () => load());
  els.shell.addEventListener("click", async () => {
    const directory = shellDirectory(currentTarget(), lastHeaders);
    const result = await postTerm(directory);
    window.alert(result.message || result.command || "No terminal launcher is configured.");
  });
  await loadChrome();
  await load();
}

let lastHeaders = {};

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
  commandCatalog = commands.commands || [];
  populateAutocomplete(commands, names);
  els.commands.replaceChildren(
    ...commandCatalog.map((command) => {
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
    ...Array.from(values)
      .sort()
      .map((value) => {
        const option = document.createElement("option");
        option.value = value;
        return option;
      }),
  );
}

async function load() {
  const target = currentTarget();
  const viewMode = currentViewMode();
  els.input.value = displayInput(target);
  updatePreview();
  updateViewLinks(viewMode);
  els.raw.href = rawPath(target);
  setStatus(els.status, "Loading live resource...");
  els.content.replaceChildren();
  hideFilesBrowser(els.files);
  els.thread.replaceChildren();
  els.thread.hidden = true;

  try {
    const resource = await fetchResource(target);
    lastHeaders = resource.headers;
    const kind = detectNodeKind(target, { commands: commandCatalog, resource });
    els.kind.textContent = `Kind: ${kind}`;
    setDefinitionList(els.run, resource.headers);
    setDefinitionList(els.backing, backingFilesFromHeaders(resource.headers));
    setStatus(
      els.status,
      `${resource.status} ${resource.contentType || ""}`.trim() +
        " — reload to recompute",
    );

    if (viewMode === "files") {
      await renderFilesBrowser(els.files, target, api);
      els.content.hidden = true;
      els.thread.hidden = true;
      return;
    }

    const showThread = viewMode !== "content" && isThreadContext(kind);
    if (showThread) {
      const model = await buildThreadModel(target, api);
      renderThread(els.thread, model, { activePath: target });
    } else {
      els.thread.hidden = true;
    }

    els.content.hidden = false;
    await renderResource(els.content, resource);
  } catch (error) {
    setStatus(els.status, error.message);
    els.kind.textContent = "";
  }
}

function updateViewLinks(viewMode) {
  const activeMode = viewMode === "auto" ? "thread" : viewMode;
  const links = [
    ["thread", els.viewThread],
    ["files", els.viewFiles],
    ["content", els.viewContent],
  ];
  for (const [mode, node] of links) {
    node.href = viewModeHref(mode);
    const active = activeMode === mode;
    node.classList.toggle("active", active);
    node.setAttribute("aria-current", active ? "page" : "false");
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
