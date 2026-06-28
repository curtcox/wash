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

export async function probeFeatures() {
  const features = {
    executionHeaders: false,
    explain: false,
    mutation: false,
  };
  try {
    const response = await fetch("/", {
      headers: { Accept: "text/plain" },
    });
    features.executionHeaders = HEADER_KEYS.some((key) =>
      response.headers.get(key),
    );
    features.mutation = response.headers.has("Allow")
      ? response.headers.get("Allow").includes("PUT")
      : true;
  } catch {
    return features;
  }
  try {
    await getExplain("/");
    features.explain = true;
  } catch {
    features.explain = false;
  }
  return features;
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

export async function getNamePreview(scope, name, target) {
  const params = new URLSearchParams();
  for (const value of ["preview", normalizeScope(scope), name, target]) {
    params.append("arg", value || "");
  }
  return getJson(`/names?${params.toString()}`);
}

export async function getHelp() {
  return getJson("/help");
}

export async function getExplain(target) {
  const suffix = rawPath(target).replace(/^\//, "");
  const path = suffix ? `/explain/${suffix}` : "/explain/";
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`explain returned ${response.status}`);
  }
  return response.json();
}

export async function postTerm(directory) {
  const trimmed = (directory || ".").replace(/^\/+/, "");
  const response = await fetch(`/term/${trimmed}`, { method: "POST" });
  return response.json();
}

export async function putResource(target, body) {
  const response = await fetch(rawPath(target), {
    method: "PUT",
    body,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`PUT ${target} returned ${response.status}: ${text.slice(0, 200)}`);
  }
  return response;
}

export async function deleteResource(target) {
  const response = await fetch(rawPath(target), { method: "DELETE" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`DELETE ${target} returned ${response.status}: ${text.slice(0, 200)}`);
  }
  return response;
}

export async function postResource(target, body) {
  const response = await fetch(rawPath(target), {
    method: "POST",
    body,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`POST ${target} returned ${response.status}: ${text.slice(0, 200)}`);
  }
  return response;
}

export async function postAppend(parentPath, body) {
  const suffix = (parentPath || ".").replace(/^\/+/, "") || ".";
  const response = await fetch(`/append/${suffix}`, {
    method: "POST",
    body,
    headers: { Accept: "application/json" },
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`append returned ${response.status}: ${text.slice(0, 200)}`);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`append returned non-JSON: ${text.slice(0, 200)}`);
  }
}

export async function postNameNew(scope, name, target) {
  return postNameCommand("name-new", scope, name, target);
}

export async function postNameSet(scope, name, target) {
  return postNameCommand("name-set", scope, name, target);
}

export async function postNameRm(scope, name) {
  return postNameCommand("name-rm", scope, name);
}

async function postNameCommand(command, scope, name, target = "") {
  const params = new URLSearchParams();
  params.append("arg", normalizeScope(scope));
  params.append("arg", name || "");
  if (target) {
    params.append("arg", target);
  }
  const response = await fetch(`/${command}?${params.toString()}`, { method: "POST" });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${command} returned ${response.status}: ${text.slice(0, 200)}`);
  }
  return text;
}

function normalizeScope(scope) {
  const trimmed = (scope || ".").trim();
  if (!trimmed || trimmed === "/") {
    return ".";
  }
  return trimmed.replace(/^\/+/, "");
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
