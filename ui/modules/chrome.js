export function setStatus(node, message) {
  node.textContent = message;
}

export function setDefinitionList(node, values) {
  const children = [];
  for (const [key, value] of Object.entries(values)) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent = String(value || "");
    children.push(dt, dd);
  }
  node.replaceChildren(...children);
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
