import { renderMarkdownToHtml } from "../vendor/markdown.js";

const TEXT_LIMIT = 256 * 1024;

export async function renderResource(container, resource) {
  if (!resource.ok) {
    renderErrorDiagnostic(container, resource, await resource.blob.text());
    return;
  }
  const type = resource.contentType.split(";")[0].trim();
  const { text, truncated } = await readText(resource.blob);
  if (type === "application/json" || resource.url.endsWith(".json")) {
    renderJson(container, text, resource, truncated);
  } else if (type.startsWith("image/")) {
    renderImage(container, resource.blob);
  } else if (type === "application/pdf") {
    renderFrame(container, resource.blob);
  } else if (type === "text/html") {
    renderHtml(container, text);
  } else if (
    type === "text/markdown" ||
    resource.url.endsWith(".md") ||
    resource.url.endsWith(".markdown")
  ) {
    renderMarkdown(container, text, resource, truncated);
  } else if (type.startsWith("text/") || type === "") {
    renderText(container, text, resource, truncated);
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

async function readText(blob) {
  const truncated = blob.size > TEXT_LIMIT;
  const text = await blob.slice(0, TEXT_LIMIT).text();
  if (truncated) {
    return {
      text: `${text}\n\n[truncated at ${TEXT_LIMIT} bytes]`,
      truncated: true,
    };
  }
  return { text, truncated: false };
}

function renderText(container, text, resource, truncated) {
  const pre = document.createElement("pre");
  pre.textContent = text;
  const nodes = [pre];
  if (truncated) {
    nodes.push(renderEscapeBar(resource));
  }
  container.replaceChildren(...nodes);
}

function renderJson(container, text, resource, truncated) {
  const pre = document.createElement("pre");
  pre.className = "json-view";
  try {
    pre.textContent = JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    pre.textContent = text;
  }
  const nodes = [pre];
  if (truncated) {
    nodes.push(renderEscapeBar(resource));
  }
  container.replaceChildren(...nodes);
}

function renderMarkdown(container, text, resource, truncated) {
  const wrap = document.createElement("div");
  wrap.className = "markdown-view";

  const article = document.createElement("article");
  article.className = "markdown-body";
  article.innerHTML = renderMarkdownToHtml(text);
  wrap.appendChild(article);

  const source = document.createElement("details");
  source.className = "markdown-source";
  const summary = document.createElement("summary");
  summary.textContent = "Source";
  const pre = document.createElement("pre");
  pre.textContent = text;
  source.replaceChildren(summary, pre);
  wrap.appendChild(source);

  if (truncated) {
    wrap.appendChild(renderEscapeBar(resource));
  }
  container.replaceChildren(wrap);
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
  container.replaceChildren(div, renderEscapeBar(resource));
}

function renderEscapeBar(resource) {
  const bar = document.createElement("div");
  bar.className = "render-escape";

  const raw = document.createElement("a");
  raw.href = resource.url;
  raw.textContent = "View raw";
  raw.target = "_blank";
  raw.rel = "noopener noreferrer";

  const download = document.createElement("a");
  download.href = URL.createObjectURL(resource.blob);
  download.download = filenameFromUrl(resource.url);
  download.textContent = "Download";

  bar.replaceChildren(raw, download);
  return bar;
}

function filenameFromUrl(url) {
  try {
    const name = new URL(url, location.origin).pathname.split("/").pop();
    return name || "download";
  } catch {
    return "download";
  }
}
