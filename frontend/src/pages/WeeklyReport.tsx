import React, { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';
import { UI_COPY } from '../lib/copy';

interface BriefMeta {
  id: number;
  calendar_week: number;
  year: number;
  created_at: string;
  summary?: string;
}

const WeeklyReport: React.FC = () => {
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [briefs, setBriefs] = useState<BriefMeta[]>([]);
  const [status, setStatus] = useState<string | null>(null);

  const loadBriefs = async () => {
    try {
      const res = await apiFetch('/api/v1/media/weekly-brief/list');
      if (res.ok) {
        const data = await res.json();
        setBriefs(Array.isArray(data) ? data : data.briefs || []);
      }
    } catch { /* ignore */ }
  };

  useEffect(() => { loadBriefs(); }, []);

  const handleGenerate = async () => {
    setGenerating(true);
    setStatus(null);
    try {
      const res = await apiFetch('/api/v1/media/weekly-brief/generate', { method: 'POST' });
      if (res.ok) {
        setStatus('Bericht erstellt');
        loadBriefs();
      } else {
        setStatus('Fehler bei der Erstellung');
      }
    } catch {
      setStatus('Verbindungsfehler');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async (week?: number) => {
    setDownloading(true);
    try {
      const url = week
        ? `/api/v1/media/weekly-brief/${week}`
        : '/api/v1/media/weekly-brief/latest';
      const res = await apiFetch(url);
      if (res.ok) {
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `ViralFlux_Wochenbericht${week ? `_KW${week}` : ''}.pdf`;
        a.click();
        URL.revokeObjectURL(a.href);
      }
    } catch { /* ignore */ }
    finally { setDownloading(false); }
  };

  const now = new Date();
  const kw = Math.ceil(((now.getTime() - new Date(now.getFullYear(), 0, 1).getTime()) / 86400000 + new Date(now.getFullYear(), 0, 1).getDay() + 1) / 7);

  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
        {UI_COPY.weeklyReport}
      </h1>
      <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 32 }}>
        ViralFlux Wochenbericht — KW {kw} / {now.getFullYear()}
      </p>

      {/* Action Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 32 }}>
        <button
          onClick={handleGenerate}
          disabled={generating}
          style={{
            padding: '24px 20px', borderRadius: 12,
            border: '1px solid var(--border-color)', background: 'var(--bg-card)',
            cursor: generating ? 'wait' : 'pointer', textAlign: 'left',
            transition: 'border-color 0.2s',
          }}
        >
          <div style={{ fontSize: 24, marginBottom: 8 }}>{generating ? '...' : '+'}</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
            {generating ? 'Wird erstellt...' : 'Neuen Bericht erstellen'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Erstellt den Wochenbericht fuer die aktuelle Kalenderwoche
          </div>
        </button>

        <button
          onClick={() => handleDownload()}
          disabled={downloading}
          style={{
            padding: '24px 20px', borderRadius: 12,
            border: '1px solid var(--accent-violet)', background: 'var(--accent-violet)',
            cursor: downloading ? 'wait' : 'pointer', textAlign: 'left',
            color: '#fff',
          }}
        >
          <div style={{ fontSize: 24, marginBottom: 8 }}>{downloading ? '...' : '\u2193'}</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
            {downloading ? 'Download...' : 'Aktuellen Bericht herunterladen'}
          </div>
          <div style={{ fontSize: 12, opacity: 0.8 }}>
            PDF-Wochenbericht fuer GELO
          </div>
        </button>
      </div>

      {status && (
        <div style={{
          padding: '10px 16px', borderRadius: 8, marginBottom: 24,
          background: status.includes('Fehler') ? 'rgba(220,38,38,0.1)' : 'rgba(5,150,105,0.1)',
          color: status.includes('Fehler') ? '#dc2626' : '#059669',
          fontSize: 13, fontWeight: 500,
        }}>
          {status}
        </div>
      )}

      {/* Brief content summary */}
      <div style={{
        padding: 24, borderRadius: 12,
        border: '1px solid var(--border-color)', background: 'var(--bg-card)',
        marginBottom: 24,
      }}>
        <div style={{
          fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
          textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16,
        }}>
          Inhalt des Berichts
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {[
            { title: 'Zusammenfassung', desc: 'Signalscore, nationale Risikobewertung und Handlungsempfehlung' },
            { title: 'Regionale Schwerpunkte', desc: 'Top-5 Bundeslaender mit hoechster Aktivitaet und Trend' },
            { title: 'Signalqualitaet', desc: 'Aktuelle Backtest-Metriken, Trefferquote und Vorlaufzeit' },
            { title: 'Budgetempfehlungen', desc: 'Konkrete Budget-Shifts pro Region und Kanalmix' },
            { title: 'Produktpriorisierung', desc: 'GELO-Produkte mit passender Indikation und Kampagnenvorschlag' },
          ].map((item) => (
            <div key={item.title} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <div style={{
                width: 6, height: 6, borderRadius: '50%', marginTop: 6, flexShrink: 0,
                background: 'var(--accent-violet)',
              }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{item.title}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* History */}
      {briefs.length > 0 && (
        <div>
          <div style={{
            fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
            textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12,
          }}>
            Bisherige Berichte
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {briefs.slice(0, 10).map((b) => (
              <div
                key={b.id}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 16px', borderRadius: 8,
                  border: '1px solid var(--border-color)', background: 'var(--bg-card)',
                  fontSize: 13,
                }}
              >
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                  KW {b.calendar_week} / {b.year}
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  {new Date(b.created_at).toLocaleDateString('de-DE')}
                </span>
                <button
                  onClick={() => handleDownload(b.calendar_week)}
                  style={{
                    all: 'unset', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                    color: 'var(--accent-violet)',
                  }}
                >
                  PDF
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default WeeklyReport;
