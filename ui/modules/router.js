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
  const trimmed = target.trim();
  if (!trimmed || trimmed === "/") {
    return "/";
  }
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

export function framedPath(target) {
  const raw = rawPath(target);
  return raw === "/" ? "/ui/" : `/ui${raw}`;
}
