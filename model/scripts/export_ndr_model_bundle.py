from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
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
DEFAULT_GATES = {
    "min_precision": 0.90,
    "min_recall": 0.90,
    "min_f1_score": 0.90,
    "min_roc_auc": 0.95,
    "max_false_positive_rate": 0.05,
    "min_train_rows_for_operational_claim": 500,
    "min_test_rows_for_operational_claim": 200,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export an NDR scan detection model bundle with readiness metadata.",
    )
    parser.add_argument("--model-json", type=Path, default=Path("models/scan_detection_xgb_v3_holdout.json"))
    parser.add_argument("--model-pkl", type=Path, default=Path("models/scan_detection_xgb_v3_holdout.pkl"))
    parser.add_argument("--feature-names", type=Path, default=Path("models/feature_names_v3_holdout.json"))
    parser.add_argument("--metrics", type=Path, default=Path("models/metrics_xgb_v3_holdout.json"))
    parser.add_argument("--data-report", type=Path, default=Path("models/data_sufficiency_report.json"))
    parser.add_argument(
        "--source-evaluation",
        type=Path,
        default=Path("models/source_evaluations/source_evaluation_report.json"),
    )
    parser.add_argument(
        "--group-cv-evaluation",
        type=Path,
        default=Path("models/group_cv_evaluation/group_cv_report.json"),
        help="Optional real-only group-separated cross-validation report.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml"),
    )
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--bundle-name", default="xgboost-scan-detection-ndr-ml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    required = [args.model_json, args.feature_names, args.metrics]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"missing required model artifact(s): {missing}")

    features_payload = read_json(args.feature_names)
    metrics = read_json(args.metrics)
    data_report = read_optional_json(args.data_report)
    source_evaluation = read_optional_json(args.source_evaluation)
    group_cv_evaluation = read_optional_json(args.group_cv_evaluation)
    features = [str(feature) for feature in features_payload.get("features", [])]
    threshold = args.threshold
    if threshold is None:
        threshold = float(metrics.get("prediction_threshold", 0.8))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    copied_files = copy_artifacts(args, args.output_dir)
    manifest = build_manifest(
        args=args,
        output_dir=args.output_dir,
        copied_files=copied_files,
        features=features,
        features_payload=features_payload,
        metrics=metrics,
        data_report=data_report,
        source_evaluation=source_evaluation,
        group_cv_evaluation=group_cv_evaluation,
        threshold=threshold,
    )
    write_json(args.output_dir / "manifest.json", manifest)
    write_json(args.output_dir / "readiness_report.json", manifest["readiness"])
    (args.output_dir / "model_card.md").write_text(render_model_card(manifest), encoding="utf-8")
    (args.output_dir / "readiness_report.md").write_text(
        render_readiness(manifest["readiness"]), encoding="utf-8"
    )

    print(f"exported model bundle to {args.output_dir}")
    print(
        "lab_integration_status="
        + ("pass" if manifest["readiness"]["lab_integration_ready"] else "fail")
    )
    print(
        "operational_status="
        + ("pass" if manifest["readiness"]["operational_ready"] else "fail")
    )


def copy_artifacts(args: argparse.Namespace, output_dir: Path) -> dict[str, str]:
    mappings = {
        args.model_json: output_dir / "model.json",
        args.feature_names: output_dir / "feature_names.json",
        args.metrics: output_dir / "metrics.json",
    }
    if args.model_pkl.exists():
        mappings[args.model_pkl] = output_dir / "model.pkl"
    predictor = Path(__file__).with_name("predict_xgb_scan_detection.py")
    if predictor.exists():
        mappings[predictor] = output_dir / "predict_xgb_scan_detection.py"
    copied = {}
    for source, target in mappings.items():
        shutil.copy2(source, target)
        copied[target.name] = sha256_file(target)
    return copied


def build_manifest(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    copied_files: dict[str, str],
    features: list[str],
    features_payload: dict[str, Any],
        metrics: dict[str, Any],
        data_report: dict[str, Any] | None,
        source_evaluation: dict[str, Any] | None,
        group_cv_evaluation: dict[str, Any] | None,
        threshold: float,
) -> dict[str, Any]:
    readiness = readiness_report(
        features=features,
        metrics=metrics,
        data_report=data_report,
        source_evaluation=source_evaluation,
        group_cv_evaluation=group_cv_evaluation,
    )
    return {
        "bundle_name": args.bundle_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bundle_dir": str(output_dir),
        "model_type": "xgboost_binary_scan_detection",
        "prediction_threshold": threshold,
        "label_map": features_payload.get("label_map", {"normal": 0, "scanning": 1}),
        "feature_count": len(features),
        "feature_columns": features,
        "artifact_sha256": copied_files,
        "source_artifacts": {
            "model_json": str(args.model_json),
            "model_pkl": str(args.model_pkl) if args.model_pkl.exists() else None,
            "feature_names": str(args.feature_names),
            "metrics": str(args.metrics),
            "data_report": str(args.data_report) if args.data_report.exists() else None,
            "source_evaluation": str(args.source_evaluation)
            if args.source_evaluation.exists()
            else None,
            "group_cv_evaluation": str(args.group_cv_evaluation)
            if args.group_cv_evaluation.exists()
            else None,
        },
        "readiness": readiness,
    }


def readiness_report(
    *,
    features: list[str],
    metrics: dict[str, Any],
    data_report: dict[str, Any] | None,
    source_evaluation: dict[str, Any] | None,
    group_cv_evaluation: dict[str, Any] | None,
) -> dict[str, Any]:
    checks = []
    leaked_features = sorted(set(features).intersection(LEAKAGE_COLUMNS))
    checks.append(check("feature_schema_present", bool(features), {"feature_count": len(features)}))
    checks.append(
        check(
            "no_leakage_or_identity_features",
            not leaked_features,
            {"leaked_features": leaked_features},
        )
    )
    checks.extend(metric_gate_checks(metrics))
    checks.extend(data_volume_checks(metrics))
    if data_report is not None:
        checks.append(
            check(
                "data_sufficiency_report_available",
                True,
                {
                    "is_insufficient": data_report.get("data_sufficiency", {}).get("is_insufficient"),
                    "total_samples": data_report.get("total_samples"),
                },
            )
        )
    else:
        checks.append(check("data_sufficiency_report_available", False, {}))

    if source_evaluation is not None:
        modes = source_evaluation.get("modes", {})
        checks.append(
            check(
                "source_separated_evaluation_available",
                bool(modes),
                {"modes": sorted(modes.keys())},
            )
        )
    else:
        checks.append(
            check(
                "source_separated_evaluation_available",
                False,
                {
                    "reason": (
                        "ML dependencies are not installed in the current WSL environment; "
                        "run train_eval_xgb_sources.py after setup."
                    )
                },
            )
        )

    group_cv_present = group_cv_evaluation is not None
    checks.extend(group_cv_gate_checks(group_cv_evaluation, bundle_features=features))

    lab_required = {
        "feature_schema_present",
        "no_leakage_or_identity_features",
        "metric_precision_gate",
        "metric_recall_gate",
        "metric_f1_gate",
        "metric_roc_auc_gate",
        "metric_false_positive_rate_gate",
    }
    operational_required = lab_required.union(
        {
            "train_row_volume_gate",
            "test_row_volume_gate",
            "source_separated_evaluation_available",
        }
    )
    if group_cv_present:
        operational_required = operational_required.union(
            {
                "group_cv_evaluation_available",
                "group_cv_no_group_overlap",
                "group_cv_no_raw_identity_features",
                "group_cv_feature_schema_matches_bundle",
                "group_cv_volume_gate",
                "group_cv_metric_precision_gate",
                "group_cv_metric_recall_gate",
                "group_cv_metric_f1_gate",
                "group_cv_metric_roc_auc_gate",
                "group_cv_false_positive_rate_gate",
            }
        )
    return {
        "gates": DEFAULT_GATES,
        "checks": checks,
        "lab_integration_ready": all(
            item["passed"] for item in checks if item["name"] in lab_required
        ),
        "operational_ready": all(
            item["passed"] for item in checks if item["name"] in operational_required
        ),
        "notes": [
            "Lab integration means the model bundle has usable artifacts, stable feature schema, and real-test metrics above gates.",
            "Operational ready additionally requires stronger train/test volume, source-separated real/synthetic evaluation evidence, and group-separated real-only evaluation when available.",
            "Synthetic data must not be used to inflate final real-only performance claims.",
        ],
    }


def group_cv_gate_checks(report: dict[str, Any] | None, bundle_features: list[str] | None = None) -> list[dict[str, Any]]:
    if report is None:
        return [
            check(
                "group_cv_evaluation_available",
                False,
                {"reason": "run train_eval_xgb_group_cv.py to generate real-only grouped evidence"},
            )
        ]

    metrics = report.get("out_of_fold_metrics") or {}
    leakage = report.get("leakage_checks") or {}
    folds = report.get("folds") or []
    report_features = [str(feature) for feature in report.get("feature_columns") or []]
    bundle_features = bundle_features or []
    train_rows = [int(fold.get("train_rows") or 0) for fold in folds]
    rows = int(metrics.get("rows") or report.get("total_rows") or 0)
    cm = metrics.get("confusion_matrix") or [[0, 0], [0, 0]]
    tn, fp, _fn, _tp = confusion_values(cm)
    false_positive_rate = fp / max(tn + fp, 1)

    return [
        check(
            "group_cv_evaluation_available",
            True,
            {
                "rows": rows,
                "group_count": report.get("group_count"),
                "n_splits": report.get("n_splits"),
            },
        ),
        check(
            "group_cv_no_group_overlap",
            not leakage.get("group_overlap_between_train_and_test"),
            {"group_overlap_between_train_and_test": leakage.get("group_overlap_between_train_and_test")},
        ),
        check(
            "group_cv_no_raw_identity_features",
            not leakage.get("raw_identity_features"),
            {"raw_identity_features": leakage.get("raw_identity_features")},
        ),
        check(
            "group_cv_feature_schema_matches_bundle",
            bool(report_features) and report_features == bundle_features,
            {
                "group_cv_feature_count": len(report_features),
                "bundle_feature_count": len(bundle_features),
                "missing_from_group_cv": sorted(set(bundle_features) - set(report_features)),
                "extra_in_group_cv": sorted(set(report_features) - set(bundle_features)),
                "same_order": report_features == bundle_features,
            },
        ),
        check(
            "group_cv_volume_gate",
            rows >= DEFAULT_GATES["min_test_rows_for_operational_claim"]
            and bool(train_rows)
            and min(train_rows) >= DEFAULT_GATES["min_train_rows_for_operational_claim"],
            {
                "out_of_fold_rows": rows,
                "min_train_rows_per_fold": min(train_rows) if train_rows else None,
                "required_oof_rows": DEFAULT_GATES["min_test_rows_for_operational_claim"],
                "required_train_rows": DEFAULT_GATES["min_train_rows_for_operational_claim"],
            },
        ),
        check(
            "group_cv_metric_precision_gate",
            float(metrics.get("precision", 0.0)) >= DEFAULT_GATES["min_precision"],
            {"actual": metrics.get("precision"), "required": DEFAULT_GATES["min_precision"]},
        ),
        check(
            "group_cv_metric_recall_gate",
            float(metrics.get("recall", 0.0)) >= DEFAULT_GATES["min_recall"],
            {"actual": metrics.get("recall"), "required": DEFAULT_GATES["min_recall"]},
        ),
        check(
            "group_cv_metric_f1_gate",
            float(metrics.get("f1_score", 0.0)) >= DEFAULT_GATES["min_f1_score"],
            {"actual": metrics.get("f1_score"), "required": DEFAULT_GATES["min_f1_score"]},
        ),
        check(
            "group_cv_metric_roc_auc_gate",
            float(metrics.get("roc_auc", 0.0)) >= DEFAULT_GATES["min_roc_auc"],
            {"actual": metrics.get("roc_auc"), "required": DEFAULT_GATES["min_roc_auc"]},
        ),
        check(
            "group_cv_false_positive_rate_gate",
            false_positive_rate <= DEFAULT_GATES["max_false_positive_rate"],
            {"actual": false_positive_rate, "required": DEFAULT_GATES["max_false_positive_rate"]},
        ),
    ]


def metric_gate_checks(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    cm = metrics.get("confusion_matrix") or [[0, 0], [0, 0]]
    tn, fp, fn, tp = confusion_values(cm)
    normal_total = tn + fp
    false_positive_rate = fp / max(normal_total, 1)
    return [
        check(
            "metric_precision_gate",
            float(metrics.get("precision", 0.0)) >= DEFAULT_GATES["min_precision"],
            {"actual": metrics.get("precision"), "required": DEFAULT_GATES["min_precision"]},
        ),
        check(
            "metric_recall_gate",
            float(metrics.get("recall", 0.0)) >= DEFAULT_GATES["min_recall"],
            {"actual": metrics.get("recall"), "required": DEFAULT_GATES["min_recall"]},
        ),
        check(
            "metric_f1_gate",
            float(metrics.get("f1_score", 0.0)) >= DEFAULT_GATES["min_f1_score"],
            {"actual": metrics.get("f1_score"), "required": DEFAULT_GATES["min_f1_score"]},
        ),
        check(
            "metric_roc_auc_gate",
            float(metrics.get("roc_auc", 0.0)) >= DEFAULT_GATES["min_roc_auc"],
            {"actual": metrics.get("roc_auc"), "required": DEFAULT_GATES["min_roc_auc"]},
        ),
        check(
            "metric_false_positive_rate_gate",
            false_positive_rate <= DEFAULT_GATES["max_false_positive_rate"],
            {"actual": false_positive_rate, "required": DEFAULT_GATES["max_false_positive_rate"]},
        ),
        check(
            "confusion_matrix_present",
            (tn + fp + fn + tp) > 0,
            {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        ),
    ]


def data_volume_checks(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    train_rows = int((metrics.get("train_shape") or [0])[0] or 0)
    test_rows = int((metrics.get("test_shape") or [0])[0] or 0)
    return [
        check(
            "train_row_volume_gate",
            train_rows >= DEFAULT_GATES["min_train_rows_for_operational_claim"],
            {
                "actual": train_rows,
                "required": DEFAULT_GATES["min_train_rows_for_operational_claim"],
            },
        ),
        check(
            "test_row_volume_gate",
            test_rows >= DEFAULT_GATES["min_test_rows_for_operational_claim"],
            {
                "actual": test_rows,
                "required": DEFAULT_GATES["min_test_rows_for_operational_claim"],
            },
        ),
    ]


def confusion_values(matrix: Any) -> tuple[int, int, int, int]:
    try:
        tn = int(matrix[0][0])
        fp = int(matrix[0][1])
        fn = int(matrix[1][0])
        tp = int(matrix[1][1])
    except (TypeError, IndexError, ValueError):
        return 0, 0, 0, 0
    return tn, fp, fn, tp


def check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "details": details}


def render_model_card(manifest: dict[str, Any]) -> str:
    readiness = manifest["readiness"]
    lines = [
        "# NDR Scan Detection Model Card",
        "",
        f"- Bundle: {manifest['bundle_name']}",
        f"- Model type: {manifest['model_type']}",
        f"- Created at: {manifest['created_at']}",
        f"- Prediction threshold: {manifest['prediction_threshold']}",
        f"- Feature count: {manifest['feature_count']}",
        f"- Lab integration ready: {readiness['lab_integration_ready']}",
        f"- Operational ready: {readiness['operational_ready']}",
        "",
        "## Intended Use",
        "",
        "Binary scan detection for defensive NDR lab and controlled pilot workflows.",
        "Use real-only metrics as the primary performance evidence.",
        "",
        "## Required Inputs",
        "",
        "Window-level behavioral features. Raw source or destination IP values are not model features.",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {note}" for note in readiness["notes"])
    lines.extend(["", "## Artifacts", ""])
    for name, digest in manifest["artifact_sha256"].items():
        lines.append(f"- `{name}` sha256 `{digest}`")
    lines.append("")
    return "\n".join(lines)


def render_readiness(readiness: dict[str, Any]) -> str:
    lines = [
        "# NDR Model Readiness Report",
        "",
        f"- Lab integration ready: {readiness['lab_integration_ready']}",
        f"- Operational ready: {readiness['operational_ready']}",
        "",
        "| check | passed | details |",
        "| --- | --- | --- |",
    ]
    for item in readiness["checks"]:
        details = json.dumps(item["details"], sort_keys=True)
        lines.append(f"| {item['name']} | {item['passed']} | `{details}` |")
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in readiness["notes"])
    lines.append("")
    return "\n".join(lines)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return read_json(path)


def write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


if __name__ == "__main__":
    main()
