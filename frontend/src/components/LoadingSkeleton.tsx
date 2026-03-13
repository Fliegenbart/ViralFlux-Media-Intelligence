import React from 'react';

interface Props {
  lines?: number;
  style?: React.CSSProperties;
}

const LoadingSkeleton: React.FC<Props> = ({ lines = 3, style }) => (
  <div style={style} role="status" aria-label="Laden...">
    {Array.from({ length: lines }).map((_, i) => (
      <div
        key={i}
        className="skeleton-line"
        style={{
          height: i === 0 ? 20 : 14,
          width: i === lines - 1 ? '60%' : '100%',
          borderRadius: 4,
          background: 'var(--border-color, #e2e8f0)',
          marginBottom: 12,
          animation: 'skeleton-pulse 1.5s ease-in-out infinite',
        }}
      />
    ))}
    <style>{`
      @keyframes skeleton-pulse {
        0%, 100% { opacity: 0.4; }
        50% { opacity: 0.8; }
      }
      @media (prefers-reduced-motion: reduce) {
        .skeleton-line { animation: none !important; opacity: 0.5; }
      }
    `}</style>
  </div>
);

export default LoadingSkeleton;
