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
  const path = resolvedPath || "unknown";
  const message = `${action} via ${method} will touch:\n${path}\n\nContinue?`;
  return window.confirm(message);
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
