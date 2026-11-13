import { spawn } from 'node:child_process';
import path from 'node:path';
import { python, root } from './python.mjs';
const child = spawn(python, [path.join(root, 'frontend/tests/serve_backend.py')], {
  stdio: 'inherit',
  cwd: root,
});
child.on('exit', (code) => process.exit(code ?? 1));
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => child.kill(signal));
