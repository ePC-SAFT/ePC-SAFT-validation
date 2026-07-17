# Validation Repository Context

This repository owns two black-box installed-artifact campaigns:

- provider Slice 1 neutral, nonassociating PC-SAFT at explicit molar density;
- Figiel 2025 aqueous LiCl, NaCl, KCl, LiBr, NaBr, and KBr mean ionic
  activity coefficients at 298.15 K and 1 bar through 6 mol/kg.

`governance_doctrine_revision: 2`

Canonical local doctrine: `../ePC-SAFT-organization/GOVERNANCE.md`.

Each campaign validates only an immutable installed wheel through the public
`epcsaft` API. It may not depend on the lab, migration repository,
sibling source paths, package-private imports, or a copied EOS implementation.
Frozen Slice 1 scalar goldens are declared shared provider evidence. The
Hamer--Wu tables are real physical reproduction data for fitted Figiel
parameters, not a held-out prediction set. Neither is a second executable
model.

`results/provider-slice-1.json` remains bound to the narrow accepted Slice 1
wheel and its exact negative-space contract. It is not regenerated against a
broader provider candidate. The Figiel MIAC receipt is the current full-
provider-candidate campaign.

`runtime_source_of_truth: false`

`validation_source_of_truth: provider-slice-1, figiel-2025-miac`
