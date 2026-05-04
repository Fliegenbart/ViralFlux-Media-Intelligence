# Phase-Lead Graph Renewal Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research-only backend module for a vintage-aware multi-source phase-lead graph renewal filter.

**Architecture:** Add `backend/app/services/research/phase_lead/` as a sibling of the existing `tri_layer` research package. The core model optimizes latent log-incidence `x`, derives `q` and `c` from `x`, fits raw delayed-convolution source likelihoods, and keeps phase-lead inversion diagnostic-only to avoid double-counting evidence.

**Tech Stack:** Python 3, NumPy, pandas, SciPy optimization/special functions, Pydantic v2, pytest.

---

### Task 1: Schemas and Vintage Filtering

**Files:**
- Create: `backend/app/services/research/phase_lead/data_schema.py`
- Test: `backend/app/tests/test_phase_lead_data_schema.py`

- [ ] Write tests for observation validation, negative-count rejection, and revision-aware `filter_vintage`.
- [ ] Implement `ObservationRow`, `ObservationKey`, and `filter_vintage`.
- [ ] Run `pytest backend/app/tests/test_phase_lead_data_schema.py -q`.

### Task 2: Kernels and Likelihoods

**Files:**
- Create: `backend/app/services/research/phase_lead/kernels.py`
- Create: `backend/app/services/research/phase_lead/likelihoods.py`
- Test: `backend/app/tests/test_phase_lead_kernels.py`
- Test: `backend/app/tests/test_phase_lead_likelihoods.py`

- [ ] Write tests for kernel normalization, `K(q,c)`, derivative identities, negative-binomial, Student-t, and Dirichlet-multinomial likelihoods.
- [ ] Implement fixed and shifted negative-binomial kernels with stable log-sum-exp transforms.
- [ ] Implement likelihood functions with clipping and clear validation errors.
- [ ] Run both test files.

### Task 3: Mapping, Graph, and Delayed Convolution

**Files:**
- Create: `backend/app/services/research/phase_lead/mappings.py`
- Create: `backend/app/services/research/phase_lead/graph.py`
- Create: `backend/app/services/research/phase_lead/convolution.py`
- Test: `backend/app/tests/test_phase_lead_mappings_graph.py`
- Test: `backend/app/tests/test_phase_lead_convolution.py`

- [ ] Write tests for matrix dimensions, row normalization, source-to-target graph normalization, finite `Pi`/`Omega`, and delayed convolution with earliest-value padding.
- [ ] Implement `SourceMapping`, `RegionalGraph`, and `compute_mu`.
- [ ] Run mapping, graph, and convolution tests.

### Task 4: Phase Diagnostics

**Files:**
- Create: `backend/app/services/research/phase_lead/phase_diagnostics.py`
- Test: `backend/app/tests/test_phase_lead_diagnostics.py`

- [ ] Write tests where separated early/late kernels recover known `q`, and identical kernels emit weak-identifiability warnings.
- [ ] Implement profiled `x`, weighted projection, covariance approximation, and identifiability metrics.
- [ ] Run diagnostic tests.

### Task 5: Joint Model and Forecasting

**Files:**
- Create: `backend/app/services/research/phase_lead/config.py`
- Create: `backend/app/services/research/phase_lead/baseline.py`
- Create: `backend/app/services/research/phase_lead/renewal.py`
- Create: `backend/app/services/research/phase_lead/joint_model.py`
- Create: `backend/app/services/research/phase_lead/forecast.py`
- Create: `backend/app/services/research/phase_lead/api.py`
- Test: `backend/app/tests/test_phase_lead_joint_model_synthetic.py`

- [ ] Write a synthetic end-to-end test with 3 regions, one pathogen, early wastewater kernel, late case kernel, and a directed graph.
- [ ] Implement `PhaseLeadGraphRenewalFilter.fit`, objective components, SciPy MAP optimization, deterministic forecast sampling, and `p_up`, `p_surge`, `p_front`, EEB, GEGB outputs.
- [ ] Include an explicit code comment that no phase pseudo-observation penalty is present in Option B.
- [ ] Run the synthetic integration test.

### Task 6: Documentation and Verification

**Files:**
- Create: `docs/methodology/phase_lead_graph_renewal_filter.md`

- [ ] Document the model, delayed-convolution likelihood, vintage rule, diagnostic-only phase inversion, and synthetic test command.
- [ ] Run the targeted phase-lead test suite.
- [ ] Run a full backend import smoke for the new package.
