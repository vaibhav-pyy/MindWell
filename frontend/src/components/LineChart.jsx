import { useId, useState } from 'react';
import { formatDate } from '../lib/hooks';

/**
 * Single-series line chart on a fixed 0-100 scale, with hover/focus tooltip and a table view.
 * points: [{ x: 'YYYY-MM-DD', y: number|null, label?: string }]
 * Gaps (null) break the line rather than being interpolated.
 */
export default function LineChart({ points, title, valueLabel = 'Value', height = 180, emptyText = 'No data yet.' }) {
  const [active, setActive] = useState(null);
  const [showTable, setShowTable] = useState(false);
  const tableId = useId();
  const width = 600;
  const pad = { l: 32, r: 12, t: 12, b: 26 };
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  const valid = points.filter((p) => p.y !== null && p.y !== undefined);

  if (!valid.length) return <p className="muted small">{emptyText}</p>;

  const xAt = (i) => pad.l + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const yAt = (v) => pad.t + innerH - (v / 100) * innerH;

  const segments = [];
  let current = [];
  points.forEach((p, i) => {
    if (p.y === null || p.y === undefined) {
      if (current.length) segments.push(current);
      current = [];
    } else current.push(`${xAt(i)},${yAt(p.y)}`);
  });
  if (current.length) segments.push(current);

  const labelEvery = Math.max(1, Math.ceil(points.length / 6));
  const activePoint = active !== null ? points[active] : null;

  return (
    <div className="chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title}. ${valid.length} data points. Use the table view for exact values.`}
        onMouseLeave={() => setActive(null)}
      >
        {[0, 25, 50, 75, 100].map((v) => (
          <g key={v}>
            <line className="grid-line" x1={pad.l} x2={width - pad.r} y1={yAt(v)} y2={yAt(v)} />
            <text className="axis-label" x={pad.l - 8} y={yAt(v) + 4} textAnchor="end">
              {v}
            </text>
          </g>
        ))}
        {points.map((p, i) =>
          i % labelEvery === 0 || i === points.length - 1 ? (
            <text key={p.x} className="axis-label" x={xAt(i)} y={height - 6} textAnchor="middle">
              {p.label || formatDate(p.x)}
            </text>
          ) : null,
        )}
        {activePoint && activePoint.y != null && (
          <line className="crosshair" x1={xAt(active)} x2={xAt(active)} y1={pad.t} y2={pad.t + innerH} />
        )}
        {segments.map((s, i) =>
          s.length > 1 ? <polyline key={i} className="series" points={s.join(' ')} /> : null,
        )}
        {points.map((p, i) =>
          p.y == null ? null : (
            <g key={p.x}>
              <circle className={`point ${active === i ? 'active' : ''}`} cx={xAt(i)} cy={yAt(p.y)} r={4.5} />
              <rect
                x={xAt(i) - Math.max(8, innerW / points.length / 2)}
                y={pad.t}
                width={Math.max(16, innerW / points.length)}
                height={innerH}
                fill="transparent"
                tabIndex={0}
                aria-label={`${p.label || formatDate(p.x)}: ${valueLabel} ${Math.round(p.y)}`}
                onMouseEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
              />
            </g>
          ),
        )}
      </svg>
      {activePoint && activePoint.y != null && (
        <div
          className="chart-tooltip"
          style={{ left: `${(xAt(active) / width) * 100}%`, top: `${(yAt(activePoint.y) / height) * 100}%` }}
        >
          {activePoint.label || formatDate(activePoint.x)} · {valueLabel} {Math.round(activePoint.y)}
        </div>
      )}
      <button className="btn btn-ghost btn-sm" aria-expanded={showTable} aria-controls={tableId} onClick={() => setShowTable((s) => !s)}>
        {showTable ? 'Hide table' : 'Show as table'}
      </button>
      {showTable && (
        <div className="table-scroll" id={tableId}>
          <table className="data">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">{valueLabel}</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.x}>
                  <td>{p.label || formatDate(p.x, { day: 'numeric', month: 'short', year: 'numeric' })}</td>
                  <td>{p.y == null ? '—' : Math.round(p.y)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
