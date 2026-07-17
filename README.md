# ePC-SAFT Validation

Repository role: validation

Intended GitHub home: `ePC-SAFT/ePC-SAFT-validation`

Active campaigns: provider Slice 1 explicit-density neutral EOS, Figiel 2025
aqueous alkali-halide MIAC reproduction, Esteso 1989 mixed-solvent NaCl MIAC,
Held 2012 ethanol-salt density, the Held 2012 directly measured pure-ethanol
density, pure-saturation regression, and May 2015 methane/ethane local flash.

This repository will own black-box installed-artifact, cross-package, and
literature acceptance evidence. It will not own production algorithms, private
package imports, or the broad paper archive retained by
`tannerpolley/ePC-SAFT-lab`.

The Slice 1 campaign is `campaigns/provider_slice_1.py`. Run it in an isolated environment with the
exact provider wheel supplied through `uv --with`; pass the same wheel to
`--artifact` so the result is bound to its SHA-256. The script imports only the
public `epcsaft` surface and retains no executable PC-SAFT equation copy. Its
frozen scalar goldens are shared provider anchors; black-box finite-difference
and metamorphic checks supply the separately executed evidence.

`campaigns/figiel_2025_miac.py` evaluates 164 Hamer--Wu table rows for six
aqueous salts through the installed provider's public reference-state API. It
retains predictions and a hash-bound JSON receipt. The source range stops at
6 mol/kg, matching the model range in Figiel 2025 Figure 5; no figure points
were digitized and no parameters are fitted here. Render the retained CSV with
`campaigns/plot_figiel_2025_miac.py`; plotting never recomputes the EOS.

`campaigns/provider_real_data.py` adds three small predictive campaigns using
only direct tabular experiments: 92 Esteso Table I NaCl activity-coefficient
rows over four water/ethanol compositions and seven Held Table 1 ethanol-salt
density rows for LiCl, LiBr, and NaBr, plus the authors' direct mean pure-
ethanol density measurement. It runs against one hash-bound installed wheel
and writes separate receipts and prediction tables. Render those tables
with `campaigns/plot_provider_real_data.py`; the plotting script does not import
or execute the provider.

`campaigns/pure_saturation_regression.py` validates the exact installed
provider/regression wheel pair for methane and ethane. It verifies every
installed wheel `RECORD` member before public imports, freezes the NIST source
partitions exposed by the public loader, preserves accepted methane numerical
parity, and records solver, numerical, local-physical, predictive, and stress
statuses separately. The artifact workflow decision is `PASS`; held-out
accuracy is not adjudicated because no cutoff is approved. Ethane at 100 K is
retained as an excluded stress failure. The public result does not expose
start-model reporting predictions, so the retained prediction CSV leaves those
cells empty rather than adding a validation-owned saturation solve. Render the
CSV with `campaigns/plot_pure_saturation_regression.py`.

`campaigns/may_2015_methane_ethane_flash.py` evaluates the complete 17-row May
et al. (2015), Table 5 source contract against the exact installed provider and
equilibrium wheels. It feeds `z = 0.5*x + 0.5*y`, retains public solver and KKT
diagnostics, checks material balance, and compares liquid and vapor methane
fractions with the pre-model `3*u_c` allowances. Sixteen rows produce locally
accepted package states. Four of those are composition misses and one further
row is locally rejected, so the physical campaign decision is
`NON_ADMISSION` with 12 admitted rows. This is not a package-correctness or
global-stability judgment. Render the retained CSV with
`campaigns/plot_may_2015_methane_ethane_flash.py`; the renderer imports no
production package.

The compact machine-readable roll-up is
`results/consumer-slice-2-validation-record.json`. Detailed receipts preserve
the exact commands, installed import origins, artifact and source hashes, row
outcomes, and limitations. This repository remains non-authoritative for
runtime, release, publication, promotion, and package ownership.
