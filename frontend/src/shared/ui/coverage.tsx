/** Backend warnings mark emphasis with **…**; show it as bold without parsing other Markdown. */
export function WarningText({ text }: { text: string }) {
  return (
    <>
      {text
        .split('**')
        .map((part, index) =>
          index % 2 ? <strong key={index}>{part}</strong> : <span key={index}>{part}</span>,
        )}
    </>
  );
}

export function CoverageThreshold({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="text-xs font-medium">
      Cobertura completa mínima (%)
      <input
        className="mt-1.5 block h-10 w-28 rounded-md border bg-background px-2 text-sm"
        type="number"
        min={0}
        max={100}
        step={5}
        value={Math.round(value * 100)}
        onChange={(event) => onChange(Math.min(Math.max(Number(event.target.value), 0), 100) / 100)}
      />
    </label>
  );
}
