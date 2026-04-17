import React, { useEffect, useMemo, useRef } from 'react';
import type { RegionForecast, Bundesland } from '../../../pages/cockpit/types';
import { fmtSignedPct } from '../../../pages/cockpit/format';

/**
 * Tab 02 — Wellen-Atlas.
 *
 * A data sculpture. 16 Bundesländer rise from a circular pedestal as
 * extruded, bevel-edged blocks; their height encodes the 7-day delta.
 *
 * Aesthetic direction (2026-04-17 refactor): "exhibit piece in a gallery".
 * We intentionally avoid demo-reel flourishes (spinning objects, colour
 * cycles, chrome plastics). Instead:
 *   - MeshPhysicalMaterial with clearcoat for a ceramic-on-wood feel
 *   - Three-point museum lighting with warm key / cool fill / cool rim
 *   - A soft circular pedestal instead of an infinite ground plane
 *   - An almost-imperceptible breath animation (±0.85°) — the object is
 *     still; the viewer is implied to move
 *   - Warm-earth palette mapped to delta7d buckets
 *
 * Engineering:
 *   - Scene mounts ONCE per virus scope. Region updates mutate geometry
 *     and material on existing meshes, so SWR refetches no longer cause
 *     a full teardown + rebuild ("zuppel" bug from 2026-04-17).
 *   - ResizeObserver debounced via rAF to avoid layout-thrash loops.
 *   - three.js is code-split via dynamic import so tab 01 stays lean.
 */

// Schematic grid matching GermanyChoropleth.tsx for visual continuity.
const TILES: Array<{ code: Bundesland; x: number; y: number; w?: number; h?: number }> = [
  { code: 'SH', x: 3, y: 0, w: 2 },
  { code: 'HH', x: 3, y: 1 },
  { code: 'MV', x: 4, y: 1, w: 2 },
  { code: 'HB', x: 2, y: 2 },
  { code: 'NI', x: 3, y: 2, w: 2 },
  { code: 'BE', x: 5, y: 2 },
  { code: 'BB', x: 5, y: 3 },
  { code: 'NW', x: 1, y: 3, w: 2 },
  { code: 'ST', x: 4, y: 3 },
  { code: 'SN', x: 5, y: 4 },
  { code: 'HE', x: 2, y: 4 },
  { code: 'TH', x: 3, y: 4 },
  { code: 'RP', x: 1, y: 5 },
  { code: 'BW', x: 2, y: 5, h: 2 },
  { code: 'BY', x: 3, y: 5, w: 2, h: 2 },
  { code: 'SL', x: 1, y: 6 },
];

interface Props {
  regions: RegionForecast[];
  headline: string;
  dek: string;
}

// --- Palette ---------------------------------------------------------------
// Warm-earth scale for rising waves, muted-cool scale for falling. Hex values
// picked to feel like pigment on paper rather than RGB-phosphor.
const PALETTE = {
  rising: {
    strong: 0xb94a2e,  // fired terracotta
    medium: 0xd16f3a,  // burnt ochre
    soft:   0xe3a26a,  // sienna tint
  },
  falling: {
    soft:   0x6b7a6a,  // aged moss
    medium: 0x4b5962,  // cool slate
    strong: 0x3a4450,  // deep slate
  },
  neutral: 0x8a7962,   // raw umber
  missing: 0x2f2a26,   // very dim (no regional model)
  pedestal: 0x2a241e,  // warm black, slightly lighter than bg
  background: 0x14110d, // near-black with warm cast
};

function pickColourHex(d: number | null): number {
  if (d === null || !Number.isFinite(d)) return PALETTE.missing;
  if (d >= 0.20) return PALETTE.rising.strong;
  if (d >= 0.10) return PALETTE.rising.medium;
  if (d >= 0.04) return PALETTE.rising.soft;
  if (d >= -0.04) return PALETTE.neutral;
  if (d >= -0.12) return PALETTE.falling.soft;
  if (d >= -0.20) return PALETTE.falling.medium;
  return PALETTE.falling.strong;
}

// Map delta7d to tower height in scene units. The curve is asymmetric:
// rising waves lift more than falling waves sink, because visually a "tall"
// warm tower reads as alarming where a "buried" cool tower reads as absent
// rather than relieving.
function heightForDelta(delta: number): number {
  const base = 0.35;
  if (delta >= 0) return base + delta * 11.0;
  return Math.max(0.12, base + delta * 1.1);
}

export const DataSculpture: React.FC<Props> = ({ regions, headline, dek }) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  // Scene handles are kept in a ref so we can mutate them on region updates
  // without tearing down the whole scene.
  const sceneStateRef = useRef<{
    THREE: any;
    scene: any;
    camera: any;
    renderer: any;
    group: any;
    meshesByCode: Map<string, any>;
    applyRegions: (byCode: Map<Bundesland, RegionForecast>) => void;
    cancel: () => void;
  } | null>(null);

  const regionsByCode = useMemo(() => {
    const m = new Map<Bundesland, RegionForecast>();
    regions.forEach((r) => m.set(r.code, r));
    return m;
  }, [regions]);

  // Keep the latest regionsByCode in a ref so the async `init()` can apply
  // the most recent data once the scene is ready, regardless of whether the
  // mount-effect closure captured an earlier/empty snapshot.
  const latestRegionsRef = useRef<Map<Bundesland, RegionForecast>>(regionsByCode);
  latestRegionsRef.current = regionsByCode;

  // Mount-once effect. Builds the whole scene the first time the component
  // renders, then never rebuilds — region updates go through the second
  // useEffect below.
  useEffect(() => {
    let disposed = false;

    async function init() {
      const el = mountRef.current;
      if (!el) return;

      let THREE: any;
      try {
        THREE = await import('three');
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('DataSculpture: three.js chunk failed to load', err);
        el.innerHTML = `<div class="peix-stage-fallback">
          Der 3D-Atlas konnte gerade nicht geladen werden.<br/>
          Dieselben Bundesländer-Daten findest du auch in Tab 1 &bdquo;Die Entscheidung&ldquo;.
        </div>`;
        return;
      }
      if (disposed) return;

      const width = el.clientWidth || 600;
      const height = el.clientHeight || 420;

      const scene = new THREE.Scene();
      scene.background = null; // CSS supplies the gallery wall
      scene.fog = new THREE.FogExp2(PALETTE.background, 0.032);

      // Camera: three-quarter view, slightly elevated. Static focal length;
      // no zoom animation.
      const camera = new THREE.PerspectiveCamera(34, width / height, 0.1, 120);
      camera.position.set(8.4, 9.2, 13.8);
      camera.lookAt(0, 1.0, 0);

      const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(width, height);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      if ('toneMapping' in renderer) {
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.05;
      }
      el.appendChild(renderer.domElement);

      // --- Lighting: museum three-point ------------------------------------
      // Warm key from upper-left, cool fill from lower-right, cool rim
      // behind. Values tuned by eye; clearcoat picks up the key sharply.
      const key = new THREE.DirectionalLight(0xf9d9a5, 2.4);
      key.position.set(8, 14, 6);
      scene.add(key);

      const fill = new THREE.DirectionalLight(0x9fb4c8, 0.55);
      fill.position.set(-6, 3, 8);
      scene.add(fill);

      const rim = new THREE.DirectionalLight(0xb8c4d8, 0.9);
      rim.position.set(-3, 6, -10);
      scene.add(rim);

      const ambient = new THREE.AmbientLight(0x3a3229, 0.28);
      scene.add(ambient);

      // --- Pedestal ---------------------------------------------------------
      // A low cylindrical base — not a flat infinite plane. Gives the
      // sculpture a "displayed" quality.
      const pedestalGeo = new THREE.CylinderGeometry(7.6, 7.9, 0.22, 96, 1, false);
      const pedestalMat = new THREE.MeshStandardMaterial({
        color: PALETTE.pedestal,
        roughness: 0.9,
        metalness: 0.0,
      });
      const pedestal = new THREE.Mesh(pedestalGeo, pedestalMat);
      pedestal.position.y = -0.11;
      scene.add(pedestal);

      // Subtle ground shadow catcher so the blocks feel planted.
      const catcherGeo = new THREE.CircleGeometry(7.4, 96);
      const catcherMat = new THREE.MeshBasicMaterial({
        color: 0x000000,
        transparent: true,
        opacity: 0.22,
      });
      const catcher = new THREE.Mesh(catcherGeo, catcherMat);
      catcher.rotation.x = -Math.PI / 2;
      catcher.position.y = 0.001;
      scene.add(catcher);

      // --- Group for the sculpture itself ----------------------------------
      const group = new THREE.Group();
      scene.add(group);

      // Per-code mesh registry so region updates can mutate in place.
      const meshesByCode = new Map<string, any>();
      const geometryCache = new Map<string, any>();

      // Helper: build a bevelled extrude-geometry for a tower. ExtrudeBuffer
      // lets us do a tiny bevel without paying much perf, which reads as
      // crafted rather than generic-cube.
      const cellSize = 1.18;
      const gap = 0.1;

      const buildGeometry = (width: number, depth: number, height: number) => {
        const shape = new THREE.Shape();
        const hw = width / 2;
        const hd = depth / 2;
        const r = 0.08; // corner radius
        shape.moveTo(-hw + r, -hd);
        shape.lineTo(hw - r, -hd);
        shape.quadraticCurveTo(hw, -hd, hw, -hd + r);
        shape.lineTo(hw, hd - r);
        shape.quadraticCurveTo(hw, hd, hw - r, hd);
        shape.lineTo(-hw + r, hd);
        shape.quadraticCurveTo(-hw, hd, -hw, hd - r);
        shape.lineTo(-hw, -hd + r);
        shape.quadraticCurveTo(-hw, -hd, -hw + r, -hd);
        const geo = new THREE.ExtrudeGeometry(shape, {
          depth: Math.max(0.08, height),
          bevelEnabled: true,
          bevelThickness: 0.03,
          bevelSize: 0.03,
          bevelSegments: 2,
          curveSegments: 4,
        });
        // ExtrudeGeometry extrudes along +Z by default; rotate so it grows
        // up along +Y like a tower.
        geo.rotateX(-Math.PI / 2);
        return geo;
      };

      // Build initial meshes with height=base; the update effect will set
      // real heights.
      TILES.forEach((t) => {
        const w = (t.w || 1) * cellSize + ((t.w || 1) - 1) * gap;
        const d = (t.h || 1) * cellSize + ((t.h || 1) - 1) * gap;
        const baseHeight = 0.5;
        const geo = buildGeometry(w, d, baseHeight);
        geometryCache.set(t.code, { w, d, h: baseHeight });
        const mat = new THREE.MeshPhysicalMaterial({
          color: PALETTE.missing,
          roughness: 0.55,
          metalness: 0.0,
          clearcoat: 0.35,
          clearcoatRoughness: 0.4,
          reflectivity: 0.18,
        });
        const mesh = new THREE.Mesh(geo, mat);
        // centre the sculpture: max x is ~6, max y (grid) is 6; shift by
        // the centroid of the occupied grid so the sculpture sits on the
        // pedestal centre.
        const x = t.x * (cellSize + gap) - 3.6;
        const z = t.y * (cellSize + gap) - 3.4;
        mesh.position.set(x, 0, z);
        mesh.userData = { code: t.code };
        group.add(mesh);
        meshesByCode.set(t.code, mesh);
      });

      // Slightly tilt the whole group for a three-quarter reading.
      group.rotation.y = -0.14;

      // --- Motion: breath only --------------------------------------------
      // A single sine wave with very low amplitude. Readers who stare
      // will see it; readers who glance won't — that's the gallery feel.
      let raf = 0;
      const startedAt = performance.now();
      const animate = () => {
        const t = (performance.now() - startedAt) / 1000;
        const breath = Math.sin(t * (Math.PI * 2) / 12) * 0.015; // ±0.86°
        group.rotation.y = -0.14 + breath;
        renderer.render(scene, camera);
        raf = requestAnimationFrame(animate);
      };
      animate();

      // --- Resize, debounced via rAF ---------------------------------------
      let resizeScheduled = false;
      const resize = () => {
        if (resizeScheduled) return;
        resizeScheduled = true;
        requestAnimationFrame(() => {
          resizeScheduled = false;
          if (!mountRef.current) return;
          const w = mountRef.current.clientWidth;
          const h = mountRef.current.clientHeight;
          if (w === 0 || h === 0) return;
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          renderer.setSize(w, h);
        });
      };
      const ro = new ResizeObserver(resize);
      ro.observe(el);

      const cancel = () => {
        cancelAnimationFrame(raf);
        ro.disconnect();
        meshesByCode.forEach((m) => {
          if (m.geometry) m.geometry.dispose();
          if (m.material) m.material.dispose();
        });
        pedestalGeo.dispose();
        pedestalMat.dispose();
        catcherGeo.dispose();
        catcherMat.dispose();
        renderer.dispose();
        try {
          el.removeChild(renderer.domElement);
        } catch {
          /* element already gone */
        }
      };

      // Apply region data to existing meshes — mutates geometry and colour
      // in place. Called once right after scene setup AND on every
      // regionsByCode change (via the second effect below).
      const applyRegions = (byCode: Map<Bundesland, RegionForecast>) => {
        const cellSizeLocal = 1.18;
        const gapLocal = 0.1;
        TILES.forEach((t) => {
          const mesh = meshesByCode.get(t.code);
          if (!mesh) return;
          const r = byCode.get(t.code);
          const delta =
            r && typeof r.delta7d === 'number' && Number.isFinite(r.delta7d)
              ? r.delta7d
              : null;
          const targetHeight = delta === null ? 0.18 : heightForDelta(delta);
          const oldHeight = mesh.userData.currentHeight;
          if (oldHeight === undefined || Math.abs(oldHeight - targetHeight) > 0.02) {
            const widthL = (t.w || 1) * cellSizeLocal + ((t.w || 1) - 1) * gapLocal;
            const depthL = (t.h || 1) * cellSizeLocal + ((t.h || 1) - 1) * gapLocal;
            const shapeL = new THREE.Shape();
            const hwL = widthL / 2;
            const hdL = depthL / 2;
            const crL = 0.08;
            shapeL.moveTo(-hwL + crL, -hdL);
            shapeL.lineTo(hwL - crL, -hdL);
            shapeL.quadraticCurveTo(hwL, -hdL, hwL, -hdL + crL);
            shapeL.lineTo(hwL, hdL - crL);
            shapeL.quadraticCurveTo(hwL, hdL, hwL - crL, hdL);
            shapeL.lineTo(-hwL + crL, hdL);
            shapeL.quadraticCurveTo(-hwL, hdL, -hwL, hdL - crL);
            shapeL.lineTo(-hwL, -hdL + crL);
            shapeL.quadraticCurveTo(-hwL, -hdL, -hwL + crL, -hdL);
            const newGeo = new THREE.ExtrudeGeometry(shapeL, {
              depth: Math.max(0.08, targetHeight),
              bevelEnabled: true,
              bevelThickness: 0.03,
              bevelSize: 0.03,
              bevelSegments: 2,
              curveSegments: 4,
            });
            newGeo.rotateX(-Math.PI / 2);
            if (mesh.geometry) mesh.geometry.dispose();
            mesh.geometry = newGeo;
            mesh.userData.currentHeight = targetHeight;
          }
          if (mesh.material && mesh.material.color) {
            mesh.material.color.setHex(pickColourHex(delta));
            mesh.material.clearcoat = delta !== null && delta >= 0.2 ? 0.6 : 0.35;
            mesh.material.needsUpdate = true;
          }
          mesh.userData.region = r || null;
        });
      };

      sceneStateRef.current = {
        THREE,
        scene,
        camera,
        renderer,
        group,
        meshesByCode,
        applyRegions,
        cancel,
      };

      // Apply whatever the most recent regions map is — guards against the
      // mount-before-update race that otherwise leaves all towers at the
      // default base-height / missing-colour.
      applyRegions(latestRegionsRef.current);
    }

    init();
    return () => {
      disposed = true;
      sceneStateRef.current?.cancel();
      sceneStateRef.current = null;
    };
    // Mount-only. Region updates go through the second effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Data-update effect. Delegates to the applyRegions callback stashed on
  // the scene-state ref; that callback mutates existing mesh geometry and
  // material colour in place — no scene teardown, no flicker.
  // If the scene is not ready yet (async import still in flight), we skip;
  // the mount-effect will pick up latestRegionsRef.current once it's done.
  useEffect(() => {
    sceneStateRef.current?.applyRegions(regionsByCode);
  }, [regionsByCode]);

  // Side panel: top 4 risers, rendered outside the canvas for type quality.
  const topRisers = useMemo(
    () =>
      regions
        .slice()
        .filter((r) => typeof r.delta7d === 'number' && Number.isFinite(r.delta7d))
        .sort((a, b) => (b.delta7d ?? 0) - (a.delta7d ?? 0))
        .slice(0, 4),
    [regions],
  );

  return (
    <section className="peix-stage peix-sculpture peix-fade-in" data-stage="dark">
      <div className="peix-sculpture__grain" aria-hidden />
      <div className="peix-sculpture__vignette" aria-hidden />

      <div className="peix-sculpture__lede">
        <div className="peix-sculpture__kicker">
          <span className="peix-sculpture__mark">◆</span>
          <span>wellen-atlas</span>
          <span className="peix-sculpture__sep">·</span>
          <span>live</span>
        </div>
        <h2 className="peix-sculpture__headline">
          {headline.split('—').map((part, i) => (
            <span key={i}>
              {i === 0 ? part : <em>{part}</em>}
              {i === 0 && <span className="peix-sculpture__emdash">—</span>}
            </span>
          ))}
        </h2>
        <p className="peix-sculpture__dek">{dek}</p>

        {topRisers.length > 0 && (
          <ol className="peix-sculpture__roster">
            {topRisers.map((r, idx) => (
              <li key={r.code} className="peix-sculpture__roster-row">
                <span className="peix-sculpture__roster-idx">{String(idx + 1).padStart(2, '0')}</span>
                <span className="peix-sculpture__roster-name">{r.name}</span>
                <span className="peix-sculpture__roster-rule" aria-hidden />
                <span className="peix-sculpture__roster-delta">{fmtSignedPct(r.delta7d)}</span>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="peix-sculpture__canvas" ref={mountRef} />

      <figcaption className="peix-sculpture__caption">
        <span className="peix-sculpture__caption-label">Legende</span>
        <span className="peix-sculpture__caption-scale">
          <span className="peix-sculpture__caption-tick">fallend</span>
          <span className="peix-sculpture__caption-gradient" />
          <span className="peix-sculpture__caption-tick">steigend</span>
        </span>
        <span className="peix-sculpture__caption-meta">
          16 Bundesländer · Höhe ∝ Δ7d · keramische Darstellung
        </span>
      </figcaption>
    </section>
  );
};

export default DataSculpture;
