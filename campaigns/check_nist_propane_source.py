from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "nist-srd69-propane-saturation.csv"
DEFAULT_METADATA = ROOT / "data" / "nist-srd69-propane-saturation.yaml"
EXPECTED_COLUMNS = [
    "row_id",
    "component_id",
    "role",
    "T_K",
    "p_sat_Pa",
    "rho_sat_liq_kg_m3",
    "source_pressure_relative_uncertainty",
    "source_liquid_density_relative_uncertainty",
]
EXPECTED_TEMPERATURES = tuple(range(100, 361, 20))
EXPECTED_ROLES = {
    100: "stress",
    120: "held_out",
    140: "held_out",
    160: "training",
    180: "held_out",
    200: "held_out",
    220: "training",
    240: "held_out",
    260: "held_out",
    280: "training",
    300: "held_out",
    320: "held_out",
    340: "training",
    360: "stress",
}
EXPECTED_SOURCE_HASHES = {
    "nist_query_download": "e98f6e71594eef0aaa786e84080a69c163b595e898bd5d34bd94081b55fc3da4",
    "nist_query_page": "1240d7da467561f554801996f34c94791e7e65e8566ace01d0f0c3bad7b67acc",
    "nist_recommended_citation": "b52cde42af9090457a4112956a8e2b749d8202d725ba1595daf875c1ecf8466e",
}
EXPECTED_DOWNLOAD_URL = (
    "https://webbook.nist.gov/cgi/fluid.cgi?Action=Data&Wide=on&ID=C74986&"
    "Type=SatP&Digits=8&THigh=360&TLow=100&TInc=20&RefState=DEF&TUnit=K&"
    "PUnit=Pa&DUnit=kg%2Fm3&HUnit=kJ%2Fmol&WUnit=m%2Fs&VisUnit=uPa*s&STUnit=N%2Fm"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _expected_uncertainties(temperature: int) -> tuple[str, str]:
    pressure = "" if temperature < 120 else ("0.001" if temperature <= 180 else "0.0002")
    liquid_density = "0.0001" if temperature < 350 else ""
    return pressure, liquid_density


def _check_download(download_path: Path, rows: list[dict[str, str]]) -> None:
    if sha256(download_path) != EXPECTED_SOURCE_HASHES["nist_query_download"]:
        raise ValueError("official NIST query download hash changed")
    with download_path.open(newline="", encoding="utf-8") as stream:
        source_rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(source_rows) != len(rows):
        raise ValueError("official NIST query row count changed")
    for retained, source in zip(rows, source_rows, strict=True):
        if (
            retained["T_K"],
            retained["p_sat_Pa"],
            retained["rho_sat_liq_kg_m3"],
        ) != (
            source["Temperature (K)"],
            source["Pressure (Pa)"],
            source["Density (l, kg/m3)"],
        ):
            raise ValueError(f"retained values differ from NIST download at {retained['row_id']}")


def check(
    csv_path: Path,
    metadata_path: Path,
    download_path: Path | None = None,
) -> dict[str, object]:
    with csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(f"unexpected CSV columns: {reader.fieldnames}")
        rows = list(reader)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    if metadata["dataset_id"] != "nist-webbook-propane-saturation-100-360-k-v1":
        raise ValueError("unexpected dataset identity")
    if metadata["citation"]["doi"] != "10.18434/T4D303":
        raise ValueError("unexpected NIST source DOI")
    if metadata["reference_equation"]["doi"] != "10.1021/je900217v":
        raise ValueError("unexpected propane reference-equation DOI")
    source_hashes = {name: source["sha256"] for name, source in metadata["sources"].items()}
    if source_hashes != EXPECTED_SOURCE_HASHES:
        raise ValueError("official source hashes changed")
    if metadata["sources"]["nist_query_download"]["url"] != EXPECTED_DOWNLOAD_URL:
        raise ValueError("official NIST query locator changed")

    csv_hash = sha256(csv_path)
    if metadata["retained_files"]["csv"]["sha256"] != csv_hash:
        raise ValueError("retained CSV hash does not match metadata")
    for contract_name in ("fit_target_contract", "comparison_contract"):
        contract = metadata[contract_name]
        if contract["sha256"] != canonical_hash(contract["payload"]):
            raise ValueError(f"{contract_name} payload hash does not match metadata")
    comparison = metadata["comparison_contract"]["payload"]
    if any(
        comparison[name] is not None
        for name in (
            "pressure_comparison_allowance",
            "liquid_density_comparison_allowance",
            "model_accuracy_floor",
        )
    ):
        raise ValueError("source packet must not invent a model comparison allowance")

    if len(rows) != len(EXPECTED_TEMPERATURES):
        raise ValueError(f"expected {len(EXPECTED_TEMPERATURES)} rows, found {len(rows)}")
    pressures: list[float] = []
    liquid_densities: list[float] = []
    role_ids: dict[str, list[str]] = {"training": [], "held_out": [], "stress": []}
    for row, temperature in zip(rows, EXPECTED_TEMPERATURES, strict=True):
        expected_id = f"nist-propane-sat-{temperature}-k"
        if row["row_id"] != expected_id or row["component_id"] != "propane":
            raise ValueError(f"unexpected row identity at {temperature} K")
        if row["T_K"] != f"{temperature:.5f}" or row["role"] != EXPECTED_ROLES[temperature]:
            raise ValueError(f"temperature grid or role changed at {expected_id}")
        if (
            row["source_pressure_relative_uncertainty"],
            row["source_liquid_density_relative_uncertainty"],
        ) != _expected_uncertainties(temperature):
            raise ValueError(f"source uncertainty contract changed at {expected_id}")
        pressure = float(row["p_sat_Pa"])
        liquid_density = float(row["rho_sat_liq_kg_m3"])
        if not all(math.isfinite(value) and value > 0.0 for value in (pressure, liquid_density)):
            raise ValueError(f"nonpositive or nonfinite source value at {expected_id}")
        pressures.append(pressure)
        liquid_densities.append(liquid_density)
        role_ids[row["role"]].append(row["row_id"])
    if any(right <= left for left, right in zip(pressures[:-1], pressures[1:], strict=True)):
        raise ValueError("saturation pressure must increase across the retained grid")
    if any(right >= left for left, right in zip(liquid_densities[:-1], liquid_densities[1:], strict=True)):
        raise ValueError("saturated liquid density must decrease across the retained grid")

    target = metadata["fit_target_contract"]["payload"]
    for role in ("training", "held_out", "stress"):
        if target[f"{role}_row_ids"] != role_ids[role]:
            raise ValueError(f"{role} partition does not match retained rows")
    if target["fit_parameter_names"] != [
        "segment_count",
        "segment_diameter_angstrom",
        "dispersion_energy_over_k_kelvin",
    ] or target["fit_parameter_units"] != ["1", "angstrom", "K"]:
        raise ValueError("fit coordinate identity changed")

    if download_path is not None:
        _check_download(download_path, rows)

    return {
        "status": "accepted",
        "dataset_id": metadata["dataset_id"],
        "source_locator": metadata["citation"]["locator"],
        "rows": len(rows),
        "partitions": {role: len(row_ids) for role, row_ids in role_ids.items()},
        "csv_sha256": csv_hash,
        "metadata_sha256": sha256(metadata_path),
        "fit_target_sha256": metadata["fit_target_contract"]["sha256"],
        "comparison_contract_sha256": metadata["comparison_contract"]["sha256"],
        "source_sha256": source_hashes,
        "download_verified": download_path is not None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the frozen NIST propane source contract.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument(
        "--download",
        type=Path,
        help="Optional exact NIST tab-delimited download for transformation verification.",
    )
    args = parser.parse_args()
    print(json.dumps(check(args.csv, args.metadata, args.download), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
