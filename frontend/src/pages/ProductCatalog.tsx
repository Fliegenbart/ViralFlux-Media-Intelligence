import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  CatalogProduct,
  CatalogProductCreateInput,
  CatalogProductUpdateInput,
  ProductConditionMapping,
  ProductMatchCandidate,
} from '../types/media';

type IntelTab = 'bestand' | 'anlage' | 'mapping' | 'audit';

interface ManualConditionLinkInput {
  condition_key: string;
  is_approved: boolean;
  fit_score: number;
  priority: number;
  mapping_reason: string;
  notes: string;
}

const tabTitleMap: Record<IntelTab, string> = {
  bestand: '1) Bestand',
  anlage: '2) Produktanlage',
  mapping: '3) Mapping-Vorschau',
  audit: '4) Audit & Freigabe',
};

const audienceModeOptions = ['b2c', 'b2b', 'both'] as const;
const formatAudienceMode = (value: string) => {
  if (value === 'b2b') return 'B2B';
  if (value === 'both') return 'B2B + B2C';
  return 'B2C';
};

const splitList = (value: string): string[] =>
  value
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0);

const joinList = (value: string[]): string => (value || []).join(', ');

const mapLabel = (status?: string) => {
  if (!status) return 'Unbekannt';
  if (status === 'approved') return 'Freigegeben';
  if (status === 'needs_review') return 'Review';
  return status;
};

const mapStateClass = (status?: string) => {
  if (status === 'approved') return 'text-emerald-700 bg-emerald-50 border border-emerald-200';
  if (status === 'needs_review') return 'text-amber-700 bg-amber-50 border border-amber-200';
  return 'text-slate-600 bg-slate-100 border border-slate-200';
};

const defaultCatalogForm: CatalogProductCreateInput = {
  brand: 'gelo',
  product_name: '',
  source_url: '',
  source_hash: '',
  active: true,
  sku: '',
  target_segments: [],
  conditions: [],
  forms: [],
  age_min_months: null,
  age_max_months: null,
  audience_mode: 'both',
  channel_fit: [],
  compliance_notes: '',
};

const ProductCatalogPanel: React.FC = () => {
  const location = useLocation();
  const [activeTab, setActiveTab] = useState<IntelTab>('bestand');
  const [loading, setLoading] = useState(false);
  const [products, setProducts] = useState<CatalogProduct[]>([]);
  const [mappings, setMappings] = useState<ProductConditionMapping[]>([]);
  const [previewRows, setPreviewRows] = useState<ProductMatchCandidate[]>([]);
  const [showOnlyPending, setShowOnlyPending] = useState(true);
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null);
  const [manualConditionLink, setManualConditionLink] = useState<ManualConditionLinkInput>({
    condition_key: '',
    is_approved: false,
    fit_score: 0.75,
    priority: 600,
    mapping_reason: '',
    notes: '',
  });

  const [productForm, setProductForm] = useState<CatalogProductCreateInput>(defaultCatalogForm);
  const [editingProductId, setEditingProductId] = useState<number | null>(null);
  const [formListInputs, setFormListInputs] = useState({
    target_segments: '',
    conditions: '',
    forms: '',
    channel_fit: '',
  });
  const [savingProduct, setSavingProduct] = useState(false);
  const [brandFilter] = useState('gelo');
  const [statusNotice, setStatusNotice] = useState<string | null>(null);
  const [detailProductId, setDetailProductId] = useState<number | null>(null);

  const loadProducts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/media/products?brand=${encodeURIComponent(brandFilter)}`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setProducts(data.products || []);
    } catch (e) {
      console.error('Product list error', e);
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }, [brandFilter]);

  const loadMappings = useCallback(async () => {
    try {
      const qs = new URLSearchParams({
        brand: brandFilter,
        only_pending: showOnlyPending ? 'true' : 'false',
      });
      const res = await fetch(`/api/v1/media/product-mapping?${qs.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      setMappings(data.mappings || []);
    } catch (e) {
      console.error('Product mapping load error', e);
      setMappings([]);
    }
  }, [brandFilter, showOnlyPending]);

  const loadMatchPreview = useCallback(async () => {
    try {
      const qs = new URLSearchParams({
        brand: brandFilter,
        limit: '80',
      });
      const res = await fetch(`/api/v1/media/products/match-preview?${qs.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      setPreviewRows(data.items || []);
    } catch (e) {
      console.error('Match preview load error', e);
      setPreviewRows([]);
    }
  }, [brandFilter]);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadProducts(), loadMappings(), loadMatchPreview()]);
  }, [loadProducts, loadMappings, loadMatchPreview]);

  const selectedProduct = useMemo(
    () => products.find((item) => item.id === selectedProductId) || null,
    [products, selectedProductId],
  );

  const matchingMappings = useMemo(() => {
    if (!selectedProduct) return mappings;
    return mappings.filter((item) => item.product_id === selectedProduct.id);
  }, [mappings, selectedProduct]);

  const productTopMappings = useMemo(() => {
    return [...matchingMappings]
      .sort((a, b) => {
        if ((b.is_approved ? 1 : 0) !== (a.is_approved ? 1 : 0)) {
          return (b.is_approved ? 1 : 0) - (a.is_approved ? 1 : 0);
        }
        const scoreDelta = Number(b.fit_score || 0) - Number(a.fit_score || 0);
        if (scoreDelta !== 0) return scoreDelta;
        return (b.priority || 0) - (a.priority || 0);
      })
      .slice(0, 3);
  }, [matchingMappings]);

  const recommendationSamples = useMemo(() => {
    if (!selectedProduct) return [] as ProductMatchCandidate[];
    const key = selectedProduct.product_name.toLowerCase();
    const direct = previewRows.filter((row) => {
      const candidate = (row.candidate_product || '').toLowerCase();
      const recommended = (row.recommended_product || '').toLowerCase();
      return candidate === key || recommended === key;
    });
    return direct.slice(0, 3);
  }, [previewRows, selectedProduct]);

  const pendingMappings = useMemo(() => {
    return mappings
      .filter((row) => !row.is_approved)
      .sort((a, b) => Number(b.fit_score || 0) - Number(a.fit_score || 0));
  }, [mappings]);

  const auditRows = useMemo(() => {
    const rows = showOnlyPending ? [...pendingMappings] : [...mappings];
    return rows.sort((a, b) => {
      if (a.is_approved === b.is_approved) {
        return Number(b.fit_score || 0) - Number(a.fit_score || 0);
      }
      return a.is_approved ? 1 : -1;
    });
  }, [showOnlyPending, mappings, pendingMappings]);

  const runRefresh = useCallback(async () => {
    setStatusNotice(null);
    await refreshAll();
    setStatusNotice('Daten aktualisiert.');
  }, [refreshAll]);

  const startNew = useCallback(() => {
    setEditingProductId(null);
    setProductForm({ ...defaultCatalogForm });
    setFormListInputs({ target_segments: '', conditions: '', forms: '', channel_fit: '' });
    setStatusNotice(null);
  }, []);

  const editProduct = useCallback((item: CatalogProduct) => {
    setEditingProductId(item.id);
    setProductForm({
      brand: item.brand || brandFilter,
      product_name: item.product_name || '',
      source_url: item.source_url || '',
      source_hash: item.source_hash || '',
      active: item.active,
      sku: item.sku || '',
      target_segments: item.target_segments || [],
      conditions: item.conditions || [],
      forms: item.forms || [],
      age_min_months: item.age_min_months,
      age_max_months: item.age_max_months,
      audience_mode: (item.audience_mode === 'b2c' || item.audience_mode === 'b2b' || item.audience_mode === 'both') ? item.audience_mode : 'both',
      channel_fit: item.channel_fit || [],
      compliance_notes: item.compliance_notes || '',
    });
    setFormListInputs({
      target_segments: joinList(item.target_segments || []),
      conditions: joinList(item.conditions || []),
      forms: joinList(item.forms || []),
      channel_fit: joinList(item.channel_fit || []),
    });
    setActiveTab('anlage');
    setStatusNotice(null);
  }, [brandFilter]);

  const setFormValue = (key: keyof CatalogProductCreateInput, value: string | boolean | number | null | string[]) => {
    setProductForm((prev) => ({ ...prev, [key]: value }));
  };

  const setTextList = (key: keyof typeof formListInputs, value: string) => {
    setFormListInputs((prev) => ({ ...prev, [key]: value }));
    if (key === 'target_segments') setFormValue('target_segments', splitList(value));
    if (key === 'conditions') setFormValue('conditions', splitList(value));
    if (key === 'forms') setFormValue('forms', splitList(value));
    if (key === 'channel_fit') setFormValue('channel_fit', splitList(value));
  };

  const saveProduct = useCallback(async () => {
    if (!productForm.product_name.trim()) return;

    setSavingProduct(true);
    setStatusNotice(null);
    try {
      const payload: CatalogProductCreateInput | CatalogProductUpdateInput = {
        brand: productForm.brand,
        product_name: productForm.product_name.trim(),
        source_url: productForm.source_url?.trim() || undefined,
        source_hash: productForm.source_hash?.trim() || undefined,
        active: productForm.active,
        sku: productForm.sku?.trim() || null,
        target_segments: splitList(formListInputs.target_segments),
        conditions: splitList(formListInputs.conditions),
        forms: splitList(formListInputs.forms),
        age_min_months: productForm.age_min_months,
        age_max_months: productForm.age_max_months,
        audience_mode: productForm.audience_mode || 'both',
        channel_fit: splitList(formListInputs.channel_fit),
        compliance_notes: productForm.compliance_notes?.trim() || null,
      };

      if (editingProductId) {
        const res = await fetch(`/api/v1/media/products/${editingProductId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${res.status}`);
        }
        setStatusNotice('Produkt aktualisiert.');
      } else {
        const res = await fetch('/api/v1/media/products', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${res.status}`);
        }
        setStatusNotice('Produkt angelegt.');
      }

      setEditingProductId(null);
      setProductForm({ ...defaultCatalogForm });
      setFormListInputs({ target_segments: '', conditions: '', forms: '', channel_fit: '' });
      await refreshAll();
    } catch (e) {
      console.error('Save product error', e);
      setStatusNotice('Speichern fehlgeschlagen.');
    } finally {
      setSavingProduct(false);
    }
  }, [editingProductId, formListInputs, productForm, refreshAll]);

  const runProductMatch = useCallback(
    async (productId: number) => {
      try {
        const res = await fetch(`/api/v1/media/products/${productId}/match/run`, { method: 'POST' });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${res.status}`);
        }
        await refreshAll();
        setStatusNotice('Mapping-Neuberechnung abgeschlossen.');
      } catch (e) {
        console.error('Run match error', e);
        setStatusNotice('Mapping-Neuberechnung fehlgeschlagen.');
      }
    },
    [refreshAll],
  );

  const deleteProduct = useCallback(
    async (productId: number) => {
      if (!window.confirm('Dieses Produkt deaktivieren (Soft-Delete)?')) return;
      try {
        const res = await fetch(`/api/v1/media/products/${productId}`, { method: 'DELETE' });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${res.status}`);
        }
        await refreshAll();
        setStatusNotice('Produkt deaktiviert.');
      } catch (e) {
        console.error('Delete product error', e);
        setStatusNotice('Produkt konnte nicht deaktiviert werden.');
      }
    },
    [refreshAll],
  );

  const updateMappingApproval = useCallback(
    async (mappingId: number, isApproved: boolean) => {
      try {
        const res = await fetch(`/api/v1/media/product-mapping/${mappingId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            is_approved: isApproved,
            priority: isApproved ? 800 : 350,
          }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${res.status}`);
        }
        await loadMappings();
        setStatusNotice('Mapping-Status aktualisiert.');
      } catch (e) {
        console.error('Update mapping error', e);
        setStatusNotice('Mapping-Status nicht aktualisiert.');
      }
    },
    [loadMappings],
  );

  const quickProbeForProduct = useCallback((product: CatalogProduct) => {
    setSelectedProductId(product.id);
    setActiveTab('mapping');
    setDetailProductId(product.id);
  }, []);

  const updateManualConditionLink = useCallback(
    (field: keyof ManualConditionLinkInput, value: string | boolean | number) => {
      setManualConditionLink((prev) => ({ ...prev, [field]: value }));
    },
    [],
  );

  const saveManualConditionLink = useCallback(async () => {
    if (!selectedProduct || !manualConditionLink.condition_key.trim()) return;

    try {
      const payload = {
        condition_key: manualConditionLink.condition_key.trim(),
        is_approved: manualConditionLink.is_approved,
        fit_score: manualConditionLink.fit_score,
        priority: manualConditionLink.priority,
        mapping_reason: manualConditionLink.mapping_reason.trim() || undefined,
        notes: manualConditionLink.notes.trim() || undefined,
      };
      const res = await fetch(`/api/v1/media/products/${selectedProduct.id}/condition-links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      await refreshAll();
      setManualConditionLink((prev) => ({
        ...prev,
        condition_key: '',
        mapping_reason: '',
        notes: '',
      }));
      setStatusNotice('Manuelle Lageverknüpfung gespeichert.');
    } catch (e) {
      console.error('Save manual mapping error', e);
      setStatusNotice('Manuelle Lageverknüpfung fehlgeschlagen.');
    }
  }, [selectedProduct, manualConditionLink, refreshAll]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    void loadMappings();
  }, [loadMappings]);

  useEffect(() => {
    if (statusNotice) {
      const timeout = window.setTimeout(() => setStatusNotice(null), 4000);
      return () => window.clearTimeout(timeout);
    }
  }, [statusNotice]);

  useEffect(() => {
    const params = new URLSearchParams(location.search || '');
    const focus = (params.get('focus') || '').trim().toLowerCase();
    if (focus === 'audit') {
      setActiveTab((prev) => (prev === 'audit' ? prev : 'audit'));
    }

    const productParam = (params.get('product') || '').trim();
    if (!productParam) return;

    const asId = Number(productParam);
    if (Number.isFinite(asId) && asId > 0) {
      setSelectedProductId((prev) => (prev === asId ? prev : asId));
      return;
    }

    const needle = productParam.toLowerCase();
    const hit = products.find((p) => String(p.product_name || '').toLowerCase() === needle);
    if (hit) {
      setSelectedProductId((prev) => (prev === hit.id ? prev : hit.id));
    }
  }, [location.search, products]);

  return (
    <div className="space-y-6">
      <div className="card p-6 bg-gradient-to-br from-violet-50 via-pink-50/30 to-white border-violet-200/30">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
          <div>
            <h2 className="text-2xl font-black text-slate-900 tracking-tight">Produkt-Intelligence</h2>
            <p className="text-sm text-slate-500 mt-2">Neuer produktbasierter Entscheidungsstrom für Gelo: manuelle Anlage, KI-Match-Status, Review-Flow.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setActiveTab('bestand')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold ${activeTab === 'bestand' ? 'bg-violet-500 text-white border border-violet-500' : 'bg-slate-100 text-slate-600 border border-slate-200'}`}
            >
              {tabTitleMap.bestand}
            </button>
            <button
              onClick={() => setActiveTab('anlage')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold ${activeTab === 'anlage' ? 'bg-violet-500 text-white border border-violet-500' : 'bg-slate-100 text-slate-600 border border-slate-200'}`}
            >
              {tabTitleMap.anlage}
            </button>
            <button
              onClick={() => setActiveTab('mapping')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold ${activeTab === 'mapping' ? 'bg-violet-500 text-white border border-violet-500' : 'bg-slate-100 text-slate-600 border border-slate-200'}`}
            >
              {tabTitleMap.mapping}
            </button>
            <button
              onClick={() => setActiveTab('audit')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold ${activeTab === 'audit' ? 'bg-violet-500 text-white border border-violet-500' : 'bg-slate-100 text-slate-600 border border-slate-200'}`}
            >
              {tabTitleMap.audit}
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
          <button onClick={runRefresh} className="media-button" disabled={loading}>
            {loading ? 'Lade...' : 'Neu laden'}
          </button>
          <button onClick={startNew} className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 text-slate-600 hover:bg-slate-50">
            Neues Produkt
          </button>
          <label className="ml-auto flex items-center gap-2 text-slate-600">
            <input
              type="checkbox"
              checked={showOnlyPending}
              onChange={(event) => setShowOnlyPending(event.target.checked)}
            />
            nur Review offen
          </label>
        </div>
        {statusNotice && <div className="mt-3 text-xs text-emerald-600">{statusNotice}</div>}
      </div>

      {activeTab === 'bestand' && (
        <div className="card p-5">
          <h3 className="text-lg font-semibold text-slate-900 mb-3">Bestand</h3>
          <p className="text-xs text-slate-500 mb-3">Leitfaden zuerst: Produkt anlegen → Mapping prüfen → Freigabe.</p>
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-slate-500 border-b border-slate-200">
                <tr>
                  <th className="py-2 pr-4">Produkt</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Zielgruppen</th>
                  <th className="py-2 pr-4">Indikationen</th>
                  <th className="py-2 pr-4">Review</th>
                  <th className="py-2 text-right">Aktionen</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product) => (
                  <React.Fragment key={product.id}>
                    <tr className="border-b border-slate-100">
                      <td className="py-2 pr-4">
                        <div className="text-slate-700">{product.product_name}</div>
                        <div className="text-slate-400">SKU: {product.sku || '-'}</div>
                      </td>
                      <td className="py-2 pr-4">
                        <span className="text-slate-700">{product.active ? 'Aktiv' : 'Inaktiv'}</span>
                      </td>
                      <td className="py-2 pr-4">
                        <span className="text-slate-600">{product.target_segments.join(', ') || '-'}</span>
                      </td>
                      <td className="py-2 pr-4 text-slate-700">{product.conditions.join(', ') || '-'}</td>
                      <td className="py-2 pr-4">
                        <span className={`px-2 py-1 rounded-full ${mapStateClass(product.review_state)}`}>
                          {mapLabel(product.review_state)}
                        </span>
                      </td>
                      <td className="py-2 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => quickProbeForProduct(product)}
                            className="px-2 py-1 rounded border border-slate-200 text-slate-600 hover:bg-slate-50"
                          >
                            Mapping prüfen
                          </button>
                          <button
                            onClick={() => setDetailProductId((value) => (value === product.id ? null : product.id))}
                            className="px-2 py-1 rounded border border-slate-200 text-slate-600 hover:bg-slate-50"
                          >
                            {detailProductId === product.id ? 'Details schließen' : 'Details'}
                          </button>
                        </div>
                      </td>
                    </tr>
                    {detailProductId === product.id && (
                      <tr className="border-b border-slate-100 bg-slate-50">
                        <td colSpan={6} className="py-3 pr-4">
                          <div className="flex flex-wrap gap-2">
                            <span className="soft-panel px-2 py-1 rounded">Formen: {product.forms.join(', ') || '-'}</span>
                            <span className="soft-panel px-2 py-1 rounded">Alter: {product.age_min_months || 0}-{product.age_max_months || '∞'} Monate</span>
                            <span className="soft-panel px-2 py-1 rounded">Kanäle: {product.channel_fit.join(', ') || '-'}</span>
                            <span className="soft-panel px-2 py-1 rounded">Mode: {formatAudienceMode(product.audience_mode || 'both')}</span>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            <button onClick={() => runProductMatch(product.id)} className="px-2 py-1 rounded border border-slate-200 text-slate-600 hover:bg-slate-50">
                              Match jetzt
                            </button>
                            <button onClick={() => editProduct(product)} className="px-2 py-1 rounded border border-slate-200 text-slate-600 hover:bg-slate-50">
                              Bearbeiten
                            </button>
                            <button onClick={() => deleteProduct(product.id)} className="px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50">
                              Deaktivieren
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
                {products.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-4 text-center text-slate-400">
                      Noch kein Produkt im Katalog.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'anlage' && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div className="card p-5">
            <h3 className="text-lg font-semibold text-slate-900 mb-3">
              {editingProductId ? 'Produkt bearbeiten' : 'Neues Produkt anlegen'}
            </h3>
            <div className="grid grid-cols-1 gap-3">
              <div className="text-xs text-slate-600">
                <span className="text-rose-500">*</span> Produktname
              </div>
              <input value={productForm.product_name} onChange={(e) => setFormValue('product_name', e.target.value)} className="media-input" placeholder="Produktname" />
              <div className="text-[11px] text-slate-400">Interner Name für den Produktsatz.</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input value={productForm.sku || ''} onChange={(e) => setFormValue('sku', e.target.value)} className="media-input" placeholder="SKU" />
                <input value={productForm.source_url || ''} onChange={(e) => setFormValue('source_url', e.target.value)} className="media-input" placeholder="Source URL (optional, z.B. manuell://...)" />
              </div>
              <div className="text-xs text-slate-600">
                <span className="text-rose-500">*</span> Zielgruppen (Komma-getrennt)
              </div>
              <input value={formListInputs.target_segments} onChange={(e) => setTextList('target_segments', e.target.value)} className="media-input" placeholder="Zielgruppen (Komma-getrennt)" />
              <div className="text-[11px] text-slate-400">z. B. erwachsene, kinder, apothekenberatung</div>
              <div className="text-xs text-slate-600">
                <span className="text-rose-500">*</span> Indikationslage (Komma-getrennt)
              </div>
              <input value={formListInputs.conditions} onChange={(e) => setTextList('conditions', e.target.value)} className="media-input" placeholder="Indikationslage (Komma-getrennt)" />
              <div className="text-[11px] text-slate-400">z. B. bronchitis_husten, rhinitis, erkaltung_akut</div>
              <div className="text-xs text-slate-600">
                <span className="text-rose-500">*</span> Produktform
              </div>
              <input value={formListInputs.forms} onChange={(e) => setTextList('forms', e.target.value)} className="media-input" placeholder="Produktform (spray, sirup, ...)" />
              <div className="text-[11px] text-slate-400">z. B. spray, sirup, troche</div>
              <div className="grid grid-cols-2 gap-3">
                <input
                  value={productForm.age_min_months ?? ''}
                  onChange={(e) => setFormValue('age_min_months', e.target.value ? Number(e.target.value) : null)}
                  type="number"
                  min={0}
                  className="media-input"
                  placeholder="Alter min (Monate)"
                />
                <input
                  value={productForm.age_max_months ?? ''}
                  onChange={(e) => setFormValue('age_max_months', e.target.value ? Number(e.target.value) : null)}
                  type="number"
                  min={0}
                  className="media-input"
                  placeholder="Alter max (Monate)"
                />
              </div>
              <select
                value={productForm.audience_mode || 'both'}
                onChange={(e) => setFormValue('audience_mode', e.target.value)}
                className="media-input"
              >
                {audienceModeOptions.map((option) => (
                  <option key={option} value={option}>
                    {formatAudienceMode(option)}
                  </option>
                ))}
              </select>
              <input value={formListInputs.channel_fit} onChange={(e) => setTextList('channel_fit', e.target.value)} className="media-input" placeholder="Kanäle (Komma-getrennt, z.B. search,programmatic)" />
              <input
                value={productForm.compliance_notes || ''}
                onChange={(e) => setFormValue('compliance_notes', e.target.value)}
                className="media-input"
                placeholder="Compliance-Hinweise / Ausschlüsse"
              />
              <label className="flex items-center gap-2 text-xs text-slate-600">
                <input
                  type="checkbox"
                  checked={productForm.active}
                  onChange={(e) => setFormValue('active', e.target.checked)}
                />
                Produkt aktiv
              </label>
              <button onClick={saveProduct} disabled={savingProduct} className="media-button w-fit">
                {savingProduct ? 'Speichere...' : editingProductId ? 'Produkt aktualisieren' : 'Produkt anlegen'}
              </button>
            </div>
          </div>

          <div className="card p-5">
            <h3 className="text-lg font-semibold text-slate-900 mb-3">Empfehlungsprobe</h3>
            {selectedProduct ? (
              <div className="space-y-3">
                <p className="text-xs text-slate-500">Top {Math.min(recommendationSamples.length, 3)} Regionen/Opportunities für „{selectedProduct.product_name}"</p>
                {recommendationSamples.length === 0 && (
                  <p className="text-xs text-slate-400">Noch keine Probe-Daten für dieses Produkt.</p>
                )}
                {recommendationSamples.map((sample) => (
                  <div key={sample.opportunity_id} className="rounded-lg p-3 border border-slate-200 bg-slate-50">
                    <div className="text-sm text-slate-700">{sample.opportunity_type} · {sample.status}</div>
                    <div className="text-xs text-slate-500 mt-1">
                      Trigger: {sample.trigger_event || '-'}
                    </div>
                    <div className="text-xs text-slate-600 mt-2">
                      Mapping: {mapLabel(sample.mapping_status)} ({Math.round((sample.mapping_confidence || 0) * 100)}%)
                    </div>
                    <div className="text-xs text-slate-400 mt-1">
                      Lage: {sample.condition_key || '-'} · {sample.condition_label || '-'}
                    </div>
                  </div>
                ))}
                <p className="text-xs text-slate-400">
                  <strong>Hinweis:</strong> Bei Bedarf diese Vorschläge im Audit-Tab freigeben, dann geht die Freigabe in den Ausspielungsfluss.
                </p>
              </div>
            ) : (
              <p className="text-xs text-slate-400">Bitte ein Produkt auswählen (z. B. über „Mapping prüfen").</p>
            )}
          </div>
        </div>
      )}

      {activeTab === 'mapping' && (
        <div className="card p-5">
          <h3 className="text-lg font-semibold text-slate-900 mb-3">Mapping-Vorschau</h3>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="overflow-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-200">
                    <th className="py-2 text-left pr-4">Produkt</th>
                    <th className="py-2 text-left pr-4">Lageklasse</th>
                    <th className="py-2 text-left pr-4">Score</th>
                    <th className="py-2 text-left pr-4">Quelle</th>
                    <th className="py-2 text-left pr-4">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {productTopMappings.map((row) => (
                    <tr key={`${row.mapping_id}-${row.condition_key}`} className="border-b border-slate-100">
                      <td className="py-2 pr-4 text-slate-700">{row.product_name}</td>
                      <td className="py-2 pr-4 text-slate-700">{row.condition_label}</td>
                      <td className="py-2 pr-4 text-slate-700">{row.fit_score.toFixed(2)}</td>
                      <td className="py-2 pr-4 text-slate-500">{row.rule_source}</td>
                      <td className="py-2">
                        <span className={`px-2 py-1 rounded-full ${mapStateClass(row.is_approved ? 'approved' : 'needs_review')}`}>
                          {row.is_approved ? 'approved' : 'needs_review'}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {productTopMappings.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-4 text-slate-400 text-center">
                        Für dieses Produkt sind keine Top-Mappings vorhanden.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="space-y-3 text-xs">
              <h4 className="font-semibold text-slate-700">Quick-Review Aktionen</h4>
              <div className="rounded-lg p-3 border border-slate-200 text-slate-600">
                <p>Produkt manuell nachjustieren und den KI-Review erneut anstoßen:</p>
                {selectedProduct ? (
                  <div className="mt-2 flex items-center gap-2 flex-wrap">
                    <button onClick={() => runProductMatch(selectedProduct.id)} className="media-button w-auto">
                      Mapping neu berechnen
                    </button>
                    <button onClick={() => editProduct(selectedProduct)} className="px-3 py-1.5 text-xs border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50">
                      Produkt bearbeiten
                    </button>
                  </div>
                ) : (
                  <div>Bitte zuerst ein Produkt per Mapping prüfen auswählen.</div>
                )}
              </div>
              <div className="rounded-lg p-3 border border-slate-200">
                <p className="text-slate-600 mb-2">Copy-Vorschläge (für UI)</p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <button className="px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50">Consumer Copy</button>
                  <button className="px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50">Apotheken-Mail</button>
                  <button className="px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50">Ärzte-Ansprache</button>
                </div>
                <p className="text-slate-400 mt-2">Diese Module werden via Qwen/AI-Prozess nur nach Freigabe in den Kampagnenfluss gegeben.</p>
              </div>

              {selectedProduct && (
                <div className="rounded-lg p-3 border border-slate-200">
                  <h4 className="font-semibold text-slate-700 mb-2">Manuelle Lage-Verknüpfung</h4>
                  <div className="grid grid-cols-1 gap-2">
                    <input
                      value={manualConditionLink.condition_key}
                      onChange={(event) => updateManualConditionLink('condition_key', event.target.value)}
                      className="media-input"
                      placeholder="Lageklasse (z.B. bronchitis_husten)"
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step={0.01}
                        value={manualConditionLink.fit_score}
                        onChange={(event) => updateManualConditionLink('fit_score', Number(event.target.value))}
                        className="media-input"
                        placeholder="Fit-Score (0-1)"
                      />
                      <input
                        type="number"
                        min={0}
                        max={999}
                        value={manualConditionLink.priority}
                        onChange={(event) => updateManualConditionLink('priority', Number(event.target.value))}
                        className="media-input"
                        placeholder="Priorität"
                      />
                    </div>
                    <input
                      value={manualConditionLink.mapping_reason}
                      onChange={(event) => updateManualConditionLink('mapping_reason', event.target.value)}
                      className="media-input"
                      placeholder="Begründung"
                    />
                    <input
                      value={manualConditionLink.notes}
                      onChange={(event) => updateManualConditionLink('notes', event.target.value)}
                      className="media-input"
                      placeholder="Notiz (optional)"
                    />
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={manualConditionLink.is_approved}
                        onChange={(event) => updateManualConditionLink('is_approved', event.target.checked)}
                      />
                      <span className="text-slate-600">Als freigegeben speichern</span>
                    </label>
                    <button
                      onClick={saveManualConditionLink}
                      className="px-3 py-1.5 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 w-fit"
                    >
                      Manuelle Verknüpfung speichern
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'audit' && (
        <div className="card p-5">
          <h3 className="text-lg font-semibold text-slate-900 mb-3">Audit & Freigabe</h3>
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="py-2 pr-4">Produkt</th>
                  <th className="py-2 pr-4">Lageklasse</th>
                  <th className="py-2 pr-4">Score</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Regelherkunft</th>
                  <th className="py-2 pr-4">Notiz</th>
                  <th className="py-2 text-right">Aktion</th>
                </tr>
              </thead>
              <tbody>
                {auditRows.map((row) => (
                  <tr key={row.mapping_id} className="border-b border-slate-100 align-top">
                    <td className="py-2 pr-4">
                      <div className="text-slate-700">{row.product_name}</div>
                      <div className="text-slate-400">ID {row.product_id}</div>
                    </td>
                    <td className="py-2 pr-4 text-slate-700">{row.condition_key}</td>
                    <td className="py-2 pr-4 text-slate-700">{row.fit_score.toFixed(2)}</td>
                    <td className="py-2 pr-4">
                      <span className={`px-2 py-1 rounded-full ${mapStateClass(row.is_approved ? 'approved' : 'needs_review')}`}>
                        {row.is_approved ? 'approved' : 'needs_review'}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-slate-500">{row.rule_source || 'auto'}</td>
                    <td className="py-2 pr-4 text-slate-400 max-w-[220px]">
                      {row.notes || '-'}
                    </td>
                    <td className="py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => updateMappingApproval(row.mapping_id, true)}
                          className="px-2 py-1 rounded border border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                        >
                          Freigeben
                        </button>
                        <button
                          onClick={() => updateMappingApproval(row.mapping_id, false)}
                          className="px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50"
                        >
                          Blockieren
                        </button>
                        <button onClick={() => setSelectedProductId(row.product_id)} className="px-2 py-1 rounded border border-slate-200 text-slate-600 hover:bg-slate-50">
                          Mapping prüfen
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {auditRows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-4 text-center text-slate-400">
                      Keine Mapping-Einträge für diesen Filter vorhanden.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProductCatalogPanel;
