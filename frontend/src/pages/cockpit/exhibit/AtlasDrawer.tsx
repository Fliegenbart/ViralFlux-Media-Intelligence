import React, { useEffect, useMemo, useRef } from 'react';
import type { CockpitSnapshot, RegionForecast, Bundesland } from '../types';
import { fmtSignedPct } from '../format';
import { Drawer } from './Drawer';
import { CaptionStrip, MethodBadge } from './primitives';

/**
 * AtlasDrawer — Drawer II. Orthographic data-sculpture of 16 Bundesländer
 * as towers + per-tower roster underneath.
 *
 * Why orthographic (per Design-Notizen):
 *   "Gewählt gegen ISO weil Perspektive dramatisiert — die Türme sollen
 *    Daten sein, keine Bühne. Orthographie ist der Vitrinen-Look und
 *    behält die Lesbarkeit der relativen Höhen."
 *
 * Motion: ±0.016 breath only, plus a scroll-coupled camera tilt that's
 * bound to the drawer-body scrollTop. Nothing rotates autonomously.
 */

// Approximate 4×5 grid layout matching the geography of Germany.
const ATLAS_LAYOUT: Record<Bundesland, [number, number]> = {
  SH: [3, 4],   MV: [4, 4],   HH: [3, 3.4], HB: [2, 3.2],
  NI: [2, 2.8], BE: [4.2, 2.8], BB: [4, 2.6], ST: [3.2, 2.4],
  NW: [1, 2.2], SN: [4, 1.8], TH: [3, 1.6], HE: [1.8, 1.4],
  RP: [1, 0.8], SL: [0.6, 0.2], BW: [1.8, 0], BY: [3.2, 0.2],
};

// Build a three-stop warm/cool palette from fall (slate) → neutral → ochre → fired.
function lerp(a: number, b: number, t: number): number {
  return a * (1 - t) + b * t;
}
function colorForRiseRGB(rise: number | null): [number, number, number] {
  if (rise === null || !Number.isFinite(rise)) return [0.17, 0.15, 0.13]; // missing
  const t = Math.max(0, Math.min(1, (rise + 0.4) / 0.9));
  const stops: [number, number, number][] = [
    [0.29, 0.42, 0.38], // slate-green
    [0.42, 0.43, 0.38], // neutral warm
    [0.72, 0.55, 0.38], // warm ochre
    [0.84, 0.54, 0.35], // ochre
    [0.72, 0.29, 0.18], // fired
  ];
  const p = t * (stops.length - 1);
  const i = Math.floor(p);
  const f = p - i;
  const a = stops[i];
  const b = stops[Math.min(i + 1, stops.length - 1)];
  return [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)];
}

interface AtlasSceneProps {
  regions: RegionForecast[];
  /** Code of the state to highlight with an ochre ring (usually the shift destination). */
  highlightCode?: Bundesland | null;
  active: boolean;
}

const AtlasScene: React.FC<AtlasSceneProps> = ({
  regions,
  highlightCode,
  active,
}) => {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!active || !mountRef.current) return;
    const mount = mountRef.current;
    let mounted = true;
    let raf = 0;
    let cleanup = () => {};

    const start = async () => {
      if (!mounted || !mountRef.current) return;
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      if (w < 10 || h < 10) {
        setTimeout(start, 120);
        return;
      }

      let THREE: any;
      try {
        THREE = await import('three');
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('AtlasDrawer: three.js failed to load', err);
        if (mount) {
          mount.innerHTML =
            '<div style="padding:56px 36px;color:rgba(246,241,231,.6);font-style:italic;font-family:Fraunces,Georgia,serif;text-align:center">Der 3D-Atlas konnte gerade nicht geladen werden.</div>';
        }
        return;
      }
      if (!mounted) return;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color('#14110d');

      // Orthographic camera — museum vitrine feel, no perspective drama.
      const viewSize = 4.2;
      const aspect = w / h;
      const camera = new THREE.OrthographicCamera(
        -viewSize * aspect,
        viewSize * aspect,
        viewSize,
        -viewSize,
        0.1,
        100,
      );
      camera.position.set(5.5, 6.5, 7);
      camera.lookAt(2.5, 0, 2);

      const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: false,
        powerPreference: 'high-performance',
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(w, h);
      mount.appendChild(renderer.domElement);

      // Lighting — warm key + cool fill, gallery spots.
      const key = new THREE.DirectionalLight(0xffeccc, 1.1);
      key.position.set(4, 10, 3);
      scene.add(key);
      const fill = new THREE.DirectionalLight(0x8899aa, 0.35);
      fill.position.set(-5, 4, -2);
      scene.add(fill);
      scene.add(new THREE.AmbientLight(0x2a241c, 0.6));

      // Floor — barely-there plane to ground the towers.
      const floorGeo = new THREE.PlaneGeometry(14, 14);
      const floorMat = new THREE.MeshStandardMaterial({
        color: 0x1a1713,
        roughness: 1,
        metalness: 0,
      });
      const floor = new THREE.Mesh(floorGeo, floorMat);
      floor.rotation.x = -Math.PI / 2;
      floor.position.y = -0.01;
      scene.add(floor);

      // Grid hairlines — very subtle.
      const grid = new THREE.GridHelper(10, 10, 0x2a241c, 0x201a15);
      grid.position.y = 0;
      scene.add(grid);

      // Towers — one per Bundesland with geography in the 4×5 grid.
      const byCode = new Map<Bundesland, RegionForecast>();
      regions.forEach((r) => byCode.set(r.code, r));

      const disposables: any[] = [];
      (Object.keys(ATLAS_LAYOUT) as Bundesland[]).forEach((code) => {
        const pos = ATLAS_LAYOUT[code];
        const region = byCode.get(code);
        const rise = region?.delta7d ?? null;
        const wave = region?.pRising ?? 0.4;
        const heightVal = Math.max(0.08, ((rise ?? 0) + 0.4) * 2.2);
        const side = 0.32 + wave * 0.1;
        const [r, g, b] = colorForRiseRGB(rise);

        const geo = new THREE.BoxGeometry(side, heightVal, side);
        const mat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(r, g, b),
          roughness: 0.58,
          metalness: 0.02,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(pos[0] - 0.5, heightVal / 2, 4 - pos[1]);
        scene.add(mesh);
        disposables.push(geo, mat);

        // Base plate per tower — hairline ground footprint.
        const baseGeo = new THREE.PlaneGeometry(side + 0.1, side + 0.1);
        const baseMat = new THREE.MeshBasicMaterial({
          color: 0x2a241c,
          transparent: true,
          opacity: 0.7,
        });
        const base = new THREE.Mesh(baseGeo, baseMat);
        base.rotation.x = -Math.PI / 2;
        base.position.set(pos[0] - 0.5, 0.002, 4 - pos[1]);
        scene.add(base);
        disposables.push(baseGeo, baseMat);
      });

      // Highlight ring on the shift destination.
      if (highlightCode && ATLAS_LAYOUT[highlightCode]) {
        const hpos = ATLAS_LAYOUT[highlightCode];
        const ringGeo = new THREE.RingGeometry(0.4, 0.42, 64);
        const ringMat = new THREE.MeshBasicMaterial({
          color: 0xd68a5a,
          side: THREE.DoubleSide,
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.rotation.x = -Math.PI / 2;
        ring.position.set(hpos[0] - 0.5, 0.005, 4 - hpos[1]);
        scene.add(ring);
        disposables.push(ringGeo, ringMat);
      }

      // Scroll-parallax — bind to drawer body scrollTop.
      let scrollY = 0;
      const drawerBody = mount.closest('.ex-drawer-body') as HTMLElement | null;
      const onScroll = () => {
        scrollY = drawerBody ? drawerBody.scrollTop : 0;
      };
      drawerBody &&
        drawerBody.addEventListener('scroll', onScroll, { passive: true });

      const tick = () => {
        if (!mounted) return;
        const t = Math.max(0, Math.min(1.2, scrollY / 400));
        // Gentle sin² breath (±0.016 unit, ~0.9°)
        const breath = Math.sin(performance.now() / 4000) ** 2 * 0.016;
        camera.position.x = 5.5 + breath;
        camera.position.y = 6.5 + t * 1.2;
        camera.position.z = 7 - t * 0.8;
        camera.lookAt(2.5, 0, 2);
        renderer.render(scene, camera);
        raf = requestAnimationFrame(tick);
      };
      tick();

      const onResize = () => {
        if (!mountRef.current) return;
        const ww = mount.clientWidth;
        const hh = mount.clientHeight;
        if (ww < 10 || hh < 10) return;
        const ar = ww / hh;
        camera.left = -viewSize * ar;
        camera.right = viewSize * ar;
        camera.top = viewSize;
        camera.bottom = -viewSize;
        camera.updateProjectionMatrix();
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setSize(ww, hh, false);
      };
      window.addEventListener('resize', onResize);

      cleanup = () => {
        cancelAnimationFrame(raf);
        window.removeEventListener('resize', onResize);
        drawerBody && drawerBody.removeEventListener('scroll', onScroll);
        disposables.forEach((d) => d.dispose?.());
        floorGeo.dispose();
        floorMat.dispose();
        renderer.dispose();
        if (mount) mount.innerHTML = '';
      };
    };

    start();
    return () => {
      mounted = false;
      cleanup();
    };
  }, [active, regions, highlightCode]);

  return (
    <div className="ex-atlas-canvas-wrap" ref={mountRef}>
      <div className="ex-atlas-overlay">
        <div className="ex-tl">Wellen-Atlas · Orthogr. Projektion</div>
        <div className="ex-br">Höhe = Anstieg · Farbe = Richtung</div>
      </div>
    </div>
  );
};

// --------------------------------------------------------------
// AtlasDrawer root
// --------------------------------------------------------------
interface AtlasDrawerProps {
  open: boolean;
  onClose: () => void;
  snapshot: CockpitSnapshot;
}

export const AtlasDrawer: React.FC<AtlasDrawerProps> = ({
  open,
  onClose,
  snapshot,
}) => {
  const calibrated = snapshot.modelStatus?.calibrationMode === 'calibrated';
  const highlightCode: Bundesland | null = useMemo(() => {
    const toName = snapshot.primaryRecommendation?.toName;
    if (!toName) return null;
    const match = snapshot.regions.find((r) => r.name === toName);
    return (match?.code as Bundesland) ?? null;
  }, [snapshot]);
  const sorted = useMemo(
    () =>
      [...snapshot.regions]
        .filter((r) => typeof r.delta7d === 'number' && Number.isFinite(r.delta7d))
        .sort((a, b) => (b.delta7d ?? -Infinity) - (a.delta7d ?? -Infinity)),
    [snapshot.regions],
  );

  return (
    <Drawer
      open={open}
      onClose={onClose}
      stageVar={true}
      kicker={
        <>
          <span>Drawer II</span>
          <span>·</span>
          <span>Wellen-Atlas</span>
          <span>·</span>
          <span>{snapshot.isoWeek}</span>
        </>
      }
      title={
        <>
          Das Land als <em>Datenskulptur</em>.
        </>
      }
      footLeft="Orthographie · Höhe = erwarteter Anstieg"
      footRight="Atmet. Dreht nicht. 16 Türme."
    >
      {open && (
        <AtlasScene
          regions={snapshot.regions}
          highlightCode={highlightCode}
          active={open}
        />
      )}
      <div
        style={{
          padding: '40px 56px 8px',
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 32,
        }}
      >
        <div>
          <div
            className="ex-mono"
            style={{
              color: 'rgba(246,241,231,.45)',
              marginBottom: 8,
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 11,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
            }}
          >
            Lesart
          </div>
          <p
            style={{
              fontFamily: 'Fraunces, Georgia, serif',
              fontStyle: 'italic',
              fontSize: 16,
              lineHeight: 1.5,
              margin: 0,
              color: 'rgba(246,241,231,.60)',
              fontVariationSettings: '"opsz" 36',
            }}
          >
            Turmhöhe ist nicht die aktuelle Welle — sondern der erwartete
            Anstieg der nächsten Wochen. Farbe ist Richtung, nicht Stärke.
          </p>
        </div>
        <div>
          <div
            className="ex-mono"
            style={{
              color: 'rgba(246,241,231,.45)',
              marginBottom: 8,
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 11,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
            }}
          >
            Skala
          </div>
          <CaptionStrip label="fällt" pinAt={0.5} value="steigt" />
        </div>
        <div>
          <div
            className="ex-mono"
            style={{
              color: 'rgba(246,241,231,.45)',
              marginBottom: 8,
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 11,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
            }}
          >
            Methode
          </div>
          <MethodBadge calibrated={calibrated} />
          <div
            style={{
              color: 'rgba(246,241,231,.60)',
              fontSize: 13,
              marginTop: 8,
              fontStyle: 'italic',
              fontFamily: 'Fraunces, Georgia, serif',
            }}
          >
            Die 16 Türme sind unabhängig kalibriert, nicht normiert.
          </div>
        </div>
      </div>
      <hr
        style={{
          margin: '32px 56px 0',
          height: 1,
          background: 'rgba(246,241,231,.16)',
          border: 0,
        }}
      />
      <div style={{ padding: '8px 0' }}>
        {sorted.map((l, i) => {
          const rise = l.delta7d ?? 0;
          const dirClass = rise > 0.05 ? 'up' : rise < -0.05 ? 'down' : 'flat';
          return (
            <div className="ex-atlas-tower-caption" key={l.code}>
              <span className="ex-idx">
                {String(i + 1).padStart(2, '0')}
              </span>
              <div>
                <span className="ex-name">{l.name}</span>
                <span
                  style={{
                    marginLeft: 12,
                    color: 'rgba(246,241,231,.45)',
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: 11,
                    letterSpacing: '.08em',
                  }}
                >
                  {l.code}
                </span>
                {l.decisionLabel && (
                  <div
                    style={{
                      fontSize: 12,
                      color: 'rgba(246,241,231,.45)',
                      fontFamily: 'Fraunces, Georgia, serif',
                      fontStyle: 'italic',
                      marginTop: 2,
                    }}
                  >
                    Entscheidung · {l.decisionLabel}
                  </div>
                )}
              </div>
              <span className={`ex-v ${dirClass}`}>
                {fmtSignedPct(rise)}
              </span>
            </div>
          );
        })}
      </div>
    </Drawer>
  );
};

export default AtlasDrawer;
