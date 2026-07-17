# Consumer Slice 2 Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retain an audited May 2015 methane/ethane VLE source contract, then validate immutable installed regression and equilibrium candidates against real observations without owning production algorithms.

**Architecture:** Validation first freezes source rows and tolerances before model execution. Later black-box campaigns import only public installed package surfaces, emit hash-bound tables/receipts, and render plots from retained tables without recomputing models.

**Tech Stack:** Python 3.13 standard library, installed `epcsaft`, `epcsaft-equilibrium`, and `epcsaft-regression` wheels, Matplotlib only in plot commands.

## Global Constraints

- Read `AGENTS.md`, `CONTEXT.md`, organization doctrine, and the canonical Slice 2 design before editing.
- Own no production equation, derivative, solver, private import, or source-checkout dependency.
- Acquire numerical source rows only from the ACS article record or official NIST ThermoML archive for DOI `10.1021/acs.jced.5b00610`.
- Freeze source rows, units, uncertainty fields, transformations, and acceptance tolerances before executing the model.
- Retain compact audited data, not a broad paper archive.
- Every campaign binds exact wheel hashes and verifies installed import origins.
- Plot scripts read retained source/model CSV only and never import a production package.
- Failure to obtain the actual source table stops equilibrium physical admission; do not substitute lab workbook or generated values.

---

### Task 1: Audit and retain the May 2015 methane/ethane source table

**Files:**
- Create: `data/may-2015-methane-ethane-vle.csv`
- Create: `data/may-2015-methane-ethane-vle.yaml`
- Create: `campaigns/check_may_2015_source.py`
- Create: `tests/test_may_2015_source.py`

**Interfaces:**
- Consumes: official ACS/NIST record for DOI `10.1021/acs.jced.5b00610`.
- Produces: immutable `(row_id,T_K,P_Pa,x_methane,y_methane,uncertainty...)` rows and a no-model tolerance contract.

- [ ] **Step 1: Obtain the official numerical record**

Search the NIST ThermoML archive by exact DOI. Download the exact ThermoML/JSON record or publisher supplement, record its URL, retrieval date, SHA-256, article citation, table identity, and use basis. Visually compare the retained methane/ethane table headings and at least two numerical rows with the article/supplement. Stop if the numerical table cannot be obtained or identified unambiguously.

- [ ] **Step 2: Write the failing source-contract test**

Require exact columns, unique ordered row IDs, positive finite `T_K` and `P_Pa`, `0 < x_methane,y_methane < 1`, normalized binary complements, nonnegative reported uncertainties, one DOI, and exact retained-file hashes. Require at least one isotherm with three or more coexistence rows; do not encode a row count until the official table is inspected.

- [ ] **Step 3: Run the source test and verify RED**

Run: `python -m pytest tests/test_may_2015_source.py -q`

Expected: failure because the audited files do not exist.

- [ ] **Step 4: Retain the compact table and provenance**

Write one CSV row per methane/ethane coexistence measurement. Preserve source decimal precision. Convert pressure to Pa only when the YAML records the exact source unit and conversion. The YAML must name every retained source field, omitted field, transformation, uncertainty meaning, and source hash.

- [ ] **Step 5: Freeze tolerances without model output**

The checker must derive row-level comparison allowances from the reported expanded/standard uncertainties exactly as defined by the source. If a model-accuracy floor wider than experimental uncertainty is required, state its engineering purpose and numerical value in YAML before any package wheel is supplied. The checker hashes this tolerance block.

- [ ] **Step 6: Run and commit the source contract**

Run: `python -m pytest tests/test_may_2015_source.py -q`

Expected: pass without importing any ePC-SAFT package.

```bash
git add data/may-2015-methane-ethane-vle.csv data/may-2015-methane-ethane-vle.yaml campaigns/check_may_2015_source.py tests/test_may_2015_source.py
git commit -m "data: retain May methane ethane VLE source"
```

### Task 2: Add the installed-artifact pure-saturation regression campaign

**Files:**
- Create: `campaigns/pure_saturation_regression.py`
- Create: `campaigns/plot_pure_saturation_regression.py`
- Create: `tests/test_pure_saturation_regression.py`
- Create: `results/.gitkeep` only if the directory is absent

**Interfaces:**
- Consumes: exact provider and regression wheels plus public `fit_pure_saturation` and loader APIs.
- Produces: component-specific receipts, prediction CSVs, and plots for methane and ethane.

- [ ] **Step 1: Write failing artifact and result tests**

Require three CLI arguments: `--provider-wheel`, `--regression-wheel`, and `--output-dir`. Reject non-wheel paths, source-checkout imports, wheel/install hash mismatches, missing components, changed source partitions, nonfinite predictions, and a receipt lacking separate solver/numerical/physical statuses.

- [ ] **Step 2: Run the campaign test and verify RED**

Run: `python -m pytest tests/test_pure_saturation_regression.py -q`

Expected: failure because the campaign is absent.

- [ ] **Step 3: Implement the public-only campaign**

For methane and ethane, load the public dataset/specification, fit through the public workflow, and retain one CSV row per observation containing source value, start-model prediction, fitted-model prediction, training/held-out/stress role, relative errors, solver status, parameter fingerprint, and wheel hashes. Keep Ceres acceptance separate from prediction metrics.

- [ ] **Step 4: Implement plot-only rendering**

Render pressure and liquid-density observation/start/fitted series from CSV. The plot script may import Matplotlib and CSV/JSON libraries only. It must not import `epcsaft` or `epcsaft_regression`.

- [ ] **Step 5: Run isolated campaigns**

Install exact wheels in an isolated environment, run the campaign, then run the plot command. Expected: both component fits are reproducible; all retained rows appear in tables and plots; no stress endpoint determines pass/fail.

- [ ] **Step 6: Commit campaign code; retain result artifacts only after review**

```bash
git add campaigns/pure_saturation_regression.py campaigns/plot_pure_saturation_regression.py tests/test_pure_saturation_regression.py
git commit -m "test: validate pure saturation regression artifacts"
```

Do not commit generated result files until the independent review identifies the exact accepted artifact set.

### Task 3: Add the installed-artifact two-phase flash campaign

**Files:**
- Create: `campaigns/may_2015_methane_ethane_flash.py`
- Create: `campaigns/plot_may_2015_methane_ethane_flash.py`
- Create: `tests/test_may_2015_methane_ethane_flash.py`

**Interfaces:**
- Consumes: audited May data, exact provider/equilibrium wheels, and public `two_phase_flash`.
- Produces: source/model comparison rows and a hash-bound local-two-phase validation receipt.

- [ ] **Step 1: Write failing black-box tests**

Require `--provider-wheel`, `--equilibrium-wheel`, `--source`, and `--output-dir`. For every selected coexistence row, construct the overall feed with recorded phase fraction `beta=0.5`:

```python
z_methane = 0.5 * x_methane + 0.5 * y_methane
z_ethane = 1.0 - z_methane
```

Require the returned material balance to reproduce that feed and compare pressure-fixed phase compositions with the pre-model tolerance contract. Reject missing rows, changed source hashes, globality claims, source imports, and a result that reports a collapsed phase as accepted.

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest tests/test_may_2015_methane_ethane_flash.py -q`

Expected: failure because the campaign is absent or the equilibrium wheel is not supplied.

- [ ] **Step 3: Implement public-only execution and receipts**

Import only `epcsaft` and `epcsaft_equilibrium` public names. Bind wheel members to installed files before import. Retain source and model phase compositions, pressure, phase fractions, balance/KKT diagnostics, solver/numerical/local-physical status, parameter fingerprint, source/tolerance hashes, and explicit `globality_certificate=false`.

- [ ] **Step 4: Implement plot-only rendering**

Plot source and model `x-y` or pressure-composition rows from the retained CSV only. Include source uncertainty bars where the audited fields support them. The renderer imports no production package.

- [ ] **Step 5: Run the isolated campaign**

Run against exact installed wheels. Expected: all selected rows remain within the frozen comparison contract and every local solver/KKT gate passes. Any failing row leaves physical admission failed; do not remove rows or loosen tolerances after seeing output.

- [ ] **Step 6: Commit campaign code and stop for review**

```bash
git add campaigns/may_2015_methane_ethane_flash.py campaigns/plot_may_2015_methane_ethane_flash.py tests/test_may_2015_methane_ethane_flash.py
git commit -m "test: validate methane ethane two phase flash"
```

### Task 4: Reconcile validation scope and accepted artifacts

**Files:**
- Modify: `AGENTS.md`
- Modify: `CONTEXT.md`
- Modify: `README.md`
- Add reviewed result CSV/JSON/PNG/SVG/PDF files under `results/`

**Interfaces:**
- Consumes: independently reviewed campaign artifacts.
- Produces: exact validation candidates for migration receipts.

- [ ] **Step 1: Update scope without claiming runtime authority**

Add the pure-saturation regression and methane/ethane local-flash campaigns with exact package commits, wheel hashes, source hashes, tolerance hashes, domains, and limitations. Keep validation non-authoritative for runtime.

- [ ] **Step 2: Verify retained plots and tables**

Check every plotted series against its retained CSV, verify source/model row counts and hashes, and render each new plot for visual inspection. Record any failed physical comparison instead of hiding it.

- [ ] **Step 3: Run all validation tests and cleanup**

Run `python -m pytest -q`, campaign-specific isolated commands, `git diff --check`, exact tracked-file review, and the cleanup hook.

- [ ] **Step 4: Commit and stop for independent review**

```bash
git add AGENTS.md CONTEXT.md README.md results
git commit -m "docs: record consumer slice 2 validation candidates"
```

Report exact source, code, wheel, result, and plot hashes. Do not push, promote, or broaden the capability.
