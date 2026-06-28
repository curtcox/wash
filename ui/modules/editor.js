import { directoryFor, nodeDirectoryFor } from "./thread.js";
import { mutatesBadge } from "./chrome.js";

const META_FIELDS = [
  "arity",
  "input",
  "output",
  "methods",
  "mime",
  "mutates",
  "parse-mode",
  "stderr",
  "exit",
];

export function validateMetaText(text) {
  const errors = [];
  const lines = (text || "").split("\n");
  let methods = ["GET"];
  let mutates = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }
    const parts = line.split(/\s+/);
    const field = parts[0];
    if (!META_FIELDS.includes(field)) {
      errors.push(`unknown meta field: ${field}`);
      continue;
    }
    if (field === "methods") {
      methods = parts.slice(1);
      if (methods.length === 0) {
        errors.push("methods requires at least one value");
      }
    }
    if (field === "mutates") {
      if (parts[1] === "true") {
        mutates = true;
      } else if (parts[1] !== "false") {
        errors.push("mutates must be true or false");
      }
    }
  }
  if (methods.includes("GET") && mutates) {
    errors.push("GET with mutates true is invalid");
  }
  return { errors, valid: errors.length === 0 };
}

export function defaultNameScope(target) {
  let dir = directoryFor(target);
  while (dir !== "/") {
    const parts = dir.split("/").filter(Boolean);
    const last = parts[parts.length - 1] || "";
    if (/^[0-9]+$|^[A-Z]$/.test(last)) {
      parts.pop();
      dir = parts.length ? `/${parts.join("/")}` : "/";
      continue;
    }
    break;
  }
  if (dir === "/") {
    return ".";
  }
  return dir.replace(/^\/+/, "") || ".";
}

export function availableMutations({ kind, resourceOk = false }) {
  const actions = [];
  if (kind === "plain-file" || kind === "env-config") {
    actions.push(resourceOk ? "save" : "create");
    if (resourceOk) {
      actions.push("delete", "rename");
    }
  }
  if (kind === "sdt-node" || kind === "sdt-collection") {
    actions.push("append-child", "append-sibling");
  }
  if (kind === "command") {
    actions.push("run");
  }
  if (kind === "directory") {
    actions.push("create");
  }
  return actions;
}

export function appendTargets(target, kind) {
  if (kind === "sdt-node") {
    const nodeDir = nodeDirectoryFor(target);
    const parent = directoryFor(nodeDir);
    return {
      child: nodeDir,
      sibling: parent,
    };
  }
  if (kind === "sdt-collection") {
    const collection = directoryFor(target);
    return {
      child: collection,
      sibling: directoryFor(collection),
    };
  }
  return { child: null, sibling: null };
}

export function isMetaPath(target) {
  const segments = (target || "").split("/").filter(Boolean);
  return segments[0] === "env" && segments[1] === "meta";
}

export function renderAuthorPanel(container, context, handlers) {
  const {
    target,
    kind,
    resourceOk,
    resolvedPath,
    initialText = "",
    names = [],
  } = context;
  const actions = availableMutations({ kind, resourceOk });
  if (actions.length === 0) {
    container.hidden = true;
    container.replaceChildren();
    return;
  }

  container.hidden = false;
  const panel = document.createElement("section");
  panel.className = "author-panel-inner";

  const heading = document.createElement("h2");
  heading.textContent = "Author";
  panel.appendChild(heading);

  const resolved = document.createElement("p");
  resolved.className = "author-resolved";
  resolved.textContent = `Resolved path: ${resolvedPath || target || "/"}`;
  panel.appendChild(resolved);

  const editor = createBodyEditor(initialText);
  panel.appendChild(editor.root);

  const toolbar = document.createElement("div");
  toolbar.className = "author-toolbar";

  if (actions.includes("save") || actions.includes("create")) {
    toolbar.appendChild(
      makeActionButton("Save", "PUT", () =>
        handlers.onSave(editor.getValue(), { exists: resourceOk, resolvedPath }),
      ),
    );
  }
  if (actions.includes("delete")) {
    toolbar.appendChild(
      makeActionButton("Delete", "DELETE", () =>
        handlers.onDelete({ resolvedPath }),
      ),
    );
  }
  if (actions.includes("rename")) {
    toolbar.appendChild(renderRenameControls(target, handlers));
  }
  if (actions.includes("run")) {
    toolbar.appendChild(
      makeActionButton("Run", "POST", () =>
        handlers.onRun(editor.getValue(), { resolvedPath }),
        { mutates: true },
      ),
    );
  }
  if (actions.includes("append-child") || actions.includes("append-sibling")) {
    const targets = appendTargets(target, kind);
    if (targets.child) {
      toolbar.appendChild(
        makeActionButton("Append child", "POST", () =>
          handlers.onAppend(targets.child, editor.getValue(), { resolvedPath }),
          { mutates: true },
        ),
      );
    }
    if (targets.sibling && targets.sibling !== targets.child) {
      toolbar.appendChild(
        makeActionButton("Append sibling", "POST", () =>
          handlers.onAppend(targets.sibling, editor.getValue(), { resolvedPath }),
          { mutates: true },
        ),
      );
    }
  }

  panel.appendChild(toolbar);

  if (isMetaPath(target)) {
    const validation = validateMetaText(editor.getValue());
    panel.appendChild(renderMetaValidation(validation));
    editor.textarea.addEventListener("input", () => {
      panel.querySelector(".meta-validation")?.replaceWith(
        renderMetaValidation(validateMetaText(editor.getValue())),
      );
    });
  }

  panel.appendChild(renderNameEditor(context, names, handlers));

  container.replaceChildren(panel);
}

function createBodyEditor(initialText) {
  const root = document.createElement("div");
  root.className = "body-editor";

  const textarea = document.createElement("textarea");
  textarea.className = "body-textarea";
  textarea.spellcheck = false;
  textarea.value = initialText;
  root.appendChild(textarea);

  const uploadRow = document.createElement("label");
  uploadRow.className = "upload-row";
  const upload = document.createElement("input");
  upload.type = "file";
  upload.addEventListener("change", async () => {
    const file = upload.files?.[0];
    if (!file) {
      return;
    }
    textarea.value = await file.text();
    upload.value = "";
  });
  uploadRow.appendChild(upload);
  uploadRow.appendChild(document.createTextNode(" Upload file"));
  root.appendChild(uploadRow);

  return {
    root,
    textarea,
    getValue() {
      return textarea.value;
    },
  };
}

function renderRenameControls(target, handlers) {
  const wrap = document.createElement("div");
  wrap.className = "rename-row";
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "New path";
  input.value = target;
  input.spellcheck = false;
  const button = makeActionButton("Rename", "PUT+DELETE", () =>
    handlers.onRename(input.value, { from: target }),
  );
  wrap.replaceChildren(input, button);
  return wrap;
}

function renderNameEditor(context, names, handlers) {
  const section = document.createElement("section");
  section.className = "name-editor";
  const title = document.createElement("h3");
  title.textContent = "Name";
  section.appendChild(title);

  const scope = document.createElement("input");
  scope.type = "text";
  scope.placeholder = "Scope directory";
  scope.value = defaultNameScope(context.target);
  scope.spellcheck = false;

  const name = document.createElement("input");
  name.type = "text";
  name.placeholder = "Name";
  name.spellcheck = false;

  const targetInput = document.createElement("input");
  targetInput.type = "text";
  targetInput.placeholder = "Target path";
  targetInput.value = context.target.endsWith("/a")
    ? context.target
    : `${nodeDirectoryFor(context.target)}/a`;
  targetInput.spellcheck = false;

  const preview = document.createElement("p");
  preview.className = "name-preview";
  const updatePreview = () => {
    preview.textContent = `Preview: ${scope.value || "."}:${name.value || "?"} → ${targetInput.value || "?"}`;
  };
  for (const input of [scope, name, targetInput]) {
    input.addEventListener("input", updatePreview);
  }
  updatePreview();

  const row = document.createElement("div");
  row.className = "name-row";
  row.replaceChildren(scope, name, targetInput);
  section.appendChild(row);
  section.appendChild(preview);

  const buttons = document.createElement("div");
  buttons.className = "author-toolbar";
  buttons.appendChild(
    makeActionButton("Create name", "POST", () =>
      handlers.onNameNew(scope.value, name.value, targetInput.value),
      { mutates: true },
    ),
  );
  buttons.appendChild(
    makeActionButton("Retarget name", "POST", () =>
      handlers.onNameSet(scope.value, name.value, targetInput.value),
      { mutates: true },
    ),
  );
  buttons.appendChild(
    makeActionButton("Drop name", "POST", () =>
      handlers.onNameRm(scope.value, name.value),
      { mutates: true },
    ),
  );
  section.appendChild(buttons);
  return section;
}

function renderMetaValidation(validation) {
  const node = document.createElement("div");
  node.className = "meta-validation";
  if (validation.valid) {
    node.textContent = "Meta validation: ok";
    return node;
  }
  node.textContent = validation.errors.join("; ");
  node.classList.add("error");
  return node;
}

function makeActionButton(label, method, onClick, { mutates = false } = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "author-action";
  if (mutates) {
    button.appendChild(mutatesBadge());
    button.appendChild(document.createTextNode(" "));
  }
  button.appendChild(document.createTextNode(`${label} (${method})`));
  button.addEventListener("click", onClick);
  return button;
}
