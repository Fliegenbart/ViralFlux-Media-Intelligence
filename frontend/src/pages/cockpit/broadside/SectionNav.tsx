import React, { useEffect, useState } from 'react';

/**
 * SectionNav — floating section-index at the right margin of the
 * broadside. Shows §-numerals + italic section-labels, highlights
 * the one currently in the viewport (scroll-spy via IntersectionObserver),
 * and scrolls smoothly to the anchor on click.
 *
 * Visual idiom: small cream-paper card stuck to the right edge,
 * mono numerals + serif-italic labels.
 */

export interface SectionNavItem {
  id: string;         // DOM id of the <section>
  numeral: string;    // § I · § II …
  label: string;      // "Entscheidung"
}

interface Props {
  items: SectionNavItem[];
}

export const SectionNav: React.FC<Props> = ({ items }) => {
  const [activeId, setActiveId] = useState<string>(items[0]?.id ?? '');

  useEffect(() => {
    // Observe each section; mark the one most central to the viewport as
    // "active". The rootMargin pulls the trigger band up so the transition
    // happens slightly before a section reaches the exact middle — feels
    // more accurate when scrolling down.
    const elements = items
      .map((it) => document.getElementById(it.id))
      .filter((el): el is HTMLElement => el !== null);
    if (elements.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        // Among intersecting entries, pick the one with the highest ratio.
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible.length > 0) {
          setActiveId(visible[0].target.id);
        }
      },
      {
        // Triggers when the centerline of the section crosses the band
        // that spans roughly the middle 30 % of the viewport.
        rootMargin: '-40% 0px -55% 0px',
        threshold: [0, 0.25, 0.5, 0.75, 1],
      },
    );
    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [items]);

  const scrollTo = (id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    // Optimistically update so the highlight doesn't lag behind the scroll
    setActiveId(id);
  };

  return (
    <nav className="ex-broadside-toc" aria-label="Abschnittsnavigation">
      {items.map((it, i) => (
        <React.Fragment key={it.id}>
          <button
            type="button"
            className={
              'ex-broadside-toc__item' +
              (activeId === it.id ? ' ex-broadside-toc__item--active' : '')
            }
            onClick={() => scrollTo(it.id)}
            aria-current={activeId === it.id ? 'true' : undefined}
          >
            <span className="ex-broadside-toc__num">{it.numeral}</span>
            <span className="ex-broadside-toc__label">{it.label}</span>
          </button>
          {i < items.length - 1 && <span className="ex-broadside-toc__rule" aria-hidden />}
        </React.Fragment>
      ))}
    </nav>
  );
};

export default SectionNav;
