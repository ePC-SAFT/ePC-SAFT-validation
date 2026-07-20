# Validation Repository Context

This repository owns eight black-box installed-artifact campaigns:

- provider Slice 1 neutral, nonassociating PC-SAFT at explicit molar density;
- Figiel 2025 aqueous LiCl, NaCl, KCl, LiBr, NaBr, and KBr mean ionic
  activity coefficients at 298.15 K and 1 bar through 6 mol/kg.
- Esteso 1989 NaCl mean ionic activity coefficients in 20, 40, 60, and 80
  mass-percent ethanol/water at 298.15 K;
- Held 2012 LiCl, LiBr, and NaBr solution densities in ethanol at 298.15 K
  and ambient pressure.
- Held 2012 directly measured pure-ethanol density at 298.15 K and ambient
  pressure through the neutral-associating provider path.
- pure-methane parity and pure-ethane saturation regression over retained NIST
  SRD 69 observations; and
- May et al. 2015 Table 5 methane/ethane local two-phase flash over all 17
  retained coexistence rows; and
- neutral HELD v1 over the same 17 midpoint feeds, one source-derived
  liquid-side case, and three frozen public pressure-state sampled Gibbs
  audits.

`governance_doctrine_revision: 2`

Canonical local doctrine: `../ePC-SAFT-organization/GOVERNANCE.md`.

Each campaign validates only an immutable installed wheel through the public
`epcsaft` API. It may not depend on the lab, migration repository,
sibling source paths, package-private imports, or a copied EOS implementation.
Frozen Slice 1 scalar goldens are declared shared provider evidence. The
Hamer--Wu tables are real physical reproduction data for fitted Figiel
parameters, not a held-out prediction set. The Esteso and Held tables are
direct experiments that exercise mixed-solvent activity and specified-pressure
density respectively. The pure-ethanol anchor isolates association and density
closure without ionic terms. None is a second executable model.

`results/provider-slice-1.json` remains bound to the narrow accepted Slice 1
wheel and its exact negative-space contract. It is not regenerated against a
broader provider candidate. The current full-provider candidate is covered by
the Figiel MIAC reproduction and the three direct-data records produced by
`campaigns/provider_real_data.py`.

The Consumer Slice 2 regression record binds regression implementation commit
`50a488b91686388432fd50a0d6bfc5b15825e4f1`, evidence commit
`1c0c8bdbabbed20795cb2d093a7d15ee03accedb`, regression wheel SHA-256
`e4bf7ec673a9e6f5b70ce1ef39d9f28a73c709cf38974019c09790cc4f9bfa49`,
and provider wheel SHA-256
`f92f79c8d6f614660e5c201b7061c9b02b5cd1a25a4ed8c8fee0b59adaabf2bf`.
Both component workflows pass solver, numerical-confirmation, and local-
physical gates, and methane preserves the accepted numerical result. Held-out
errors have no approved cutoff and are descriptive only. The failed ethane
100 K reporting state remains an excluded stress failure. The public
regression result exposes before/after parameters and objective values but not
start-model reporting predictions; validation does not recreate saturation.

The Consumer Slice 2 flash record binds equilibrium commit
`e16f1e0fff62892615ef11e4012cd1e63a329e39`, tree
`6fc131c03e392acd5ab6678ff6e17e59a4afce02`, equilibrium wheel SHA-256
`9f3adbc6f5539ae14cbff15b14a9eccf289ce238b316f78a81a25c1b91b3cc49`,
and provider wheel SHA-256
`17c6735ee117469b13b76b6a669d0b4430071c8eaebdf1e405baefc9adcb838b`.
Its source contract is commit `73a37f5935e919a34d1e4fa3af285951d6fac8e7`,
CSV SHA-256 `5cd1e74925a3c6504f5106dcf911f2cae2d6e99a5133fccc20454d8991bdbc7f`,
and frozen tolerance SHA-256
`ad744526678355be6ca47cf27ab9ff7ae66b7661c27e36ffe259c5b6295f1016`.
Twelve rows pass the frozen `3 * u_c` comparison, four package-accepted local
states are model/data misses, and one row is rejected by the package local-
physical gate. The 17-row validation decision is `NON_ADMISSION`; package
solver correctness, predictive agreement, and migration authority remain
separate claims. The route fixes two phases and claims no phase discovery,
continuation, TPD, or global stability.

The neutral HELD v1 record binds provider wheel SHA-256
`17c6735ee117469b13b76b6a669d0b4430071c8eaebdf1e405baefc9adcb838b`,
equilibrium wheel SHA-256
`8ecd70e0192b76b3a107629201c3e8bf34f2d945ca7c8192f824a0df7c9dde12`,
candidate receipt SHA-256
`a8a1fe6f0836cef3afd9edfe390fb2d131b1a7a441e160f4cd7176524038dc30`,
and case-contract SHA-256
`5aceaada58e3010d4232b8f3cf0f0447e2c174a33bbc54c9be7b8675464aa771`.
Artifact integrity passes. The derived row-011 liquid case and the row-012
one-phase result pass their finite sampled tangent audits, but only 2 of 18
cases return accepted HELD states. Thirteen May cases fail closed on a third
Stage-II candidate, three exhaust the declared Stage-II budget, and row 012
returns one phase rather than the observed two-phase topology. The installed-
artifact, declared-search, two-phase, sampled-phase-set, and predictive
decisions are therefore `NON_ADMISSION`. Solver, numerical, and physical
statuses are passed for the two returned states and not adjudicated for the
sixteen fail-closed cases; no failure is relabeled as predictive disagreement.
Every result retains `globality_certificate=not_guaranteed`.

`runtime_source_of_truth: false`

`validation_source_of_truth: provider-slice-1, figiel-2025-miac, esteso-1989-water-ethanol-nacl, held-2012-ethanol-salt-density, held-2012-pure-ethanol-density, pure-saturation-regression, may-2015-methane-ethane-flash, neutral-held-v1`

The executed plan is
`docs/plans/2026-07-17-neutral-held-v1-validation-plan.md`. It freezes a
public-wheel-only sampled Gibbs-surface audit, the unchanged May campaign, and
one source-derived liquid-side case inside the existing feed domain. Its
decision is `NON_ADMISSION` and its authority effect is none.

`next_validation_plan: neutral-held-v1`

`next_validation_plan_status: completed_non_admission`
