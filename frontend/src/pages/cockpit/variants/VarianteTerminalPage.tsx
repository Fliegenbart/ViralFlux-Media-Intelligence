import React, { useState } from 'react';
import '../../../styles/peix-gate.css';
import CockpitGate from '../CockpitGate';
import { useCockpitSnapshot } from '../useCockpitSnapshot';
import { VarianteTerminal } from './VarianteTerminal';

const DEFAULT_VIRUS = 'Influenza A';
const SUPPORTED_VIRUSES = ['Influenza A', 'Influenza B', 'RSV A'] as const;

export const VarianteTerminalPage: React.FC = () => {
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
        background: '#0a0e13',
        color: '#4fd1c5',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 12,
        letterSpacing: '0.14em',
      }}>
        ◆ LOADING COCKPIT SNAPSHOT …
      </div>
    );
  }

  if (error && !snapshot) {
    return (
      <div style={{
        padding: 32,
        background: '#0a0e13',
        color: '#e57373',
        fontFamily: "'JetBrains Mono', monospace",
        minHeight: '100vh',
      }}>
        <div style={{ fontSize: 12, letterSpacing: '0.14em' }}>ERROR · COCKPIT UNAVAILABLE</div>
        <pre style={{ marginTop: 12, color: '#e8efe6' }}>{error.message}</pre>
        <button
          onClick={reload}
          style={{
            marginTop: 16,
            background: 'transparent',
            border: '1px solid #4fd1c5',
            color: '#4fd1c5',
            padding: '6px 14px',
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >RETRY</button>
      </div>
    );
  }

  if (!snapshot) return null;

  return (
    <VarianteTerminal
      snapshot={snapshot}
      virusTyp={virusTyp}
      onVirusChange={setVirusTyp}
      supportedViruses={SUPPORTED_VIRUSES}
    />
  );
};

export default VarianteTerminalPage;
