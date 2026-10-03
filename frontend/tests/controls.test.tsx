import { readFileSync } from 'node:fs';
import path from 'node:path';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
import { Button } from '../src/shared/ui/button';
import { NativeSelect, NativeSelectOption } from '../src/shared/ui/native-select';
import { Textarea } from '../src/shared/ui/textarea';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;

function render(node: React.ReactNode) {
  container = document.createElement('div');
  document.body.append(container);
  const root = createRoot(container);
  act(() => root.render(node));
  return container;
}

afterEach(() => container?.remove());

describe('shared controls', () => {
  it('NativeSelect places the wrapper with className and keeps one look for the select', () => {
    const view = render(
      <NativeSelect aria-label="Familia" className="mt-1 w-full">
        <NativeSelectOption value="a">A</NativeSelectOption>
      </NativeSelect>,
    );
    const wrapper = view.querySelector('[data-slot="native-select-wrapper"]')!;
    const select = view.querySelector('select')!;
    expect(wrapper.className).toContain('w-full');
    expect(wrapper.className).not.toContain('w-fit');
    expect(select.className).toContain('h-9');
    expect(select.className).toContain('text-sm');
    expect(select.className).not.toContain('mt-1');
  });

  it('Textarea and Button share the small text size', () => {
    const view = render(
      <>
        <Textarea aria-label="Notas" className="min-h-16" />
        <Button>Guardar</Button>
      </>,
    );
    const textarea = view.querySelector('textarea')!;
    expect(textarea.dataset.slot).toBe('textarea');
    expect(textarea.className).toContain('text-sm');
    expect(textarea.className).toContain('min-h-16');
    expect(textarea.className).not.toContain('min-h-20');
    expect(view.querySelector('button')!.className).toContain('text-sm');
  });
});

describe('theme.css', () => {
  it('keeps element rules in the base layer so Tailwind utilities can size controls', () => {
    const css = readFileSync(path.join(process.cwd(), 'src/shared/ui/theme.css'), 'utf8');
    const unlayered = css.replace(/@layer base \{[\s\S]*?\n\}/, '');
    for (const selector of ['button,', '* {', ':focus-visible', "input[type='checkbox']"]) {
      expect(css).toContain(selector);
      expect(unlayered).not.toContain(selector);
    }
  });
});
