import React from 'react';

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          role="alert"
          style={{
            padding: 32,
            textAlign: 'center',
            color: 'var(--text-primary, #1e293b)',
          }}
        >
          <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>
            Ein Fehler ist aufgetreten
          </h2>
          <p
            style={{
              fontSize: 14,
              color: 'var(--text-muted, #64748b)',
              marginBottom: 16,
            }}
          >
            {this.state.error?.message || 'Unbekannter Fehler'}
          </p>
          <button
            onClick={this.handleReset}
            style={{
              padding: '8px 16px',
              borderRadius: 6,
              border: '1px solid var(--border-color, #e2e8f0)',
              background: 'var(--bg-secondary, #fff)',
              cursor: 'pointer',
              fontSize: 14,
              color: 'var(--text-primary, #1e293b)',
            }}
          >
            Erneut versuchen
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
