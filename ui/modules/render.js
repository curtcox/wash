const TEXT_LIMIT = 256 * 1024;

export async function renderResource(container, resource) {
  if (!resource.ok) {
    renderErrorDiagnostic(container, resource, await resource.blob.text());
    return;
  }
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

function renderErrorDiagnostic(container, resource, text) {
  const section = document.createElement("section");
  section.className = "diagnostic error";
  const title = document.createElement("h2");
  title.textContent = `HTTP ${resource.status}`;
  const pre = document.createElement("pre");
  try {
    const diagnostic = JSON.parse(text);
    pre.textContent = JSON.stringify(
      {
        error: diagnostic.error,
        pipeline: diagnostic.pipeline,
        command: diagnostic.command,
        exit_status: diagnostic.exit_status,
        stdout: diagnostic.stdout,
        stderr: diagnostic.stderr,
      },
      null,
      2,
    );
  } catch {
    pre.textContent = text;
  }
  section.replaceChildren(title, pre);
  container.replaceChildren(section);
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
