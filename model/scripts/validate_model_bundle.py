from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


LEAKAGE_COLUMNS = {
    "label",
    "target",
    "type",
    "scan_subtype",
    "timestamp",
    "ts",
    "window_start",
    "window_end",
    "scenario_id",
    "run_id",
    "phase",
    "phases",
    "technique_id",
    "technique_ids",
    "src_entity",
    "src_ip",
    "dst_ip",
    "id.orig_h",
    "id.resp_h",
    "is_synthetic",
    "data_source",
}
METADATA_COLUMNS = [
    "window_start",
    "window_end",
    "scenario_id",
    "run_id",
    "label",
    "scan_subtype",
    "phase",
    "phases",
    "technique_id",
    "technique_ids",
    "src_entity",
    "data_source",
    "is_synthetic",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an exported NDR model bundle and optionally run smoke inference.",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml"),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("../ipcam-backdoor-test-environment/data/features/datasets/ipcam-scan-subtype-60s.csv"),
        help="Optional feature CSV for runtime prediction validation.",
    )
    parser.add_argument("--prediction-output", type=Path, default=Path("models/model_bundle_validation_predictions.csv"))
    parser.add_argument("--output-json", type=Path, default=Path("models/model_bundle_validation.json"))
    parser.add_argument("--output-md", type=Path, default=Path("models/model_bundle_validation.md"))
    parser.add_argument("--threshold", type=float, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = validate_bundle(args)
    write_json(args.output_json, report)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    print("bundle_validation=" + ("pass" if report["passed"] else "fail"))
    if report.get("prediction_output"):
        print(f"wrote predictions to {report['prediction_output']}")


def validate_bundle(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    manifest_path = args.model_dir / "manifest.json"
    manifest = read_optional_json(manifest_path)
    checks.append(check("manifest_exists", manifest is not None, {"path": str(manifest_path)}))

    feature_columns: list[str] = []
    threshold = args.threshold
    if manifest:
        feature_columns = [str(value) for value in manifest.get("feature_columns") or []]
        if threshold is None:
            threshold = float(manifest.get("prediction_threshold", 0.8))
        checks.append(check("feature_schema_present", bool(feature_columns), {"feature_count": len(feature_columns)}))
        leaked = sorted(set(feature_columns).intersection(LEAKAGE_COLUMNS))
        checks.append(check("no_leakage_or_identity_features", not leaked, {"leaked_features": leaked}))
        checks.extend(artifact_checks(args.model_dir, manifest))
    else:
        threshold = 0.8 if threshold is None else threshold

    prediction_summary = None
    prediction_output = None
    if args.input and args.input.exists() and feature_columns and (args.model_dir / "model.json").exists():
        prediction_summary, prediction_output = run_prediction_smoke(
            model_dir=args.model_dir,
            input_path=args.input,
            output_path=args.prediction_output,
            feature_columns=feature_columns,
            threshold=float(threshold),
        )
        checks.extend(prediction_summary["checks"])
    else:
        checks.append(
            check(
                "prediction_input_available",
                False,
                {
                    "input": str(args.input) if args.input else None,
                    "input_exists": args.input.exists() if args.input else False,
                    "has_feature_schema": bool(feature_columns),
                    "model_json_exists": (args.model_dir / "model.json").exists(),
                },
            )
        )

    passed = all(item["passed"] for item in checks)
    return {
        "passed": passed,
        "model_dir": str(args.model_dir),
        "input": str(args.input) if args.input else None,
        "prediction_output": str(prediction_output) if prediction_output else None,
        "threshold": threshold,
        "checks": checks,
        "prediction_summary": prediction_summary,
        "limitations": [
            "This validates bundle runtime compatibility and artifact integrity.",
            "Smoke inference metrics are not operational performance evidence.",
            "Operational readiness still depends on real run-separated evaluation gates.",
        ],
    }


def artifact_checks(model_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    expected_hashes = manifest.get("artifact_sha256") or {}
    required = ["model.json", "feature_names.json", "metrics.json", "predict_xgb_scan_detection.py"]
    for filename in required:
        path = model_dir / filename
        result.append(check(f"artifact_exists_{filename}", path.exists(), {"path": str(path)}))
    for filename, expected in sorted(expected_hashes.items()):
        path = model_dir / filename
        if not path.exists():
            result.append(check(f"artifact_hash_{filename}", False, {"path": str(path), "reason": "missing"}))
            continue
        actual = sha256_file(path)
        result.append(
            check(
                f"artifact_hash_{filename}",
                actual == expected,
                {"path": str(path), "expected": expected, "actual": actual},
            )
        )

    feature_names_path = model_dir / "feature_names.json"
    feature_payload = read_optional_json(feature_names_path)
    manifest_features = [str(value) for value in manifest.get("feature_columns") or []]
    file_features = [str(value) for value in (feature_payload or {}).get("features", [])]
    result.append(
        check(
            "feature_names_match_manifest",
            bool(file_features) and file_features == manifest_features,
            {
                "manifest_feature_count": len(manifest_features),
                "feature_file_count": len(file_features),
                "same_order": file_features == manifest_features,
            },
        )
    )
    return result


def run_prediction_smoke(
    *,
    model_dir: Path,
    input_path: Path,
    output_path: Path,
    feature_columns: list[str],
    threshold: float,
) -> tuple[dict[str, Any], Path]:
    try:
        import pandas as pd
        import xgboost as xgb
        from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, roc_auc_score
    except ImportError as exc:
        raise SystemExit("missing ML dependency. Activate .venv-wsl and install requirements.txt.") from exc

    frame = pd.read_csv(input_path)
    metadata = frame[[column for column in METADATA_COLUMNS if column in frame.columns]].copy()
    features = frame.drop(columns=[column for column in LEAKAGE_COLUMNS if column in frame.columns], errors="ignore")
    features = features.apply(pd.to_numeric, errors="coerce").replace([float("inf"), float("-inf")], 0).fillna(0)
    missing_features = [column for column in feature_columns if column not in features.columns]
    extra_features = [column for column in features.columns if column not in feature_columns]
    features = features.reindex(columns=feature_columns, fill_value=0)

    model = xgb.Booster()
    model.load_model(str(model_dir / "model.json"))
    probabilities = model.predict(xgb.DMatrix(features, feature_names=feature_columns))
    if getattr(probabilities, "ndim", 1) > 1:
        probabilities = probabilities[:, 1]
    predictions = (probabilities >= threshold).astype(int)

    output = metadata.copy()
    output["scanning_probability"] = probabilities
    output["predicted_label"] = predictions
    output["predicted_name"] = output["predicted_label"].map({0: "normal", 1: "scanning"})
    output["threshold"] = threshold
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False)

    checks = [
        check("prediction_input_available", True, {"input": str(input_path), "rows": int(len(frame))}),
        check("prediction_rows_match_input", len(output) == len(frame), {"input_rows": int(len(frame)), "output_rows": int(len(output))}),
        check("prediction_probability_range", bool(((output["scanning_probability"] >= 0) & (output["scanning_probability"] <= 1)).all()), {}),
        check("prediction_has_no_null_probability", not output["scanning_probability"].isna().any(), {}),
        check("prediction_feature_alignment", True, {"filled_missing_features": missing_features, "ignored_extra_features": extra_features}),
    ]
    metrics = None
    if "label" in frame.columns:
        y_true = frame["label"].astype(str).map({"normal": 0, "scanning": 1})
        known = y_true.notna()
        if known.any():
            y_true_known = y_true[known].astype(int)
            y_pred_known = predictions[known.to_numpy()]
            probabilities_known = probabilities[known.to_numpy()]
            precision, recall, f1, _support = precision_recall_fscore_support(
                y_true_known,
                y_pred_known,
                average="binary",
                zero_division=0,
            )
            try:
                roc_auc = float(roc_auc_score(y_true_known, probabilities_known))
            except ValueError:
                roc_auc = None
            metrics = {
                "rows": int(known.sum()),
                "precision": float(precision),
                "recall": float(recall),
                "f1_score": float(f1),
                "roc_auc": roc_auc,
                "confusion_matrix": confusion_matrix(y_true_known, y_pred_known, labels=[0, 1]).tolist(),
            }
            checks.append(check("prediction_labeled_metric_computed", True, metrics))

    return (
        {
            "input_rows": int(len(frame)),
            "output_rows": int(len(output)),
            "feature_count": len(feature_columns),
            "filled_missing_features": missing_features,
            "ignored_extra_features": extra_features,
            "metrics_if_labeled": metrics,
            "checks": checks,
        },
        output_path,
    )


def check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "details": details}


def read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Model Bundle Validation",
        "",
        f"- Passed: {report['passed']}",
        f"- Model dir: `{report['model_dir']}`",
        f"- Input: `{report['input']}`",
        f"- Prediction output: `{report.get('prediction_output')}`",
        "",
        "## Checks",
        "",
        "| check | passed | details |",
        "| --- | --- | --- |",
    ]
    for item in report["checks"]:
        lines.append(
            f"| {item['name']} | {item['passed']} | `{json.dumps(item['details'], sort_keys=True)}` |"
        )
    summary = report.get("prediction_summary") or {}
    if summary:
        lines.extend(["", "## Prediction Summary", ""])
        lines.append(f"- Input rows: {summary.get('input_rows')}")
        lines.append(f"- Output rows: {summary.get('output_rows')}")
        lines.append(f"- Feature count: {summary.get('feature_count')}")
        metrics = summary.get("metrics_if_labeled")
        if metrics:
            lines.append(f"- Labeled smoke metrics: `{json.dumps(metrics, sort_keys=True)}`")
    lines.extend(["", "## Limitations", ""])
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
