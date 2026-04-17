import React from 'react';

/**
 * GalleryHero — the shared "exhibit stage" used by Decision / Timeline /
 * Impact tabs. The Atlas (tab 02) remains special (it owns the 3D canvas)
 * but every other tab uses this component as its hero, so the cockpit
 * reads as one curated object rather than four disparate pages.
 *
 * Composition:
 *   +------------------+---------------------+
 *   |  editorial lede  |    hero visual      |
 *   +------------------+---------------------+
 *   |         caption strip (optional)       |
 *   +-----------------------------------------+
 *
 * The lede side takes kicker + headline + dek + optional actions.
 * The visual side is caller-controlled — a big number block, a chart,
 * a mini-map, anything.
 *
 * Variants:
 *   - `size="short"` → 440 min-height (for chart-heavy pages)
 *   - `size="tall"`  → 620 min-height (for full-bleed imagery)
 *   - default         → 520
 */

export interface GalleryHeroCaption {
  label: string;           // e.g. "Diagramm 01" — always terracotta
  scale?: React.ReactNode; // optional middle column (gradient bar etc.)
  meta?: React.ReactNode;  // right column (small tabular meta)
}

interface Props {
  kicker: string;
  headline: React.ReactNode;
  dek?: React.ReactNode;
  actions?: React.ReactNode;
  visual: React.ReactNode;
  caption?: GalleryHeroCaption;
  size?: 'short' | 'tall';
}

export const GalleryHero: React.FC<Props> = ({
  kicker,
  headline,
  dek,
  actions,
  visual,
  caption,
  size,
}) => {
  const sizeClass =
    size === 'short'
      ? 'peix-gal-stage--short'
      : size === 'tall'
        ? 'peix-gal-stage--tall'
        : '';
  return (
    <section className={`peix-gal-stage ${sizeClass}`.trim()}>
      <div className="peix-gal-stage__grain" aria-hidden />
      <div className="peix-gal-stage__vignette" aria-hidden />

      <div className="peix-gal-stage__lede">
        <div className="peix-gal-stage__kicker">
          <span className="peix-gal-stage__mark">◆</span>
          <span>{kicker}</span>
        </div>
        <h1 className="peix-gal-stage__headline">{headline}</h1>
        {dek && <p className="peix-gal-stage__dek">{dek}</p>}
        {actions && <div className="peix-gal-stage__actions">{actions}</div>}
      </div>

      <div className="peix-gal-stage__visual">{visual}</div>

      {caption && (
        <figcaption className="peix-gal-caption">
          <span className="peix-gal-caption__label">{caption.label}</span>
          <span className="peix-gal-caption__scale">
            {caption.scale ?? (
              <>
                <span className="peix-gal-caption__tick">—</span>
                <span className="peix-gal-caption__bar" />
                <span className="peix-gal-caption__tick">+</span>
              </>
            )}
          </span>
          <span className="peix-gal-caption__meta">{caption.meta ?? ''}</span>
        </figcaption>
      )}
    </section>
  );
};

export default GalleryHero;
