import { currentTarget, framedPath, rawPath } from "./modules/router.js";
import { fetchResource, getCommands, getNames, getRootInfo, postTerm } from "./modules/api.js";
import { renderResource } from "./modules/render.js";
import { setDefinitionList, setStatus } from "./modules/chrome.js";

const els = {
  commands: document.querySelector("#commands-panel"),
  content: document.querySelector("#content"),
  form: document.querySelector("#goto-form"),
  input: document.querySelector("#goto-input"),
  names: document.querySelector("#names-panel"),
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
    location.href = framedPath(els.input.value);
  });
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
    ...(names.findings || []).map((finding) => {
      const div = document.createElement("div");
      div.className = `chip ${finding.severity === "error" ? "error" : ""}`;
      div.textContent = `${finding.location}: ${finding.message}`;
      return div;
    }),
  );
}

async function load() {
  const target = currentTarget();
  els.input.value = target;
  els.raw.href = rawPath(target);
  setStatus(els.status, "Loading live resource...");
  els.content.replaceChildren();
  try {
    const resource = await fetchResource(target);
    setDefinitionList(els.run, resource.headers);
    setStatus(els.status, `${resource.status} ${resource.contentType || ""}`.trim());
    await renderResource(els.content, resource);
  } catch (error) {
    setStatus(els.status, error.message);
  }
}

boot();
