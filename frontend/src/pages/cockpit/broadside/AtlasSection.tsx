import React, { useEffect, useMemo, useRef } from 'react';
import type { CockpitSnapshot, RegionForecast, Bundesland } from '../types';
import { fmtSignedPct } from '../format';
import { CaptionStrip, MethodBadge } from '../exhibit/primitives';
import SectionHeader from './SectionHeader';

/**
 * § II — Wellen-Atlas.
 *
 * Full-bleed dark stage: 16 Bundesländer as towers on a warm-black
 * pedestal, height = expected 3-week rise. The 3D canvas is no longer
 * constrained by a drawer width — it's the full width of the broadside
 * with a tall viewport so the sculpture actually feels like one.
 *
 * Current commit: same orthographic camera as before (minor cleanup).
 * The perspective/motion upgrade lands in a dedicated follow-up commit.
 */

const ATLAS_LAYOUT: Record<Bundesland, [number, number]> = {
  SH: [3, 4],   MV: [4, 4],   HH: [3, 3.4], HB: [2, 3.2],
  NI: [2, 2.8], BE: [4.2, 2.8], BB: [4, 2.6], ST: [3.2, 2.4],
  NW: [1, 2.2], SN: [4, 1.8], TH: [3, 1.6], HE: [1.8, 1.4],
  RP: [1, 0.8], SL: [0.6, 0.2], BW: [1.8, 0], BY: [3.2, 0.2],
};

function lerp(a: number, b: number, t: number): number {
  return a * (1 - t) + b * t;
}
function colorForRiseRGB(rise: number | null): [number, number, number] {
  if (rise === null || !Number.isFinite(rise)) return [0.17, 0.15, 0.13];
  const t = Math.max(0, Math.min(1, (rise + 0.4) / 0.9));
  const stops: [number, number, number][] = [
    [0.29, 0.42, 0.38],
    [0.42, 0.43, 0.38],
    [0.72, 0.55, 0.38],
    [0.84, 0.54, 0.35],
    [0.72, 0.29, 0.18],
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
  highlightCode?: Bundesland | null;
}

const AtlasScene: React.FC<AtlasSceneProps> = ({ regions, highlightCode }) => {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!mountRef.current) return;
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
        console.warn('AtlasSection: three.js failed to load', err);
        if (mount) {
          mount.innerHTML =
            '<div style="padding:56px 36px;color:rgba(246,241,231,.6);font-style:italic;font-family:var(--ex-serif);text-align:center">Der 3D-Atlas konnte gerade nicht geladen werden.</div>';
        }
        return;
      }
      if (!mounted) return;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color('#14110d');
      scene.fog = new THREE.FogExp2(0x0e0a06, 0.038);

      // Perspective camera — dramatic angle, three-quarter view. Low
      // fov keeps the towers from warping at the edges but still gives
      // real depth. Camera sits further back + higher than the
      // orthographic setup to make tall towers feel tall.
      const camera = new THREE.PerspectiveCamera(32, w / h, 0.1, 140);
      camera.position.set(7.8, 8.4, 9.4);
      camera.lookAt(2.5, 0.4, 2);

      const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: false,
        powerPreference: 'high-performance',
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(w, h);
      if ('toneMapping' in renderer) {
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.15;
      }
      mount.appendChild(renderer.domElement);

      // --- Lighting: architectural-model drama -----------------------
      // Warm key from upper-left, cool fill from lower-right, cool rim.
      const key = new THREE.DirectionalLight(0xfde2b8, 1.4);
      key.position.set(6, 12, 4);
      scene.add(key);
      const fill = new THREE.DirectionalLight(0x7a8fa6, 0.5);
      fill.position.set(-6, 3, -4);
      scene.add(fill);
      const rim = new THREE.DirectionalLight(0xb8c4d8, 0.6);
      rim.position.set(-3, 5, -10);
      scene.add(rim);
      scene.add(new THREE.AmbientLight(0x2a241c, 0.38));

      // --- Floor & grid ---------------------------------------------
      const floorGeo = new THREE.PlaneGeometry(16, 16);
      const floorMat = new THREE.MeshStandardMaterial({
        color: 0x14100b,
        roughness: 1,
        metalness: 0,
      });
      const floor = new THREE.Mesh(floorGeo, floorMat);
      floor.rotation.x = -Math.PI / 2;
      floor.position.y = -0.01;
      scene.add(floor);

      const grid = new THREE.GridHelper(12, 12, 0x3a2e22, 0x221a12);
      grid.position.y = 0;
      scene.add(grid);

      // --- Towers (taller + more breathing scale) --------------------
      const byCode = new Map<Bundesland, RegionForecast>();
      regions.forEach((r) => byCode.set(r.code, r));
      const disposables: any[] = [];
      const towerMeshes: { code: Bundesland; mesh: any; baseY: number }[] = [];

      // Top-3 risers get spotlight treatment.
      const top3Codes = new Set<Bundesland>(
        regions
          .filter((r) => typeof r.delta7d === 'number')
          .sort((a, b) => (b.delta7d ?? -1) - (a.delta7d ?? -1))
          .slice(0, 3)
          .map((r) => r.code),
      );

      (Object.keys(ATLAS_LAYOUT) as Bundesland[]).forEach((code) => {
        const pos = ATLAS_LAYOUT[code];
        const region = byCode.get(code);
        const rise = region?.delta7d ?? null;
        const wave = region?.pRising ?? 0.4;
        // Taller scale factor: +0.4 offset, × 3.2 multiplier (was 2.2),
        // minimum 0.2 so baseline towers still register.
        const heightVal = Math.max(0.2, ((rise ?? 0) + 0.4) * 3.2);
        const side = 0.36 + wave * 0.12;
        const [r, g, b] = colorForRiseRGB(rise);
        const geo = new THREE.BoxGeometry(side, heightVal, side);
        const mat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(r, g, b),
          roughness: top3Codes.has(code) ? 0.40 : 0.60,
          metalness: top3Codes.has(code) ? 0.12 : 0.02,
          emissive: top3Codes.has(code)
            ? new THREE.Color(0x2a1410)
            : new THREE.Color(0x000000),
          emissiveIntensity: top3Codes.has(code) ? 0.4 : 0,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(pos[0] - 0.5, heightVal / 2, 4 - pos[1]);
        mesh.userData = { code, isTop3: top3Codes.has(code) };
        scene.add(mesh);
        towerMeshes.push({ code, mesh, baseY: heightVal / 2 });
        disposables.push(geo, mat);

        const baseGeo = new THREE.PlaneGeometry(side + 0.12, side + 0.12);
        const baseMat = new THREE.MeshBasicMaterial({
          color: top3Codes.has(code) ? 0x4a2a1a : 0x2a241c,
          transparent: true,
          opacity: top3Codes.has(code) ? 0.85 : 0.7,
        });
        const base = new THREE.Mesh(baseGeo, baseMat);
        base.rotation.x = -Math.PI / 2;
        base.position.set(pos[0] - 0.5, 0.003, 4 - pos[1]);
        scene.add(base);
        disposables.push(baseGeo, baseMat);
      });

      // --- Spotlight on Top-3 ---------------------------------------
      // One narrow warm cone per top-riser tower — ochre colour,
      // angled from above. Makes the top-3 literally glow without
      // turning the rest of the atlas into a disco.
      top3Codes.forEach((code) => {
        const pos = ATLAS_LAYOUT[code];
        if (!pos) return;
        const sp = new THREE.SpotLight(
          0xffb066,
          2.2,
          6.5,
          Math.PI / 8,
          0.45,
          1.2,
        );
        sp.position.set(pos[0] - 0.5 + 0.3, 6.5, 4 - pos[1] + 0.3);
        sp.target.position.set(pos[0] - 0.5, 0, 4 - pos[1]);
        scene.add(sp);
        scene.add(sp.target);
      });

      // --- Destination ring (the recommendation target) -------------
      if (highlightCode && ATLAS_LAYOUT[highlightCode]) {
        const hpos = ATLAS_LAYOUT[highlightCode];
        const ringGeo = new THREE.RingGeometry(0.46, 0.52, 64);
        const ringMat = new THREE.MeshBasicMaterial({
          color: 0xd68a5a,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.95,
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.rotation.x = -Math.PI / 2;
        ring.position.set(hpos[0] - 0.5, 0.006, 4 - hpos[1]);
        scene.add(ring);
        disposables.push(ringGeo, ringMat);
      }

      // --- Motion: drift + top-3 pulse -------------------------------
      // Camera drift: a slow Lissajous-ish figure (sin on x, cos on y)
      // so it never repeats identically. Stays gentle (±1° feel), but
      // the dual-axis drift makes the perspective feel alive.
      // Plus top-3 tower pulse: ±3 % height every 2.8 s, emissive pulse.
      const camBase = {
        x: camera.position.x,
        y: camera.position.y,
        z: camera.position.z,
      };
      const startedAt = performance.now();
      const tick = () => {
        if (!mounted) return;
        const t = (performance.now() - startedAt) / 1000;
        const driftX = Math.sin(t / 9) * 0.22;
        const driftY = Math.cos(t / 11) * 0.14;
        camera.position.x = camBase.x + driftX;
        camera.position.y = camBase.y + driftY;
        camera.lookAt(2.5, 0.4, 2);
        const pulse = 1 + Math.sin(t * (Math.PI * 2) / 2.8) * 0.03;
        towerMeshes.forEach(({ mesh, baseY }) => {
          if (mesh.userData?.isTop3) {
            mesh.scale.y = pulse;
            mesh.position.y = baseY * pulse;
          }
        });
        renderer.render(scene, camera);
        raf = requestAnimationFrame(tick);
      };
      tick();

      const onResize = () => {
        if (!mountRef.current) return;
        const ww = mount.clientWidth;
        const hh = mount.clientHeight;
        if (ww < 10 || hh < 10) return;
        camera.aspect = ww / hh;
        camera.updateProjectionMatrix();
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setSize(ww, hh, false);
      };
      window.addEventListener('resize', onResize);

      cleanup = () => {
        cancelAnimationFrame(raf);
        window.removeEventListener('resize', onResize);
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
  }, [regions, highlightCode]);

  return <div className="ex-atlas-stage__canvas" ref={mountRef} />;
};

// ---------- Root --------------------------------------------------------
interface Props {
  snapshot: CockpitSnapshot;
}

export const AtlasSection: React.FC<Props> = ({ snapshot }) => {
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

  const topRiserCount = sorted.filter((r) => (r.delta7d ?? 0) > 0.05).length;
  const badges: Array<{ label: string; tone: 'go' | 'watch' | 'neutral' | 'solid' | 'ochre' }> = [
    { label: `${snapshot.regions.length} BL`, tone: 'neutral' },
    { label: `${topRiserCount} steigend`, tone: topRiserCount > 0 ? 'go' : 'neutral' },
    { label: 'Perspektive', tone: 'ochre' },
  ];

  return (
    <>
      <SectionHeader
        numeral="§ II"
        kicker="3D-Datenskulptur · Höhe = erwarteter Anstieg"
        title={
          <>
            Der <em>Wellen-Atlas</em>
          </>
        }
        stamp={snapshot.isoWeek}
        badges={badges}
      />

      <div
        className="ex-section-body ex-section-body--bleed"
        style={{ marginTop: -112 }}
      >
        <div className="ex-atlas-stage">
          <div className="ex-atlas-stage__grain" aria-hidden />
          <AtlasScene
            regions={snapshot.regions}
            highlightCode={highlightCode}
          />
          <div className="ex-atlas-stage__overlay">
            <span>Wellen-Atlas · Perspektiv-Projektion</span>
            <span style={{ alignSelf: 'flex-end' }}>
              Höhe = Anstieg · Farbe = Richtung
            </span>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 40 }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 40,
            marginBottom: 40,
          }}
        >
          <div>
            <div
              className="ex-mono"
              style={{ color: 'var(--ex-ink-45)', marginBottom: 8 }}
            >
              Lesart
            </div>
            <p
              style={{
                fontFamily: 'var(--ex-serif)',
                fontStyle: 'italic',
                fontSize: 16,
                lineHeight: 1.5,
                margin: 0,
                color: 'var(--ex-ink-60)',
              }}
            >
              Turmhöhe ist nicht die aktuelle Welle — sondern der
              erwartete Anstieg der nächsten Wochen. Farbe ist
              Richtung, nicht Stärke.
            </p>
          </div>
          <div>
            <div
              className="ex-mono"
              style={{ color: 'var(--ex-ink-45)', marginBottom: 8 }}
            >
              Skala
            </div>
            <CaptionStrip
              label="fällt"
              pinAt={0.5}
              value="steigt"
              onPaper={true}
            />
          </div>
          <div>
            <div
              className="ex-mono"
              style={{ color: 'var(--ex-ink-45)', marginBottom: 8 }}
            >
              Methode
            </div>
            <MethodBadge calibrated={calibrated} onPaper={true} />
            <div
              style={{
                fontSize: 13,
                marginTop: 8,
                fontFamily: 'var(--ex-serif)',
                fontStyle: 'italic',
                color: 'var(--ex-ink-60)',
              }}
            >
              Die 16 Türme sind unabhängig kalibriert, nicht normiert.
            </div>
          </div>
        </div>

        <div className="ex-atlas-roster">
          {sorted.map((l, i) => {
            const rise = l.delta7d ?? 0;
            const dirClass = rise > 0.05 ? 'up' : rise < -0.05 ? 'down' : 'flat';
            return (
              <div className="ex-atlas-roster-row" key={l.code}>
                <span className="ex-idx">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="ex-name">
                  {l.name}
                  <span className="ex-code">{l.code}</span>
                </span>
                <span className={`ex-val ${dirClass}`}>
                  {fmtSignedPct(rise)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
};

export default AtlasSection;
