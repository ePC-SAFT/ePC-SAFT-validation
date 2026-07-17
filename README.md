# ePC-SAFT Validation

Repository role: validation

Intended GitHub home: `ePC-SAFT/ePC-SAFT-validation`

Active campaigns: provider Slice 1 explicit-density neutral EOS, Figiel 2025
aqueous alkali-halide MIAC reproduction, Esteso 1989 mixed-solvent NaCl MIAC,
Held 2012 ethanol-salt density, and the Held 2012 directly measured pure-
ethanol density through the neutral-associating provider path.

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
