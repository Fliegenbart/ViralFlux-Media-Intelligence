import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

type IntegrationStatus = 'connected' | 'degraded' | 'disconnected';

type Integration = {
  name: string;
  system: string;
  status: IntegrationStatus;
  lastSuccessfulSync: string;
  description: string;
};

const STATUS_UI: Record<IntegrationStatus, { label: string; dot: string; badgeBg: string; badgeText: string }> = {
  connected: {
    label: 'Verbunden',
    dot: 'bg-emerald-400',
    badgeBg: 'bg-emerald-50',
    badgeText: 'text-emerald-700',
  },
  degraded: {
    label: 'Eingeschraenkt',
    dot: 'bg-amber-400',
    badgeBg: 'bg-amber-50',
    badgeText: 'text-amber-700',
  },
  disconnected: {
    label: 'Getrennt',
    dot: 'bg-rose-400',
    badgeBg: 'bg-rose-50',
    badgeText: 'text-rose-700',
  },
};

type IntegrationStatusResponse = {
  sap?: { last_sync_at: string | null };
  ims?: { last_sync_at: string | null };
  any?: { last_sync_at: string | null };
};

const parseDate = (s: string | null | undefined) => {
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
};

const computeStatus = (last: Date | null): IntegrationStatus => {
  if (!last) return 'disconnected';
  const ageMs = Date.now() - last.getTime();
  const hours = ageMs / (1000 * 60 * 60);
  if (hours <= 48) return 'connected';
  if (hours <= 24 * 7) return 'degraded';
  return 'disconnected';
};

const fmtLast = (d: Date | null) => {
  if (!d) return 'Noch nie';
  try {
    return d.toLocaleString('de-DE', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch (_) {
    return d.toISOString();
  }
};

const DataIntegration: React.FC = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState<IntegrationStatusResponse | null>(null);

  const lastSync = useMemo(() => {
    const sap = parseDate(status?.sap?.last_sync_at ?? null);
    const ims = parseDate(status?.ims?.last_sync_at ?? null);
    const best = sap && ims ? (sap > ims ? sap : ims) : sap || ims;
    return fmtLast(best);
  }, [status]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await fetch('/api/webhooks/integrations/status');
        if (!res.ok) return;
        const data = (await res.json()) as IntegrationStatusResponse;
        if (alive) setStatus(data);
      } catch (_) {}
    };
    load();
    const id = window.setInterval(load, 30_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  const sapLast = parseDate(status?.sap?.last_sync_at ?? null);
  const imsLast = parseDate(status?.ims?.last_sync_at ?? null);

  const integrations: Integration[] = useMemo(
    () => [
      {
        name: 'SAP ERP',
        system: 'sap',
        status: computeStatus(sapLast),
        lastSuccessfulSync: fmtLast(sapLast),
        description: 'Nicht direkt angebunden. SAP muss die Daten via M2M-Webhook an ViralFlux pushen.',
      },
      {
        name: 'IMS Health',
        system: 'ims',
        status: computeStatus(imsLast),
        lastSuccessfulSync: fmtLast(imsLast),
        description: 'Nicht direkt angebunden. IMS/ETL muss die Daten via M2M-Webhook an ViralFlux pushen.',
      },
    ],
    [sapLast, imsLast]
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-[1200px] mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="w-10 h-10 rounded-xl flex items-center justify-center transition bg-white border border-slate-200 hover:bg-slate-50 hover:border-slate-300"
              aria-label="Zurueck ins Media Cockpit"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">Enterprise Integrationen</h1>
              <p className="text-xs text-slate-400">Server-to-Server Sync statt manueller CSV-Uploads</p>
            </div>
          </div>

          <div className="text-xs text-slate-400">
            Letzter erfolgreicher M2M-Sync: <span className="text-slate-600 font-medium">{lastSync}</span>
          </div>
        </div>
      </header>

      <main className="max-w-[1200px] mx-auto px-6 py-6 space-y-6">
        <section className="rounded-2xl p-4 bg-amber-50/60 border border-amber-200">
          <div className="text-xs font-semibold text-amber-800">Hinweis</div>
          <p className="text-xs text-slate-600 mt-1">
            SAP ERP und IMS Health sind aktuell nicht automatisch per Connector verbunden. Diese Systeme gelten erst dann als
            &quot;Verbunden&quot;, wenn sie regelmaessig Daten an unseren Webhook pushen.
          </p>
        </section>

        <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {integrations.map((integration) => {
            const ui = STATUS_UI[integration.status];
            return (
              <div
                key={integration.system}
                className="card p-5"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <span className={`w-2.5 h-2.5 rounded-full ${ui.dot}`} />
                      <h2 className="text-base font-semibold text-slate-900">{integration.name}</h2>
                    </div>
                    <p className="text-xs text-slate-400 mt-2">{integration.description}</p>
                  </div>

                  <div className={`px-2.5 py-1 rounded-lg ${ui.badgeBg}`}>
                    <span className={`text-xs font-semibold ${ui.badgeText}`}>{ui.label}</span>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl p-3 bg-slate-50 border border-slate-200">
                    <div className="text-[11px] text-slate-400">Letzter Sync</div>
                    <div className="text-sm text-slate-700 font-medium mt-1">{integration.lastSuccessfulSync}</div>
                  </div>
                  <div className="rounded-xl p-3 bg-slate-50 border border-slate-200">
                    <div className="text-[11px] text-slate-400">Transport</div>
                    <div className="text-sm text-slate-700 font-medium mt-1">Webhook (API-Key)</div>
                  </div>
                </div>
              </div>
            );
          })}
        </section>

        <section className="card p-5">
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-slate-900">Webhook Endpoint (ERP/IMS)</h3>
            <p className="text-xs text-slate-400">
              Dieser Endpoint ersetzt manuelle CSV-Uploads. Das Backend antwortet sofort mit <span className="text-slate-700 font-semibold">HTTP 202 Accepted</span> und verarbeitet die Inserts asynchron via Celery.
            </p>
          </div>

          <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-xl p-4 bg-slate-50 border border-slate-200">
              <div className="text-[11px] text-slate-400 mb-2">Endpoint</div>
              <div className="font-mono text-xs text-slate-700">POST /api/webhooks/erp/sales-sync</div>

              <div className="text-[11px] text-slate-400 mt-4 mb-2">Header</div>
              <div className="font-mono text-xs text-slate-700">X-API-Key: &lt;M2M_SECRET_KEY&gt;</div>

              <div className="text-[11px] text-slate-400 mt-4 mb-2">Beispiel-Payload</div>
              <pre className="font-mono text-[11px] leading-5 text-slate-700 overflow-auto rounded-lg p-3 bg-white border border-slate-200">
{`{
  "product_id": "GELO-12345",
  "region_code": "DE-BW",
  "units_sold": 1240,
  "revenue": 15340.50,
  "timestamp": "2026-02-18T23:59:00+01:00"
}`}
              </pre>
            </div>

            <div className="rounded-xl p-4 bg-slate-50 border border-slate-200">
              <div className="text-[11px] text-slate-400 mb-2">Beispiel (curl)</div>
              <pre className="font-mono text-[11px] leading-5 text-slate-700 overflow-auto rounded-lg p-3 bg-white border border-slate-200">
{`curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <M2M_SECRET_KEY>" \
  -d '{"product_id":"GELO-12345","region_code":"DE-BW","units_sold":1240,"revenue":15340.50,"timestamp":"2026-02-18T23:59:00+01:00"}' \
  https://fluxengine.labpulse.ai/api/webhooks/erp/sales-sync`}
              </pre>

              <div className="mt-4 rounded-xl p-3 bg-emerald-50/60 border border-emerald-200">
                <div className="text-xs text-emerald-800 font-semibold">Hinweis</div>
                <p className="text-xs text-slate-600 mt-1">
                  Manuelle Datei-Uploads sind bewusst deaktiviert. Integrationen laufen automatisiert, revisionssicher und ohne UI-Prozessbruch.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
};

export default DataIntegration;
