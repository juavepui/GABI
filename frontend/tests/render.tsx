import type { ReactNode } from 'react';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/** Renders a screen with its own query cache and router, without network or a backend. */
export function renderScreen(node: ReactNode, path = '/') {
  const container = document.createElement('div');
  document.body.append(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let root: Root;
  act(() => {
    root = createRoot(container);
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>
      </QueryClientProvider>,
    );
  });
  return {
    container,
    text: () => container.textContent ?? '',
    /** Waits until the visible text contains `expected`. */
    async findText(expected: string) {
      for (let attempt = 0; attempt < 50; attempt++) {
        if (container.textContent?.includes(expected)) return;
        await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
      }
      throw new Error(`«${expected}» no aparece en: ${container.textContent}`);
    },
    unmount() {
      act(() => root.unmount());
      container.remove();
    },
  };
}
