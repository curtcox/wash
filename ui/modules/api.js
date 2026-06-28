import { rawPath } from "./router.js";

const HEADER_KEYS = [
  "x-webshell-source",
  "x-webshell-command",
  "x-webshell-pipeline",
  "x-webshell-resolved-path",
];

export async function fetchResource(target) {
  const response = await fetch(rawPath(target), {
    headers: { Accept: "application/json, text/*;q=0.9, */*;q=0.8" },
  });
  const headers = {};
  for (const key of HEADER_KEYS) {
    const value = response.headers.get(key);
    if (value) {
      headers[headerLabel(key)] = value;
    }
  }
  const blob = await response.blob();
  const contentType = response.headers.get("content-type") || "";
  let listing = null;
  if (response.ok && contentType.startsWith("text/plain")) {
    const text = await blob.text();
    listing = parseListingText(text);
    if (listing.length === 0 && text.trim() !== "") {
      listing = null;
    }
    return {
      blob: new Blob([text], { type: contentType }),
      contentType,
      headers,
      listing,
      ok: response.ok,
      status: response.status,
      url: response.url,
    };
  }
  return {
    blob,
    contentType,
    headers,
    listing,
    ok: response.ok,
    status: response.status,
    url: response.url,
  };
}

export async function fetchListing(target) {
  const response = await fetch(rawPath(target), {
    headers: { Accept: "text/plain" },
  });
  if (!response.ok) {
    throw new Error(`${target || "/"} returned ${response.status}`);
  }
  const text = await response.text();
  return {
    entries: parseListingText(text),
    path: rawPath(target),
  };
}

export async function fetchText(target) {
  const response = await fetch(rawPath(target), {
    headers: { Accept: "text/plain" },
  });
  if (!response.ok) {
    throw new Error(`${target} returned ${response.status}`);
  }
  return response.text();
}

export async function getRootInfo() {
  return getJson("/rootinfo");
}

export async function getCommands() {
  return getJson("/commands");
}

export async function getNames() {
  return getJson("/names");
}

export async function postTerm(directory) {
  const trimmed = (directory || ".").replace(/^\/+/, "");
  const response = await fetch(`/term/${trimmed}`, { method: "POST" });
  return response.json();
}

async function getJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

function headerLabel(key) {
  return key.replace("x-webshell-", "").replaceAll("-", " ");
}

function parseListingText(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const isDir = line.endsWith("/");
      return {
        isDir,
        name: isDir ? line : line,
      };
    });
}
