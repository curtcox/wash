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

export function commandNameFromScriptPath(target) {
  const segments = (target || "/").split("/").filter(Boolean);
  if (segments.length !== 2 || segments[0] !== "bin") {
    return null;
  }
  return segments[1];
}

export function commandNameFromMetaPath(target) {
  const segments = (target || "/").split("/").filter(Boolean);
  if (segments.length !== 3 || segments[0] !== "env" || segments[1] !== "meta") {
    return null;
  }
  return segments[2];
}

export function commandAuthorPaths(commandName) {
  return {
    script: `/bin/${commandName}`,
    meta: `/env/meta/${commandName}`,
    pathFile: "/env/path",
    execFile: "/exec",
  };
}

export function parseLineFile(text) {
  return (text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"));
}

export function envPathNeedsWire(text, directory = "bin") {
  return !parseLineFile(text).includes(directory);
}

export function execNeedsRule(text, rule) {
  const trimmed = (rule || "").trim();
  if (!trimmed) {
    return false;
  }
  return !parseLineFile(text).includes(trimmed);
}

export function appendLineFileEntry(text, line) {
  const lines = (text || "").split("\n");
  while (lines.length && !lines[lines.length - 1].trim()) {
    lines.pop();
  }
  if (!parseLineFile(text).includes(line)) {
    lines.push(line);
  }
  return `${lines.join("\n")}\n`;
}

export function suggestExecRule(commandName, scriptBody = "") {
  const firstLine = (scriptBody || "").split("\n")[0]?.trim() || "";
  if (firstLine.startsWith("#!")) {
    if (firstLine.includes("python")) {
      return "* python3";
    }
    if (firstLine.includes("sh") || firstLine.includes("bash")) {
      return "* sh";
    }
  }
  if ((commandName || "").endsWith(".py")) {
    return "* python3";
  }
  if ((commandName || "").endsWith(".sh")) {
    return "* sh";
  }
  return "* python3";
}

export function defaultCommandMeta() {
  return "methods GET\nmime text/plain\n";
}

export function planCommandSetup({
  commandName,
  pathText = "",
  execText = "",
  metaExists = false,
  scriptBody = "",
}) {
  const paths = commandAuthorPaths(commandName);
  const execRule = suggestExecRule(commandName, scriptBody);
  const steps = [];
  if (!metaExists) {
    steps.push({
      body: defaultCommandMeta(),
      label: "Create env/meta",
      path: paths.meta,
    });
  }
  if (envPathNeedsWire(pathText)) {
    steps.push({
      body: appendLineFileEntry(pathText, "bin"),
      label: "Wire bin into env/path",
      path: paths.pathFile,
    });
  }
  if (execNeedsRule(execText, execRule)) {
    steps.push({
      body: appendLineFileEntry(execText, execRule),
      label: "Add exec interpreter rule",
      path: paths.execFile,
    });
  }
  return { execRule, paths, steps };
}

export function renderAuthorPanel(container, context, handlers) {
  const {
    target,
    kind,
    resourceOk,
    resolvedPath,
    initialText = "",
    names = [],
    commandSetup = null,
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
    panel.appendChild(renderMetaForm(editor));
    const validation = validateMetaText(editor.getValue());
    panel.appendChild(renderMetaValidation(validation));
    editor.textarea.addEventListener("input", () => {
      panel.querySelector(".meta-validation")?.replaceWith(
        renderMetaValidation(validateMetaText(editor.getValue())),
      );
    });
  }

  if (commandSetup) {
    panel.appendChild(renderCommandAuthorSection(commandSetup, editor, handlers));
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

function renderMetaForm(editor) {
  const section = document.createElement("section");
  section.className = "meta-form";
  const title = document.createElement("h3");
  title.textContent = "Meta fields";
  section.appendChild(title);

  const fields = document.createElement("div");
  fields.className = "meta-form-grid";
  const controls = {};
  for (const field of META_FIELDS) {
    const label = document.createElement("label");
    label.textContent = field;
    const input = document.createElement("input");
    input.type = "text";
    input.name = field;
    input.spellcheck = false;
    input.placeholder = field === "mutates" ? "true or false" : "";
    controls[field] = input;
    label.appendChild(input);
    fields.appendChild(label);
  }
  section.appendChild(fields);

  const syncFromTextarea = () => {
    const values = parseMetaText(editor.getValue());
    for (const field of META_FIELDS) {
      controls[field].value = values[field] || "";
    }
  };
  const syncToTextarea = () => {
    editor.textarea.value = serializeMetaText(
      Object.fromEntries(META_FIELDS.map((field) => [field, controls[field].value])),
    );
    editor.textarea.dispatchEvent(new Event("input"));
  };

  syncFromTextarea();
  for (const input of Object.values(controls)) {
    input.addEventListener("change", syncToTextarea);
  }
  editor.textarea.addEventListener("input", syncFromTextarea);

  const hint = document.createElement("p");
  hint.className = "meta-form-hint";
  hint.textContent = "Form edits update the raw meta below; raw edits refresh the form.";
  section.appendChild(hint);
  return section;
}

function parseMetaText(text) {
  const values = {};
  for (const raw of (text || "").split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }
    const parts = line.split(/\s+/);
    const field = parts[0];
    if (META_FIELDS.includes(field)) {
      values[field] = parts.slice(1).join(" ");
    }
  }
  return values;
}

function serializeMetaText(values) {
  const lines = [];
  for (const field of META_FIELDS) {
    const value = (values[field] || "").trim();
    if (value) {
      lines.push(`${field} ${value}`);
    }
  }
  return lines.length ? `${lines.join("\n")}\n` : "";
}

function renderCommandAuthorSection(setup, editor, handlers) {
  const section = document.createElement("section");
  section.className = "command-author";
  const title = document.createElement("h3");
  title.textContent = "Command setup";
  section.appendChild(title);

  const status = document.createElement("dl");
  status.className = "command-status";
  appendStatusRow(status, "Script", setup.scriptExists ? "present" : "missing");
  appendStatusRow(status, "Meta", setup.metaExists ? "present" : "missing");
  appendStatusRow(
    status,
    "env/path",
    setup.needsPathWire ? "bin not wired" : "bin wired",
  );
  appendStatusRow(
    status,
    "exec",
    setup.needsExecRule ? `needs ${setup.execRule}` : "rule present",
  );
  section.appendChild(status);

  const toolbar = document.createElement("div");
  toolbar.className = "author-toolbar";
  if (setup.needsPathWire) {
    toolbar.appendChild(
      makeActionButton("Wire bin", "PUT", () =>
        handlers.onWireEnvPath({
          merged: appendLineFileEntry(setup.pathText, "bin"),
          resolvedPath: "/env/path",
        }),
      ),
    );
  }
  if (setup.needsExecRule) {
    toolbar.appendChild(
      makeActionButton("Add exec rule", "PUT", () =>
        handlers.onAddExecRule({
          merged: appendLineFileEntry(setup.execText, setup.execRule),
          resolvedPath: "/exec",
        }),
      ),
    );
  }
  if (setup.steps.length > 0 || !setup.scriptExists) {
    toolbar.appendChild(
      makeActionButton("Create command", "PUT", () =>
        handlers.onCreateCommand({
          commandName: setup.commandName,
          scriptBody: editor.getValue(),
          setup,
        }),
        { mutates: true },
      ),
    );
  }
  section.appendChild(toolbar);

  const hint = document.createElement("p");
  hint.className = "command-hint";
  hint.textContent =
    "Command authoring writes the script, env/meta, env/path wiring, and exec rule. Each file can also be saved independently.";
  section.appendChild(hint);
  return section;
}

function appendStatusRow(node, key, value) {
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = key;
  dd.textContent = value;
  node.appendChild(dt);
  node.appendChild(dd);
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
