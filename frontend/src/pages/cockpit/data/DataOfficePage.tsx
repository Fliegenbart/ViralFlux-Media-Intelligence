import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import '../../../styles/peix.css';
import '../../../styles/peix-gate.css';
import '../../../styles/peix-data.css';

import CockpitGate from '../CockpitGate';
import { useCockpitSnapshot } from '../useCockpitSnapshot';
import {
  useOutcomeImportBatches,
  useOutcomeBatchDetail,
  useTruthCoverage,
  uploadOutcomeCsv,
  deleteOutcomeBatch,
  type OutcomeImportBatch,
  type OutcomeImportResult,
} from './useOutcomeData';

/**
 * /cockpit/data — Data Office.
 *
 * Die Datenverwaltungs-Oberfläche für das GELO-Pilot-Setup. Vier
 * Blöcke unter einer gemeinsamen Top-Bar:
 *
 *   §  Status-Stripe — Coverage, letzter Import, offene Issues, M2M-Status
 *   I  Truth-Coverage — Heatmap pro Bundesland (wie viele Wochen Truth-Daten)
 *   II Upload-Panel   — Drag-and-Drop CSV, Validate-Vorschau, Commit
 *   III Batch-History — letzte 20 Imports mit Drilldown auf Issues
 *   IV M2M-Integration — curl-Beispiel + Kontakt für API-Key
 *
 * Auth: Gate-Cookie (peix26) reicht für alle GET-Endpoints.
 * POST /outcomes/import ist admin-only — wenn der User nur Gate-Cookie
 * hat, kommt beim Commit ein 403 zurück und das UI zeigt "Admin-Login
 * erforderlich" + den Weg zum Key. Honest-by-default.
 */

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

const BUNDESLAENDER = [
  { code: 'BW', name: 'Baden-Württ.' },
  { code: 'BY', name: 'Bayern' },
  { code: 'BE', name: 'Berlin' },
  { code: 'BB', name: 'Brandenburg' },
  { code: 'HB', name: 'Bremen' },
  { code: 'HH', name: 'Hamburg' },
  { code: 'HE', name: 'Hessen' },
  { code: 'MV', name: 'Meckl.-Vorp.' },
  { code: 'NI', name: 'Niedersachs.' },
  { code: 'NW', name: 'NRW' },
  { code: 'RP', name: 'Rheinl.-Pfalz' },
  { code: 'SL', name: 'Saarland' },
  { code: 'SN', name: 'Sachsen' },
  { code: 'ST', name: 'Sachsen-A.' },
  { code: 'SH', name: 'Schleswig-H.' },
  { code: 'TH', name: 'Thüringen' },
];

function fmtDateDE(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function fmtDateTimeDE(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return (
    d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }) +
    ' · ' +
    d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
  );
}

// ------------------------------------------------------------------
// Coverage Heatmap
// ------------------------------------------------------------------

const CoverageHeatmap: React.FC<{
  perRegion: Array<{ region_code: string; coverage_weeks: number }> | null;
}> = ({ perRegion }) => {
  const weeksByCode = useMemo(() => {
    const m = new Map<string, number>();
    (perRegion ?? []).forEach((r) => {
      const prev = m.get(r.region_code) ?? 0;
      m.set(r.region_code, Math.max(prev, r.coverage_weeks));
    });
    return m;
  }, [perRegion]);

  return (
    <>
      <div className="coverage-grid">
        {BUNDESLAENDER.map((bl) => {
          const weeks = weeksByCode.get(bl.code) ?? 0;
          const hasData = weeks > 0;
          return (
            <div
              key={bl.code}
              className={`coverage-cell ${hasData ? 'has-data' : 'empty'}`}
              title={`${bl.name} · ${weeks} Wochen Truth-Daten`}
            >
              <div className="code">{bl.code}</div>
              <div className="weeks">
                {weeks}
                <span className="unit"> w</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="coverage-legend">
        <span>
          <span className="sw has" />Hat Truth-Daten
        </span>
        <span>
          <span className="sw empty" />Leer — kein Outcome-Record
        </span>
      </div>
    </>
  );
};

// ------------------------------------------------------------------
// Upload Panel
// ------------------------------------------------------------------

interface UploadState {
  fileName: string | null;
  csvPayload: string | null;
  replaceExisting: boolean;
  validateOnly: boolean;
  result: OutcomeImportResult | null;
  error: { status: number; message: string } | null;
  busy: boolean;
}

const INITIAL_UPLOAD: UploadState = {
  fileName: null,
  csvPayload: null,
  replaceExisting: false,
  validateOnly: true,
  result: null,
  error: null,
  busy: false,
};

const UploadPanel: React.FC<{ onImported: () => void }> = ({ onImported }) => {
  const [state, setState] = useState<UploadState>(INITIAL_UPLOAD);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const readFile = useCallback(async (file: File) => {
    const txt = await file.text();
    setState((s) => ({
      ...s,
      fileName: file.name,
      csvPayload: txt,
      result: null,
      error: null,
    }));
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const f = e.dataTransfer.files?.[0];
      if (f) void readFile(f);
    },
    [readFile],
  );

  const onFilePicked = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (f) void readFile(f);
    },
    [readFile],
  );

  const reset = () => {
    setState(INITIAL_UPLOAD);
    if (inputRef.current) inputRef.current.value = '';
  };

  const submit = async () => {
    if (!state.csvPayload) return;
    setState((s) => ({ ...s, busy: true, result: null, error: null }));
    const res = await uploadOutcomeCsv({
      brand: 'GELO',
      sourceLabel: 'cockpit_upload',
      csvPayload: state.csvPayload,
      fileName: state.fileName ?? undefined,
      replaceExisting: state.replaceExisting,
      validateOnly: state.validateOnly,
    });
    if (res.ok) {
      setState((s) => ({ ...s, busy: false, result: res.result }));
      if (!state.validateOnly) onImported();
    } else {
      setState((s) => ({
        ...s,
        busy: false,
        error: { status: res.status, message: res.message },
      }));
    }
  };

  return (
    <div className="upload-panel">
      <div>
        <label
          className={`upload-drop ${dragOver ? 'drag-over' : ''} ${state.fileName ? 'has-file' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          htmlFor="upload-file-input"
        >
          <input
            id="upload-file-input"
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={onFilePicked}
          />
          {state.fileName ? (
            <>
              <div className="primary">CSV geladen</div>
              <div className="file-name">{state.fileName}</div>
              <div className="secondary">
                {state.csvPayload
                  ? `${state.csvPayload.split('\n').length} Zeilen · ${(state.csvPayload.length / 1024).toFixed(1)} kB`
                  : ''}
              </div>
            </>
          ) : (
            <>
              <div className="primary">CSV hier hineinziehen</div>
              <div className="secondary">oder klicken zum Auswählen</div>
              <div className="secondary" style={{ opacity: 0.7, marginTop: 8 }}>
                Format: <a className="btn-link" href="/api/v1/media/outcomes/template" target="_blank" rel="noreferrer">Template herunterladen</a>
              </div>
            </>
          )}
        </label>

        {state.result && (
          <div className={`upload-result ${state.error ? 'error' : 'success'}`}>
            <h4>
              {state.validateOnly ? 'Validierung' : 'Import'} · {state.result.status ?? 'ok'}
            </h4>
            <div>
              <b>{state.result.rows_valid ?? state.result.rows_total ?? 0}</b> gültige Zeilen ·{' '}
              <b>{state.result.rows_imported ?? 0}</b> importiert ·{' '}
              <b>{state.result.rows_rejected ?? 0}</b> abgelehnt ·{' '}
              <b>{state.result.rows_duplicate ?? 0}</b> Duplikate
            </div>
            {state.result.issues && state.result.issues.length > 0 && (
              <>
                <div style={{ marginTop: 12, fontWeight: 500 }}>
                  {state.result.issues.length} Issue{state.result.issues.length === 1 ? '' : 's'}
                </div>
                <pre>
                  {state.result.issues
                    .slice(0, 10)
                    .map(
                      (i) =>
                        `[${i.severity}] ${i.code}${i.row_number ? ` · Zeile ${i.row_number}` : ''}: ${i.message}`,
                    )
                    .join('\n')}
                  {state.result.issues.length > 10 ? `\n… +${state.result.issues.length - 10} weitere` : ''}
                </pre>
              </>
            )}
          </div>
        )}

        {state.error && (
          <div className="upload-result error">
            <h4>
              Fehler · HTTP {state.error.status}
              {state.error.status === 403 && ' · Admin-Login erforderlich'}
            </h4>
            <div>
              {state.error.status === 403
                ? 'Für den tatsächlichen Commit eines Imports brauchst du einen peix-Admin-Login. Das Cockpit-Gate (peix26) reicht für Validierung und Read-only-Ansichten, nicht für Schreib-Aktionen. Kontakt: data@peix.de'
                : state.error.message}
            </div>
          </div>
        )}
      </div>

      <div className="upload-options">
        <div className="block-kicker" style={{ marginBottom: 4 }}>
          Optionen
        </div>
        <label>
          <input
            type="checkbox"
            checked={state.validateOnly}
            onChange={(e) => setState((s) => ({ ...s, validateOnly: e.target.checked, result: null, error: null }))}
          />
          <span>
            <b>Nur validieren</b> — prüft das CSV ohne Datenbank-Commit. Empfohlen
            für den ersten Durchlauf: zeigt welche Zeilen OK sind und wo Issues
            stecken, ohne irgendwas zu persistieren.
          </span>
        </label>
        <label>
          <input
            type="checkbox"
            checked={state.replaceExisting}
            onChange={(e) => setState((s) => ({ ...s, replaceExisting: e.target.checked }))}
          />
          <span>
            <b>Bestehende Werte ersetzen</b> — wenn für denselben
            (Woche / Region / Produkt) bereits ein Truth-Record existiert,
            wird der alte Wert überschrieben. Default: bestehende Werte bleiben.
          </span>
        </label>

        <div className="upload-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!state.csvPayload || state.busy}
            onClick={submit}
          >
            {state.busy
              ? 'Läuft …'
              : state.validateOnly
                ? 'Validieren'
                : 'Importieren'}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={!state.csvPayload || state.busy}
            onClick={reset}
          >
            Zurücksetzen
          </button>
        </div>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------
// Batch History with drilldown
// ------------------------------------------------------------------

const BatchRow: React.FC<{
  batch: OutcomeImportBatch;
  expanded: boolean;
  deleting: boolean;
  onToggle: () => void;
  onDelete: () => void;
}> = ({ batch, expanded, deleting, onToggle, onDelete }) => {
  const statusClass =
    batch.status === 'imported'
      ? 'imported'
      : batch.status === 'validated'
        ? 'validated'
        : batch.status === 'failed' || batch.status === 'rejected'
          ? 'failed'
          : batch.status === 'deleted'
            ? 'deleted'
            : '';
  const isDeleted = batch.status === 'deleted';
  return (
    <tr
      className={`${expanded ? 'open' : ''}${isDeleted ? ' row-deleted' : ''}`}
      onClick={onToggle}
    >
      <td className="batch-id">{batch.batch_id.slice(0, 12)}</td>
      <td className="batch-source">
        {batch.source_label ?? batch.source_system ?? '—'}
        {batch.external_batch_id && (
          <span style={{ color: 'var(--ink-40)', fontFamily: "'JetBrains Mono', monospace", fontSize: 11, marginLeft: 8 }}>
            ·&nbsp;{batch.external_batch_id}
          </span>
        )}
      </td>
      <td>
        <span className={`batch-status ${statusClass}`}>{batch.status}</span>
      </td>
      <td className="batch-rows">
        {batch.rows_imported ?? batch.rows_valid ?? 0}
        <span className="minor"> / {batch.rows_total ?? 0}</span>
        {batch.rows_rejected ? (
          <span style={{ color: 'var(--signal)', marginLeft: 10 }}>
            −{batch.rows_rejected}
          </span>
        ) : null}
      </td>
      <td className="batch-date">
        {fmtDateDE(batch.week_min)} → {fmtDateDE(batch.week_max)}
      </td>
      <td className="batch-date">{fmtDateTimeDE(batch.imported_at ?? batch.created_at)}</td>
      <td className="batch-actions" onClick={(e) => e.stopPropagation()}>
        {isDeleted ? (
          <span className="batch-deleted-flag" title="Bereits gelöscht">—</span>
        ) : (
          <button
            type="button"
            className="batch-delete-btn"
            disabled={deleting}
            onClick={onDelete}
            title="Batch + importierte Records löschen"
            aria-label="Batch löschen"
          >
            {deleting ? '…' : '⌫'}
          </button>
        )}
      </td>
    </tr>
  );
};

const BatchDetail: React.FC<{ batchId: string }> = ({ batchId }) => {
  const { data, loading, error } = useOutcomeBatchDetail(batchId);

  if (loading) {
    return (
      <tr>
        <td colSpan={7} className="batch-detail">
          <div style={{ color: 'var(--ink-60)', fontStyle: 'italic' }}>lädt Detail …</div>
        </td>
      </tr>
    );
  }
  if (error) {
    return (
      <tr>
        <td colSpan={7} className="batch-detail">
          <div style={{ color: 'var(--signal)' }}>
            Fehler beim Laden: {error.message}
          </div>
        </td>
      </tr>
    );
  }
  if (!data) return null;

  const issues = data.issues ?? [];
  return (
    <tr>
      <td colSpan={7} className="batch-detail">
        <h4>
          Batch {data.batch_id.slice(0, 12)} · {data.rows_imported ?? 0} importiert,{' '}
          {data.rows_rejected ?? 0} abgelehnt
        </h4>
        {issues.length === 0 ? (
          <div style={{ color: 'var(--ink-60)', fontStyle: 'italic' }}>
            Keine Issues — Import war sauber.
          </div>
        ) : (
          <>
            <div
              className="block-kicker"
              style={{ marginBottom: 8, color: 'var(--ink-60)' }}
            >
              {issues.length} Issue{issues.length === 1 ? '' : 's'}
            </div>
            {issues.slice(0, 50).map((i, idx) => (
              <div className="issue-row" key={idx}>
                <span className={`sev ${i.severity.toLowerCase()}`}>{i.severity}</span>
                <span className="code">{i.code}</span>
                <span className="message">
                  {i.message}
                  {i.field && <span style={{ color: 'var(--ink-40)' }}> · {i.field}</span>}
                </span>
                <span className="row-num">
                  {i.row_number ? `Zeile ${i.row_number}` : ''}
                </span>
              </div>
            ))}
            {issues.length > 50 && (
              <div style={{ color: 'var(--ink-40)', marginTop: 12, fontStyle: 'italic' }}>
                … +{issues.length - 50} weitere Issues verborgen
              </div>
            )}
          </>
        )}
      </td>
    </tr>
  );
};

const BatchHistory: React.FC<{
  refreshKey: number;
  onDeleted?: () => void;
}> = ({ refreshKey, onDeleted }) => {
  const { data, loading, error, reload } = useOutcomeImportBatches('GELO', 20);
  const [openId, setOpenId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Trigger reload when parent bumps refreshKey.
  React.useEffect(() => {
    if (refreshKey > 0) reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  const handleDelete = async (batchId: string) => {
    const confirmed = window.confirm(
      'Batch + alle importierten Records unwiderruflich löschen?\n\n' +
        'Truth-Coverage und § IV Feedback-Loop werden ohne diese Zeilen\n' +
        'neu berechnet. Rückgängig machen ist nicht möglich.',
    );
    if (!confirmed) return;
    setDeletingId(batchId);
    setDeleteError(null);
    const res = await deleteOutcomeBatch(batchId);
    setDeletingId(null);
    if (!res.ok) {
      setDeleteError(
        res.status === 403
          ? 'Admin-Login erforderlich (das Gate-Cookie reicht nur für Read-only-Aktionen).'
          : `Fehler (HTTP ${res.status}): ${res.message}`,
      );
      return;
    }
    reload();
    onDeleted?.();
  };

  const batches = data?.batches ?? [];

  if (loading && batches.length === 0) {
    return <div className="empty-state">Lädt Import-Historie …</div>;
  }
  if (error) {
    return <div className="error-banner">Fehler: {error.message}</div>;
  }
  if (batches.length === 0) {
    return (
      <div className="empty-state">
        Noch keine Import-Batches. Lade oben eine CSV hoch oder nutze den
        M2M-Endpoint.
      </div>
    );
  }

  return (
    <>
      {deleteError ? (
        <div className="error-banner" style={{ marginBottom: 12 }}>
          {deleteError}
        </div>
      ) : null}
      <table className="batch-table">
        <thead>
          <tr>
            <th>Batch-ID</th>
            <th>Quelle</th>
            <th>Status</th>
            <th>Zeilen</th>
            <th>Wochen-Range</th>
            <th>Importiert</th>
            <th className="batch-actions-head">Aktion</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((b) => (
            <React.Fragment key={b.batch_id}>
              <BatchRow
                batch={b}
                expanded={openId === b.batch_id}
                deleting={deletingId === b.batch_id}
                onToggle={() => setOpenId(openId === b.batch_id ? null : b.batch_id)}
                onDelete={() => handleDelete(b.batch_id)}
              />
              {openId === b.batch_id && <BatchDetail batchId={b.batch_id} />}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </>
  );
};

// ------------------------------------------------------------------
// M2M Card
// ------------------------------------------------------------------

const M2MCard: React.FC = () => {
  const origin =
    typeof window !== 'undefined' ? window.location.origin : 'https://fluxengine.labpulse.ai';
  const sample =
    `curl -X POST '${origin}/api/v1/media/outcomes/ingest' \\\n` +
    `  -H 'X-API-Key: <your-m2m-key>' \\\n` +
    `  -H 'Content-Type: application/json' \\\n` +
    `  -d '{\n` +
    `    "brand": "GELO",\n` +
    `    "source_system": "gelo_bi",\n` +
    `    "external_batch_id": "2026-04-week-16",\n` +
    `    "observations": [\n` +
    `      {\n` +
    `        "product": "GeloMyrtol",\n` +
    `        "region_code": "BB",\n` +
    `        "window_start": "2026-04-13T00:00:00",\n` +
    `        "window_end": "2026-04-19T23:59:59",\n` +
    `        "metric_name": "sales_units",\n` +
    `        "metric_value": 1420,\n` +
    `        "channel": "apotheke",\n` +
    `        "metadata": {"source": "IQVIA"}\n` +
    `      }\n` +
    `    ]\n` +
    `  }'`;

  return (
    <div className="m2m-card">
      <div>
        <h3>M2M-Integration</h3>
        <p>
          Der produktive Weg für GELO-BI: Outcome-Observations per API
          pushen, ohne manuelle CSV-Uploads. Der Endpoint akzeptiert einen
          strukturierten JSON-Batch und läuft über einen langlebigen
          API-Key.
        </p>
        <p>
          <b style={{ color: 'var(--paper)' }}>Was ihr braucht:</b> einen
          API-Key von peix (über data@peix.de anfragen) und eine
          Liefervereinbarung zum Metriken-Vokabular (Produkt-Kennung,
          Regionen-Scope, Metrik-Namen).
        </p>
        <div className="field">
          <div className="field-label">Endpoint</div>
          <div className="field-value">
            POST {origin}/api/v1/media/outcomes/ingest
          </div>
        </div>
        <div className="field">
          <div className="field-label">Header</div>
          <div className="field-value">X-API-Key: &lt;m2m-key&gt;</div>
        </div>
      </div>
      <div>
        <div className="field-label">Beispiel-Request (curl)</div>
        <pre>{sample}</pre>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------
// Status Stripe — 4 Kacheln oben
// ------------------------------------------------------------------

const StatusStripe: React.FC<{
  batches: OutcomeImportBatch[];
  coverage: {
    coverage_weeks: number;
    latest_week: string | null;
    regions_covered: number;
    products_covered: number;
  } | null;
}> = ({ batches, coverage }) => {
  const lastBatch = batches[0] ?? null;
  const totalRowsImported = batches.reduce(
    (s, b) => s + (b.rows_imported ?? 0),
    0,
  );
  const openIssues = batches.reduce(
    (s, b) => s + Math.max(0, b.rows_rejected ?? 0),
    0,
  );

  return (
    <div className="status-stripe">
      <div className="status-cell">
        <div className="label">Truth-Coverage</div>
        <div className="big">
          {coverage && coverage.coverage_weeks > 0 ? (
            <>
              {coverage.coverage_weeks}
              <span className="unit">Wochen</span>
            </>
          ) : (
            <span className="dash">—</span>
          )}
        </div>
        <div className="note">
          {coverage?.latest_week
            ? `Letzte Woche: ${fmtDateDE(coverage.latest_week)}`
            : 'Noch keine Truth-Daten angebunden.'}
        </div>
      </div>

      <div className="status-cell">
        <div className="label">Letzter Import</div>
        <div className="big">
          {lastBatch ? (
            <>
              {lastBatch.rows_imported ?? 0}
              <span className="unit">Rows</span>
            </>
          ) : (
            <span className="dash">—</span>
          )}
        </div>
        <div className="note">
          {lastBatch
            ? `${fmtDateTimeDE(lastBatch.imported_at ?? lastBatch.created_at)} · ${lastBatch.source_label ?? lastBatch.source_system ?? '—'}`
            : 'Noch kein Import durchgelaufen.'}
        </div>
      </div>

      <div className="status-cell">
        <div className="label">Kumulierte Records</div>
        <div className="big">
          {totalRowsImported > 0 ? (
            totalRowsImported.toLocaleString('de-DE')
          ) : (
            <span className="dash">—</span>
          )}
        </div>
        <div className="note">
          über {batches.length} Batch{batches.length === 1 ? '' : 'es'}
          {openIssues > 0 ? ` · ${openIssues} abgelehnt` : ''}
        </div>
      </div>

      <div className="status-cell">
        <div className="label">Regionen × Produkte</div>
        <div className="big">
          {coverage && coverage.regions_covered > 0 ? (
            <>
              {coverage.regions_covered}
              <span className="unit">× {coverage.products_covered ?? 0}</span>
            </>
          ) : (
            <span className="dash">—</span>
          )}
        </div>
        <div className="note">
          Coverage-Matrix aus Truth-Records
        </div>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------
// Main Page
// ------------------------------------------------------------------

export const DataOfficePage: React.FC = () => {
  const { snapshot, loading, error } = useCockpitSnapshot({
    virusTyp: 'Influenza A',
    horizonDays: 14,
    leadTarget: 'ATEMWEGSINDEX',
  });

  const isAuth401 =
    error &&
    (((error as Error & { status?: number }).status === 401) ||
      /HTTP 401/.test(error.message));
  const { data: batchesData } = useOutcomeImportBatches('GELO', 20);
  const { data: coverageData } = useTruthCoverage('GELO', 'Influenza A');
  const [importTick, setImportTick] = useState(0);

  if (isAuth401) {
    return <CockpitGate />;
  }

  if (loading && !snapshot) {
    return (
      <div className="peix-data">
        <div className="page">
          <div style={{ padding: 80, textAlign: 'center', fontStyle: 'italic' }}>
            lädt Data Office …
          </div>
        </div>
      </div>
    );
  }

  const batches = batchesData?.batches ?? [];
  const coverageSummary = coverageData
    ? {
        coverage_weeks: coverageData.coverage_weeks ?? 0,
        latest_week: coverageData.latest_week ?? null,
        regions_covered: coverageData.regions_covered ?? 0,
        products_covered: coverageData.products_covered ?? 0,
      }
    : null;
  const perRegion = (coverageData?.per_region_product ?? []).map((r) => ({
    region_code: r.region_code,
    coverage_weeks: r.coverage_weeks,
  }));

  return (
    <div className="peix-data">
      <div className="topbar">
        <div className="topbar-inner">
          <div className="topbar-brand">
            <span className="dot" />
            VIRALFLUX · COCKPIT
          </div>
          <div className="topbar-section">
            <b>DATA OFFICE</b>
          </div>
          <div className="topbar-section">
            Client · <b>GELO</b>
          </div>
          <Link to="/cockpit" className="topbar-back">
            ← Cockpit
          </Link>
        </div>
      </div>

      <div className="page">
        <div className="page-head">
          <div className="numeral">§</div>
          <div>
            <h1>
              Data Office
              <span className="sub">
                Sell-Out, Spend, Outcome. CSV oder API. Hier wird das Modell auf eure Realität kalibriert.
              </span>
            </h1>
          </div>
          <div className="stamp">
            Brand · <b>GELO</b>
            <br />
            Virus · <b>Influenza A</b>
            <br />
            Generiert · <b>{fmtDateTimeDE(snapshot?.generatedAt)}</b>
          </div>
        </div>

        <StatusStripe batches={batches} coverage={coverageSummary} />

        <p className="data-primer">
          Im <b>Data Office</b> lebt die Wirklichkeit, die das Cockpit zu
          seinen Prognosen in Beziehung setzt — Woche für Woche, pro
          Bundesland, pro Produkt. Ohne diese Daten sind alle EUR-Werte im
          Cockpit Striche und der Feedback-Loop in § VI bleibt leer.
          Eingegeben wird wahlweise <b>manuell per CSV</b> (siehe unten) oder
          automatisiert über die <b>M2M-API</b> (unterster Block). Jede
          Zeile ist ein Tupel <i>(Woche, Region, Produkt) → Media-Spend +
          Outcome</i>.
        </p>

        <div className="block">
          <div className="block-head">
            <h2 className="block-title">Truth-Coverage · 16 Bundesländer</h2>
            <span className="block-kicker">
              Wie viele Wochen Outcome-Daten je Bundesland vorhanden sind
            </span>
          </div>
          <p className="data-section-primer">
            Jede Zelle zeigt, für wie viele Kalenderwochen ein Bundesland
            bereits Outcome-Werte hat. Dunkle Zellen = dünne Datenlage,
            dort sind Aussagen im Backtest und Feedback-Loop statistisch
            schwach. Ein Bundesland mit 0 Wochen erscheint nicht im
            Reconciliation-Panel von § IV — ehrlich statt geschätzt.
          </p>
          <CoverageHeatmap perRegion={perRegion} />
        </div>

        <div className="block">
          <div className="block-head">
            <h2 className="block-title">CSV-Upload</h2>
            <span className="block-kicker">
              Manuelle Einspielung · Validate-First empfohlen
            </span>
          </div>
          <p className="data-section-primer">
            <b>Was kommt hier rein?</b> Eine Zeile pro Woche × Bundesland ×
            Produkt. Jede Zeile bündelt <b>Media-Spend</b> (was GELO
            ausgegeben hat) <i>und</i> <b>Outcome</b> (was dabei
            herausgekommen ist — Sales, Bestellungen, Revenue, Reichweite).
            Das System lernt daraus: welche Empfehlung der letzten Woche
            hat tatsächlich Reach/Umsatz gebracht, wo lag die Prognose
            daneben. Die erste Zeile ist der CSV-Header, danach Daten-
            Zeilen in exakt der Reihenfolge:
          </p>
          <div className="csv-schema">
            <table>
              <thead>
                <tr>
                  <th>Spalte</th>
                  <th>Bedeutung</th>
                  <th>Pflicht?</th>
                  <th>Beispiel</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><code>week_start</code></td>
                  <td>Wochenstart, Montag, ISO-Format</td>
                  <td>✓</td>
                  <td><code>2026-02-02</code></td>
                </tr>
                <tr>
                  <td><code>product</code></td>
                  <td>GELO-Produktname</td>
                  <td>✓</td>
                  <td><code>GeloProsed</code></td>
                </tr>
                <tr>
                  <td><code>region_code</code></td>
                  <td>Bundesland-Code (SH, BW…) oder voller Name</td>
                  <td>✓</td>
                  <td><code>SH</code> oder <code>Hamburg</code></td>
                </tr>
                <tr>
                  <td><code>media_spend_eur</code></td>
                  <td>ausgegebenes Media-Budget in dieser Woche</td>
                  <td>empfohlen</td>
                  <td><code>12000</code></td>
                </tr>
                <tr>
                  <td><code>sales_units</code></td>
                  <td>verkaufte Einheiten (Packungen)</td>
                  <td colSpan={1} rowSpan={3} className="span-required">
                    mindestens eines
                  </td>
                  <td><code>140</code></td>
                </tr>
                <tr>
                  <td><code>order_count</code></td>
                  <td>Anzahl Bestellungen</td>
                  <td><code>44</code></td>
                </tr>
                <tr>
                  <td><code>revenue_eur</code></td>
                  <td>Umsatz in Euro</td>
                  <td><code>18500</code></td>
                </tr>
                <tr>
                  <td><code>qualified_visits</code></td>
                  <td>qualifizierte Website-/Landingpage-Besuche</td>
                  <td>optional</td>
                  <td><code>320</code></td>
                </tr>
                <tr>
                  <td><code>search_lift_index</code></td>
                  <td>Google-Trends-Lift gegenüber Vorwoche</td>
                  <td>optional</td>
                  <td><code>18.5</code></td>
                </tr>
                <tr>
                  <td><code>impressions</code></td>
                  <td>Ad-Impressions</td>
                  <td>optional</td>
                  <td><code>240000</code></td>
                </tr>
                <tr>
                  <td><code>clicks</code></td>
                  <td>Ad-Clicks</td>
                  <td>optional</td>
                  <td><code>5800</code></td>
                </tr>
              </tbody>
            </table>
            <p className="schema-note">
              Leere Zellen sind erlaubt — einfach leer lassen, das System
              zählt sie als „nicht berichtet". Die Pflicht-Regel lautet:
              eine Zeile muss mindestens <b>eines</b> von <code>sales_units</code>,
              <code>order_count</code> oder <code>revenue_eur</code>
              enthalten, sonst wird sie abgelehnt. Starte immer mit
              „Nur validieren" — der Import meldet dir jede problematische
              Zeile mit Zeilennummer und Grund.
            </p>
          </div>
          <UploadPanel onImported={() => setImportTick((t) => t + 1)} />
        </div>

        <div className="block">
          <div className="block-head">
            <h2 className="block-title">Import-Historie</h2>
            <span className="block-kicker">
              Letzte 20 Batches · Klick für Issue-Detail
            </span>
          </div>
          <p className="data-section-primer">
            Jeder CSV-Import wird als <b>Batch</b> archiviert — mit
            Zeitstempel, Zeilenzahl, Status und den Issues (falls welche
            aufgetreten sind). Klick auf eine Zeile öffnet die Issue-Liste
            des Batches. Willst du einen Batch rückgängig machen oder die
            Historie aufräumen, nutze das <b>⌫</b>-Symbol pro Zeile (löscht
            die importierten Records <i>und</i> den Batch-Eintrag).
          </p>
          <BatchHistory refreshKey={importTick} onDeleted={() => setImportTick((t) => t + 1)} />
        </div>

        <div className="block">
          <div className="block-head">
            <h2 className="block-title">Automatisierte Integration</h2>
            <span className="block-kicker">
              M2M-API für produktiven Betrieb
            </span>
          </div>
          <p className="data-section-primer">
            Statt jeden Montag ein CSV manuell zu schieben kann GELOs
            Media-System die Outcome-Zeilen direkt per HTTP-POST an die
            M2M-API pushen. Derselbe Datensatz-Standard wie oben, aber
            als JSON-Array statt CSV. Nutzt einen pro-Kunden-API-Key;
            wenn die manuelle CSV-Phase steht, schalten wir auf nächtliche
            M2M-Imports um. Ab dann seht ihr das Cockpit jeden Morgen frisch.
          </p>
          <M2MCard />
        </div>

        <footer className="page-foot">
          <div>
            ViralFlux · Data Office · <b>peix gmbh</b>
          </div>
          <div>
            Kontakt für API-Keys & Schema: <b>data@peix.de</b>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default DataOfficePage;
