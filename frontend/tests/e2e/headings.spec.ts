import { expect, test, type Page } from '@playwright/test';

/** Every heading in document order, as a screen reader lists them (closed folds included). */
async function headings(page: Page) {
  return page.locator('main').evaluate((main) =>
    Array.from(main.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]')).map((node) => ({
      level: Number(node.getAttribute('aria-level') ?? node.tagName.slice(1)),
      name: (node.textContent ?? '').trim().replace(/\s+/g, ' '),
    })),
  );
}

/** One h1 first, and no level skipped on the way down (h2 → h4 is a skip; h4 → h2 is not). */
function skips(list: { level: number; name: string }[]) {
  const problems: string[] = [];
  if (list[0]?.level !== 1) problems.push('la página no empieza por un h1');
  if (list.filter((item) => item.level === 1).length !== 1) problems.push('más de un h1');
  list.forEach((item, index) => {
    const previous = list[index - 1];
    if (previous && item.level > previous.level + 1)
      problems.push(`h${previous.level} «${previous.name}» → h${item.level} «${item.name}»`);
  });
  return problems;
}

const pages: { path: string; sections: string[] }[] = [
  {
    path: '/administracion',
    sections: ['Datos', 'Actualizar datos', 'Configuración local', 'Modo de trabajo', 'Trabajos'],
  },
  {
    path: '/empresas/T001',
    sections: [
      'Histórico de precios',
      'Checklist fundamental',
      'Modelo y procedencia',
      'Documentos y próximas cuentas',
      'Próximos catalizadores',
    ],
  },
  { path: '/cartera/seguimiento', sections: [] },
];

for (const { path, sections } of pages) {
  test(`${path}: cada sección tiene un encabezado y ninguno se salta un nivel (#178)`, async ({
    page,
  }) => {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await page.waitForLoadState('networkidle');
    const list = await headings(page);
    expect(skips(list), JSON.stringify(list, null, 1)).toEqual([]);
    for (const name of sections)
      expect(
        list.some((item) => item.level > 1 && item.name.startsWith(name)),
        `«${name}» no es un encabezado: ${JSON.stringify(list.map((item) => item.name))}`,
      ).toBe(true);
  });
}
