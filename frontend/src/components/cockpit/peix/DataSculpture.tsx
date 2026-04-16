import React, { useEffect, useRef } from 'react';
import type { RegionForecast, Bundesland } from '../../../pages/cockpit/types';
import { fmtSignedPct } from '../../../pages/cockpit/format';

/**
 * The signature 3D map. Bundesländer are rendered as extruded
 * tiles whose height encodes delta7d (rising = tall warm, falling = sunk cool).
 *
 * Uses three.js (dynamically imported via a CDN-fallback for demo mode).
 * In the full app it will import from 'three' — add to package.json:
 *   "three": "^0.165.0"   "@types/three": "^0.165.0"
 */

// Schematic grid matching GermanyChoropleth.tsx for visual continuity
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

export const DataSculpture: React.FC<Props> = ({ regions, headline, dek }) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const stateRef = useRef<any>(null);

  useEffect(() => {
    let disposed = false;

    async function init() {
      const el = mountRef.current;
      if (!el) return;
      // Dynamic import keeps bundler happy when `three` is not yet installed.
      // When running in the app with `three` in deps, this resolves immediately.
      const THREE = await import(/* webpackIgnore: true */ 'three').catch(() => null);
      if (!THREE) {
        el.innerHTML = `<div style="padding:24px;color:#f5f3ee;font-family:'Inter Tight',sans-serif;font-size:13px;opacity:0.7">
          3D-Stage benötigt <code>three</code> (package.json). Fallback: SVG-Karte siehe Tab 1.
        </div>`;
        return;
      }
      if (disposed) return;

      const width = el.clientWidth;
      const height = el.clientHeight;
      const scene = new THREE.Scene();
      scene.background = null;
      scene.fog = new THREE.Fog(0x070911, 18, 42);

      const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 100);
      camera.position.set(7.5, 9, 13.5);
      camera.lookAt(0, 0, 0);

      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(width, height);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      el.appendChild(renderer.domElement);

      // Lights — two warm, one cool, strong rim to sculpt edges
      const key = new THREE.DirectionalLight(0xffe8cc, 1.6);
      key.position.set(6, 10, 5); scene.add(key);
      const fill = new THREE.DirectionalLight(0x7ab6ff, 0.6);
      fill.position.set(-6, 4, -4); scene.add(fill);
      const amb = new THREE.AmbientLight(0x2a3142, 0.6); scene.add(amb);

      // Ground
      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(26, 26),
        new THREE.MeshStandardMaterial({ color: 0x0d1220, roughness: 0.95, metalness: 0.1 }),
      );
      ground.rotation.x = -Math.PI / 2;
      ground.position.y = -0.02;
      scene.add(ground);

      // Helper: map delta7d to height and colour
      const colourFor = (d: number) => {
        if (d >= 0.25) return new THREE.Color(0xd94a2c);
        if (d >= 0.15) return new THREE.Color(0xef7e44);
        if (d >= 0.05) return new THREE.Color(0xf9b588);
        if (d >= -0.05) return new THREE.Color(0x6b7180);
        if (d >= -0.12) return new THREE.Color(0x2f998b);
        return new THREE.Color(0x166a61);
      };

      const group = new THREE.Group();
      scene.add(group);

      const regionByCode = new Map<Bundesland, RegionForecast>();
      regions.forEach((r) => regionByCode.set(r.code, r));

      const cell = 1.3;
      const gap = 0.06;

      TILES.forEach((t) => {
        const r = regionByCode.get(t.code);
        if (!r) return;
        const w = (t.w || 1) * cell + ((t.w || 1) - 1) * gap;
        const h = (t.h || 1) * cell + ((t.h || 1) - 1) * gap;
        const height = 0.4 + Math.max(0, r.delta7d) * 12 + Math.min(0, r.delta7d) * 1.2;
        const z = t.y * (cell + gap) - 4;
        const x = t.x * (cell + gap) - 3.6;

        const geo = new THREE.BoxGeometry(w, Math.max(0.15, height), h);
        const mat = new THREE.MeshStandardMaterial({
          color: colourFor(r.delta7d),
          roughness: 0.42,
          metalness: 0.08,
          transparent: true,
          opacity: 0.94,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.set(x, Math.max(0.075, height / 2), z);
        mesh.userData = r;
        group.add(mesh);

        // Label sprite (Bundesland code)
        const canvas = document.createElement('canvas');
        canvas.width = 128; canvas.height = 64;
        const ctx = canvas.getContext('2d');
        if (ctx) {
          ctx.fillStyle = 'rgba(245,243,238,0.92)';
          ctx.font = 'bold 38px "Inter Tight", sans-serif';
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillText(t.code, 64, 32);
        }
        const tex = new THREE.CanvasTexture(canvas);
        tex.colorSpace = THREE.SRGBColorSpace;
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: 0.85 }));
        sprite.position.set(x, Math.max(0.075, height / 2) + Math.max(0.15, height / 2) + 0.35, z);
        sprite.scale.set(0.9, 0.45, 1);
        group.add(sprite);
      });

      // Subtle scene tilt animation
      let angle = 0;
      let target = 0;
      let raf = 0;
      const animate = () => {
        angle += 0.0018;
        target = Math.sin(angle) * 0.25;
        group.rotation.y = target;
        renderer.render(scene, camera);
        raf = requestAnimationFrame(animate);
      };
      animate();

      const resize = () => {
        const w = el.clientWidth;
        const h = el.clientHeight;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      };
      const ro = new ResizeObserver(resize);
      ro.observe(el);

      stateRef.current = { scene, renderer, group, ro, cancel: () => {
        cancelAnimationFrame(raf);
        ro.disconnect();
        renderer.dispose();
        el.removeChild(renderer.domElement);
      } };
    }

    init();
    return () => {
      disposed = true;
      if (stateRef.current?.cancel) stateRef.current.cancel();
    };
  }, [regions]);

  return (
    <section className="peix-stage peix-fade-in" data-stage="dark">
      <div className="peix-stage-lede">
        <div className="peix-kicker">wellen-atlas · live</div>
        <h2>
          {headline.split('—').map((part, i) => (
            <span key={i}>
              {i === 0 ? part : <em>{part}</em>}
              {i === 0 && '—'}
            </span>
          ))}
        </h2>
        <p className="dek">{dek}</p>

        <div style={{ display: 'grid', gap: 10, marginTop: 8 }}>
          {regions
            .slice()
            .sort((a, b) => b.delta7d - a.delta7d)
            .slice(0, 4)
            .map((r) => (
              <div key={r.code} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                padding: '10px 0', borderTop: '1px solid rgba(255,255,255,0.08)',
                fontFamily: 'var(--peix-font-sans)', fontSize: 14,
              }}>
                <span style={{ color: '#f5f3ee' }}>{r.name}</span>
                <span className="peix-num" style={{ color: '#ffb897', fontWeight: 500 }}>{fmtSignedPct(r.delta7d)}</span>
              </div>
            ))}
        </div>
      </div>

      <div className="peix-stage-canvas" ref={mountRef} />

      <div className="peix-stage-legend">
        <span>niedrig · fallend</span>
        <span className="bar" />
        <span>hoch · steigend</span>
      </div>
    </section>
  );
};

export default DataSculpture;
