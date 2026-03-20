import React, { useState } from 'react';

import { TruthImportBatchDetailResponse, TruthImportBatchSummary, TruthImportIssue, TruthImportResponse, TruthSnapshot } from '../../../types/media';
import { formatDateShort, formatDateTime, truthFreshnessLabel, truthLayerLabel } from '../cockpitUtils';
import { batchStatusLabel, issueFieldLabel } from './evidenceUtils';

interface Props {
  truthSnapshot?: TruthSnapshot;
  truthPreview: TruthImportResponse | null;
  truthBatchDetail: TruthImportBatchDetailResponse | null;
  truthActionLoading: boolean;
  truthBatchDetailLoading: boolean;
  onSubmitTruthCsv: (payload: {
    file: File;
    sourceLabel: string;
    replaceExisting: boolean;
    validateOnly: boolean;
  }) => Promise<void>;
  onLoadTruthBatchDetail: (batchId: string) => Promise<void>;
}

const ImportValidationSection: React.FC<Props> = ({
  truthSnapshot,
  truthPreview,
  truthBatchDetail,
  truthActionLoading,
  truthBatchDetailLoading,
  onSubmitTruthCsv,
  onLoadTruthBatchDetail,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [sourceLabel, setSourceLabel] = useState('manual_csv');
  const [replaceExisting, setReplaceExisting] = useState(false);

  const selectedBatch = truthBatchDetail?.batch || truthPreview?.batch_summary || truthSnapshot?.latest_batch;
  const displayIssues: TruthImportIssue[] = truthPreview?.issues?.length
    ? truthPreview.issues
    : (truthBatchDetail?.issues || []);

  return (
    <>
      <section className="truth-analyst-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading">
            <span className="section-kicker">CSV-Import</span>
            <h2 className="subsection-title">Import der Kundendaten vorbereiten</h2>
            <p className="subsection-copy">
              Erwartet werden `week_start`, `product`, `region_code`, `media_spend_eur` plus mindestens eine echte Kundenmetrik wie `sales_units`, `order_count` oder `revenue_eur`.
            </p>
          </div>

          <div className="truth-form-grid">
            <label className="campaign-field campaign-field-wide">
              <span>Datei</span>
              <input
                className="media-input"
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
              />
            </label>

            <label className="campaign-field">
              <span>Quellenname</span>
              <input
                className="media-input"
                value={sourceLabel}
                onChange={(event) => setSourceLabel(event.target.value)}
                placeholder="manual_csv"
              />
            </label>

            <label className="campaign-field truth-checkbox-field">
              <span>Vorhandene Daten ersetzen</span>
              <div className="truth-checkbox-row">
                <input
                  type="checkbox"
                  checked={replaceExisting}
                  onChange={(event) => setReplaceExisting(event.target.checked)}
                />
                <small>Bestehende Zeilen für dieselbe Woche, dasselbe Produkt und dieselbe Region überschreiben.</small>
              </div>
            </label>
          </div>

          <div className="campaign-setup-footer">
            <div className="campaign-setup-note">
              {file ? `Bereit: ${file.name}` : 'Zuerst eine Wochen-CSV auswählen, dann prüfen und erst danach importieren.'}
            </div>
            <div className="review-action-row">
              <a className="media-button secondary" href={truthSnapshot?.template_url || '/api/v1/media/outcomes/template'}>
                CSV-Vorlage laden
              </a>
              <button
                className="media-button secondary"
                type="button"
                disabled={!file || truthActionLoading}
                onClick={() => file && onSubmitTruthCsv({ file, sourceLabel, replaceExisting, validateOnly: true })}
              >
                {truthActionLoading ? 'Prüfung läuft...' : 'Datei prüfen'}
              </button>
              <button
                className="media-button primary"
                type="button"
                disabled={!file || truthActionLoading}
                onClick={() => file && onSubmitTruthCsv({ file, sourceLabel, replaceExisting, validateOnly: false })}
              >
                {truthActionLoading ? 'Import läuft...' : 'Import starten'}
              </button>
            </div>
          </div>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading">
            <span className="section-kicker">Import-Vorschau</span>
            <h2 className="subsection-title">Prüfung und Ergebnis</h2>
            <p className="subsection-copy">
              Erst prüfen, dann importieren. Vorschau und importierte Datei zeigen dieselben Kennzahlen und Hinweise.
            </p>
          </div>

          {truthPreview?.batch_summary ? (
            <>
              <div className="metric-strip">
                <div className="metric-box">
                  <span>Status</span>
                  <strong>{batchStatusLabel(truthPreview.batch_summary.status)}</strong>
                </div>
                <div className="metric-box">
                  <span>Gültige Zeilen</span>
                  <strong>{truthPreview.batch_summary.rows_valid}</strong>
                </div>
                <div className="metric-box">
                  <span>Hinweise</span>
                  <strong>{truthPreview.issues.length}</strong>
                </div>
              </div>
              <div className="soft-panel review-panel-soft">
                <div className="evidence-row">
                  <span>Abdeckung nach Import</span>
                  <strong>{truthPreview.coverage_after_import?.coverage_weeks ?? 0} Wochen</strong>
                </div>
                <div className="evidence-row">
                  <span>Status Kundendaten</span>
                  <strong>{truthLayerLabel(truthPreview.coverage_after_import)}</strong>
                </div>
                <div className="evidence-row">
                  <span>Aktualität</span>
                  <strong>{truthFreshnessLabel(truthPreview.coverage_after_import?.truth_freshness_state)}</strong>
                </div>
              </div>
              <p className="section-copy">{truthPreview.message}</p>
            </>
          ) : (
            <div className="review-muted-copy">
              Noch keine Vorschau vorhanden. Lade eine CSV hoch und starte zuerst die Prüfung.
            </div>
          )}
        </div>
      </section>

      <section className="truth-analyst-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading">
            <span className="section-kicker">Import-Historie</span>
            <h2 className="subsection-title">Letzte Importe</h2>
          </div>
          <div className="truth-history-list">
            {(truthSnapshot?.recent_batches || []).length > 0 ? truthSnapshot!.recent_batches.map((batch: TruthImportBatchSummary) => (
              <button
                key={batch.batch_id}
                type="button"
                className={`truth-history-item ${selectedBatch?.batch_id === batch.batch_id ? 'is-active' : ''}`}
                onClick={() => onLoadTruthBatchDetail(batch.batch_id)}
              >
                <div>
                  <strong>{batch.file_name || batch.source_label || batch.batch_id}</strong>
                  <span>{batchStatusLabel(batch.status)} · {formatDateTime(batch.uploaded_at)}</span>
                </div>
                <small>{batch.rows_imported}/{batch.rows_total} importiert</small>
              </button>
            )) : (
              <div className="review-muted-copy">Noch keine Importe für Kundendaten vorhanden.</div>
            )}
          </div>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading">
            <span className="section-kicker">Import-Details</span>
            <h2 className="subsection-title">Ausgewählter Import</h2>
          </div>
          {truthBatchDetailLoading ? (
            <div className="review-muted-copy">Import-Details laden…</div>
          ) : selectedBatch ? (
            <div className="soft-panel review-panel-soft" style={{ display: 'grid', gap: 0 }}>
              <div className="evidence-row">
                <span>Import-ID</span>
                <strong>{selectedBatch.batch_id}</strong>
              </div>
              <div className="evidence-row">
                <span>Status</span>
                <strong>{batchStatusLabel(selectedBatch.status)}</strong>
              </div>
              <div className="evidence-row">
                <span>Zeitraum</span>
                <strong>{formatDateShort(selectedBatch.week_min)} bis {formatDateShort(selectedBatch.week_max)}</strong>
              </div>
              <div className="evidence-row">
                <span>Abdeckung nach Import</span>
                <strong>{selectedBatch.coverage_after_import?.coverage_weeks ?? 0} Wochen</strong>
              </div>
            </div>
          ) : (
            <div className="review-muted-copy">Wähle einen Import aus der Historie oder prüfe eine neue Datei.</div>
          )}
        </div>
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading">
          <span className="section-kicker">Hinweis-Tabelle</span>
          <h2 className="subsection-title">Probleme und Zuordnungshinweise</h2>
          <p className="subsection-copy">
            Jeder ausgeschlossene Datensatz bleibt sichtbar. Es gibt keine stillen Ausfälle.
          </p>
        </div>
        <div className="truth-issue-table">
          {displayIssues.length > 0 ? displayIssues.map((issue, index) => (
            <div key={`${issue.issue_code}-${issue.row_number || index}`} className="truth-issue-row">
              <div>
                <strong>Zeile {issue.row_number ?? '-'}</strong>
                <span>{issueFieldLabel(issue.field_name)} · {issue.issue_code}</span>
              </div>
              <p>{issue.message}</p>
            </div>
          )) : (
            <div className="review-muted-copy">Keine Hinweise sichtbar. Die aktuelle Vorschau oder der ausgewählte Import ist sauber.</div>
          )}
        </div>
      </section>
    </>
  );
};

export default ImportValidationSection;
