# Analytics recipes: clean → price → baseline → exact bridge → idle/leak → savings → explain re-runs

For "why did X change, what is controllable, what should we do" problems (energy bills, costs, KPIs).
Order of attribution is the scoring rule: **remove price, volume, mix and weather effects before calling
anything waste**, and the parts must add up exactly. Copy the `# file:` blocks; adapt column names.

Contents: 1 Cleaning · 2 Tariff pricing · 3 Daily frame + baseline · 4 Exact bridge (Bennet + Shapley)
· 5 Ranges · 6 Idle load and leaks · 7 Savings, CO2e, payback · 8 Explaining a re-run · 9 Tests · 10 Q&A lines

## 1. Cleaning interval data (duplicates, negatives, resets, gaps, reconciliation)

**`app/analytics/clean.py`** — interval cleaning, reconciliation, asset breakdown (47 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/analytics/clean.py`. Read it only when you need to edit it.

## 2. Tariff pricing with a mid-period change (and time-of-use)

`valid_to` is exclusive. If rows overlap only because they carry different `period` labels (peak /
off-peak), pass the hour windows from the data card as `tou_windows` and the join is done per period.

**`app/analytics/tariff.py`** — tariff validation and mid-period pricing (merge_asof) (40 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/analytics/tariff.py`. Read it only when you need to edit it.

## 3. Daily frame + regression baseline

Expected energy = intercept·days + β_nonprod·non-production days + Σ β_p·units_p + β_c·CDD + β_h·HDD.
Per-product coefficients are what separate **mix** from **volume**: a shift toward an energy-heavy product
raises kWh per unit without any waste. Fit on the reference period only (it defines "normal").

**`app/analytics/baseline.py`** — daily frame, calendar anomalies, OLS baseline with r2/CV(RMSE) (54 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/analytics/baseline.py`. Read it only when you need to edit it.

Report `r2` and `cv_rmse` (ASHRAE Guideline 14 uses CV(RMSE) ≤ 15% for monthly / ≤ 30% hourly as a
calibration bar — quote it only as context). If per-product coefficients come out negative or unstable,
say so in limitations and fall back to pooled intensity (units total) with mix reported as "not separable".

## 4. Exact bridge: Bennet price/quantity split + Shapley over quantity factors

1. **Tariff vs quantity** (symmetric, exact): with average prices P̄ = cost/kWh per period,
   `tariff = (P̄_B − P̄_A)·(E_A + E_B)/2` and `quantity = (E_B − E_A)·(P̄_A + P̄_B)/2`; they sum to C_B − C_A.
2. **Quantity → volume, mix, weather, waste** via Shapley values over the baseline model with
   `waste = actual − expected` (zero by construction in the reference period). Shapley is order-independent
   and sums exactly to E_B − E_A, so the whole bridge adds up to the bill change to machine precision.
3. Displayed numbers use largest-remainder rounding so the rounded parts still sum to the rounded total.

The tariff term includes any shift of consumption into peak hours (load timing); state that in limitations
or, when TOU windows are known, report "load timing" separately by repricing period B at A's price per period.

**`app/analytics/bridge.py`** — Bennet price/quantity split + Shapley factors = exactly additive bridge, with bootstrap ranges (93 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/analytics/bridge.py`. Read it only when you need to edit it.

## 5. Ranges honesty rules

- Every saving, CO2e and payback figure is `[low, high]`; bridge components carry bootstrap ranges.
- The point estimate always lies inside its displayed range (`to_contract` enforces it).
- Assumption inputs (recoverable share, capex, price range, emission factor) live in one table with a
  `source` column (`data pack`, `statement`, `assumption`) and are echoed in the response `assumptions`.

## 6. Idle load and leak signatures

Shift hours are **local**; meter timestamps are UTC. Convert with the site time zone from the data card
before classifying hours.

**`app/analytics/anomaly.py`** — idle load and leak signature detection (28 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/analytics/anomaly.py`. Read it only when you need to edit it.

Only claim waste when the bridge's waste component is positive **and** an asset-level signature explains
it (`leak_check` flag, idle share up). Otherwise report "unexplained residual" and no machine blame —
false waste claims are scored down.

## 7. Savings, CO2e, payback (ranges throughout)

**`app/analytics/savings.py`** — savings/CO2e/payback as ranges (19 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/analytics/savings.py`. Read it only when you need to edit it.

## 8. Explaining a re-run (late data drop, corrected tariff, calibration fix)

**`app/analytics/rerun.py`** — diff_bridges for explaining a re-run (14 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/analytics/rerun.py`. Read it only when you need to edit it.

Protocol: snapshot the canonical requests' responses (`eval/reports/before_v<N>.json`), ingest the new
files (data version N+1), re-run, call `diff_bridges`, write `docs/CHANGES_v<N+1>.md`, add an eval case.

## 9. Tests (synthetic data with known truth)

**`tests/test_analytics.py`** — import numpy as np (87 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/tests/test_analytics.py`. Read it only when you need to edit it.

## 10. Q&A lines

- "The bridge is exact: a symmetric price/quantity split plus Shapley values over the baseline model, so
  the causes sum to the bill change to machine precision, independent of the order we remove them in."
- "Waste is what's left after tariff, volume, mix and weather — and we only call it a leak when an asset
  signature (compressor load at night and weekends) explains it."
- "Ranges come from a weekly block bootstrap of the baseline period; savings ranges propagate recoverable
  share, price and capex ranges. Every assumption is listed in the response."
