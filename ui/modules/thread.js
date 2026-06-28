import { framedPath } from "./router.js";

const ORDINAL_PATTERN = /^[0-9]+$|^[A-Z]$/;

export function isOrdinalSegment(name) {
  return ORDINAL_PATTERN.test(name);
}

export function normalizeTarget(target) {
  const trimmed = (target || "/").replace(/\/+$/, "");
  return trimmed || "/";
}

export function nodeDirectoryFor(target) {
  const parts = normalizeTarget(target).split("/").filter(Boolean);
  if (parts.length && (parts[parts.length - 1] === "a" || parts[parts.length - 1] === "b")) {
    parts.pop();
  }
  return parts.length ? `/${parts.join("/")}` : "/";
}

export function directoryFor(target) {
  const normalized = normalizeTarget(target);
  if (normalized === "/") {
    return "/";
  }
  const parts = normalized.split("/").filter(Boolean);
  const last = parts[parts.length - 1];
  if (last === "a" || last === "b") {
    parts.pop();
    return parts.length ? `/${parts.join("/")}` : "/";
  }
  if (isOrdinalSegment(last)) {
    return parts.length ? `/${parts.join("/")}` : "/";
  }
  parts.pop();
  return parts.length ? `/${parts.join("/")}` : "/";
}

export function collectMainLine(nodeDir) {
  const mainLine = [];
  let current = nodeDir;
  while (current && current !== "/") {
    const parts = current.split("/").filter(Boolean);
    const ordinal = parts[parts.length - 1];
    if (!isOrdinalSegment(ordinal)) {
      break;
    }
    mainLine.unshift({ ordinal, path: current });
    parts.pop();
    current = parts.length ? `/${parts.join("/")}` : "/";
  }
  return { collectionRoot: current, mainLine };
}

export function detectNodeKind(target, { commands = [], resource } = {}) {
  const path = normalizeTarget(target);
  const segments = path.split("/").filter(Boolean);
  if (segments[0] === "env") {
    return "env-config";
  }
  const commandNames = new Set((commands || []).map((entry) => entry.name));
  if (segments.length && commandNames.has(segments[0])) {
    return "command";
  }
  const nodeDir = nodeDirectoryFor(path);
  const nodeParts = nodeDir.split("/").filter(Boolean);
  const lastSegment = nodeParts[nodeParts.length - 1] || "";
  if (isOrdinalSegment(lastSegment)) {
    return "sdt-node";
  }
  if (resource?.listing) {
    const ordinals = resource.listing.filter(
      (entry) => entry.isDir && isOrdinalSegment(entry.name),
    );
    if (ordinals.length > 0 || resource.listing.some((entry) => entry.name === "a")) {
      return ordinals.length > 0 ? "sdt-collection" : "sdt-node";
    }
    return "directory";
  }
  if (path.endsWith("/")) {
    return "directory";
  }
  return "plain-file";
}

export function shellDirectory(target, headers = {}) {
  if (headers.pipeline || headers.command) {
    return ".";
  }
  const dir = directoryFor(target);
  return dir === "/" ? "." : dir.replace(/^\/+/, "");
}

export function activeSiblingBranch(activePath, parentPath, siblings = []) {
  const nodeDir = nodeDirectoryFor(activePath);
  const parent = normalizeTarget(parentPath);
  for (const sibling of siblings) {
    const branchPath =
      parent === "/"
        ? `/${sibling}`
        : `${parent}/${sibling}`.replace(/\/+/g, "/");
    if (nodeDir === branchPath || nodeDir.startsWith(`${branchPath}/`)) {
      return sibling;
    }
  }
  return null;
}

export function isThreadContext(kind) {
  return kind === "sdt-node" || kind === "sdt-collection";
}

export async function buildThreadModel(target, api) {
  const nodeDir = nodeDirectoryFor(target);
  const { collectionRoot, mainLine } = collectMainLine(nodeDir);
  if (mainLine.length === 0) {
    return null;
  }

  const enriched = [];
  for (const node of mainLine) {
    const parentPath = node.path.split("/").slice(0, -1).join("/") || "/";
    const listing = await api.fetchListing(parentPath).catch(() => ({ entries: [] }));
    const siblings = listing.entries
      .filter((entry) => entry.isDir && isOrdinalSegment(entry.name))
      .map((entry) => entry.name)
      .filter((name) => name !== node.ordinal)
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));

    const aText = await api.fetchText(`${node.path}/a`).catch(() => "");
    const bText = await api.fetchText(`${node.path}/b`).catch(() => "");
    enriched.push({
      ...node,
      aPreview: summarizeText(aText),
      bMeta: parseProvenance(bText),
      siblings,
    });
  }

  return {
    collectionRoot,
    currentPath: normalizeTarget(target),
    mainLine: enriched,
    nodeDir,
  };
}

export function renderThread(container, model, { activePath, names = [] } = {}) {
  if (!model) {
    container.replaceChildren();
    container.hidden = true;
    return;
  }
  container.hidden = false;
  const article = document.createElement("article");
  article.className = "thread";

  const header = document.createElement("header");
  header.className = "thread-header";
  const title = document.createElement("h2");
  title.textContent = "Thread";
  const rootLink = document.createElement("a");
  rootLink.href = framedPath(model.collectionRoot);
  rootLink.textContent = model.collectionRoot === "/" ? "root" : model.collectionRoot;
  header.replaceChildren(title, rootLink);
  article.appendChild(header);

  for (const node of model.mainLine) {
    article.appendChild(renderThreadNode(node, activePath, names));
  }

  container.replaceChildren(article);
}

function renderThreadNode(node, activePath, names = []) {
  const section = document.createElement("section");
  section.className = "thread-node";
  if (node.path === nodeDirectoryFor(activePath)) {
    section.classList.add("current");
  }

  const heading = document.createElement("h3");
  const link = document.createElement("a");
  link.href = framedPath(`${node.path}/a`);
  link.textContent = node.ordinal;
  heading.appendChild(link);
  section.appendChild(heading);

  const nodeNames = namesForNode(names, node.path);
  if (nodeNames.length > 0) {
    const nameRow = document.createElement("div");
    nameRow.className = "thread-names";
    for (const entry of nodeNames) {
      const chip = document.createElement("a");
      chip.className = `chip name-chip${entry.inert ? " inert" : ""}`;
      chip.href = framedPath(entry.target.startsWith("/") ? entry.target : `/${entry.target}`);
      chip.textContent = entry.name;
      if (entry.inert) {
        chip.title = "Shadowed by a literal child.";
      }
      nameRow.appendChild(chip);
    }
    section.appendChild(nameRow);
  }

  if (node.aPreview) {
    const pre = document.createElement("pre");
    pre.className = "node-a";
    pre.textContent = node.aPreview;
    section.appendChild(pre);
  }

  if (node.bMeta) {
    section.appendChild(renderProvenance(node.bMeta));
  }

  if (node.siblings.length > 0) {
    const details = document.createElement("details");
    details.className = "thread-branches";
    const parent = node.path.split("/").slice(0, -1).join("/") || "/";
    if (activeSiblingBranch(activePath, parent, node.siblings)) {
      details.open = true;
    }
    const summary = document.createElement("summary");
    summary.textContent = `${node.siblings.length} branch${node.siblings.length === 1 ? "" : "es"}`;
    details.appendChild(summary);
    const list = document.createElement("div");
    list.className = "branch-list";
    for (const sibling of node.siblings) {
      const branch = document.createElement("a");
      branch.className = "chip";
      branch.href = framedPath(`${parent}/${sibling}/a`);
      branch.textContent = sibling;
      list.appendChild(branch);
    }
    details.appendChild(list);
    section.appendChild(details);
  }

  return section;
}

function renderProvenance(meta) {
  const dl = document.createElement("dl");
  dl.className = "node-b";
  const entries = [];
  if (meta.created) {
    entries.push(["created", meta.created]);
  }
  if (meta.author) {
    entries.push(["author", meta.author]);
  }
  for (const [key, value] of Object.entries(meta)) {
    if (key === "created" || key === "author") {
      continue;
    }
    entries.push([key, typeof value === "string" ? value : JSON.stringify(value)]);
  }
  for (const [key, value] of entries) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent = value;
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  return dl;
}

function parseProvenance(text) {
  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return { raw: trimmed };
  }
}

function namesForNode(names, nodePath) {
  const target = `${nodePath}/a`;
  return (names || []).filter((entry) => {
    const normalized = entry.target.startsWith("/") ? entry.target : `/${entry.target}`;
    return normalized === target;
  });
}

function summarizeText(text, limit = 240) {
  const compact = text.replace(/\s+/g, " ").trim();
  if (!compact) {
    return "";
  }
  if (compact.length <= limit) {
    return compact;
  }
  return `${compact.slice(0, limit)}…`;
}
