# Validation Repository Context

This repository owns the black-box installed-artifact campaign for provider
Slice 1: neutral, nonassociating, nonionic PC-SAFT at explicit molar density.

`governance_doctrine_revision: 2`

Canonical local doctrine: `../ePC-SAFT-organization/GOVERNANCE.md`.

The campaign validates only an immutable installed wheel through the six-symbol
public `epcsaft` API. It may not depend on the lab, migration repository,
sibling source paths, package-private imports, or a copied EOS implementation.
Frozen scalar goldens are declared shared provider evidence. They are not a
second executable model and do not count as an independent oracle.

`runtime_source_of_truth: false`

`validation_source_of_truth: provider-slice-1`
