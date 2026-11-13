import { X } from 'lucide-react';
import type { ActiveFilter } from './active-filters';

/** The filters in force as tags; «×» removes only that one, at once (#320). */
export function ActiveFilterTags({
  filters,
  remove,
}: {
  filters: ActiveFilter[];
  remove: (updates: ActiveFilter['remove']) => void;
}) {
  if (!filters.length) return null;
  return (
    <div
      aria-label="Filtros activos"
      role="group"
      className="mt-3 flex flex-wrap items-center gap-2 text-xs"
    >
      <span className="font-medium">Filtros activos:</span>
      {filters.map((filter) => (
        <span
          key={filter.key}
          className="inline-flex items-center gap-1 rounded-full border bg-muted/40 py-0.5 pl-2.5 pr-1"
        >
          {filter.label}
          <button
            type="button"
            className="rounded-full p-0.5 hover:bg-muted"
            aria-label={'Quitar filtro: ' + filter.label}
            onClick={() => remove(filter.remove)}
          >
            <X size={14} aria-hidden="true" />
          </button>
        </span>
      ))}
    </div>
  );
}
