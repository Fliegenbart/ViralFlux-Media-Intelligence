import React, { useEffect, useMemo, useRef, useState } from 'react';
import type {
  CockpitSnapshot,
  RegionForecast,
  Bundesland,
  SiteEarlyWarningAlert,
} from '../types';
import { fmtSignedPct } from '../format';
import SectionHeader from './SectionHeader';
import type { GateTone } from './SectionHeader';
import AtlasChoropleth from './AtlasChoropleth';

// 2026-04-23 Atlas-Refactor: 3D-Türme + Hex-Toggle entfernt zugunsten
// einer realen Deutschland-Karte (Choropleth). AtlasScene und AtlasHexgrid
// bleiben als Files im Repo (nicht mehr importiert), können später
// gelöscht werden.

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

function firstNumber(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

function compactValue(value: number | null): string {
  if (value === null) return '—';
  return Math.round(value).toLocaleString('de-DE');
}

function alertReasons(alert: SiteEarlyWarningAlert): string[] {
  const rawReasons = alert.reasons;
  const reasons = Array.isArray(rawReasons)
    ? rawReasons
    : typeof rawReasons === 'string' && rawReasons.trim()
      ? rawReasons.split(',').map((item) => item.trim()).filter(Boolean)
      : [];
  const qualityFlags = alert.quality_flags ?? alert.qualityFlags ?? [];
  const flags = [...reasons, ...qualityFlags];
  if (alert.unter_bg === 'ja' || alert.unterBg === 'ja') flags.push('unter_bg');
  if (alert.laborwechsel === 'ja') flags.push('laborwechsel');
  return Array.from(new Set(flags));
}

function activeAlertsFrom(snapshot: CockpitSnapshot): SiteEarlyWarningAlert[] {
  const payload = snapshot.siteEarlyWarning ?? snapshot.site_early_warning ?? null;
  if (!payload) return [];
  if (Array.isArray(payload.activeAlerts)) return payload.activeAlerts;
  if (Array.isArray(payload.active_alerts)) return payload.active_alerts;
  return [];
}

function activeAlertCount(snapshot: CockpitSnapshot, alerts: SiteEarlyWarningAlert[]): number {
  const payload = snapshot.siteEarlyWarning ?? snapshot.site_early_warning ?? null;
  if (!payload) return alerts.length;
  if (typeof payload.active_alert_count === 'number') return payload.active_alert_count;
  if (typeof payload.activeAlertCount === 'number') return payload.activeAlertCount;
  if (typeof payload.active_alerts === 'number') return payload.active_alerts;
  return alerts.length;
}

const SiteEarlyWarningLayer: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const payload = snapshot.siteEarlyWarning ?? snapshot.site_early_warning ?? null;
  const alerts = activeAlertsFrom(snapshot);
  const count = activeAlertCount(snapshot, alerts);
  const redCount = payload?.active_red_alerts ?? payload?.activeRedAlerts ?? alerts.filter((a) => a.stage === 'red').length;
  const yellowCount = payload?.active_yellow_alerts ?? payload?.activeYellowAlerts ?? alerts.filter((a) => a.stage === 'yellow').length;
  const latestDate = payload?.latest_measurement_date ?? payload?.latestMeasurementDate ?? '—';

  return (
    <div className="site-warning-layer" aria-label="AMELAG Standort-Frühwarnung">
      <div className="site-warning-head">
        <div>
          <div className="site-warning-kicker">AMELAG Standort-Frühwarnung</div>
          <h3>Lokale Baseline statt letzter Einzelwert</h3>
        </div>
        <div className="site-warning-counts">
          <span className="red">{redCount} rot</span>
          <span className="yellow">{yellowCount} gelb</span>
          <span>{count} aktiv</span>
        </div>
      </div>
      <p className="site-warning-note">
        Ein Standort wird nicht alarmiert, nur weil der letzte Messwert stark
        steigt. Verglichen wird gegen die lokale Standort-Baseline; Qualitätsflags
        wie unter_bg oder Laborwechsel bleiben sichtbar. Diese Warnungen sind
        lokal und nicht budgetwirksam.
      </p>
      <div className="site-warning-meta">
        <span>Latest wastewater data: {latestDate}</span>
        <span>Vergleich: current_value gegen baseline_value</span>
      </div>
      {alerts.length > 0 ? (
        <div className="site-alert-list">
          {alerts.slice(0, 8).map((alert) => {
            const current = firstNumber(alert.current_value, alert.currentValue);
            const baseline = firstNumber(alert.baseline_value, alert.baselineValue);
            const changePct = firstNumber(alert.change_pct, alert.changePct);
            const flags = alertReasons(alert);
            return (
              <div className={`site-alert site-alert-${alert.stage}`} key={`${alert.standort}-${alert.typ}-${alert.datum}`}>
                <div className="site-alert-main">
                  <span className={`site-alert-stage ${alert.stage}`}>{alert.stage}</span>
                  <span className="site-alert-name">{alert.standort}</span>
                  <span className="site-alert-region">{alert.bundesland}</span>
                  <span className="site-alert-virus">{alert.typ}</span>
                </div>
                <div className="site-alert-values">
                  <span>current {compactValue(current)}</span>
                  <span>baseline {compactValue(baseline)}</span>
                  <span>
                    change {changePct !== null ? `${changePct > 0 ? '+' : ''}${changePct.toFixed(0)} %` : '—'}
                  </span>
                </div>
                <div className="site-alert-flags">
                  {flags.length > 0 ? flags.join(' · ') : 'quality_flags=none'}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="site-warning-empty">
          Noch kein site_early_warning Detailblock im Snapshot. Sobald aktive
          Standort-Alarme mitgeliefert werden, erscheinen hier Standort,
          Virus, Baseline, aktueller Wert, Abweichung und Flags.
        </div>
      )}
    </div>
  );
};

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
  virusLabel: string;
  onHoverRegion?: (code: string | null) => void;
}

// Hover-State: which tower the pointer currently hovers. null when not
// over any tower. Lives outside the Three.js useEffect because it's
// bridging the 3D scene to a React-rendered tooltip overlay.
interface HoverState {
  code: string;
  screenX: number;
  screenY: number;
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

export const AtlasScene: React.FC<AtlasSceneProps> = ({
  regions,
  topRisers,
  topRiserCodes,
  shiftFromCode,
  shiftToCode,
  virusLabel,
  onHoverRegion,
}) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [hover, setHover] = useState<HoverState | null>(null);

  // regionsByCode — keeps tooltip body copy in sync with the latest
  // props without having to drill into the Three.js closure.
  const regionsByCode = useMemo(() => {
    const m = new Map<string, RegionForecast>();
    regions.forEach((r) => m.set(r.code, r));
    return m;
  }, [regions]);

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
      // Tower meshes tracked for raycaster hover detection. The userData.code
      // on each mesh lets the React tooltip resolve the region payload.
      const towerMeshes: any[] = [];

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
        mesh.userData = { code, kind: 'tower' };
        group.add(mesh);
        towerMeshes.push(mesh);
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

      // ----- Hover raycaster ---------------------------------------
      // Projects the pointer into the 3D scene, intersects with the
      // tower meshes, and lifts the hovered region's code into React
      // state. The tooltip UI is rendered outside the canvas as a
      // plain React <div> so it can use HTML typography + line
      // breaks — pure Three.js text would force canvas textures.
      const raycaster = new THREE.Raycaster();
      const pointer = new THREE.Vector2();
      let lastHoveredCode: string | null = null;
      const onPointerMove = (e: PointerEvent) => {
        const rect = renderer.domElement.getBoundingClientRect();
        pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(pointer, camera);
        const hits = raycaster.intersectObjects(towerMeshes, false);
        if (hits.length > 0) {
          const code = (hits[0].object as any).userData?.code as string | undefined;
          if (code) {
            if (code !== lastHoveredCode) {
              lastHoveredCode = code;
              onHoverRegion?.(code);
            }
            setHover({ code, screenX: e.clientX, screenY: e.clientY });
            renderer.domElement.style.cursor = 'pointer';
            return;
          }
        }
        if (lastHoveredCode !== null) {
          lastHoveredCode = null;
          onHoverRegion?.(null);
        }
        setHover(null);
        renderer.domElement.style.cursor = '';
      };
      const onPointerLeave = () => {
        if (lastHoveredCode !== null) {
          lastHoveredCode = null;
          onHoverRegion?.(null);
        }
        setHover(null);
        renderer.domElement.style.cursor = '';
      };
      renderer.domElement.addEventListener('pointermove', onPointerMove);
      renderer.domElement.addEventListener('pointerleave', onPointerLeave);

      cleanup = () => {
        cancelAnimationFrame(raf);
        window.removeEventListener('resize', onResize);
        renderer.domElement.removeEventListener('pointermove', onPointerMove);
        renderer.domElement.removeEventListener('pointerleave', onPointerLeave);
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

  const hoverRegion = hover ? regionsByCode.get(hover.code) ?? null : null;

  return (
    <>
      <div className="atlas-canvas" ref={mountRef} />
      {hover && hoverRegion ? (
        <AtlasTooltip
          hover={hover}
          region={hoverRegion}
          virusLabel={virusLabel}
        />
      ) : null}
    </>
  );
};

// -----------------------------------------------------------------
// AtlasTooltip — HTML-overlay at the pointer position, showing a
// plain-language explanation of the hovered tower. Rendered outside
// the WebGL canvas so we can use crisp typography + multi-line copy.
// Positioned via fixed coordinates (screenX/Y from the pointer event).
// -----------------------------------------------------------------
const AtlasTooltip: React.FC<{
  hover: HoverState;
  region: RegionForecast;
  virusLabel: string;
}> = ({ hover, region, virusLabel }) => {
  const pct = typeof region.delta7d === 'number' ? region.delta7d * 100 : null;
  const tone =
    pct === null
      ? 'flat'
      : pct > 15
        ? 'strong-rise'
        : pct > 2
          ? 'rise'
          : pct < -15
            ? 'strong-fall'
            : pct < -2
              ? 'fall'
              : 'flat';
  const verdict = (() => {
    if (region.decisionLabel === 'TrainingPending') {
      return `Für dieses Bundesland ist das Regional-Modell noch nicht trainiert — der Turm steht hier nur als Platzhalter, ohne Prognose.`;
    }
    if (pct === null) {
      return `Keine verwertbare Δ-Messung im Prognosefenster — der Turm bleibt flach.`;
    }
    const sign = pct >= 0 ? '+' : '';
    const abs = Math.abs(pct).toFixed(0);
    if (tone === 'strong-rise') {
      return `Frühsignal: deutlicher Anstieg der ${virusLabel}-Aktivität im Prognosefenster — rund ${sign}${abs} % gegenüber heute. Klassischer Wellen-Anfang; in Marketing-Sprache: Region als Priorisierungskandidat prüfen, kein freigegebener Shift.`;
    }
    if (tone === 'rise') {
      return `Frühsignal: moderater Anstieg um etwa ${sign}${abs} % im Prognosefenster — Welle noch nicht klar, aber Tendenz nach oben. In Marketing-Sprache: genauer beobachten, nicht überreagieren.`;
    }
    if (tone === 'strong-fall') {
      return `Frühsignal: ${virusLabel}-Aktivität geht im Prognosefenster deutlich zurück, um etwa ${sign}${abs} %. Wellen-Ende oder Sommer-Delle; in Marketing-Sprache: Entlastungskandidat prüfen, Budget aber nicht automatisch verschieben.`;
    }
    if (tone === 'fall') {
      return `Frühsignal: leichter Rückgang von rund ${sign}${abs} % im Prognosefenster. Keine Welle hier; in Marketing-Sprache: kein aktiver Trigger, aber auch kein Anlass zum Aktivieren.`;
    }
    return `Plateau — das Signal im Prognosefenster bleibt nahezu unverändert (${sign}${abs} %). Weder Alarm noch Chance.`;
  })();

  return (
    <div
      className={`atlas-tooltip atlas-tooltip-${tone}`}
      style={{ left: hover.screenX, top: hover.screenY }}
      role="tooltip"
    >
      <div className="atlas-tooltip-head">
        <span className="atlas-tooltip-name">{region.name}</span>
        {pct !== null ? (
          <span className="atlas-tooltip-delta">
            {pct >= 0 ? '+' : ''}
            {pct.toFixed(0)}% · Δ
          </span>
        ) : null}
      </div>
      <p className="atlas-tooltip-body">{verdict}</p>
      {region.decisionLabel && region.decisionLabel !== 'TrainingPending' ? (
        <div className="atlas-tooltip-meta">
          Entscheidungs-Label · <b>{region.decisionLabel}</b>
        </div>
      ) : null}
    </div>
  );
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

  // 2026-04-22 Atlas-Cleanup: virusShort wurde in atlas-hud-corner tr
  // gerendert — beide sind jetzt weg (SectionHeader zeigt den Virus
  // bereits im Subtitle). Variable entfernt, damit kein toter Code
  // bleibt.

  const horizonDays = snapshot.modelStatus?.horizonDays ?? 21;

  const readiness = snapshot.modelStatus?.forecastReadiness ?? 'UNKNOWN';
  // 2026-04-21 Integrity-Fix + Pfad-C: readiness states DATA_STALE,
  // DRIFT_WARN und SEASON_OFF vom Backend-Gate. Alle drei mappen auf
  // 'watch' (kein GO), die Labels unterscheiden den Grund.
  const gateTone: GateTone =
    readiness === 'GO_RANKING' || readiness === 'RANKING_OK'
      ? 'go'
      : readiness === 'WATCH'
        || readiness === 'LEAD_ONLY'
        || readiness === 'DATA_STALE'
        || readiness === 'DRIFT_WARN'
        || readiness === 'SEASON_OFF'
        ? 'watch'
        : 'unknown';
  const gateLabel =
    readiness === 'DATA_STALE'
      ? 'Signal · data stale'
      : readiness === 'DRIFT_WARN'
        ? 'Signal · drift warning'
        : readiness === 'SEASON_OFF'
          ? 'Signal · season off'
          : gateTone === 'go'
            ? 'Signal · active'
            : gateTone === 'watch'
              ? 'Signal · watch'
              : 'Signal · unknown';

  // For HUD: show the shift line "BY → BB" when we have it.
  const shiftHudLine =
    shiftFromCode && shiftToCode && shiftFromCode !== shiftToCode
      ? `${shiftFromCode} → ${shiftToCode}`
      : null;

  // Label the active model horizon from the snapshot so the UI does not
  // imply a fixed 7-day claim when the GELO path is operated as h5.
  const RANKING_HORIZON_LABEL = `${horizonDays} Tage`;
  const RANKING_HORIZON_SHORT = `${horizonDays}d`;

  return (
    <section className="instr-section" id="sec-atlas">
      <SectionHeader
        numeral="II"
        title="AMELAG Standort-Frühwarnung"
        subtitle={
          <>
            {activeRegionCount} / 16 Bundesländer
            {pendingRegionCount > 0 ? ` (${pendingRegionCount} Training pending)` : ''}{' '}
            · Färbung = Δ über {RANKING_HORIZON_LABEL}
          </>
        }
        gate={{ label: gateLabel, tone: gateTone }}
        primer={
          <>
            Deutschland-Karte mit allen 16 Bundesländern.{' '}
            <b>Farbe</b>: rot = steigendes regionales Signal, grün =
            flach oder rückläufig. Die Intensität zeigt die Stärke des
            aktiven Prognosefensters. Riser <b>pulsieren</b>; der stärkste
            Riser wird zusätzlich markiert. Das Tool ist ein
            <b> Früherkennungs-System</b> gegen das RKI-Meldewesen, keine
            automatische Budgetfreigabe und keine absolute Fallzahl-Prognose.
          </>
        }
      />

      <div className="atlas-wrap atlas-wrap-choropleth">
        {/* 2026-04-23: Echte Deutschland-Karte als Choropleth. Bundesländer
           leuchten in HSL-Schattierung pro Δ7d, Riser pulsieren mit
           Geschwindigkeit proportional zur Stärke. Top-Riser zusätzlich
           mit weißem Stroke + kräftigem Glow. */}
        <AtlasChoropleth snapshot={snapshot} />

        <div className="atlas-hud">
          <div className="atlas-hud-corner bl">
            <div>{activeRegionCount} / 16 Länder aktiv</div>
            {pendingRegionCount > 0 ? (
              <div className="atlas-hud-pending">
                {pendingRegionCount}× Training pending
              </div>
            ) : null}
            {shiftHudLine && (
              <div>
                Signal-Kandidat · <span className="sig">{shiftHudLine}</span>
              </div>
            )}
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
                Signalrichtung
              </span>
            )}
          </div>
        </div>
      </div>
      <SiteEarlyWarningLayer snapshot={snapshot} />
    </section>
  );
};

export default AtlasSection;
