import { renderMarkdownToHtml } from "../vendor/markdown.js";
import { renderCollapsibleJson } from "../vendor/json-view.js";

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

function renderViewToolbar({ modes, activeMode, onChange }) {
  const bar = document.createElement("div");
  bar.className = "view-toolbar";
  for (const mode of modes) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = mode.label;
    button.className = mode.id === activeMode ? "active" : "";
    button.addEventListener("click", () => onChange(mode.id));
    bar.appendChild(button);
  }
  return bar;
}

function renderText(container, text, resource, truncated) {
  const wrap = document.createElement("div");
  wrap.className = "text-view";
  const pre = document.createElement("pre");
  pre.textContent = text;
  let mode = "pretty";

  const applyMode = () => {
    pre.classList.toggle("text-raw", mode === "raw");
    pre.classList.toggle("text-pretty", mode === "pretty");
  };

  const toolbar = renderViewToolbar({
    modes: [
      { id: "pretty", label: "Pretty" },
      { id: "raw", label: "Raw" },
    ],
    activeMode: mode,
    onChange: (next) => {
      mode = next;
      applyMode();
      for (const button of toolbar.querySelectorAll("button")) {
        button.classList.toggle("active", button.textContent.toLowerCase() === mode);
      }
    },
  });
  applyMode();
  wrap.replaceChildren(toolbar, pre);
  if (truncated) {
    wrap.appendChild(renderEscapeBar(resource));
  }
  container.replaceChildren(wrap);
}

function renderJson(container, text, resource, truncated) {
  const wrap = document.createElement("div");
  wrap.className = "json-view-wrap";
  let parsed = null;
  let parseError = "";
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    parseError = error instanceof Error ? error.message : String(error);
  }

  const treeHost = document.createElement("div");
  treeHost.className = "json-tree-host";
  const source = document.createElement("pre");
  source.className = "json-view";
  source.hidden = true;
  source.textContent = parsed !== null ? JSON.stringify(parsed, null, 2) : text;

  let mode = parsed !== null ? "tree" : "source";
  const applyMode = () => {
    treeHost.hidden = mode !== "tree";
    source.hidden = mode !== "source";
    if (mode === "tree" && parsed !== null) {
      renderCollapsibleJson(parsed, treeHost);
    }
  };

  const modes =
    parsed !== null
      ? [
          { id: "tree", label: "Tree" },
          { id: "source", label: "Source" },
        ]
      : [{ id: "source", label: "Source" }];

  const toolbar = renderViewToolbar({
    modes,
    activeMode: mode,
    onChange: (next) => {
      mode = next;
      applyMode();
      for (const button of toolbar.querySelectorAll("button")) {
        const label = button.textContent.toLowerCase();
        button.classList.toggle("active", label === mode);
      }
    },
  });

  if (parseError) {
    const note = document.createElement("p");
    note.className = "json-parse-error";
    note.textContent = `Invalid JSON: ${parseError}`;
    wrap.appendChild(note);
  }

  applyMode();
  wrap.append(toolbar, treeHost, source);
  if (truncated) {
    wrap.appendChild(renderEscapeBar(resource));
  }
  container.replaceChildren(wrap);
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
  const wrap = document.createElement("div");
  wrap.className = "html-view";
  const iframe = document.createElement("iframe");
  let trusted = false;

  const applyMode = () => {
    if (trusted) {
      iframe.removeAttribute("sandbox");
    } else {
      iframe.sandbox = "allow-forms allow-popups";
    }
    iframe.srcdoc = html;
  };

  const toolbar = renderViewToolbar({
    modes: [
      { id: "sandbox", label: "Sandboxed" },
      { id: "trusted", label: "Trusted" },
    ],
    activeMode: trusted ? "trusted" : "sandbox",
    onChange: (next) => {
      trusted = next === "trusted";
      applyMode();
      for (const button of toolbar.querySelectorAll("button")) {
        const label = button.textContent.toLowerCase();
        button.classList.toggle(
          "active",
          (trusted && label === "trusted") || (!trusted && label === "sandboxed"),
        );
      }
    },
  });

  applyMode();
  wrap.replaceChildren(toolbar, iframe);
  container.replaceChildren(wrap);
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
