export function currentTarget() {
  const path = decodeURI(location.pathname);
  if (path === "/ui" || path === "/ui/") {
    return "/";
  }
  if (path.startsWith("/ui/")) {
    return `/${path.slice(4)}`;
  }
  return path || "/";
}

export function rawPath(target) {
  const trimmed = canonicalizeInput(target);
  if (!trimmed || trimmed === "/") {
    return "/";
  }
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

export function framedPath(target) {
  const raw = rawPath(target);
  return raw === "/" ? "/ui/" : `/ui${raw}`;
}

export function canonicalizeInput(input) {
  const raw = input.trim();
  if (!raw || raw === "/") {
    return "/";
  }
  const prefix = raw.startsWith("/") ? "/" : "";
  const body = raw.replace(/^\/+/, "");
  const segments = body.split("/").map(canonicalizeSegment);
  return prefix + segments.join("/");
}

export function displayInput(input) {
  const raw = input.trim();
  if (!raw || raw === "/") {
    return "/";
  }
  const prefix = raw.startsWith("/") ? "/" : "";
  const body = raw.replace(/^\/+/, "");
  const segments = body.split("/").map(displaySegment);
  return prefix + segments.join("/");
}

function canonicalizeSegment(segment) {
  const question = segment.indexOf("?");
  if (question < 0) {
    return segment;
  }
  const name = segment.slice(0, question);
  const query = segment.slice(question + 1);
  if (!query) {
    return `${name}?`;
  }
  const params = splitSugar(query).map((token) => {
    const equal = token.indexOf("=");
    if (equal > 0) {
      const key = token.slice(0, equal);
      const value = token.slice(equal + 1);
      return `${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
    }
    return `arg=${encodeURIComponent(token)}`;
  });
  return `${name}?${params.join("&")}`;
}

function displaySegment(segment) {
  const question = segment.indexOf("?");
  if (question < 0) {
    return segment;
  }
  const name = segment.slice(0, question);
  const query = segment.slice(question + 1);
  if (!query) {
    return `${name}?`;
  }
  const params = query.split("&").filter(Boolean).map((part) => {
    const [rawKey, rawValue = ""] = part.split("=", 2);
    const key = decodeURIComponent(rawKey);
    const value = decodeURIComponent(rawValue);
    if (key === "arg") {
      return quoteIfNeeded(value);
    }
    return `${key}=${quoteIfNeeded(value)}`;
  });
  return `${name}?${params.join(" ")}`;
}

function splitSugar(query) {
  const tokens = [];
  let current = "";
  let quoted = false;
  for (const ch of query.trim()) {
    if (ch === '"') {
      quoted = !quoted;
      continue;
    }
    if (/\s/.test(ch) && !quoted) {
      if (current) {
        tokens.push(current);
        current = "";
      }
      continue;
    }
    current += ch;
  }
  if (current) {
    tokens.push(current);
  }
  if (!tokens.length && query.trim() === "") {
    return [];
  }
  return tokens;
}

function quoteIfNeeded(value) {
  if (value === "" || /\s/.test(value)) {
    return `"${value.replaceAll('"', '\\"')}"`;
  }
  return value;
}
