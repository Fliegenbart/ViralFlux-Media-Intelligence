# Phase-Lead Graph Renewal Filter

This document describes the research-only FluxEngine module in
`backend/app/services/research/phase_lead/`.

## Purpose

The module fits a short-horizon regional epidemic field model for Germany.
It predicts latent infection incidence for each region, pathogen, issue date,
and forecast horizon. The first MVP supports one-pathogen runs with
AMELAG-like wastewater, SurvStat-like counts, optional additional count
streams, a static regional graph, and 3-14 day renewal forecasts.

## Core State

The optimized state is log-incidence:

```text
x[i, v, t] = log(n[i, v, t] + epsilon)
```

The implementation optimizes `x`. Growth and acceleration are deterministic
finite differences:

```text
q = Delta x
c = Delta^2 x
```

They are not separate free states in the MVP. This keeps trajectories
internally consistent.

## Delayed-Convolution Observation Model

Each source has its own observation kernel over infection age. For source
`m`, observation unit `o`, pathogen `v`, and day `t`, the mean is:

```text
mu[m,o,v,t] =
  alpha[m,o,v,t] *
  sum_i H[m][o,i] *
  sum_a k[m,v](a) * n[i,v,t-a]
```

The code path is:

- `data_schema.py`: typed observation rows and vintage filtering
- `mappings.py`: source-to-region matrix `H`
- `kernels.py`: infection-age kernels and phase transforms
- `convolution.py`: delayed-convolution `mu`
- `likelihoods.py`: negative-binomial, Student-t, and Dirichlet-multinomial helpers
- `joint_model.py`: MAP objective and renewal forecast

## Option B: No Double Counting

The phase-lead diagnostic estimates `q` and `c` from source phase geometry,
but these values are not added as extra observations in the Option B
posterior. The full delayed-convolution likelihood already contains the same
information. Adding both would double-count evidence.

In code, `joint_model.py` deliberately excludes any `phase` term from
`objective_components`. The phase diagnostic is used only for:

- initialization support,
- diagnostics,
- identifiability checks,
- proposal values,
- warnings,
- model introspection.

## Phase Transform

For a kernel `k(a)`, the diagnostic transform is:

```text
K(q,c) = sum_a k(a) exp(-a q + a(a-1)c/2)
```

The implementation uses log-sum-exp for stability and exposes tilted moments:

```text
d log K / d q = -E[a]
d log K / d c = 0.5 E[a(a-1)]
```

## Vintage Requirement

Historical validation must use only observations available on the issue date:

```text
publication_date <= issue_date
revision_date <= issue_date, when revision_date exists
```

`filter_vintage` selects the latest available revision per observation key.
Future revised data are intentionally excluded.

## Forecast Outputs

The forecast returns seeded posterior predictive samples and summaries:

- `p_up`: probability that log-incidence rises beyond a threshold
- `p_surge`: probability that log-incidence exceeds baseline plus margin
- `p_front`: probability of future acceleration above baseline
- `EEB`: expected excess burden over the configured horizons
- `GEGB`: growth-weighted expected burden
- `region_rankings`: per-pathogen ranking by GEGB

The MVP uses a MAP fit plus seed-controlled negative-binomial renewal
simulation. It is deterministic when the same seed is provided.

## Run Tests

Targeted test suite:

```bash
pytest \
  backend/app/tests/test_phase_lead_data_schema.py \
  backend/app/tests/test_phase_lead_kernels.py \
  backend/app/tests/test_phase_lead_likelihoods.py \
  backend/app/tests/test_phase_lead_mappings_graph.py \
  backend/app/tests/test_phase_lead_convolution.py \
  backend/app/tests/test_phase_lead_diagnostics.py \
  backend/app/tests/test_phase_lead_joint_model_synthetic.py \
  -q
```

The synthetic integration test builds three regions, one pathogen, an early
wastewater kernel, a late case kernel, and a directed graph. It verifies that
the objective improves from initialization, fitted `x` tracks the known latent
trajectory, phase diagnostics are present, no phase pseudo-penalty exists, and
forecast outputs have the expected structure.
