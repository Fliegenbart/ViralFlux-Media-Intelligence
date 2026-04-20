import React, { useState } from 'react';
import '../../../styles/peix-gate.css';
import CockpitGate from '../CockpitGate';
import { useCockpitSnapshot } from '../useCockpitSnapshot';
import { VarianteExecutive } from './VarianteExecutive';

const DEFAULT_VIRUS = 'Influenza A';
const SUPPORTED_VIRUSES = ['Influenza A', 'Influenza B', 'RSV A'] as const;

export const VarianteExecutivePage: React.FC = () => {
  const [virusTyp, setVirusTyp] = useState<string>(DEFAULT_VIRUS);
  const { snapshot, loading, error, reload } = useCockpitSnapshot({
    virusTyp,
    horizonDays: 14,
    leadTarget: 'ATEMWEGSINDEX',
  });

  const isAuth401 =
    error &&
    (((error as Error & { status?: number }).status === 401) ||
      /HTTP 401/.test(error.message));

  if (isAuth401 && !snapshot) {
    return <CockpitGate />;
  }

  if (loading && !snapshot) {
    return (
      <div style={{
        minHeight: '100vh',
        background: '#fbf8f3',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: "'Instrument Serif', serif",
        fontStyle: 'italic',
        fontSize: 24,
        color: '#8b6f2a',
      }}>
        Cockpit lädt …
      </div>
    );
  }

  if (error && !snapshot) {
    return (
      <div style={{ padding: 64, fontFamily: 'Inter, sans-serif' }}>
        <h2>Cockpit nicht verfügbar</h2>
        <p style={{ color: '#666' }}>{error.message}</p>
        <button onClick={reload} style={{ marginTop: 12 }}>Erneut versuchen</button>
      </div>
    );
  }

  if (!snapshot) return null;

  return (
    <VarianteExecutive
      snapshot={snapshot}
      virusTyp={virusTyp}
      onVirusChange={setVirusTyp}
      supportedViruses={SUPPORTED_VIRUSES}
    />
  );
};

export default VarianteExecutivePage;
