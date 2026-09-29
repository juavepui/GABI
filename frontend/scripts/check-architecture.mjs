// Read the TypeScript AST, including exports and dynamic imports; never execute app code.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const FEATURES = new Set(['market', 'portfolio', 'research', 'administration']);
const SHARED = new Set(['api', 'ui', 'lib', 'assets']);
const EXTENSIONS = /\.(?:[cm]?[jt]sx?)$/;

function filesIn(directory) {
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const name = path.join(directory, entry.name);
    return entry.isDirectory() ? filesIn(name) : EXTENSIONS.test(name) ? [name] : [];
  });
}

export function section(relative) {
  const parts = relative.replaceAll('\\', '/').split('/');
  if (parts[0] === 'app') return { layer: 'app' };
  if (parts[0] === 'features' && FEATURES.has(parts[1]))
    return { layer: 'feature', feature: parts[1] };
  if (parts[0] === 'shared' && SHARED.has(parts[1])) return { layer: 'shared', area: parts[1] };
  if (parts.length === 1 && ['main.tsx', 'vite-env.d.ts'].includes(parts[0]))
    return { layer: 'entry' };
  return { layer: 'invalid' };
}

export function boundaryError(from, to) {
  const own = section(from);
  const other = section(to);
  if (other.layer === 'invalid') return 'dependency outside the architecture directories';
  if (own.layer === 'shared' && other.layer !== 'shared')
    return 'shared cannot depend on app/features';
  if (
    own.layer === 'feature' &&
    other.layer !== 'shared' &&
    !(other.layer === 'feature' && own.feature === other.feature)
  )
    return 'features cannot import app or another feature';
  if (
    own.layer === 'app' &&
    other.layer === 'feature' &&
    !/^features\/[^/]+\/index\.[jt]sx?$/.test(to)
  )
    return 'app must import the feature public index';
  if (own.layer === 'app' && !['app', 'feature', 'shared'].includes(other.layer))
    return 'app cannot import the entry point';
  if (own.layer === 'entry' && !['app', 'shared'].includes(other.layer))
    return 'main only mounts app/shared';
  return null;
}

export function check(root) {
  const source = path.join(root, 'src');
  const files = filesIn(source).sort();
  const errors = [];
  const graph = new Map(files.map((file) => [file, new Set()]));
  let options = {
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    jsx: ts.JsxEmit.Preserve,
    allowJs: true,
    paths: { '@/*': [path.join(source, '*')] },
  };
  const config = ['tsconfig.app.json', 'tsconfig.json']
    .map((name) => path.join(root, name))
    .find(fs.existsSync);
  if (config) {
    const read = ts.readConfigFile(config, ts.sys.readFile);
    if (read.error) return [ts.flattenDiagnosticMessageText(read.error.messageText, ' ')];
    const parsed = ts.parseJsonConfigFileContent(read.config, ts.sys, root);
    const configErrors = parsed.errors.filter((item) => item.code !== 18003); // Empty scaffold is intentional.
    if (configErrors.length)
      return configErrors.map((item) => ts.flattenDiagnosticMessageText(item.messageText, ' '));
    options = { ...options, ...parsed.options };
  }
  for (const file of files) {
    const relative = path.relative(source, file).replaceAll('\\', '/');
    const own = section(relative);
    if (own.layer === 'invalid')
      errors.push(`${relative}: use app, features/<capability>, or shared/<area>`);
    if (!/\.tsx?$/.test(relative))
      errors.push(`${relative}: frontend production source must be TypeScript`);
    const ast = ts.createSourceFile(
      file,
      fs.readFileSync(file, 'utf8'),
      ts.ScriptTarget.Latest,
      true,
    );
    for (const diagnostic of ast.parseDiagnostics) {
      errors.push(`${relative}: ${ts.flattenDiagnosticMessageText(diagnostic.messageText, ' ')}`);
    }
    function report(node, message) {
      const { line } = ast.getLineAndCharacterOfPosition(node.getStart(ast));
      errors.push(`${relative}:${line + 1}: ${message}`);
    }
    function dependency(node, name) {
      if (
        name.startsWith('node:') ||
        ['fs', 'path', 'sqlite3', 'better-sqlite3', 'axios'].includes(name.split('/')[0])
      ) {
        report(node, 'browser data access uses shared/api and the local HTTP contract');
        return;
      }
      const resolved = ts.resolveModuleName(name, file, options, ts.sys).resolvedModule;
      let target = resolved?.resolvedFileName;
      if (
        !target &&
        name.startsWith('.') &&
        fs.existsSync(path.resolve(path.dirname(file), name))
      ) {
        target = path.resolve(path.dirname(file), name); // CSS/images.
      }
      if (!target && name.startsWith('@/') && fs.existsSync(path.resolve(source, name.slice(2)))) {
        target = path.resolve(source, name.slice(2));
      }
      if (!target) {
        const configuredAlias = Object.keys(options.paths ?? {}).some((pattern) => {
          if (!pattern.includes('*')) return name === pattern;
          const [prefix, suffix] = pattern.split('*');
          return name.startsWith(prefix) && name.endsWith(suffix);
        });
        if (name.startsWith('.') || name.startsWith('@/') || configuredAlias)
          report(node, `unresolved local import ${name}`);
        return;
      }
      target = path.resolve(target);
      if (target.includes(`${path.sep}node_modules${path.sep}`)) {
        return;
      }
      const targetRelative = path.relative(source, target).replaceAll('\\', '/');
      const problem = boundaryError(relative, targetRelative);
      if (problem) report(node, `${name}: ${problem}`);
      if (graph.has(target)) graph.get(file).add(target);
    }
    function walk(node) {
      if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
        dependency(node, node.moduleSpecifier.text);
      }
      if (ts.isImportTypeNode(node) && ts.isLiteralTypeNode(node.argument)) {
        dependency(node, node.argument.literal.text);
      }
      if (ts.isImportEqualsDeclaration(node)) report(node, 'use ES module imports');
      if (ts.isCallExpression(node)) {
        const name = ts.isIdentifier(node.expression)
          ? node.expression.text
          : ts.isPropertyAccessExpression(node.expression)
            ? node.expression.name.text
            : '';
        if (node.expression.kind === ts.SyntaxKind.ImportKeyword) {
          if (node.arguments.length !== 1 || !ts.isStringLiteralLike(node.arguments[0])) {
            report(node, 'dynamic imports must have a literal module name');
          } else dependency(node, node.arguments[0].text);
        }
        if (['require', 'eval'].includes(name))
          report(node, 'use statically inspectable ES modules');
        if (name === 'fetch' && !(own.layer === 'shared' && own.area === 'api')) {
          report(node, 'HTTP transport belongs in shared/api');
        }
      }
      if (
        ts.isNewExpression(node) &&
        ['XMLHttpRequest', 'WebSocket', 'EventSource'].includes(node.expression.getText(ast)) &&
        !(own.layer === 'shared' && own.area === 'api')
      )
        report(node, 'HTTP transport belongs in shared/api');
      ts.forEachChild(node, walk);
    }
    walk(ast);
  }
  const active = [];
  const done = new Set();
  function visit(file) {
    if (active.includes(file)) {
      errors.push(
        'dependency cycle: ' +
          [...active.slice(active.indexOf(file)), file]
            .map((item) => path.relative(source, item).replaceAll('\\', '/'))
            .join(' -> '),
      );
      return;
    }
    if (done.has(file)) return;
    active.push(file);
    for (const target of graph.get(file)) visit(target);
    active.pop();
    done.add(file);
  }
  for (const file of files) visit(file);
  return errors;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = fileURLToPath(new URL('../', import.meta.url));
  const errors = check(root);
  if (errors.length) {
    console.error(errors.join('\n'));
    process.exitCode = 1;
  } else
    console.log(
      `Frontend architecture OK (${filesIn(path.join(root, 'src')).length} source files).`,
    );
}
