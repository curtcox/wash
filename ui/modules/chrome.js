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
