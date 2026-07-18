# Neutral HELD v1 Validation Plan

Status: prepared; implementation not started

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans`, `chemical-engineer`, `scientific-testing`, and
> `matplotlib-plotting`. Validation owns no production solver or EOS.

**Goal:** Validate an immutable installed `neutral-held-v1` candidate through
public artifacts, an independent binary Gibbs-surface audit, and retained real
May methane/ethane coexistence evidence without converting finite search into
a global proof.

**Architecture:** Freeze derived one- and two-phase cases before HELD output.
Execute only installed provider/equilibrium wheels. Use the provider's public
pressure-state route to sample the model Gibbs surface independently of HELD's
explicit-volume native path. Retain machine-readable rows first; render plots
from retained rows only.

**Tech stack:** Python 3.13 standard library, exact installed provider and
equilibrium wheels, and Matplotlib only in plot commands.

## Global constraints

- Read `AGENTS.md`, `CONTEXT.md`, organization doctrine, the migration Slice 3
  design, and the equilibrium HELD design before editing.
- Do not import package-private names, call sibling source, compile provider or
  equilibrium source, copy ePC-SAFT equations, or expose a runtime oracle.
- Bind every run to exact wheel hashes and verify installed RECORD/import
  origins before model execution.
- Preserve the frozen May source rows and `3*u_c` comparison contract. Do not
  change a source row, tolerance, or failed model/data classification after
  HELD output is known.
- Treat the Gibbs-surface scan as a finite sampled audit. It is independent
  evidence, not deterministic continuous globality.
- Plot scripts consume CSV/JSON only and import no ePC-SAFT package.

---

### Task 1: Freeze the HELD validation cases before package execution

**Files:**

- Create: `data/may-2015-neutral-held-cases.yaml`
- Create: `campaigns/check_neutral_held_cases.py`
- Create: `tests/test_neutral_held_cases.py`

- [ ] Write RED tests requiring the existing May CSV/metadata/tolerance hashes,
  exact source row IDs, derivation formulas, and no model output fields.
- [ ] Retain every existing midpoint two-phase feed
  `z=(x_source+y_source)/2` used by the Slice 2 campaign.
- [ ] Before executing HELD, derive one liquid-side single-phase case from row
  011's measured coexistence interval while remaining inside the already
  approved methane-feed rectangle:

```text
source row: may2015-ch4-c2h6-011
z_liquid = x_methane - 2*x_comparison_allowance
         = 0.5957 - 2*0.0165
         = 0.5627
```

  Require the value inside `[0.4661,0.66705]` and below the frozen
  uncertainty-expanded liquid boundary. Label phase-count status
  `source-backed-inference`, not direct observation or global proof. Do not
  expand the public feed domain to manufacture a vapor-side case.
- [ ] Record the exact formula, source/tolerance hashes, expected side of the
  coexistence interval, and why no new experimental observable is invented.
- [ ] Run the source checker and tests without importing any package. Commit
  this bounded contract before receiving the HELD wheel.

### Task 2: Implement the independent installed-provider Gibbs-surface audit

**Files:**

- Create: `campaigns/neutral_held_v1.py`
- Create: `tests/test_neutral_held_v1.py`

- [ ] Write RED CLI tests requiring `--provider-wheel`,
  `--equilibrium-wheel`, `--cases`, and `--output-dir`.
- [ ] Verify wheel SHA-256, installed RECORD contents, import origins, package
  versions, and absence of source-checkout paths before import.
- [ ] Freeze the sampled audit before the candidate run: 1001 uniform methane
  compositions over `[1e-8,1-1e-8]`, applied to source row 001's midpoint,
  source row 012's midpoint, and the derived row 011 liquid-side case. Freeze
  dimensionless tangent/chord violation allowance `1e-6` and composition-grid
  localization allowance `2*delta_x`.
- [ ] For each audit `T,P` and composition grid, call only public
  `EPCSAFT.evaluate(..., pressure=P, phase=...)`. Retain every accepted
  vapor/liquid/single density branch and failure reason.
- [ ] Independently form the dimensionless molar Gibbs audit value from the
  public residual Helmholtz value `a_r`, density, and the generic ideal-mixture
  identity:

```text
g_bar = sum_i x_i*[ln(x_i*rho/rho_ref)-1]
        + a_r + P/(rho*R*T)
rho_ref = 1 mol/m3
```

  Keep this compact test-only transform inside the campaign and label it as an
  independent oracle, not production authority.
- [ ] For a two-phase HELD result, evaluate the line joining the returned phase
  Gibbs points and require no sampled branch point below it beyond a frozen
  numerical allowance. Check returned phase compositions, densities, phase
  fractions, material balance, and total free energy against the sampled
  convex-envelope evidence.
- [ ] For a one-phase result, evaluate the tangent line at the returned state
  and require no sampled branch point below it beyond the same allowance.
- [ ] Record grid incompleteness explicitly; passing the sampled audit cannot
  change the package's `globality_certificate="not_guaranteed"`.
- [ ] Reject a HELD result that reports guaranteed globality, omits its search
  profile/bounds, accepts `search_exhausted`, or disagrees with installed
  provider identity.

### Task 3: Execute HELD against the real May campaign

**Files:**

- Modify: `campaigns/neutral_held_v1.py`
- Create: `campaigns/plot_neutral_held_v1.py`
- Modify: `tests/test_neutral_held_v1.py`

- [ ] Run `tp_flash` for all 17 midpoint feeds plus the one frozen row 011
  liquid-side case in one isolated wheel environment.
- [ ] Retain per case: source inputs, HELD phase count/states/fractions,
  Stage-I/II/III statuses, best TPD, bounds/gap, attempt counts, local
  residuals, confirmation, provider fingerprint, sampled-envelope checks, and
  exact artifact/environment hashes.
- [ ] For the 17 coexistence rows, compare HELD phase compositions against the
  unchanged `3*u_c` contract. Preserve rows 002/009/010/011 as model/data
  misses unless the new output independently satisfies the frozen rule;
  preserve row 012's prior fixed-route rejection as historical comparison.
- [ ] Keep algorithm acceptance separate from experimental prediction. HELD
  may pass its sampled free-energy/phase-set audit while the same EOS remains
  a predictive `NON_ADMISSION` on some rows.
- [ ] Render two compact figures from retained CSV only: source versus HELD
  coexistence compositions, and one representative sampled Gibbs surface with
  the accepted tangent/chord. Include uncertainty and non-admission markers.
- [ ] Visually inspect every figure and verify plotted values against retained
  rows. The plotter must not import `epcsaft` or `epcsaft_equilibrium`.

### Task 4: Retain the validation decision and stop for review

**Files:**

- Modify: `AGENTS.md`
- Modify: `CONTEXT.md`
- Modify: `README.md`
- Add: reviewed CSV/JSON/PNG/SVG/PDF artifacts under `results/`

- [ ] Record separate decisions for artifact integrity, solver/local
  certification, HELD declared-search completion, sampled phase-set audit,
  one-phase/two-phase behavior, and experimental predictive agreement.
- [ ] Bind every result to provider/equilibrium commits, trees, wheels, source
  hashes, case-contract hash, environment manifest, commands, and plot hashes.
- [ ] Run all validation tests, source checkers, isolated campaigns, retained
  hash audit, plot review, `git diff --check`, and cleanup.
- [ ] Commit only the reviewed evidence set and return `PASS`,
  `NON_ADMISSION`, or `BLOCKED` independently for each claim. Do not push,
  promote, publish, or change runtime authority.

## Completion boundary

Completion establishes installed-artifact evidence over the declared binary
grid and source cases. It does not prove continuous globality, validate another
model family, promote the provider mixture tail, promote HELD, or authorize a
release.
