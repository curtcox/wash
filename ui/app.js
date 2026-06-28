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
  getExplain,
  getHelp,
  getNames,
  getRootInfo,
  postAppend,
  postNameNew,
  postNameRm,
  postNameSet,
  postResource,
  postTerm,
  putResource,
  deleteResource,
} from "./modules/api.js";
import {
  confirmMutation,
  renderIntegrityBanner,
  renderPostureBanner,
} from "./modules/chrome.js";
import { bundlePathWarning, isNonLocalOrigin, loadManifest } from "./modules/integrity.js";
import { hideFilesBrowser, renderFilesBrowser } from "./modules/files.js";
import { renderAuthorPanel } from "./modules/editor.js";
import {
  renderExplainPanel,
  renderNamesPanel,
  renderResolvedPath,
} from "./modules/panels.js";
import { renderResource } from "./modules/render.js";
import {
  buildThreadModel,
  detectNodeKind,
  directoryFor,
  isThreadContext,
  renderThread,
  shellDirectory,
} from "./modules/thread.js";
import { setDefinitionList, setStatus } from "./modules/chrome.js";

const api = { fetchListing, fetchText };

const els = {
  integrity: document.querySelector("#integrity-banner"),
  posture: document.querySelector("#posture-banner"),
  author: document.querySelector("#author-panel"),
  backing: document.querySelector("#backing-panel"),
  commands: document.querySelector("#commands-panel"),
  content: document.querySelector("#content"),
  explain: document.querySelector("#explain-panel"),
  files: document.querySelector("#files-panel"),
  form: document.querySelector("#goto-form"),
  help: document.querySelector("#help-panel"),
  input: document.querySelector("#goto-input"),
  kind: document.querySelector("#node-kind"),
  names: document.querySelector("#names-panel"),
  options: document.querySelector("#path-options"),
  preview: document.querySelector("#canonical-preview"),
  raw: document.querySelector("#raw-link"),
  reload: document.querySelector("#reload-button"),
  resolved: document.querySelector("#resolved-panel"),
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
let namesPayload = { names: [], findings: [] };
let explainAvailable = true;
let bundleManifest = [];

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
  bundleManifest = await loadManifest();
  renderPostureBanner(els.posture, { nonLocal: isNonLocalOrigin() });
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
  const [commands, names, help] = await Promise.all([
    getCommands().catch(() => ({ commands: [] })),
    getNames().catch(() => ({ findings: [], names: [] })),
    getHelp().catch(() => null),
  ]);
  commandCatalog = commands.commands || [];
  namesPayload = names;
  populateAutocomplete(commands, names);
  renderNamesPanel(els.names, names);
  renderHelpPanel(help);
  els.commands.replaceChildren(
    ...commandCatalog.map((command) => {
      const a = document.createElement("a");
      a.className = "chip";
      a.href = framedPath(command.name);
      a.textContent = `${command.name}${command.mutates ? " mutates" : ""}`;
      return a;
    }),
  );
}

function renderHelpPanel(help) {
  if (!help) {
    els.help.replaceChildren();
    return;
  }
  const hint = document.createElement("p");
  hint.className = "help-hint";
  hint.textContent = help.hint || "Structural help is available for installed commands.";
  const list = document.createElement("div");
  list.className = "panel-list";
  for (const name of help.commands || []) {
    const link = document.createElement("a");
    link.className = "chip";
    link.href = framedPath(name);
    link.textContent = name;
    list.appendChild(link);
  }
  els.help.replaceChildren(hint, list);
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
  hideAuthorPanel();
  hideFilesBrowser(els.files);
  els.thread.replaceChildren();
  els.thread.hidden = true;
  renderExplainPanel(els.explain, null, { loading: true });
  renderResolvedPath(els.resolved, {});
  renderIntegrityBanner(els.integrity, bundlePathWarning(target, bundleManifest));

  try {
    const resource = await fetchResource(target);
    lastHeaders = resource.headers;
    renderResolvedPath(els.resolved, resource.headers);
    const resolvedTarget = resource.headers["resolved path"] || target;
    renderIntegrityBanner(
      els.integrity,
      bundlePathWarning(resolvedTarget, bundleManifest) ||
        bundlePathWarning(target, bundleManifest),
    );
    const kind = detectNodeKind(target, { commands: commandCatalog, resource });
    els.kind.textContent = `Kind: ${kind}`;
    setDefinitionList(els.run, resource.headers);
    setDefinitionList(els.backing, backingFilesFromHeaders(resource.headers));
    setStatus(
      els.status,
      `${resource.status} ${resource.contentType || ""}`.trim() +
        " — reload to recompute",
    );
    loadExplain(target);

    if (viewMode === "files") {
      hideAuthorPanel();
      await renderFilesBrowser(els.files, target, api, { names: namesPayload.names });
      els.content.hidden = true;
      els.thread.hidden = true;
      return;
    }

    const showThread = viewMode !== "content" && isThreadContext(kind);
    if (showThread) {
      const model = await buildThreadModel(target, api);
      renderThread(els.thread, model, {
        activePath: target,
        names: namesPayload.names,
      });
    } else {
      els.thread.hidden = true;
    }

    els.content.hidden = false;
    await renderResource(els.content, resource);
    await renderAuthor(target, kind, resource);
  } catch (error) {
    setStatus(els.status, error.message);
    els.kind.textContent = "";
    hideAuthorPanel();
    renderExplainPanel(els.explain, null, { error: error.message });
  }
}

async function renderAuthor(target, kind, resource) {
  let initialText = "";
  if (resource.ok && resource.blob) {
    try {
      initialText = await resource.blob.text();
    } catch {
      initialText = "";
    }
  }
  const resolvedPath =
    resource.headers?.["resolved path"] || rawPath(target);
  renderAuthorPanel(
    els.author,
    {
      target,
      kind,
      resourceOk: resource.ok,
      resolvedPath,
      initialText,
      names: namesPayload.names,
    },
    {
      onSave: async (body, { exists, resolvedPath: resolved }) => {
        if (
          !(await confirmMutation({
            action: exists ? "Save" : "Create",
            method: "PUT",
            resolvedPath: resolved,
          }))
        ) {
          return;
        }
        await putResource(target, body);
        location.reload();
      },
      onDelete: async ({ resolvedPath: resolved }) => {
        if (
          !(await confirmMutation({
            action: "Delete",
            method: "DELETE",
            resolvedPath: resolved,
          }))
        ) {
          return;
        }
        await deleteResource(target);
        location.href = framedPath(directoryFor(target));
      },
      onRename: async (newPath, { from }) => {
        const resolved = rawPath(newPath);
        if (
          !(await confirmMutation({
            action: "Rename (PUT new path)",
            method: "PUT",
            resolvedPath: resolved,
          }))
        ) {
          return;
        }
        const body = await fetchText(from).catch(() => "");
        await putResource(newPath, body);
        if (
          !(await confirmMutation({
            action: "Rename (DELETE old path)",
            method: "DELETE",
            resolvedPath: from,
          }))
        ) {
          return;
        }
        await deleteResource(from);
        location.href = framedPath(newPath);
      },
      onRun: async (body, { resolvedPath: resolved }) => {
        if (
          !(await confirmMutation({
            action: "Run",
            method: "POST",
            resolvedPath: resolved,
          }))
        ) {
          return;
        }
        await postResource(target, body);
        location.reload();
      },
      onAppend: async (parentPath, body, { resolvedPath: resolved }) => {
        if (
          !(await confirmMutation({
            action: "Append SDT node",
            method: "POST",
            resolvedPath: resolved,
          }))
        ) {
          return;
        }
        const payload = await postAppend(parentPath, body);
        const locationPath = payload.location || payload.created;
        location.href = framedPath(`${locationPath}/a`);
      },
      onNameNew: async (scope, name, nameTarget) => {
        if (
          !(await confirmMutation({
            action: "Create name",
            method: "POST",
            resolvedPath: `${scope}:${name} → ${nameTarget}`,
          }))
        ) {
          return;
        }
        await postNameNew(scope, name, nameTarget);
        location.reload();
      },
      onNameSet: async (scope, name, nameTarget) => {
        if (
          !(await confirmMutation({
            action: "Retarget name",
            method: "POST",
            resolvedPath: `${scope}:${name} → ${nameTarget}`,
          }))
        ) {
          return;
        }
        await postNameSet(scope, name, nameTarget);
        location.reload();
      },
      onNameRm: async (scope, name) => {
        if (
          !(await confirmMutation({
            action: "Drop name",
            method: "POST",
            resolvedPath: `${scope}:${name}`,
          }))
        ) {
          return;
        }
        await postNameRm(scope, name);
        location.reload();
      },
    },
  );
}

function hideAuthorPanel() {
  els.author.hidden = true;
  els.author.replaceChildren();
}

async function loadExplain(target) {
  if (!explainAvailable || target === "/") {
    renderExplainPanel(els.explain, null);
    return;
  }
  renderExplainPanel(els.explain, null, { loading: true });
  try {
    const payload = await getExplain(target);
    renderExplainPanel(els.explain, payload);
  } catch {
    explainAvailable = false;
    renderExplainPanel(els.explain, null);
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
