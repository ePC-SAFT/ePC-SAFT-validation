"""Black-box acceptance checks for the installed provider Slice 1 wheel.

The frozen values below were independently transcribed from the Gross and
Sadowski 2001 equations before the clean implementation. They are scalar
evidence, not an executable alternative EOS.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
from typing import Any

import epcsaft


DIMENSIONLESS_RTOL = 5e-12
DIMENSIONLESS_ATOL = 5e-13
PRESSURE_RTOL = 5e-12
PRESSURE_ATOL_PA = 1e-6
DERIVATIVE_RTOL = 2e-7
GAS_CONSTANT = 8.31446261815324
EXPECTED_EXPORTS = (
    "ParameterBundle",
    "ParameterSet",
    "ParameterError",
    "unit_registry",
    "EPCSAFT",
    "EosResult",
)
GOLDENS = (
    # T [K], rho_m [mol/m3], x, a_hc, a_disp, a_res, Z, P [Pa]
    (200.0, 1000.0, (1.0, 0.0), 0.06290111429923406,
     -0.16906790398822233, -0.10616678968898827,
     0.8963961463906834, 1490610.4500443912),
    (250.0, 1000.0, (0.0, 1.0), 0.10804736768399885,
     -0.3566531475792243, -0.24860577989522545,
     0.7598730786270726, 1579484.0766964532),
    (250.0, 8000.0, (0.4, 0.6), 0.8611345413201740,
     -1.9282055648091894, -1.0670710234890153,
     0.19067336346364548, 3170693.1055920523),
)


def close(actual: float, expected: float, *, pressure: bool = False) -> None:
    rtol = PRESSURE_RTOL if pressure else DIMENSIONLESS_RTOL
    atol = PRESSURE_ATOL_PA if pressure else DIMENSIONLESS_ATOL
    if not math.isclose(actual, expected, rel_tol=rtol, abs_tol=atol):
        raise AssertionError(f"{actual!r} != {expected!r}")


def model(component_ids: tuple[str, ...] = ("methane", "ethane")) -> Any:
    parameters = epcsaft.ParameterBundle.from_catalog(
        "gross-2001-methane-ethane", version=1
    ).select(component_ids)
    return epcsaft.EPCSAFT(parameters)


def evaluate(
    eos: Any,
    temperature: float,
    density: float,
    fractions: tuple[float, float],
) -> Any:
    units = epcsaft.unit_registry
    return eos.evaluate(
        temperature=temperature * units.kelvin,
        molar_density=density * units.mole / units.meter**3,
        mole_fractions=fractions,
    )


def artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(artifact: Path) -> dict[str, Any]:
    if artifact.suffix != ".whl" or not artifact.is_file():
        raise ValueError("--artifact must name the installed provider wheel")

    module_path = Path(epcsaft.__file__).resolve()
    if not {"site-packages", "dist-packages"}.intersection(module_path.parts):
        raise AssertionError(f"epcsaft is not installed: {module_path}")
    if tuple(epcsaft.__all__) != EXPECTED_EXPORTS:
        raise AssertionError(f"unexpected public exports: {epcsaft.__all__!r}")

    distribution = metadata.distribution("epcsaft")
    installed_files = [str(path) for path in distribution.files or ()]
    forbidden_files = [
        path for path in installed_files
        if path.startswith("tests/")
        or "/_native/" in f"/{path}"
        or path.endswith((".cpp", ".hpp"))
        or "figiel-2025" in path.lower()
    ]
    if forbidden_files:
        raise AssertionError(f"forbidden wheel files: {forbidden_files!r}")

    eos = model()
    observed_goldens: list[dict[str, Any]] = []
    for temperature, density, fractions, hard_chain, dispersion, residual, z, pressure in GOLDENS:
        result = evaluate(eos, temperature, density, fractions)
        close(result.hard_chain, hard_chain)
        close(result.dispersion, dispersion)
        close(result.residual_helmholtz, residual)
        close(result.compressibility_factor, z)
        pressure_pa = result.pressure.to("pascal").magnitude
        close(pressure_pa, pressure, pressure=True)
        observed_goldens.append({
            "temperature_K": temperature,
            "molar_density_mol_m3": density,
            "mole_fractions": fractions,
            "residual_helmholtz": result.residual_helmholtz,
            "compressibility_factor": result.compressibility_factor,
            "pressure_Pa": pressure_pa,
        })

    temperature, density, fractions = 250.0, 8000.0, (0.4, 0.6)
    step = density * 1e-3
    values = [
        evaluate(eos, temperature, density + offset * step, fractions).residual_helmholtz
        for offset in (2, 1, -1, -2)
    ]
    derivative = (-values[0] + 8 * values[1] - 8 * values[2] + values[3]) / (12 * step)
    reconstructed_pressure = (
        (1 + density * derivative) * density * GAS_CONSTANT * temperature
    )
    reported_pressure = evaluate(eos, temperature, density, fractions).pressure.to(
        "pascal"
    ).magnitude
    if not math.isclose(
        reported_pressure, reconstructed_pressure, rel_tol=DERIVATIVE_RTOL
    ):
        raise AssertionError("pressure is inconsistent with the public density direction")

    reverse = model(("ethane", "methane"))
    reverse_result = evaluate(reverse, temperature, density, (0.6, 0.4))
    close(reverse_result.pressure.to("pascal").magnitude, reported_pressure, pressure=True)

    low_density = 1e-6
    low = evaluate(eos, temperature, low_density, fractions)
    if abs(low.residual_helmholtz) >= 1e-8 or abs(low.compressibility_factor - 1) >= 1e-8:
        raise AssertionError("low-density limit failed")
    ideal_pressure = low_density * GAS_CONSTANT * temperature
    if not math.isclose(
        low.pressure.to("pascal").magnitude, ideal_pressure, rel_tol=1e-8
    ):
        raise AssertionError("low-density ideal-gas pressure limit failed")

    invalid_calls = (
        {"temperature": 250.0, "molar_density": 1000 * epcsaft.unit_registry.mole / epcsaft.unit_registry.meter**3},
        {"temperature": 250 * epcsaft.unit_registry.kelvin, "molar_density": 1000.0},
    )
    for state in invalid_calls:
        try:
            eos.evaluate(**state, mole_fractions=fractions)
        except ValueError:
            pass
        else:
            raise AssertionError("bare state values must be rejected")
    try:
        evaluate(eos, temperature, 1e8, (1.0, 0.0))
    except ValueError:
        pass
    else:
        raise AssertionError("a close-packed state must be rejected")

    return {
        "schema_version": 1,
        "status": "passed",
        "claim": "provider Slice 1 explicit-density neutral EOS public behavior",
        "artifact": {
            "filename": artifact.name,
            "sha256": artifact_sha256(artifact),
            "distribution": distribution.metadata["Name"],
            "version": distribution.version,
        },
        "installation": {
            "module_path_class": "installed-site-packages",
            "root_exports": EXPECTED_EXPORTS,
        },
        "checks": {
            "gross_2001_goldens": observed_goldens,
            "density_direction_pressure_Pa": reported_pressure,
            "density_direction_reconstructed_pressure_Pa": reconstructed_pressure,
            "component_permutation": "passed",
            "low_density_limit": "passed",
            "strict_quantity_boundary": "passed",
            "close_packing_rejection": "passed",
            "wheel_negative_space": "passed",
        },
        "tolerances": {
            "dimensionless_rtol": DIMENSIONLESS_RTOL,
            "dimensionless_atol": DIMENSIONLESS_ATOL,
            "pressure_rtol": PRESSURE_RTOL,
            "pressure_atol_Pa": PRESSURE_ATOL_PA,
            "density_direction_rtol": DERIVATIVE_RTOL,
        },
        "limits": [
            "Frozen values and finite differences do not duplicate the production EOS kernel.",
            "This campaign does not validate density closure, phase identity, association, ions, equilibrium, regression, or release readiness.",
            "A passed campaign does not transfer runtime authority.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = run(arguments.artifact.resolve())
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(rendered, end="")
    else:
        arguments.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
