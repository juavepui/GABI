import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
export const root = fileURLToPath(new URL('../../', import.meta.url));
const candidates = [
  process.env.GABI_PYTHON,
  'backend/.venv/Scripts/python.exe',
  '.venv/Scripts/python.exe',
  'backend/.venv/bin/python',
  '.venv/bin/python',
].filter(Boolean);
export const python = candidates.map((p) => path.resolve(root, p)).find(existsSync);
if (!python)
  throw new Error('Set GABI_PYTHON to the Python environment with the backend installed.');
