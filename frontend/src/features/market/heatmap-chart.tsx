import { useNavigate } from 'react-router-dom';
import { ResponsiveContainer, Tooltip, Treemap } from 'recharts';
import type { HeatmapCompany, HeatmapResponse } from '@/shared/api/generated/types.gen';
import { formatCompactMoney, formatNumber } from '@/shared/lib/format';
import { BAND } from './heatmap-colors';

type Leaf = HeatmapCompany & { size: number };
type Frame = {
  x: number;
  y: number;
  width: number;
  height: number;
  name: string;
  children?: unknown[];
};
type TileProps = {
  index?: number;
  root?: Frame;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  depth?: number;
  name?: string;
  payload?: Leaf;
} & Partial<Leaf>;

/** A company tile (depth 2) or a sector frame with its name (depth 1). */
function Tile(props: TileProps) {
  const { x = 0, y = 0, width = 0, height = 0, depth } = props;
  if (depth === 1) return null; // Drawn by its last company, so the frame stays on top.
  if (depth !== 2 || !props.symbol || !props.band) return null;
  const band = BAND[props.band];
  const roomy = width > 38 && height > 26;
  // Below the sector's name when the tile touches the sector's top edge.
  const shift = props.root && Math.abs(y - props.root.y) < 1 && height > 44 ? 9 : 0;
  return (
    <g style={{ cursor: 'pointer' }}>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={band.fill}
        stroke="#fcfcfb"
        strokeWidth={2}
        strokeDasharray={props.band === 'none' ? '3 2' : undefined}
      />
      {roomy && (
        <text
          x={x + width / 2}
          y={y + height / 2 - 2 + shift}
          textAnchor="middle"
          fontSize={11}
          fontWeight={600}
          fill={band.ink}
          stroke="none"
        >
          {props.symbol}
        </text>
      )}
      {roomy && (
        <text
          x={x + width / 2}
          y={y + height / 2 + 11 + shift}
          textAnchor="middle"
          fontSize={10}
          fill={band.ink}
          stroke="none"
        >
          {props.composite_score == null ? '—' : formatNumber(props.composite_score, { digits: 0 })}
        </text>
      )}
      {props.root && props.index === (props.root.children?.length ?? 0) - 1 && (
        <SectorFrame frame={props.root} />
      )}
    </g>
  );
}

/** The sector's border and name, over its companies. */
function SectorFrame({ frame }: { frame: Frame }) {
  const label = frame.width > 80 && frame.height > 30;
  return (
    <g pointerEvents="none">
      <rect
        x={frame.x}
        y={frame.y}
        width={frame.width}
        height={frame.height}
        fill="none"
        stroke="#0b0b0b"
        strokeWidth={2}
      />
      {label && (
        <>
          <rect
            x={frame.x + 2}
            y={frame.y + 2}
            width={Math.min(frame.width - 4, frame.name.length * 6.5 + 10)}
            height={17}
            fill="#fcfcfb"
            opacity={0.92}
          />
          <text
            x={frame.x + 7}
            y={frame.y + 14}
            fontSize={11}
            fontWeight={600}
            fill="#0b0b0b"
            stroke="none"
          >
            {frame.name.length * 6.5 + 10 > frame.width - 4
              ? frame.name.slice(0, Math.max(3, Math.floor((frame.width - 20) / 6.5))) + '…'
              : frame.name}
          </text>
        </>
      )}
    </g>
  );
}

function Hover({ active, payload }: { active?: boolean; payload?: { payload: Leaf }[] }) {
  const item = payload?.[0]?.payload;
  if (!active || !item?.symbol) return null;
  return (
    <div className="max-w-64 rounded-lg border bg-card p-2 text-xs shadow">
      <p className="font-semibold">
        {item.symbol} · {item.name}
      </p>
      <p className="text-muted-foreground">{item.sector}</p>
      <p className="mt-1">
        {item.composite_score == null
          ? item.reason
          : `Puntuación ${formatNumber(item.composite_score, { digits: 1 })} (${BAND[item.band].label}) · puesto ${item.rank}`}
      </p>
      <p className="text-muted-foreground">En bolsa: {formatCompactMoney(item.market_cap)}</p>
    </div>
  );
}

/** The map itself; companies without a value in the stock market cannot be sized and are listed apart. */
export default function HeatmapChart({ data }: { data: HeatmapResponse }) {
  const navigate = useNavigate();
  const tree = data.sectors
    .map((sector) => ({
      name: sector.sector,
      children: data.companies
        .filter((item) => item.sector === sector.sector && item.market_cap != null)
        .map((item) => ({ ...item, size: item.market_cap ?? 0 })),
    }))
    .filter((sector) => sector.children.length > 0);
  return (
    <div
      className="h-[640px] w-full rounded-xl border bg-card p-2"
      role="img"
      aria-label="Mapa de las empresas por sector, tamaño en bolsa y puntuación GABI. La misma información está en la lista por sectores."
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <Treemap
          data={tree}
          dataKey="size"
          nameKey="name"
          isAnimationActive={false}
          content={<Tile />}
          onClick={(node) => {
            const symbol = (node as unknown as { symbol?: string }).symbol;
            if (symbol) navigate('/empresas/' + encodeURIComponent(symbol));
          }}
        >
          <Tooltip content={<Hover />} />
        </Treemap>
      </ResponsiveContainer>
    </div>
  );
}
