import React, { useEffect, useId, useRef } from 'react';

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'danger';
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const ConfirmDialog: React.FC<Props> = ({
  open,
  title,
  message,
  confirmLabel = 'Bestätigen',
  cancelLabel = 'Abbrechen',
  variant = 'default',
  loading = false,
  onConfirm,
  onCancel,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const lastFocusedRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const messageId = useId();

  // Focus trap + Escape key
  useEffect(() => {
    if (!open) return;

    lastFocusedRef.current = document.activeElement as HTMLElement | null;
    confirmRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
      }
      // Simple focus trap between cancel and confirm
      if (e.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled])');
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      lastFocusedRef.current?.focus();
    };
  }, [open, onCancel]);

  if (!open) return null;

  const confirmBg = variant === 'danger' ? '#dc2626' : '#2563eb';

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.4)',
        backdropFilter: 'blur(2px)',
      }}
      onClick={onCancel}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role={variant === 'danger' ? 'alertdialog' : 'dialog'}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={messageId}
        aria-busy={loading}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--bg-secondary, #fff)',
          border: '1px solid var(--border-color, #e2e8f0)',
          borderRadius: 12,
          padding: 24,
          maxWidth: 400,
          width: '90%',
          boxShadow: '0 8px 32px rgba(0,0,0,0.12)',
        }}
      >
        <h3
          id={titleId}
          style={{
            fontSize: 16,
            fontWeight: 600,
            marginBottom: 8,
            color: 'var(--text-primary)',
          }}
        >
          {title}
        </h3>
        <p
          id={messageId}
          style={{
            fontSize: 14,
            color: 'var(--text-secondary)',
            marginBottom: 20,
            lineHeight: 1.5,
          }}
        >
          {message}
        </p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            style={{
              padding: '8px 16px',
              borderRadius: 6,
              border: '1px solid var(--border-color)',
              background: 'transparent',
              fontSize: 13,
              cursor: 'pointer',
              color: 'var(--text-primary)',
            }}
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            disabled={loading}
            style={{
              padding: '8px 16px',
              borderRadius: 6,
              border: 'none',
              background: loading ? '#94a3b8' : confirmBg,
              color: '#fff',
              fontSize: 13,
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? 'Bitte warten...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;
