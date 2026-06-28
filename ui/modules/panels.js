import { framedPath } from "./router.js";
import { mutatesBadge } from "./chrome.js";

export function renderResolvedPath(container, headers = {}) {
  const resolved = headers["resolved path"];
  if (!resolved) {
    container.replaceChildren();
    container.hidden = true;
    return;
  }
  container.hidden = false;
  const dl = document.createElement("dl");
  dl.className = "resolved-path";
  const dt = document.createElement("dt");
  dt.textContent = "resolved path";
  const dd = document.createElement("dd");
  const link = document.createElement("a");
  link.href = framedPath(resolved.startsWith("/") ? resolved : `/${resolved}`);
  link.textContent = resolved;
  dd.appendChild(link);
  dl.replaceChildren(dt, dd);
  container.replaceChildren(dl);
}

export function renderNamesPanel(container, payload = {}) {
  const names = payload.names || [];
  const findings = payload.findings || [];
  const children = [];

  for (const entry of names) {
    children.push(renderNameChip(entry));
  }
  for (const finding of findings) {
    children.push(renderFindingChip(finding));
  }
  if (children.length === 0) {
    const empty = document.createElement("p");
    empty.className = "panel-empty";
    empty.textContent = "No names in this root.";
    container.replaceChildren(empty);
    return;
  }
  container.replaceChildren(...children);
}

export function namesForTarget(names, targetPath) {
  const normalized = normalizePath(targetPath);
  return (names || []).filter((entry) => {
    const target = normalizePath(entry.target);
    return target === normalized || target === `${normalized}/a`;
  });
}

export function shadowedNamesForDirectory(names, directory) {
  const scope = scopeForDirectory(directory);
  const shadowed = new Set();
  for (const entry of names || []) {
    if (entry.scope === scope && entry.inert) {
      shadowed.add(entry.name);
    }
  }
  return shadowed;
}

export function renderExplainPanel(container, payload, { loading = false, error = "" } = {}) {
  const details = document.createElement("details");
  details.className = "explain-panel";
  const summary = document.createElement("summary");
  summary.textContent = "What ran ▾";
  details.appendChild(summary);

  if (loading) {
    const pending = document.createElement("p");
    pending.className = "explain-status";
    pending.textContent = "Loading parse trace…";
    details.appendChild(pending);
    container.replaceChildren(details);
    return details;
  }
  if (error) {
    const failure = document.createElement("p");
    failure.className = "explain-status";
    failure.textContent = error;
    details.appendChild(failure);
    container.replaceChildren(details);
    return details;
  }
  if (!payload) {
    const missing = document.createElement("p");
    missing.className = "explain-status";
    missing.textContent = "Explain is unavailable on this host.";
    details.appendChild(missing);
    container.replaceChildren(details);
    return details;
  }

  if (payload.effective_pipeline) {
    const pipeline = document.createElement("pre");
    pipeline.className = "explain-pipeline";
    pipeline.textContent = payload.effective_pipeline;
    details.appendChild(pipeline);
  }

  const segments = payload.segments || [];
  if (segments.length > 0) {
    const list = document.createElement("dl");
    list.className = "explain-segments";
    for (const segment of segments) {
      const dt = document.createElement("dt");
      dt.textContent = segment.role || "segment";
      const dd = document.createElement("dd");
      dd.textContent = formatSegment(segment);
      if (segment.metadata?.mutates) {
        dd.appendChild(document.createTextNode(" "));
        dd.appendChild(mutatesBadge());
      }
      list.appendChild(dt);
      list.appendChild(dd);
    }
    details.appendChild(list);
  }

  container.replaceChildren(details);
  return details;
}

function renderNameChip(entry) {
  const chip = document.createElement("a");
  chip.className = "chip name-chip";
  if (entry.inert) {
    chip.classList.add("inert");
    chip.title = "Shadowed by a literal child; name is inert.";
  }
  chip.href = framedPath(entry.target.startsWith("/") ? entry.target : `/${entry.target}`);
  const scope = entry.scope === "." ? "" : `${entry.scope}:`;
  chip.textContent = `${scope}${entry.name} → ${entry.target}`;
  if (entry.inert) {
    const marker = document.createElement("span");
    marker.className = "name-marker";
    marker.textContent = " inert";
    chip.appendChild(marker);
  }
  return chip;
}

function renderFindingChip(finding) {
  const chip = document.createElement("div");
  chip.className = `chip finding-chip ${finding.severity || "info"}`;
  const location = finding.location || "unknown";
  const message = finding.message || "";
  if (finding.code === "escape-target") {
    const linkTarget = escapeTargetFromMessage(message);
    if (linkTarget) {
      const link = document.createElement("a");
      link.href = framedPath(linkTarget.startsWith("/") ? linkTarget : `/${linkTarget}`);
      link.textContent = `${location}: ${message}`;
      chip.replaceChildren(link);
      return chip;
    }
  }
  chip.textContent = `${location}: ${message}`;
  return chip;
}

function escapeTargetFromMessage(message) {
  const match = message.match(/resolves outside the root to (.+)$/);
  return match ? match[1].trim() : "";
}

export { escapeTargetFromMessage };

function formatSegment(segment) {
  const parts = [];
  if (segment.name) {
    parts.push(segment.name);
  }
  if (segment.raw && segment.raw !== segment.name) {
    parts.push(`(${segment.raw})`);
  }
  if (segment.metadata) {
    const meta = [];
    if (segment.metadata.arity !== undefined) {
      meta.push(`arity=${segment.metadata.arity}`);
    }
    if (segment.metadata["parse-mode"]) {
      meta.push(`parse-mode=${segment.metadata["parse-mode"]}`);
    }
    if (segment.metadata.mutates) {
      meta.push("mutates");
    }
    if (meta.length) {
      parts.push(`[${meta.join(", ")}]`);
    }
  }
  return parts.join(" ") || JSON.stringify(segment);
}

function normalizePath(path) {
  const trimmed = (path || "/").replace(/\/+$/, "");
  return trimmed || "/";
}

function scopeForDirectory(directory) {
  if (!directory || directory === "/") {
    return ".";
  }
  return directory.replace(/^\/+/, "") || ".";
}
