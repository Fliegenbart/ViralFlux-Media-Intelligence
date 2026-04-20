import React, { useEffect, useMemo, useRef } from 'react';
import type { CockpitSnapshot, RegionForecast, Bundesland } from '../types';
import { fmtSignedPct } from '../format';
import SectionHeader from './SectionHeader';
import type { GateTone } from './SectionHeader';

/**
 * § II — Wellen-Atlas (3D).
 *
 * Instrumentation-Redesign 2026-04-18, cooler-pass 2026-04-18 evening.
 *
 * Vier Hero-Moves in dieser Version:
 *   1. Hex-Prism-Türme statt Box-Würfel — sechseckige Messzylinder.
 *   2. Top-3-Label-Sprites im 3D-Raum (BL-Name + Delta), Billboard.
 *   3. Transfer-Beam — Terracotta-Tube im Bogen vom From- zum To-Turm
 *      der primaryRecommendation, mit pulsierender Glow.
 *   4. Bessere Lighting: warm-key + cool-rim, Ground-Glow unter Top-3.
 *
 * HUD-Overlay (Corner-Brackets + Readouts + Riser-Ticker + Legende)
 * wie bisher.
 */

interface Props {
  snapshot: CockpitSnapshot;
}

// Schematisches Deutschland-Raster (x, z)  — -4..+4 Einheiten.
const LAENDER_COORDS: Record<Bundesland, { x: number; z: number; name: string }> = {
  SH: { x: -0.3, z: -3.6, name: 'Schleswig-Holstein' },
  HH: { x: -0.2, z: -2.9, name: 'Hamburg' },
  NI: { x: -1.1, z: -2.3, name: 'Niedersachsen' },
  HB: { x: -1.5, z: -2.7, name: 'Bremen' },
  MV: { x:  1.4, z: -3.2, name: 'Mecklenburg-Vorpommern' },
  BE: { x:  1.8, z: -1.5, name: 'Berlin' },
  BB: { x:  1.9, z: -2.1, name: 'Brandenburg' },
  ST: { x:  0.6, z: -1.5, name: 'Sachsen-Anhalt' },
  NW: { x: -2.4, z: -0.9, name: 'Nordrhein-Westfalen' },
  HE: { x: -1.3, z:  0.2, name: 'Hessen' },
  TH: { x:  0.3, z:  0.3, name: 'Thüringen' },
  SN: { x:  1.8, z:  0.2, name: 'Sachsen' },
  RP: { x: -2.2, z:  1.1, name: 'Rheinland-Pfalz' },
  SL: { x: -2.8, z:  1.8, name: 'Saarland' },
  BW: { x: -1.4, z:  2.3, name: 'Baden-Württemberg' },
  BY: { x:  0.8, z:  2.4, name: 'Bayern' },
};

interface AtlasSceneProps {
  regions: RegionForecast[];
  topRisers: RegionForecast[];                // Top-3, geordnet
  topRiserCodes: Set<Bundesland>;
  shiftFromCode: Bundesland | null;
  shiftToCode: Bundesland | null;
}

// ---------------------------------------------------------------
// Label-Texture — canvas-rendered Billboard für einen Top-Riser.
// Name groß, Delta in Terracotta darunter. Weißer Haarlinien-Rahmen.
// ---------------------------------------------------------------
function makeLabelTexture(
  THREE: any,
  name: string,
  delta: string,
): any {
  const DPR = Math.min(2, window.devicePixelRatio || 1);
  const W = 512;
  const H = 172;
  const canvas = document.createElement('canvas');
  canvas.width = W * DPR;
  canvas.height = H * DPR;
  const ctx = canvas.getContext('2d')!;
  ctx.scale(DPR, DPR);
  ctx.clearRect(0, 0, W, H);

  // Haarlinien-Rahmen mit Corner-Brackets (Instrument-Sprache)
  ctx.strokeStyle = 'rgba(244, 241, 234, 0.55)';
  ctx.lineWidth = 1;
  const bracketLen = 18;
  const pad = 2;
  // TL
  ctx.beginPath();
  ctx.moveTo(pad, pad + bracketLen); ctx.lineTo(pad, pad); ctx.lineTo(pad + bracketLen, pad);
  // TR
  ctx.moveTo(W - pad - bracketLen, pad); ctx.lineTo(W - pad, pad); ctx.lineTo(W - pad, pad + bracketLen);
  // BL
  ctx.moveTo(pad, H - pad - bracketLen); ctx.lineTo(pad, H - pad); ctx.lineTo(pad + bracketLen, H - pad);
  // BR
  ctx.moveTo(W - pad - bracketLen, H - pad); ctx.lineTo(W - pad, H - pad); ctx.lineTo(W - pad, H - pad - bracketLen);
  ctx.stroke();

  // BL-Name (Supreme fallback an system sans)
  ctx.fillStyle = '#F4F1EA';
  ctx.font = '600 38px "Supreme", "General Sans", -apple-system, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(name, W / 2, 62);

  // Delta — Terracotta, Mono, größer
  ctx.fillStyle = '#C2542A';
  ctx.font = '600 56px "JetBrains Mono", monospace';
  ctx.fillText(delta, W / 2, 124);

  const tex = new THREE.CanvasTexture(canvas);
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.anisotropy = 4;
  return tex;
}

const AtlasScene: React.FC<AtlasSceneProps> = ({
  regions,
  topRisers,
  topRiserCodes,
  shiftFromCode,
  shiftToCode,
}) => {
  const mountRef = useRef<HTMLDivElement | null>(null);

  // Stabile Dep-Signaturen: Scene soll nicht bei jedem Re-render des
  // Parents neu initialisieren.
  const regionsKey = useMemo(
    () =>
      regions
        .map((r) => `${r.code}:${r.delta7d ?? 'x'}`)
        .sort()
        .join('|'),
    [regions],
  );
  const topRiserKey = useMemo(
    () => Array.from(topRiserCodes).sort().join(','),
    [topRiserCodes],
  );
  const topRisersKey = useMemo(
    () =>
      topRisers
        .map((r) => `${r.code}:${r.delta7d ?? 'x'}:${r.name}`)
        .join('|'),
    [topRisers],
  );
  const beamKey = `${shiftFromCode ?? '-'}→${shiftToCode ?? '-'}`;

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
            '<div style="padding:56px 36px;color:rgba(244,241,234,0.6);font-style:italic;font-family:\'Supreme\',sans-serif;text-align:center">Der 3D-Atlas konnte gerade nicht geladen werden.</div>';
        }
        return;
      }
      if (!mounted) return;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color('#0A0B0E');
      scene.fog = new THREE.Fog('#0A0B0E', 8, 26);

      const camera = new THREE.PerspectiveCamera(30, w / h, 0.1, 100);
      camera.position.set(5.5, 7.0, 9.0);
      camera.lookAt(0, 0.6, 0);

      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(w, h, false);
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      if ('toneMapping' in renderer) {
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.18;
      }
      mount.appendChild(renderer.domElement);

      // ----- Floor ---------------------------------------------------
      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(24, 24),
        new THREE.MeshStandardMaterial({
          color: '#0F1216',
          roughness: 0.96,
          metalness: 0.02,
        }),
      );
      ground.rotation.x = -Math.PI / 2;
      ground.position.y = -0.01;
      ground.receiveShadow = true;
      scene.add(ground);

      // Haarlinien-Grid, mit zusätzlicher Terracotta-Note alle 4 Ticks.
      const grid = new THREE.GridHelper(24, 48, '#2A2F38', '#1A1E24');
      grid.material.opacity = 0.38;
      grid.material.transparent = true;
      scene.add(grid);

      // ----- Lighting ------------------------------------------------
      scene.add(new THREE.AmbientLight('#1A1F28', 0.55));

      // Warm Key from upper-right (morning-sun angle).
      const keyLight = new THREE.DirectionalLight('#F4E4C8', 1.05);
      keyLight.position.set(7, 11, 5);
      keyLight.castShadow = true;
      keyLight.shadow.mapSize.width = 2048;
      keyLight.shadow.mapSize.height = 2048;
      keyLight.shadow.camera.left = -9;
      keyLight.shadow.camera.right = 9;
      keyLight.shadow.camera.top = 9;
      keyLight.shadow.camera.bottom = -9;
      keyLight.shadow.bias = -0.0002;
      scene.add(keyLight);

      // Cool Rim from back-left — paints the tower silhouettes.
      const rimLight = new THREE.DirectionalLight('#6A7E9A', 0.55);
      rimLight.position.set(-6, 6, -5);
      scene.add(rimLight);

      // Low fill from front
      const fillLight = new THREE.DirectionalLight('#3A4555', 0.25);
      fillLight.position.set(0, 3, 8);
      scene.add(fillLight);

      // ----- Spotlights on Top-3 Riser ------------------------------
      const spotlights: any[] = [];
      topRiserCodes.forEach((code) => {
        const coord = LAENDER_COORDS[code];
        if (!coord) return;
        const spot = new THREE.SpotLight(
          '#D8632F',
          2.8,
          9,
          Math.PI / 7.5,
          0.38,
          1.3,
        );
        spot.position.set(coord.x, 6.0, coord.z);
        spot.target.position.set(coord.x, 0, coord.z);
        scene.add(spot);
        scene.add(spot.target);
        spotlights.push(spot);
      });

      // ----- Towers --------------------------------------------------
      const byCode = new Map<Bundesland, RegionForecast>();
      regions.forEach((r) => byCode.set(r.code, r));
      const disposables: any[] = [];
      const pulseRings: any[] = [];

      const signalColor = new THREE.Color('#C2542A');
      const slateColor = new THREE.Color('#4A5261');
      const neutralColor = new THREE.Color('#6A7380');

      const towerTipY: Partial<Record<Bundesland, number>> = {};
      const towerBaseXZ: Partial<Record<Bundesland, { x: number; z: number }>> = {};

      (Object.keys(LAENDER_COORDS) as Bundesland[]).forEach((code) => {
        const coord = LAENDER_COORDS[code];
        const region = byCode.get(code);
        const d = region?.delta7d ?? 0;

        const magnitude = Math.abs(d);
        const isRiser = d > 0.02;
        const isFaller = d < -0.02;
        const height = isRiser
          ? 0.65 + magnitude * 5.8
          : 0.22 + magnitude * 0.9;
        const radius = 0.28;

        let color;
        if (isRiser) color = signalColor;
        else if (isFaller) color = slateColor;
        else color = neutralColor;

        const group = new THREE.Group();
        group.position.set(coord.x, 0, coord.z);
        towerBaseXZ[code] = { x: coord.x, z: coord.z };
        towerTipY[code] = height;

        // 6-sided hex prism — reads mechanical/lab, not SaaS.
        const geo = new THREE.CylinderGeometry(radius, radius, height, 6, 1, false);
        const mat = new THREE.MeshStandardMaterial({
          color,
          roughness: isRiser ? 0.32 : 0.58,
          metalness: isRiser ? 0.22 : 0.06,
          emissive: isRiser ? signalColor : new THREE.Color('#000'),
          emissiveIntensity: isRiser ? 0.22 : 0,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.y = height / 2;
        // Slight random rotation for variance
        mesh.rotation.y = (code.charCodeAt(0) % 7) * 0.12;
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        group.add(mesh);
        disposables.push(geo, mat);

        // Hair-line edges — hex outline glows on risers.
        const edges = new THREE.EdgesGeometry(geo);
        const edgesMat = new THREE.LineBasicMaterial({
          color: isRiser ? '#F4F1EA' : '#8A92A0',
          transparent: true,
          opacity: isRiser ? 0.92 : 0.30,
        });
        const line = new THREE.LineSegments(edges, edgesMat);
        line.position.y = height / 2;
        line.rotation.y = mesh.rotation.y;
        group.add(line);
        disposables.push(edges, edgesMat);

        // Top cap — a flat hex disk at the tower tip. Top-3 get it glowing.
        const capGeo = new THREE.CylinderGeometry(radius * 0.98, radius * 0.98, 0.03, 6);
        const capMat = new THREE.MeshStandardMaterial({
          color: isRiser ? '#EADFC8' : '#1A1E24',
          emissive: isRiser ? new THREE.Color('#C2542A') : new THREE.Color('#000'),
          emissiveIntensity: isRiser ? 0.65 : 0,
          roughness: 0.3,
          metalness: 0.5,
        });
        const cap = new THREE.Mesh(capGeo, capMat);
        cap.rotation.y = mesh.rotation.y;
        cap.position.y = height + 0.015;
        group.add(cap);
        disposables.push(capGeo, capMat);

        // Pulse-Ring auf Top-3 — am Sockel.
        if (topRiserCodes.has(code)) {
          const ringGeo = new THREE.RingGeometry(0.48, 0.58, 64);
          const ringMat = new THREE.MeshBasicMaterial({
            color: signalColor,
            transparent: true,
            opacity: 0.55,
            side: THREE.DoubleSide,
          });
          const ring = new THREE.Mesh(ringGeo, ringMat);
          ring.rotation.x = -Math.PI / 2;
          ring.position.y = 0.015;
          group.add(ring);
          pulseRings.push(ring);
          disposables.push(ringGeo, ringMat);
        }

        // Hex base socket — a dark polygon stand the tower rises out of.
        const baseGeo = new THREE.CylinderGeometry(0.46, 0.50, 0.04, 6);
        const baseMat = new THREE.MeshStandardMaterial({
          color: '#1F242C',
          roughness: 0.85,
          metalness: 0.1,
        });
        const base = new THREE.Mesh(baseGeo, baseMat);
        base.position.y = 0.02;
        base.rotation.y = Math.PI / 6 + mesh.rotation.y;
        base.receiveShadow = true;
        group.add(base);
        disposables.push(baseGeo, baseMat);

        scene.add(group);
      });

      // ----- Ground glow under Top-3 (soft radial light disk) ----
      topRiserCodes.forEach((code) => {
        const coord = LAENDER_COORDS[code];
        if (!coord) return;
        const glowGeo = new THREE.CircleGeometry(1.1, 48);
        const glowMat = new THREE.MeshBasicMaterial({
          color: '#C2542A',
          transparent: true,
          opacity: 0.22,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        });
        const glow = new THREE.Mesh(glowGeo, glowMat);
        glow.rotation.x = -Math.PI / 2;
        glow.position.set(coord.x, 0.012, coord.z);
        scene.add(glow);
        disposables.push(glowGeo, glowMat);
      });

      // ----- TOP-3 floating billboard labels -----------------------
      const labelSprites: any[] = [];
      topRisers.forEach((r) => {
        const coord = LAENDER_COORDS[r.code];
        if (!coord) return;
        const delta = typeof r.delta7d === 'number'
          ? (r.delta7d > 0 ? '+' : '') + (r.delta7d * 100).toFixed(0) + '% · 7d'
          : '—';
        const tex = makeLabelTexture(THREE, r.name.toUpperCase(), delta);
        const spriteMat = new THREE.SpriteMaterial({
          map: tex,
          transparent: true,
          depthTest: false,
          depthWrite: false,
        });
        const sprite = new THREE.Sprite(spriteMat);
        const h = towerTipY[r.code] ?? 1;
        sprite.position.set(coord.x, h + 0.85, coord.z);
        sprite.scale.set(1.8, 0.6, 1); // Aspect 3:1 matches 512×172 canvas.
        scene.add(sprite);
        labelSprites.push(sprite);
        disposables.push(spriteMat, tex);
      });

      // ----- TRANSFER BEAM (From → To der Empfehlung) ----------
      // Ein Terracotta-Bogen im Raum von der Spitze des From-Turms
      // zur Spitze des To-Turms. TubeGeometry entlang einer Bezier-
      // Kurve mit einem Peak in der Mitte (wie ein Wurf).
      let beamTube: any | null = null;
      let beamMat: any | null = null;
      let beamHeadSphere: any | null = null;
      let beamTailSphere: any | null = null;
      if (shiftFromCode && shiftToCode && shiftFromCode !== shiftToCode) {
        const fromC = LAENDER_COORDS[shiftFromCode];
        const toC = LAENDER_COORDS[shiftToCode];
        const fromH = towerTipY[shiftFromCode] ?? 1;
        const toH = towerTipY[shiftToCode] ?? 1;
        if (fromC && toC) {
          const start = new THREE.Vector3(fromC.x, fromH + 0.15, fromC.z);
          const end = new THREE.Vector3(toC.x, toH + 0.15, toC.z);
          const mid = start.clone().lerp(end, 0.5);
          // Wurfhöhe abhängig von Distanz, minimum 1.2.
          const dist = start.distanceTo(end);
          mid.y = Math.max(start.y, end.y) + Math.max(1.2, dist * 0.35);

          const curve = new THREE.CatmullRomCurve3([start, mid, end], false, 'centripetal');
          const tubeGeo = new THREE.TubeGeometry(curve, 64, 0.035, 12, false);
          beamMat = new THREE.MeshBasicMaterial({
            color: '#D8632F',
            transparent: true,
            opacity: 0.85,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          });
          beamTube = new THREE.Mesh(tubeGeo, beamMat);
          scene.add(beamTube);
          disposables.push(tubeGeo, beamMat);

          // Tail-Sphere am Ausgangspunkt (subtiler)
          const tailGeo = new THREE.SphereGeometry(0.09, 16, 16);
          const tailMat = new THREE.MeshBasicMaterial({
            color: '#4A5261',
            transparent: true,
            opacity: 0.75,
          });
          beamTailSphere = new THREE.Mesh(tailGeo, tailMat);
          beamTailSphere.position.copy(start);
          scene.add(beamTailSphere);
          disposables.push(tailGeo, tailMat);

          // Head-Sphere am Zielpunkt — pulsiert
          const headGeo = new THREE.SphereGeometry(0.14, 24, 24);
          const headMat = new THREE.MeshBasicMaterial({
            color: '#D8632F',
            transparent: true,
            opacity: 0.95,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          });
          beamHeadSphere = new THREE.Mesh(headGeo, headMat);
          beamHeadSphere.position.copy(end);
          scene.add(beamHeadSphere);
          disposables.push(headGeo, headMat);
        }
      }

      // ----- Germany boundary outline ------------------------------
      const boundaryPts = [
        [-3.2, -3.0], [-0.8, -3.85], [1.0, -3.85], [2.4, -3.55],
        [2.7, -2.2], [2.6, 0.5], [1.8, 2.85], [0.2, 3.05],
        [-1.8, 2.85], [-3.0, 1.55], [-3.25, -0.4], [-3.2, -3.0],
      ];
      const bPts = boundaryPts.map(([x, z]) => new THREE.Vector3(x, 0.006, z));
      const bGeom = new THREE.BufferGeometry().setFromPoints(bPts);
      const boundary = new THREE.Line(
        bGeom,
        new THREE.LineBasicMaterial({
          color: '#4A5261',
          transparent: true,
          opacity: 0.62,
        }),
      );
      scene.add(boundary);
      disposables.push(bGeom);

      // ----- Animation loop ----------------------------------------
      const t0 = performance.now();
      const animate = () => {
        if (!mounted) return;
        const t = (performance.now() - t0) / 1000;

        // Kamera-Drift — sanftes figure-8.
        const r = 9.5;
        const ang = Math.sin(t * 0.08) * 0.28;
        camera.position.x = Math.sin(ang) * r + 2.2;
        camera.position.z = Math.cos(ang) * r + 1.5;
        camera.position.y = 6.4 + Math.sin(t * 0.12) * 0.45;
        camera.lookAt(0, 0.6, 0);

        // Pulse-Rings auf Top-3
        pulseRings.forEach((ring) => {
          const p = (Math.sin(performance.now() / 800) + 1) / 2;
          ring.scale.setScalar(1 + p * 0.9);
          ring.material.opacity = 0.52 * (1 - p);
        });

        // Spotlights breathing
        spotlights.forEach((s, i) => {
          s.intensity = 2.5 + Math.sin(performance.now() / 620 + i) * 0.55;
        });

        // Transfer-Beam: Opazitäts-Puls + Head-Sphere skaliert.
        if (beamMat) {
          const bp = (Math.sin(performance.now() / 650) + 1) / 2;
          beamMat.opacity = 0.55 + bp * 0.35;
        }
        if (beamHeadSphere) {
          const hp = (Math.sin(performance.now() / 420) + 1) / 2;
          beamHeadSphere.scale.setScalar(1 + hp * 0.5);
          beamHeadSphere.material.opacity = 0.65 + hp * 0.32;
        }

        // Labels immer Billboard zur Kamera → Sprite macht das automatisch.

        renderer.render(scene, camera);
        raf = requestAnimationFrame(animate);
      };
      animate();

      const onResize = () => {
        if (!mountRef.current) return;
        const ww = mount.clientWidth;
        const hh = mount.clientHeight;
        if (ww < 10 || hh < 10) return;
        camera.aspect = ww / hh;
        camera.updateProjectionMatrix();
        renderer.setSize(ww, hh, false);
      };
      window.addEventListener('resize', onResize);

      cleanup = () => {
        cancelAnimationFrame(raf);
        window.removeEventListener('resize', onResize);
        disposables.forEach((d) => d.dispose?.());
        renderer.dispose();
        if (mount) mount.innerHTML = '';
      };
    };

    start();
    return () => {
      mounted = false;
      cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regionsKey, topRiserKey, topRisersKey, beamKey]);

  return <div className="atlas-canvas" ref={mountRef} />;
};

// -----------------------------------------------------------------
// Root — Atlas Section
// -----------------------------------------------------------------
export const AtlasSection: React.FC<Props> = ({ snapshot }) => {
  const ranked = useMemo(
    () =>
      [...snapshot.regions]
        .filter((r) => typeof r.delta7d === 'number' && Number.isFinite(r.delta7d))
        .sort((a, b) => (b.delta7d ?? -Infinity) - (a.delta7d ?? -Infinity)),
    [snapshot.regions],
  );

  const topRisers = useMemo(() => ranked.slice(0, 3), [ranked]);
  const bottomFallers = useMemo(() => ranked.slice(-3).reverse(), [ranked]);

  const topRiserCodes = useMemo(
    () => new Set<Bundesland>(topRisers.map((r) => r.code)),
    [topRisers],
  );

  const activeRegionCount = useMemo(
    () =>
      snapshot.regions.filter(
        (r) => r.decisionLabel !== 'TrainingPending',
      ).length,
    [snapshot.regions],
  );
  const pendingRegionCount = snapshot.regions.length - activeRegionCount;

  const shiftFromCode = snapshot.primaryRecommendation?.fromCode ?? null;
  const shiftToCode = snapshot.primaryRecommendation?.toCode ?? null;

  const virusShort =
    snapshot.virusTyp === 'Influenza A'
      ? 'Flu-A · H3N2'
      : snapshot.virusTyp === 'Influenza B'
        ? 'Flu-B'
        : snapshot.virusTyp === 'RSV A' || snapshot.virusTyp === 'RSV'
          ? 'RSV-A'
          : snapshot.virusTyp;

  const horizonDays = snapshot.modelStatus?.horizonDays ?? 21;

  const readiness = snapshot.modelStatus?.forecastReadiness ?? 'UNKNOWN';
  const gateTone: GateTone =
    readiness === 'GO_RANKING' || readiness === 'RANKING_OK'
      ? 'go'
      : readiness === 'WATCH' || readiness === 'LEAD_ONLY'
        ? 'watch'
        : 'unknown';
  const gateLabel =
    gateTone === 'go'
      ? 'Gate · GO'
      : gateTone === 'watch'
        ? 'Gate · WATCH'
        : 'Gate · UNKNOWN';

  // For HUD: show the shift line "BY → BB" when we have it.
  const shiftHudLine =
    shiftFromCode && shiftToCode && shiftFromCode !== shiftToCode
      ? `${shiftFromCode} → ${shiftToCode}`
      : null;

  // Regional ranking always runs at RANKING_HORIZON_DAYS (h=7) — the
  // snapshot-builder enforces this regardless of the header lead horizon.
  // We label tiles and HUD explicitly with "7 d" so readers stop asking
  // whether +45 % means today, T+7 or T+21.
  const RANKING_HORIZON_LABEL = '7 Tage';
  const RANKING_HORIZON_SHORT = '7d';

  return (
    <section className="instr-section" id="sec-atlas">
      <SectionHeader
        numeral="I"
        title="Wellen-Atlas"
        subtitle={
          <>
            {activeRegionCount} / 16 Bundesländer
            {pendingRegionCount > 0 ? ` (${pendingRegionCount} Training pending)` : ''}{' '}
            · Höhe = {RANKING_HORIZON_LABEL}-Welle · Farbe = Richtung
          </>
        }
        gate={{ label: gateLabel, tone: gateTone }}
        primer={
          <>
            Jedes Bundesland als Turm. <b>Höhe</b> = erwartete
            Atemwegs-Welle in 7 Tagen gegenüber heute, <b>Farbe</b> =
            Richtung (rot für Anstieg, grün für Rückgang). Die drei
            höchsten Länder bekommen ein schwebendes Label mit der
            konkreten Zahl („+45 % · 7d"). Graue Türme = regionales
            Modell für dieses Virus noch nicht trainiert — keine
            Prognose, statt einer schlechten. Wert für dich:
            Wellenbewegung in Deutschland auf einen Blick, inklusive
            der Frage, wo du Budget aktivierst oder zurückziehst.
          </>
        }
      />

      <div className="atlas-wrap">
        <AtlasScene
          regions={snapshot.regions}
          topRisers={topRisers}
          topRiserCodes={topRiserCodes}
          shiftFromCode={shiftFromCode as Bundesland | null}
          shiftToCode={shiftToCode as Bundesland | null}
        />

        {/* Grain overlay — subtile Papier-Struktur */}
        <div className="atlas-grain" aria-hidden />

        {/* Corner brackets — instrument viewport */}
        <div className="atlas-bracket tl" />
        <div className="atlas-bracket tr" />
        <div className="atlas-bracket bl" />
        <div className="atlas-bracket br" />

        <div className="atlas-hud">
          <div className="atlas-hud-corner tl">
            <div>Projektion · Perspektive 30°</div>
            <div>Ranking · <b>+7 TAGE</b></div>
            <div>Skalierung · <b>LINEAR</b></div>
          </div>
          <div className="atlas-hud-corner tr">
            <div>{virusShort}</div>
            <div>
              Signal · <span className="sig">ONLINE</span>
            </div>
            <div>
              Ausgabe · <b>{snapshot.isoWeek}</b>
            </div>
          </div>
          <div className="atlas-hud-corner bl">
            <div>
              {activeRegionCount} / 16 Länder aktiv
            </div>
            {pendingRegionCount > 0 ? (
              <div className="atlas-hud-pending">
                {pendingRegionCount}× Training pending
              </div>
            ) : null}
            <div>
              Top-3 Spotlights <span className="sig">●●●</span>
            </div>
            {shiftHudLine && (
              <div>
                Transfer · <span className="sig">{shiftHudLine}</span>
              </div>
            )}
          </div>
          <div className="atlas-hud-corner br">
            <div>LAT 51.1657° N</div>
            <div>LON 10.4515° E</div>
            <div>ALT 640.0 m</div>
          </div>

          <div className="atlas-riser-list">
            <div className="head">Top-Riser · {RANKING_HORIZON_LABEL}</div>
            {topRisers.map((r, i) => (
              <div className="riser-row" key={r.code}>
                <span className="rank">{String(i + 1).padStart(2, '0')}</span>
                <span className="name">{r.name}</span>
                <span className="delta">
                  {fmtSignedPct(r.delta7d)} · {RANKING_HORIZON_SHORT}
                </span>
              </div>
            ))}
            {bottomFallers.map((r, i) => (
              <div
                className="riser-row fall"
                key={r.code}
                style={i === 0 ? { marginTop: 24 } : undefined}
              >
                <span className="rank">
                  {String(ranked.length - bottomFallers.length + i + 1).padStart(2, '0')}
                </span>
                <span className="name">{r.name}</span>
                <span className="delta">
                  {fmtSignedPct(r.delta7d)} · {RANKING_HORIZON_SHORT}
                </span>
              </div>
            ))}
          </div>

          <div className="atlas-legend">
            <span>
              <span className="swatch up" />Anstieg
            </span>
            <span>
              <span className="swatch flat" />Plateau
            </span>
            <span>
              <span className="swatch down" />Rückgang
            </span>
            {shiftHudLine && (
              <span>
                <span
                  className="swatch"
                  style={{ background: '#D8632F', boxShadow: '0 0 8px rgba(216,99,47,0.6)' }}
                />
                Transfer-Beam
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};

export default AtlasSection;
