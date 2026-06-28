export function setStatus(node, message) {
  node.textContent = message;
}

export function setDefinitionList(node, values) {
  const children = [];
  for (const [key, value] of Object.entries(values)) {
    if (value === "" || value === undefined || value === null) {
      continue;
    }
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent = String(value);
    children.push(dt, dd);
  }
  node.replaceChildren(...children);
}

export function stderrMergeNote(target, explainPayload) {
  const segments = (target || "").split("/").filter(Boolean);
  if (segments.includes("&")) {
    return "Pipeline uses /& merge boundary; stderr is merged into stdout.";
  }
  for (const segment of explainPayload?.segments || []) {
    if (segment.metadata?.stderr === "merge") {
      return "Command metadata sets stderr merge; streams are merged.";
    }
  }
  return "";
}

export function runPanelValues(headers = {}, target, explainPayload) {
  const values = { ...headers };
  const mergeNote = stderrMergeNote(target, explainPayload);
  if (mergeNote) {
    values["stderr merge"] = mergeNote;
  }
  return values;
}

export function mutatesBadge({ label = "mutates" } = {}) {
  const badge = document.createElement("span");
  badge.className = "mutates-badge";
  badge.textContent = label;
  return badge;
}

export async function confirmMutation({ action, method, resolvedPath }) {
  return new Promise((resolve) => {
    const path = resolvedPath || "unknown";
    const host = document.createElement("div");
    host.className = "mutation-confirm";
    host.setAttribute("role", "alertdialog");
    host.setAttribute("aria-modal", "false");
    host.setAttribute("aria-labelledby", "mutation-confirm-title");

    const panel = document.createElement("section");
    panel.className = "mutation-confirm-panel";

    const title = document.createElement("h2");
    title.id = "mutation-confirm-title";
    title.appendChild(mutatesBadge());
    title.appendChild(document.createTextNode(` ${action}`));

    const dl = document.createElement("dl");
    dl.className = "mutation-confirm-details";
    appendDefinition(dl, "method", method || "unknown");
    appendDefinition(dl, "resolved path", path);

    const actions = document.createElement("div");
    actions.className = "mutation-confirm-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Cancel";
    const proceed = document.createElement("button");
    proceed.type = "button";
    proceed.className = "danger-action";
    proceed.textContent = "Continue";
    actions.replaceChildren(cancel, proceed);

    function finish(value) {
      host.remove();
      resolve(value);
    }

    cancel.addEventListener("click", () => finish(false));
    proceed.addEventListener("click", () => finish(true));
    host.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        finish(false);
      }
    });

    panel.replaceChildren(title, dl, actions);
    host.appendChild(panel);
    document.body.appendChild(host);
    cancel.focus();
  });
}

function appendDefinition(node, key, value) {
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = key;
  dd.textContent = String(value);
  node.appendChild(dt);
  node.appendChild(dd);
}

export function renderPostureBanner(node, { nonLocal = false } = {}) {
  if (!nonLocal) {
    node.hidden = true;
    node.replaceChildren();
    return;
  }
  node.hidden = false;
  node.className = "banner banner-warning";
  node.textContent =
    "This wash UI assumes a trusted localhost origin. You are not on localhost — proceed only if you trust this server.";
}

export function renderIntegrityBanner(node, message) {
  if (!message) {
    node.hidden = true;
    node.replaceChildren();
    return;
  }
  node.hidden = false;
  node.className = "banner banner-integrity";
  node.textContent = message;
}
