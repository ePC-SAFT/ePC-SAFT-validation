# ePC-SAFT Validation

Repository role: validation

Intended GitHub home: `ePC-SAFT/ePC-SAFT-validation`

Active campaigns: provider Slice 1 explicit-density neutral EOS and the
Figiel 2025 aqueous alkali-halide MIAC comparison.

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
