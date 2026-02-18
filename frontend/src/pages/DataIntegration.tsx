import React, { useMemo } from 'react';
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
    badgeBg: 'bg-emerald-500/10',
    badgeText: 'text-emerald-300',
  },
  degraded: {
    label: 'Eingeschraenkt',
    dot: 'bg-amber-400',
    badgeBg: 'bg-amber-500/10',
    badgeText: 'text-amber-300',
  },
  disconnected: {
    label: 'Getrennt',
    dot: 'bg-rose-400',
    badgeBg: 'bg-rose-500/10',
    badgeText: 'text-rose-300',
  },
};

const DataIntegration: React.FC = () => {
  const navigate = useNavigate();

  const lastSync = useMemo(() => {
    // Mock-Timestamp: "gestern 23:59" (Berlin), damit das UI nicht von Backend-Abhaengigkeiten blockiert.
    const now = new Date();
    const mock = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    mock.setHours(23, 59, 0, 0);
    return mock.toLocaleString('de-DE', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  }, []);

  const integrations: Integration[] = useMemo(
    () => [
      {
        name: 'SAP ERP',
        system: 'sap',
        status: 'connected',
        lastSuccessfulSync: lastSync,
        description: 'Automatischer Tages-Sync der Abverkaufs- und Umsatzdaten (M2M).',
      },
      {
        name: 'IMS Health',
        system: 'ims',
        status: 'connected',
        lastSuccessfulSync: lastSync,
        description: 'Automatischer Markt-/Panel-Sync fuer Absatzvergleiche (M2M).',
      },
    ],
    [lastSync]
  );

  return (
    <div className="min-h-screen" style={{ background: '#0f172a' }}>
      <header style={{ background: '#1e293b', borderBottom: '1px solid #334155' }}>
        <div className="max-w-[1200px] mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="w-10 h-10 rounded-xl flex items-center justify-center transition hover:bg-slate-700"
              style={{ border: '1px solid #334155' }}
              aria-label="Zurueck zum Dashboard"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">Enterprise Integrationen</h1>
              <p className="text-xs text-slate-400">Server-to-Server Sync statt manueller CSV-Uploads</p>
            </div>
          </div>

          <div className="text-xs text-slate-500">
            Letzter erfolgreicher M2M-Sync: <span className="text-slate-300 font-medium">{lastSync}</span>
          </div>
        </div>
      </header>

      <main className="max-w-[1200px] mx-auto px-6 py-6 space-y-6">
        <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {integrations.map((integration) => {
            const ui = STATUS_UI[integration.status];
            return (
              <div
                key={integration.system}
                className="rounded-2xl p-5"
                style={{ background: '#1e293b', border: '1px solid #334155' }}
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <span className={`w-2.5 h-2.5 rounded-full ${ui.dot}`} />
                      <h2 className="text-base font-semibold text-white">{integration.name}</h2>
                    </div>
                    <p className="text-xs text-slate-400 mt-2">{integration.description}</p>
                  </div>

                  <div className={`px-2.5 py-1 rounded-lg ${ui.badgeBg}`}>
                    <span className={`text-xs font-semibold ${ui.badgeText}`}>{ui.label}</span>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl p-3" style={{ background: 'rgba(15,23,42,0.65)', border: '1px solid #334155' }}>
                    <div className="text-[11px] text-slate-500">Letzter Sync</div>
                    <div className="text-sm text-slate-200 font-medium mt-1">{integration.lastSuccessfulSync}</div>
                  </div>
                  <div className="rounded-xl p-3" style={{ background: 'rgba(15,23,42,0.65)', border: '1px solid #334155' }}>
                    <div className="text-[11px] text-slate-500">Transport</div>
                    <div className="text-sm text-slate-200 font-medium mt-1">Webhook (API-Key)</div>
                  </div>
                </div>
              </div>
            );
          })}
        </section>

        <section className="rounded-2xl p-5" style={{ background: '#0b1220', border: '1px solid #334155' }}>
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-white">Webhook Endpoint (ERP/IMS)</h3>
            <p className="text-xs text-slate-400">
              Dieser Endpoint ersetzt manuelle CSV-Uploads. Das Backend antwortet sofort mit <span className="text-slate-200 font-semibold">HTTP 202 Accepted</span> und verarbeitet die Inserts asynchron via Celery.
            </p>
          </div>

          <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-xl p-4" style={{ background: '#0f172a', border: '1px solid #334155' }}>
              <div className="text-[11px] text-slate-500 mb-2">Endpoint</div>
              <div className="font-mono text-xs text-slate-200">POST /api/webhooks/erp/sales-sync</div>

              <div className="text-[11px] text-slate-500 mt-4 mb-2">Header</div>
              <div className="font-mono text-xs text-slate-200">X-API-Key: &lt;M2M_SECRET_KEY&gt;</div>

              <div className="text-[11px] text-slate-500 mt-4 mb-2">Beispiel-Payload</div>
              <pre className="font-mono text-[11px] leading-5 text-slate-200 overflow-auto rounded-lg p-3" style={{ background: '#0b1220', border: '1px solid #334155' }}>
{`{
  "product_id": "GELO-12345",
  "region_code": "DE-BW",
  "units_sold": 1240,
  "revenue": 15340.50,
  "timestamp": "2026-02-18T23:59:00+01:00"
}`}
              </pre>
            </div>

            <div className="rounded-xl p-4" style={{ background: '#0f172a', border: '1px solid #334155' }}>
              <div className="text-[11px] text-slate-500 mb-2">Beispiel (curl)</div>
              <pre className="font-mono text-[11px] leading-5 text-slate-200 overflow-auto rounded-lg p-3" style={{ background: '#0b1220', border: '1px solid #334155' }}>
{`curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <M2M_SECRET_KEY>" \
  -d '{"product_id":"GELO-12345","region_code":"DE-BW","units_sold":1240,"revenue":15340.50,"timestamp":"2026-02-18T23:59:00+01:00"}' \
  https://fluxengine.labpulse.ai/api/webhooks/erp/sales-sync`}
              </pre>

              <div className="mt-4 rounded-xl p-3" style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.25)' }}>
                <div className="text-xs text-emerald-200 font-semibold">Hinweis</div>
                <p className="text-xs text-slate-300 mt-1">
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
