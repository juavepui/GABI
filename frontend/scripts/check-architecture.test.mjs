import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { boundaryError, check } from "./check-architecture.mjs";

function fixture(t, sources, config) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "gabi-architecture-"));
  t.after(() => {
    assert.equal(path.dirname(path.resolve(root)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(root).startsWith("gabi-architecture-"));
    fs.rmSync(root, { recursive: true, force: true });
  });
  for (const [name, content] of Object.entries(sources)) {
    const file = path.join(root, "src", name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, content);
  }
  if (config) fs.writeFileSync(path.join(root, "tsconfig.json"), JSON.stringify(config));
  return root;
}

test("app consumes feature public API and features consume shared", () => {
  assert.equal(boundaryError("app/routes.tsx", "features/market/index.ts"), null);
  assert.equal(boundaryError("features/market/api.ts", "shared/api/client.ts"), null);
  assert.ok(boundaryError("app/routes.tsx", "features/market/private.ts"));
  assert.ok(boundaryError("features/portfolio/page.tsx", "features/market/index.ts"));
  assert.ok(boundaryError("shared/ui/table.tsx", "features/market/index.ts"));
  assert.ok(boundaryError("app/routes.tsx", "main.tsx"));
});

test("comments and strings do not become imports", (t) => {
  const root = fixture(t, { "features/market/page.tsx": `
    // import bad from "../portfolio/page";
    const help = 'import bad from "../portfolio/page";';
    export const page = <div>{help}</div>;
  ` });
  assert.deepEqual(check(root), []);
});

test("relative imports, reexports, and lazy imports cannot bypass boundaries", (t) => {
  const root = fixture(t, {
    "features/market/page.tsx": `export { value } from '../portfolio/value';
      export const lazy = () => import('../portfolio/value');`,
    "features/portfolio/value.ts": "export const value = 1;",
  });
  assert.equal(check(root).filter((error) => error.includes("another feature")).length, 2);
});

test("configured aliases and import types are resolved through TypeScript", (t) => {
  const root = fixture(t, {
    "shared/lib/example.ts": `type Bad = import('@market/value').Value;`,
    "features/market/value.ts": "export type Value = number;",
  }, { compilerOptions: { baseUrl: "./src", paths: { "@market/*": ["features/market/*"] } } });
  assert.ok(check(root).some((error) => error.includes("shared cannot depend")));
});

test("external HTTP access belongs to shared/api", (t) => {
  const root = fixture(t, {
    "features/market/page.tsx": "fetch('/api/v1/ranking'); globalThis.fetch('/api/v1/model');",
    "shared/api/client.ts": "export const read = () => fetch('/api/v1/ranking');",
  });
  assert.equal(check(root).filter((error) => error.includes("HTTP transport belongs")).length, 2);
});

test("cycles, computed imports, and imports outside src are rejected", (t) => {
  const root = fixture(t, {
    "shared/lib/a.ts": "import './b'; const unknown = import(variable);",
    "shared/lib/b.ts": "import './a'; import '../../../outside';",
  });
  fs.writeFileSync(path.join(root, "outside.ts"), "export const value = 1;");
  const errors = check(root);
  assert.ok(errors.some((error) => error.includes("dependency cycle")));
  assert.ok(errors.some((error) => error.includes("literal module name")));
  assert.ok(errors.some((error) => error.includes("outside the architecture")));
});

test("unresolved local imports and unregistered directories fail", (t) => {
  const root = fixture(t, { "utils/unregistered.ts": "import '@/missing';" });
  assert.ok(check(root).some((error) => error.includes("unresolved local import")));
  assert.ok(check(root).some((error) => error.includes("use app, features")));
});

test("CSS aliases resolve but browser code cannot use SQLite/Node or untyped JS", (t) => {
  const root = fixture(t, {
    "app/styles.ts": "import '@/shared/ui/theme.css';",
    "shared/ui/theme.css": "body { color: black; }",
    "shared/lib/bad.js": "import { readFile } from 'fs/promises'; import 'axios/lib/client';",
  });
  const errors = check(root);
  assert.equal(errors.filter((error) => error.includes("unresolved")).length, 0);
  assert.equal(errors.filter((error) => error.includes("local HTTP contract")).length, 2);
  assert.ok(errors.some((error) => error.includes("must be TypeScript")));
});
