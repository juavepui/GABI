import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import hooks from 'eslint-plugin-react-hooks';
import refresh from 'eslint-plugin-react-refresh';
import globals from 'globals';

// Every number on screen goes through shared/lib/format.ts: Spanish separators, «—» for absences.
const formatRules = [
  {
    selector: "NewExpression[callee.object.name='Intl'][callee.property.name='NumberFormat']",
    message: 'Usa formatNumber, formatPercent o formatMoney de @/shared/lib/format.',
  },
  {
    selector: "CallExpression[callee.property.name='toFixed']",
    message:
      'toFixed formatea con punto: usa formatNumber de @/shared/lib/format (o Math.round para redondear un valor).',
  },
];
// Screens use the shared controls so every select and text area looks and sizes the same.
const controlRules = [
  {
    selector: "JSXOpeningElement[name.name='select']",
    message: 'Usa NativeSelect de @/shared/ui/native-select.',
  },
  {
    selector: "JSXOpeningElement[name.name='textarea']",
    message: 'Usa Textarea de @/shared/ui/textarea.',
  },
];

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'test-results/**',
      'playwright-report/**',
      'src/shared/api/generated/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{js,mjs,ts,tsx}'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/shared/lib/format.ts'],
    rules: { 'no-restricted-syntax': ['error', ...formatRules] },
  },
  {
    files: ['src/features/**/*.tsx', 'src/app/**/*.tsx'],
    rules: { 'no-restricted-syntax': ['error', ...formatRules, ...controlRules] },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { 'react-hooks': hooks, 'react-refresh': refresh },
    rules: {
      ...hooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true, allowExportNames: ['buttonVariants', 'badgeVariants'] },
      ],
    },
  },
);
