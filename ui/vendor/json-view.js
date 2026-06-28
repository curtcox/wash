function formatPrimitive(value) {
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  return String(value);
}

function buildCollapsibleNode(key, value) {
  if (Array.isArray(value)) {
    const details = document.createElement("details");
    details.className = "json-node";
    details.open = value.length <= 3;
    const summary = document.createElement("summary");
    summary.textContent = `${key}: [${value.length}]`;
    details.appendChild(summary);
    const list = document.createElement("div");
    list.className = "json-children";
    value.forEach((entry, index) => {
      list.appendChild(buildCollapsibleNode(String(index), entry));
    });
    details.appendChild(list);
    return details;
  }
  if (value !== null && typeof value === "object") {
    const keys = Object.keys(value);
    const details = document.createElement("details");
    details.className = "json-node";
    details.open = keys.length <= 3;
    const summary = document.createElement("summary");
    summary.textContent = `${key}: {${keys.length}}`;
    details.appendChild(summary);
    const list = document.createElement("div");
    list.className = "json-children";
    for (const childKey of keys) {
      list.appendChild(buildCollapsibleNode(childKey, value[childKey]));
    }
    details.appendChild(list);
    return details;
  }
  const leaf = document.createElement("div");
  leaf.className = "json-leaf";
  leaf.textContent = `${key}: ${formatPrimitive(value)}`;
  return leaf;
}

export function renderCollapsibleJson(value, container) {
  const root = document.createElement("div");
  root.className = "json-tree";
  if (Array.isArray(value)) {
    root.appendChild(buildCollapsibleNode("root", value));
  } else if (value !== null && typeof value === "object") {
    for (const key of Object.keys(value)) {
      root.appendChild(buildCollapsibleNode(key, value[key]));
    }
  } else {
    const leaf = document.createElement("div");
    leaf.className = "json-leaf";
    leaf.textContent = formatPrimitive(value);
    root.appendChild(leaf);
  }
  container.replaceChildren(root);
}
