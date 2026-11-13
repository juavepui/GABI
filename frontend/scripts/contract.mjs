import { createClient } from '@hey-api/openapi-ts';
import { readFileSync, readdirSync, mkdtempSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { python, root } from './python.mjs';

const frontend = path.join(root, 'frontend');
const checking = process.argv.includes('--check');
const schema = path.join(frontend, 'openapi.json');
const result = spawnSync(
  python,
  [
    path.join(root, 'scripts/export_openapi.py'),
    '--output',
    schema,
    ...(checking ? ['--check'] : []),
  ],
  { stdio: 'inherit' },
);
if (result.status !== 0) process.exit(result.status ?? 1);
const target = path.join(frontend, 'src/shared/api/generated');
const temporary = checking ? mkdtempSync(path.join(tmpdir(), 'gabi-contract-')) : null;
try {
  const output = temporary ?? target;
  await createClient({ input: schema, output, plugins: ['@hey-api/typescript'] });
  if (checking) {
    const generated = readdirSync(output)
      .filter((f) => f.endsWith('.ts'))
      .sort();
    const committed = readdirSync(target)
      .filter((f) => f.endsWith('.ts'))
      .sort();
    if (
      JSON.stringify(generated) !== JSON.stringify(committed) ||
      generated.some(
        (f) =>
          readFileSync(path.join(output, f), 'utf8').replaceAll('\r\n', '\n') !==
          readFileSync(path.join(target, f), 'utf8').replaceAll('\r\n', '\n'),
      )
    ) {
      throw new Error(
        'Generated API types changed. Run npm run generate:api and commit the contract.',
      );
    }
    console.log('OpenAPI schema and generated TypeScript are current.');
  }
} finally {
  if (
    temporary &&
    path.dirname(path.resolve(temporary)) === path.resolve(tmpdir()) &&
    path.basename(temporary).startsWith('gabi-contract-')
  )
    rmSync(temporary, { recursive: true, force: true });
}
