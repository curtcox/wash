const TEXT_LIMIT = 256 * 1024;

export async function renderResource(container, resource) {
  const type = resource.contentType.split(";")[0].trim();
  if (type === "application/json" || resource.url.endsWith(".json")) {
    renderJson(container, await resource.blob.text());
  } else if (type.startsWith("image/")) {
    renderImage(container, resource.blob);
  } else if (type === "application/pdf") {
    renderFrame(container, resource.blob);
  } else if (type === "text/html") {
    renderHtml(container, await resource.blob.text());
  } else if (type.startsWith("text/") || type === "") {
    renderText(container, await cappedText(resource.blob));
  } else {
    renderBinary(container, resource);
  }
}

async function cappedText(blob) {
  const text = await blob.slice(0, TEXT_LIMIT).text();
  if (blob.size > TEXT_LIMIT) {
    return `${text}\n\n[truncated at ${TEXT_LIMIT} bytes]`;
  }
  return text;
}

function renderText(container, text) {
  const pre = document.createElement("pre");
  pre.textContent = text;
  container.replaceChildren(pre);
}

function renderJson(container, text) {
  const pre = document.createElement("pre");
  pre.className = "json-view";
  try {
    pre.textContent = JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    pre.textContent = text;
  }
  container.replaceChildren(pre);
}

function renderImage(container, blob) {
  const img = document.createElement("img");
  img.src = URL.createObjectURL(blob);
  container.replaceChildren(img);
}

function renderFrame(container, blob) {
  const iframe = document.createElement("iframe");
  iframe.src = URL.createObjectURL(blob);
  container.replaceChildren(iframe);
}

function renderHtml(container, html) {
  const iframe = document.createElement("iframe");
  iframe.sandbox = "allow-forms allow-popups";
  iframe.srcdoc = html;
  container.replaceChildren(iframe);
}

function renderBinary(container, resource) {
  const div = document.createElement("div");
  div.className = "binary";
  div.textContent = `Binary resource, ${resource.blob.size} bytes.`;
  container.replaceChildren(div);
}
