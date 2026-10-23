"""Measure all supported images in one folder and export a size summary."""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from cavity_measure import (analyze_array, cv2, default_output_path, format_dimension, np, read_image,
                            read_json, resolve_calibration, save_measurement, save_result_summary, write_image, write_json)
from cavity_measurement.metrology import ContourMeasurementSettings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, default=PROJECT_ROOT.parent/"图片")
    parser.add_argument("--out", type=Path)
    scale = parser.add_mutually_exclusive_group()
    scale.add_argument("--mm-per-pixel", type=float)
    scale.add_argument("--calibration", type=Path)
    scale.add_argument("--pixels-only", action="store_true", help="Ignore the default calibration and output pixels")
    parser.add_argument("--measurement-config", type=Path)
    args = parser.parse_args(argv)
    out = args.out or default_output_path().parent/"尺寸测量"/datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    try:
        if not args.images.is_dir():
            raise ValueError(f"Image folder does not exist: {args.images}")
        paths = sorted(p for p in args.images.iterdir()
                       if p.is_file() and p.suffix.lower() in (".bmp", ".png", ".jpg", ".jpeg", ".tif", ".tiff"))
        if not paths:
            raise ValueError("No supported image files in the selected folder")
        calibration = resolve_calibration(args.calibration, args.mm_per_pixel, args.pixels_only)
        settings = ContourMeasurementSettings(**read_json(args.measurement_config)) if args.measurement_config else None
        if settings:
            settings.validate()
    except (ValueError, OSError, TypeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    cases, previews = [], []
    for path in paths:
        target = out/path.name  # Keep the extension to avoid equal-stem collisions.
        try:
            report, overlay, rows = analyze_array(read_image(path), calibration=calibration,
                                                  detection="contour", boundary_side="inner",
                                                  measurement_settings=settings)
            report["input_image"] = str(path.resolve())
            save_measurement(target, report, overlay, rows)
            preview = cv2.resize(overlay, None, fx=800/max(overlay.shape[:2]), fy=800/max(overlay.shape[:2]),
                                 interpolation=cv2.INTER_AREA)
            preview = cv2.copyMakeBorder(preview, 0, 800-preview.shape[0], 0, 800-preview.shape[1],
                                         cv2.BORDER_CONSTANT, value=(20, 20, 20))
            cv2.putText(preview, f"IMAGE {len(cases)+1}", (12, 78), cv2.FONT_HERSHEY_SIMPLEX,
                        .8, (0, 0, 255), 2, cv2.LINE_AA)
            previews.append(preview)
        except (ValueError, OSError, KeyError, TypeError, cv2.error) as exc:
            report = {"status": "failed", "dimensions": None, "error": str(exc),
                      "input_image": str(path.resolve())}
            write_json(target/"result.json", report)
            save_result_summary(target, report)
        case = {"image": path.name, "status": report["status"], "dimensions": report["dimensions"],
                "quality_reasons": report.get("quality_reasons", []), "error": report.get("error", ""),
                "output": str(target.resolve())}
        cases.append(case)
        print(json.dumps(case, ensure_ascii=False))
    passed = sum(case["dimensions"] is not None for case in cases)
    summary = {"passed": passed, "total": len(cases), "boundary_side": "inner", "cases": cases,
               "output": str(out.resolve()),
               "scope": "selected optical boundary dimensions; no absolute accuracy or uncertainty certification"}
    write_json(out/"summary.json", summary)
    with (out/"尺寸汇总.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["图片", "状态", "单位", "长度", "宽度", "检查信息", "结果目录"])
        for case in cases:
            dims = case["dimensions"] or {}
            writer.writerow([case["image"], case["status"], dims.get("unit", ""),
                             format_dimension(dims.get("length")), format_dimension(dims.get("width")),
                             "; ".join(case["quality_reasons"])+case["error"], case["output"]])
    if previews:
        if len(previews) % 2:
            previews.append(np.zeros_like(previews[0]))
        sheet = np.vstack([np.hstack(previews[i:i+2]) for i in range(0, len(previews), 2)])
        write_image(out/"尺寸测量总览.jpg", sheet)
    print(json.dumps({"passed": passed, "total": len(cases), "output": str(out.resolve())}, ensure_ascii=False))
    return 0 if passed == len(cases) else 2


if __name__ == "__main__":
    raise SystemExit(main())
