# Regional Hierarchy Benchmark Matrix

- Generated at: `2026-03-24T08:12:47.235300`

| Virus | Horizon | Decision | Promote | WIS Raw | WIS Mint | Delta | CRPS Raw | CRPS Mint | Delta | Cov80 Delta | Cluster W | National W |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Influenza A | 3 | benchmark_passed | yes | 14.511760 | 13.940002 | -0.571758 | 5.804704 | 5.576001 | -0.228703 | -0.010101 | 1.000000 | 0.000000 |
| Influenza A | 5 | benchmark_rejected_inferior_wis_or_crps | no | 11.124204 | 11.159483 | +0.035279 | 4.449682 | 4.463793 | +0.014111 | -0.019685 | 0.000000 | 0.000000 |
| Influenza A | 7 | benchmark_passed | yes | 9.831707 | 9.783400 | -0.048307 | 3.932683 | 3.913360 | -0.019323 | -0.006873 | 1.000000 | 0.000000 |
| Influenza B | 3 | benchmark_passed | yes | 15.297627 | 15.038749 | -0.258878 | 6.119051 | 6.015500 | -0.103551 | -0.010101 | 0.000000 | 0.000000 |
| Influenza B | 5 | benchmark_rejected_inferior_wis_or_crps | no | 12.621837 | 12.622763 | +0.000926 | 5.048735 | 5.049105 | +0.000370 | -0.007874 | 1.000000 | 0.000000 |
| Influenza B | 7 | benchmark_passed | yes | 9.496424 | 9.434313 | -0.062111 | 3.798570 | 3.773725 | -0.024845 | -0.011455 | 1.000000 | 0.000000 |
| SARS-CoV-2 | 3 | benchmark_rejected_inferior_wis_or_crps | no | 15.763939 | 15.437510 | -0.326429 | 6.305576 | 6.175004 | -0.130572 | -0.047619 | 0.800000 | 1.000000 |
| SARS-CoV-2 | 5 | benchmark_rejected_inferior_wis_or_crps | no | 6.562352 | 6.564238 | +0.001886 | 2.624941 | 2.625695 | +0.000754 | -0.019048 | 1.000000 | 0.000000 |
| SARS-CoV-2 | 7 | benchmark_passed | yes | 6.369145 | 6.361255 | -0.007890 | 2.547658 | 2.544502 | -0.003156 | -0.014354 | 1.000000 | 0.000000 |
| RSV A | 5 | benchmark_rejected_inferior_wis_or_crps | no | 3.606577 | 3.608318 | +0.001741 | 1.442631 | 1.443327 | +0.000696 | +0.000000 | 0.000000 | 0.000000 |
| RSV A | 7 | benchmark_passed | yes | 1.111950 | 1.105432 | -0.006518 | 0.444780 | 0.442173 | -0.002607 | -0.003584 | 1.000000 | 0.000000 |

## Correction Note

- `Influenza A / h3` und `Influenza B / h3` sind keine Fehlerfaelle. Beide Scopes liefen auf dem produktiven Python-3.11-Stack sauber durch und bestanden den Hierarchie-Benchmark.
- `benchmark_passed` bedeutet hier nur: Die Hierarchie verbessert WIS und CRPS unter den Guardrails. Das ist noch keine operative Produktfreigabe.
- Beide `h3`-Scopes bleiben operativ auf `WATCH`, weil das strenge Quality Gate noch nicht bestanden ist.
- `RSV A / h3` bleibt weiterhin bewusst `unsupported` und ist kein Benchmark-Fehlerfall.
