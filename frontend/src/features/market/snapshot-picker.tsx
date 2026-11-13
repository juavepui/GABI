import { dateLabel } from '@/shared/lib/format';
import { NativeSelect } from '@/shared/ui/native-select';

export function SnapshotPicker({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: { id: number; name: string; as_of_date: string }[];
  value: number;
  onChange: (id: number) => void;
}) {
  return (
    <label className="text-sm">
      {label}
      <NativeSelect
        name="snapshot_id"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1 h-9 w-full rounded-md border bg-background px-2"
      >
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name} · {dateLabel(item.as_of_date)}
          </option>
        ))}
      </NativeSelect>
    </label>
  );
}
