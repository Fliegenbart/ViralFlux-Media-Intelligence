import React, { useCallback, useRef, useState } from 'react';
import { useMediaPlan, MediaPlanUploadResult } from '../useMediaPlan';

/**
 * 2026-04-21 Media-Plan-Upload-Modal.
 *
 * Kleine, pragmatische UI für CSV-Upload. Zwei Phasen:
 *   1. Drag/Drop oder File-Input → Dry-Run-Upload (Preview).
 *   2. Preview sichtbar → "Commit"-Button → echter Upload.
 *
 * Nach erfolgreichem Commit: Modal schließt sich, Snapshot wird per
 * onCommitted-Callback neu geladen (CockpitShell reicht das durch).
 */

interface Props {
  open: boolean;
  onClose: () => void;
  onCommitted?: () => void;
  client?: string;
}

export const MediaPlanUploadModal: React.FC<Props> = ({
  open,
  onClose,
  onCommitted,
  client = 'GELO',
}) => {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<MediaPlanUploadResult | null>(null);
  const { plan, upload, clear } = useMediaPlan({ client, autoLoad: open });

  const reset = useCallback(() => {
    setPendingFile(null);
    setPreview(null);
    setError(null);
    setBusy(false);
    if (fileRef.current) fileRef.current.value = '';
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      setBusy(true);
      setError(null);
      try {
        const result = await upload(file, { dryRun: true });
        setPendingFile(file);
        setPreview(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [upload],
  );

  const handleDrop = useCallback(
    async (ev: React.DragEvent<HTMLDivElement>) => {
      ev.preventDefault();
      setIsDragging(false);
      const file = ev.dataTransfer.files?.[0];
      if (file) await handleFile(file);
    },
    [handleFile],
  );

  const handleCommit = useCallback(async () => {
    if (!pendingFile) return;
    setBusy(true);
    setError(null);
    try {
      await upload(pendingFile, { dryRun: false });
      reset();
      onCommitted?.();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [pendingFile, upload, reset, onCommitted, onClose]);

  const handleClear = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await clear();
      onCommitted?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [clear, onCommitted]);

  if (!open) return null;

  const sum = preview?.summary;
  return (
    <div
      className="mpu-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Media-Plan Upload"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="mpu-modal">
        <div className="mpu-head">
          <h2>Media-Plan · CSV-Upload</h2>
          <button
            type="button"
            className="mpu-close"
            onClick={onClose}
            aria-label="Schließen"
          >
            ×
          </button>
        </div>

        <div className="mpu-intro">
          <p>
            Lade eine <b>CSV</b> mit den Spalten <code>iso_week, bundesland,
            channel, eur</code>. Eine Zeile pro Bundesland und Kanal. Beispiel:
          </p>
          <pre className="mpu-sample">
{`iso_week,bundesland,channel,eur
2026-W17,BW,TV,15000
2026-W17,BW,Digital,8500
2026-W17,BY,TV,18000`}
          </pre>
          <p className="mpu-hint">
            Gültige Bundesland-Codes: <code>SH HH NI HB NW HE RP SL BW BY BE BB MV SN ST TH</code>,
            oder <code>DE</code> für national unallokiert.
          </p>
        </div>

        {plan && plan.row_count > 0 ? (
          <div className="mpu-current">
            <b>Aktueller Plan:</b> {plan.row_count} Zeilen ·{' '}
            {plan.total_eur.toLocaleString('de-DE')} € gesamt ·{' '}
            {plan.iso_weeks.join(', ')}
            <button
              type="button"
              className="mpu-btn mpu-btn-ghost"
              onClick={handleClear}
              disabled={busy}
              style={{ marginLeft: 12 }}
            >
              Plan löschen
            </button>
          </div>
        ) : (
          <div className="mpu-current mpu-current-empty">
            <i>Kein Plan verbunden. Lade eine CSV, um EUR-Werte freizuschalten.</i>
          </div>
        )}

        <div
          className={`mpu-drop${isDragging ? ' mpu-drop-active' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          role="button"
          tabIndex={0}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFile(f);
            }}
            hidden
          />
          {busy ? 'Prüfe CSV …' : 'CSV hier ablegen oder klicken zum Auswählen'}
          {pendingFile ? (
            <div className="mpu-filename">{pendingFile.name}</div>
          ) : null}
        </div>

        {error ? <div className="mpu-error">{error}</div> : null}

        {sum ? (
          <div className="mpu-preview">
            <div className="mpu-preview-head">
              <span>
                <b>{sum.row_count}</b> valid rows
              </span>
              <span>
                <b>{sum.total_eur.toLocaleString('de-DE')}</b> € total
              </span>
              <span>
                Wochen: <b>{sum.iso_weeks.join(', ') || '—'}</b>
              </span>
              <span>
                Bundesländer: <b>{sum.bundesland_codes.length}</b>
              </span>
              <span>
                {sum.error_count > 0 ? (
                  <span className="mpu-warn">{sum.error_count} Fehler</span>
                ) : (
                  <span className="mpu-ok">keine Fehler</span>
                )}
              </span>
            </div>
            {sum.errors.length > 0 ? (
              <details className="mpu-errors">
                <summary>Fehler-Details ({sum.errors.length})</summary>
                <ul>
                  {sum.errors.slice(0, 10).map((e, i) => (
                    <li key={i}>
                      <b>Zeile {e.row}</b>: {e.reason}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
            <div className="mpu-actions">
              <button
                type="button"
                className="mpu-btn mpu-btn-ghost"
                onClick={reset}
                disabled={busy}
              >
                Andere Datei
              </button>
              <button
                type="button"
                className="mpu-btn mpu-btn-primary"
                onClick={handleCommit}
                disabled={busy || sum.row_count === 0}
              >
                {busy ? 'Lade hoch …' : `Commit · ${sum.row_count} Zeilen übernehmen`}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default MediaPlanUploadModal;
