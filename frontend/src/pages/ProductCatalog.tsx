import React, { useCallback, useEffect, useState } from 'react';
import { useToast } from '../App';
import { apiFetch } from '../lib/api';
import {
  CatalogProduct,
  ProductConditionMapping,
} from '../types/media';

/* ── helpers ─────────────────────────────────────────────────────── */

const splitList = (v: string): string[] =>
  v.split(',').map((s) => s.trim()).filter(Boolean);

/* ── styles (CSS-var based, inline) ──────────────────────────────── */

const s = {
  page: {
    maxWidth: 960,
    margin: '0 auto',
    padding: '32px 16px',
    fontFamily: "'Inter', system-ui, sans-serif",
    color: 'var(--text-primary)',
  } as React.CSSProperties,

  topBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    flexWrap: 'wrap' as const,
    marginBottom: 28,
  } as React.CSSProperties,

  title: {
    fontSize: 22,
    fontWeight: 700,
    letterSpacing: '-0.02em',
    color: 'var(--text-primary)',
  } as React.CSSProperties,

  badge: (bg: string, fg: string) => ({
    display: 'inline-block',
    fontSize: 11,
    fontWeight: 600,
    padding: '3px 10px',
    borderRadius: 999,
    background: bg,
    color: fg,
    marginLeft: 10,
  }) as React.CSSProperties,

  btn: {
    fontSize: 13,
    fontWeight: 600,
    padding: '7px 16px',
    borderRadius: 8,
    border: 'none',
    cursor: 'pointer',
    background: 'var(--accent-violet)',
    color: '#fff',
  } as React.CSSProperties,

  btnSmall: (variant: 'default' | 'approve' | 'reject' | 'danger' = 'default') => {
    const base: React.CSSProperties = {
      fontSize: 12,
      fontWeight: 500,
      padding: '4px 10px',
      borderRadius: 6,
      border: '1px solid var(--border-color)',
      cursor: 'pointer',
      background: 'transparent',
      color: 'var(--text-secondary)',
      lineHeight: 1.4,
    };
    if (variant === 'approve') return { ...base, borderColor: 'var(--accent-emerald)', color: 'var(--accent-emerald)' };
    if (variant === 'reject') return { ...base, borderColor: 'var(--accent-red)', color: 'var(--accent-red)' };
    if (variant === 'danger') return { ...base, borderColor: 'var(--accent-red)', color: 'var(--accent-red)' };
    return base;
  },

  card: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border-color)',
    borderRadius: 12,
    padding: 20,
    marginBottom: 24,
  } as React.CSSProperties,

  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 13 } as React.CSSProperties,
  th: {
    textAlign: 'left' as const,
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
    padding: '8px 10px',
    borderBottom: '1px solid var(--border-color)',
  } as React.CSSProperties,
  td: { padding: '10px 10px', borderBottom: '1px solid var(--border-color)', verticalAlign: 'middle' as const } as React.CSSProperties,
  muted: { color: 'var(--text-muted)', fontSize: 12 } as React.CSSProperties,

  overlay: {
    position: 'fixed' as const,
    inset: 0,
    background: 'rgba(0,0,0,0.45)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 900,
  } as React.CSSProperties,

  modal: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border-color)',
    borderRadius: 14,
    padding: 28,
    width: '100%',
    maxWidth: 440,
    boxShadow: '0 12px 40px rgba(0,0,0,0.18)',
  } as React.CSSProperties,

  input: {
    width: '100%',
    padding: '8px 12px',
    fontSize: 13,
    borderRadius: 8,
    border: '1px solid var(--border-color)',
    background: 'var(--bg-secondary)',
    color: 'var(--text-primary)',
    outline: 'none',
    boxSizing: 'border-box' as const,
    marginBottom: 12,
  } as React.CSSProperties,

  statusBadge: (active: boolean) => ({
    display: 'inline-block',
    fontSize: 11,
    fontWeight: 600,
    padding: '2px 10px',
    borderRadius: 999,
    background: active ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.12)',
    color: active ? 'var(--accent-emerald)' : 'var(--accent-amber)',
  }) as React.CSSProperties,

  progressBar: {
    height: 4,
    borderRadius: 2,
    background: 'var(--border-color)',
    marginTop: 4,
    overflow: 'hidden' as const,
    width: 56,
  } as React.CSSProperties,

  progressFill: (pct: number) => ({
    height: '100%',
    width: `${pct}%`,
    borderRadius: 2,
    background: pct === 100 ? 'var(--accent-emerald)' : 'var(--accent-amber)',
    transition: 'width 0.3s ease',
  }) as React.CSSProperties,

  sectionTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: 'var(--text-primary)',
    marginBottom: 14,
  } as React.CSSProperties,

  pendingRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '8px 0',
    borderBottom: '1px solid var(--border-color)',
    fontSize: 13,
    flexWrap: 'wrap' as const,
  } as React.CSSProperties,
};

/* ── component ───────────────────────────────────────────────────── */

const ProductCatalogPanel: React.FC = () => {
  const { toast } = useToast();
  const [products, setProducts] = useState<CatalogProduct[]>([]);
  const [allMappings, setAllMappings] = useState<ProductConditionMapping[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [formName, setFormName] = useState('');
  const [formSku, setFormSku] = useState('');
  const [formConditions, setFormConditions] = useState('');
  const [saving, setSaving] = useState(false);

  /* ── data fetching ──────────────────────────────────────────────── */

  const loadProducts = useCallback(async () => {
    try {
      const res = await apiFetch('/api/v1/media/products?brand=gelo');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setProducts(data.products || []);
    } catch (e) {
      console.error('Products load error', e);
      setProducts([]);
    }
  }, []);

  const loadMappings = useCallback(async () => {
    try {
      const res = await apiFetch('/api/v1/media/product-mapping?brand=gelo&only_pending=false');
      if (!res.ok) return;
      const data = await res.json();
      setAllMappings(data.mappings || []);
    } catch (e) {
      console.error('Mappings load error', e);
      setAllMappings([]);
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadProducts(), loadMappings()]);
    setLoading(false);
  }, [loadProducts, loadMappings]);

  useEffect(() => { void refresh(); }, [refresh]);

  /* ── derived data ───────────────────────────────────────────────── */

  const pendingMappings = allMappings.filter((m) => !m.is_approved);

  const mappingsForProduct = (pid: number) => allMappings.filter((m) => m.product_id === pid);

  const approvedCount = (pid: number) => mappingsForProduct(pid).filter((m) => m.is_approved).length;
  const totalCount = (pid: number) => mappingsForProduct(pid).length;

  const allApproved = (pid: number) => {
    const maps = mappingsForProduct(pid);
    return maps.length > 0 && maps.every((m) => m.is_approved);
  };

  /* ── mutations ──────────────────────────────────────────────────── */

  const openCreate = () => {
    setEditId(null);
    setFormName('');
    setFormSku('');
    setFormConditions('');
    setModalOpen(true);
  };

  const openEdit = (p: CatalogProduct) => {
    setEditId(p.id);
    setFormName(p.product_name);
    setFormSku(p.sku || '');
    setFormConditions((p.conditions || []).join(', '));
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditId(null);
  };

  const saveProduct = async () => {
    if (!formName.trim()) return;
    setSaving(true);
    try {
      if (editId) {
        const res = await apiFetch(`/api/v1/media/products/${editId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            product_name: formName.trim(),
            sku: formSku.trim() || null,
            conditions: splitList(formConditions),
          }),
        });
        if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `HTTP ${res.status}`); }
        toast('Produkt aktualisiert.');
      } else {
        const res = await apiFetch('/api/v1/media/products', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            brand: 'gelo',
            product_name: formName.trim(),
            sku: formSku.trim() || null,
            conditions: splitList(formConditions),
            active: true,
            target_segments: [],
            forms: [],
            audience_mode: 'both',
            channel_fit: [],
          }),
        });
        if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `HTTP ${res.status}`); }
        toast('Produkt angelegt.');
      }
      closeModal();
      await refresh();
    } catch (e) {
      console.error('Save product error', e);
      toast('Speichern fehlgeschlagen.');
    } finally {
      setSaving(false);
    }
  };

  const deactivateProduct = async (id: number) => {
    if (!window.confirm('Dieses Produkt deaktivieren?')) return;
    try {
      const res = await apiFetch(`/api/v1/media/products/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      toast('Produkt deaktiviert.');
      await refresh();
    } catch (e) {
      console.error('Delete error', e);
      toast('Deaktivierung fehlgeschlagen.');
    }
  };

  const approveMappingsForProduct = async (pid: number) => {
    const pending = mappingsForProduct(pid).filter((m) => !m.is_approved);
    try {
      await Promise.all(
        pending.map((m) =>
          apiFetch(`/api/v1/media/product-mapping/${m.mapping_id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_approved: true, priority: 800 }),
          }),
        ),
      );
      toast(`${pending.length} Mapping(s) freigegeben.`);
      await loadMappings();
    } catch (e) {
      console.error('Batch approve error', e);
      toast('Freigabe fehlgeschlagen.');
    }
  };

  const updateMapping = async (mappingId: number, approved: boolean) => {
    try {
      const res = await apiFetch(`/api/v1/media/product-mapping/${mappingId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_approved: approved, priority: approved ? 800 : 350 }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      toast(approved ? 'Mapping freigegeben.' : 'Mapping abgelehnt.');
      await loadMappings();
    } catch (e) {
      console.error('Mapping update error', e);
      toast('Mapping-Update fehlgeschlagen.');
    }
  };

  /* ── render ─────────────────────────────────────────────────────── */

  return (
    <div style={s.page}>
      {/* ── Top bar ──────────────────────────────────────────────── */}
      <div style={s.topBar}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <span style={s.title}>Produkte &amp; Mappings</span>
          {pendingMappings.length > 0 && (
            <span style={s.badge('rgba(245,158,11,0.14)', 'var(--accent-amber)')}>
              {pendingMappings.length} Mapping{pendingMappings.length !== 1 ? 's' : ''} zu pr&uuml;fen
            </span>
          )}
        </div>
        <button style={s.btn} onClick={openCreate}>Neues Produkt</button>
      </div>

      {/* ── Products table ───────────────────────────────────────── */}
      <div style={s.card}>
        {loading && <div style={{ ...s.muted, marginBottom: 10 }}>Lade...</div>}
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>Produkt</th>
              <th style={s.th}>SKU</th>
              <th style={s.th}>Indikationen</th>
              <th style={s.th}>Mappings</th>
              <th style={s.th}>Status</th>
              <th style={{ ...s.th, textAlign: 'right' }}>Aktionen</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => {
              const approved = approvedCount(p.id);
              const total = totalCount(p.id);
              const pct = total > 0 ? Math.round((approved / total) * 100) : 0;
              const hasPending = total > approved;
              const isActive = allApproved(p.id);

              return (
                <tr key={p.id}>
                  <td style={s.td}>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{p.product_name}</span>
                  </td>
                  <td style={{ ...s.td, ...s.muted }}>{p.sku || '--'}</td>
                  <td style={{ ...s.td, fontSize: 12, color: 'var(--text-secondary)', maxWidth: 220 }}>
                    {(p.conditions || []).join(', ') || '--'}
                  </td>
                  <td style={s.td}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {approved}/{total}
                    </span>
                    {total > 0 && (
                      <div style={s.progressBar}>
                        <div style={s.progressFill(pct)} />
                      </div>
                    )}
                  </td>
                  <td style={s.td}>
                    <span style={s.statusBadge(isActive)}>
                      {isActive ? 'Aktiv' : 'Pr\u00fcfen'}
                    </span>
                  </td>
                  <td style={{ ...s.td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                      {hasPending && (
                        <button
                          style={s.btnSmall('approve')}
                          title="Alle offenen Mappings freigeben"
                          onClick={() => approveMappingsForProduct(p.id)}
                        >
                          &#10003;
                        </button>
                      )}
                      <button style={s.btnSmall()} title="Bearbeiten" onClick={() => openEdit(p)}>
                        &#9998;
                      </button>
                      <button style={s.btnSmall('danger')} title="Deaktivieren" onClick={() => deactivateProduct(p.id)}>
                        &#128465;
                      </button>
                    </span>
                  </td>
                </tr>
              );
            })}
            {products.length === 0 && !loading && (
              <tr>
                <td colSpan={6} style={{ ...s.td, textAlign: 'center', ...s.muted, padding: '28px 10px' }}>
                  Noch keine Produkte im Katalog.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Pending mappings section ─────────────────────────────── */}
      {pendingMappings.length > 0 && (
        <div style={{ ...s.card, background: 'rgba(245,158,11,0.05)', borderColor: 'var(--accent-amber)' }}>
          <div style={s.sectionTitle}>Offene Mappings zur Freigabe</div>
          {pendingMappings.map((m) => (
            <div key={m.mapping_id} style={s.pendingRow}>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)', minWidth: 130 }}>{m.product_name}</span>
              <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>&rarr;</span>
              <span style={{ color: 'var(--text-secondary)' }}>{m.condition_label || m.condition_key}</span>
              <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>
                Score {(m.fit_score * 100).toFixed(0)}%
              </span>
              <button style={s.btnSmall('approve')} onClick={() => updateMapping(m.mapping_id, true)} title="Freigeben">
                &#10003;
              </button>
              <button style={s.btnSmall('reject')} onClick={() => updateMapping(m.mapping_id, false)} title="Ablehnen">
                &#10007;
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── Modal: create / edit product ─────────────────────────── */}
      {modalOpen && (
        <div style={s.overlay} onClick={(e) => { if (e.target === e.currentTarget) closeModal(); }}>
          <div style={s.modal}>
            <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 20, color: 'var(--text-primary)' }}>
              {editId ? 'Produkt bearbeiten' : 'Neues Produkt'}
            </div>

            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
              Produktname
            </label>
            <input
              style={s.input}
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="z.B. GeloMyrtol forte"
              autoFocus
            />

            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
              SKU
            </label>
            <input
              style={s.input}
              value={formSku}
              onChange={(e) => setFormSku(e.target.value)}
              placeholder="z.B. GELO-MYR-100"
            />

            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
              Indikationen (kommagetrennt)
            </label>
            <input
              style={s.input}
              value={formConditions}
              onChange={(e) => setFormConditions(e.target.value)}
              placeholder="z.B. bronchitis_husten, sinusitis, erkaltung_akut"
            />

            <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
              <button style={s.btn} onClick={saveProduct} disabled={saving}>
                {saving ? 'Speichere...' : 'Speichern'}
              </button>
              <button style={{ ...s.btn, background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border-color)' }} onClick={closeModal}>
                Abbrechen
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export { ProductCatalogPanel };
export default ProductCatalogPanel;
