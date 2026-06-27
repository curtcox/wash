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
  return {
    blob: await response.blob(),
    contentType: response.headers.get("content-type") || "",
    headers,
    ok: response.ok,
    status: response.status,
    url: response.url,
  };
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

export async function postTerm(target) {
  const response = await fetch(`/term/${target.replace(/^\/+/, "")}`, { method: "POST" });
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
