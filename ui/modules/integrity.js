const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

export function isNonLocalOrigin(origin = location.origin) {
  try {
    const url = new URL(origin);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return true;
    }
    return !LOCAL_HOSTS.has(url.hostname.toLowerCase());
  } catch {
    return true;
  }
}

export function parseManifest(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function manifestRelPath(target) {
  const trimmed = (target || "/").replace(/^\/+/, "");
  if (!trimmed) {
    return "";
  }
  return trimmed;
}

export function isBundlePath(target, manifest) {
  const rel = manifestRelPath(target);
  if (!rel) {
    return false;
  }
  return manifest.includes(rel);
}

export function bundlePathWarning(target, manifest) {
  if (!isBundlePath(target, manifest)) {
    return null;
  }
  return (
    `This path is part of the wash UI bundle (${manifestRelPath(target)}). ` +
    "Editing it from the UI can break the tool. Re-run wash-ui-install or see ui/RECOVERY.md."
  );
}

export async function loadManifest(fetchText = defaultFetchText) {
  try {
    const text = await fetchText("/ui/.ui-manifest");
    return parseManifest(text);
  } catch {
    return [];
  }
}

async function defaultFetchText(path) {
  const response = await fetch(path, { headers: { Accept: "text/plain" } });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.text();
}
