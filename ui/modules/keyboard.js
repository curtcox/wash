function isEditableTarget(target) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

export function bindKeyboardShortcuts({ focusPath, reload }) {
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !event.metaKey && !event.ctrlKey && !isEditableTarget(event.target)) {
      event.preventDefault();
      focusPath();
      return;
    }
    if (
      event.altKey &&
      event.key.toLowerCase() === "r" &&
      !isEditableTarget(event.target)
    ) {
      event.preventDefault();
      reload();
    }
  });
}
