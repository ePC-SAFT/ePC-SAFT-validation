# ePC-SAFT Validation

Repository role: validation

Intended GitHub home: `ePC-SAFT/ePC-SAFT-validation`

Active campaign: provider Slice 1 explicit-density neutral EOS.

This repository will own black-box installed-artifact, cross-package, and
literature acceptance evidence. It will not own production algorithms, private
package imports, or the broad paper archive retained by
`tannerpolley/ePC-SAFT-lab`.

The current campaign is one standard-library script:
`campaigns/provider_slice_1.py`. Run it in an isolated environment with the
exact provider wheel supplied through `uv --with`; pass the same wheel to
`--artifact` so the result is bound to its SHA-256. The script imports only the
public `epcsaft` surface and retains no executable PC-SAFT equation copy.
