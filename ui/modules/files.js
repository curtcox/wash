import { framedPath } from "./router.js";
import { directoryFor } from "./thread.js";
import { shadowedNamesForDirectory } from "./panels.js";

export function filesDirectoryFor(target) {
  return directoryFor(target);
}

export async function renderFilesBrowser(container, target, api, { names = [] } = {}) {
  const directory = filesDirectoryFor(target);
  container.hidden = false;
  const section = document.createElement("section");
  section.className = "files-browser";

  const header = document.createElement("header");
  header.className = "files-header";
  const title = document.createElement("h2");
  title.textContent = "Files";
  const path = document.createElement("code");
  path.textContent = directory;
  header.replaceChildren(title, path);
  section.appendChild(header);

  let listing;
  try {
    listing = await api.fetchListing(directory);
  } catch (error) {
    const errorNode = document.createElement("p");
    errorNode.className = "files-error";
    errorNode.textContent = error.message;
    section.appendChild(errorNode);
    container.replaceChildren(section);
    return;
  }

  if (listing.entries.length === 0) {
    const empty = document.createElement("p");
    empty.className = "files-empty";
    empty.textContent = "Empty directory.";
    section.appendChild(empty);
    container.replaceChildren(section);
    return;
  }

  const shadowed = shadowedNamesForDirectory(names, directory);
  const list = document.createElement("div");
  list.className = "files-list";
  for (const entry of listing.entries) {
    const link = document.createElement("a");
    link.className = "chip";
    const baseName = entry.name.replace(/\/$/, "");
    if (shadowed.has(baseName)) {
      link.classList.add("shadows-name");
      link.title = `Literal entry shadows the name ${baseName}.`;
    }
    const suffix = entry.name.endsWith("/") ? entry.name : entry.name;
    const childPath =
      directory === "/"
        ? `/${suffix.replace(/\/$/, "")}${entry.isDir ? "/" : ""}`
        : `${directory}/${suffix.replace(/\/$/, "")}${entry.isDir ? "/" : ""}`;
    link.href = framedPath(childPath);
    link.textContent = entry.name;
    list.appendChild(link);
  }
  section.appendChild(list);
  container.replaceChildren(section);
}

export function hideFilesBrowser(container) {
  container.hidden = true;
  container.replaceChildren();
}
