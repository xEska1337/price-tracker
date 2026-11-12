interface SparklineProps {
  points: number[];
  width?: number;
  height?: number;
}

const FLAT = '#6b7280';
const DOWN = '#22c55e';
const UP = '#ef4444';

export function Sparkline({ points, width = 120, height = 32 }: SparklineProps) {
  const data = (points ?? []).filter((p) => Number.isFinite(p));

  if (data.length === 0) {
    return (
      <svg
        className="sparkline"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="no data"
      >
        <line
          x1="4"
          y1={height / 2}
          x2={width - 4}
          y2={height / 2}
          stroke="#4b5563"
          strokeWidth="1"
          strokeDasharray="2 4"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  if (data.length === 1) {

    return (
      <svg
        className="sparkline"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="single price measurement"
      >
        <circle cx={width / 2} cy={height / 2} r="2.5" fill={FLAT} />
      </svg>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const pad = 2;
  const span = max - min || 1;
  const stepX = width / (data.length - 1);

  const coords = data.map((value, index) => {
    const x = index * stepX;
    const y = height - pad - ((value - min) / span) * (height - pad * 2);
    return { x: Number(x.toFixed(1)), y: Number(y.toFixed(1)) };
  });

  const first = data[0];
  const last = data[data.length - 1];
  const color = last < first ? DOWN : last > first ? UP : FLAT;
  const lastPoint = coords[coords.length - 1];

  return (
    <svg
      className="sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="price chart"
    >
      <polyline
        points={coords.map((p) => `${p.x},${p.y}`).join(' ')}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={lastPoint.x} cy={lastPoint.y} r="2" fill={color} />
    </svg>
  );
}
