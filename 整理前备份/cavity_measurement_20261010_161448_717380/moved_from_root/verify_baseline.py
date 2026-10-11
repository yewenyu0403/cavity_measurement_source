"""Re-run the four source images against a frozen, visually reviewed regression baseline."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from cavity_measure import (analyze_array, cv2, default_output_path, np, read_image,
                            read_json, save_measurement, write_image, write_json)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regression_iou(points, expected, image_size):
    width, height = image_size
    scale = min(1., 1400/max(width, height))
    size = (int(round(height*scale)), int(round(width*scale)))
    masks = []
    for polygon in (points, expected):
        mask = np.zeros(size, np.uint8)
        cv2.fillPoly(mask, [np.rint(np.asarray(polygon)*scale).astype(np.int32)], 1)
        masks.append(mask.astype(bool))
    return float(np.count_nonzero(masks[0] & masks[1])/np.count_nonzero(masks[0] | masks[1]))


def main(argv=None):
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, default=base.parent/"图片")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    manifest = read_json(base/"baseline"/"manifest.json")
    boundary_side = manifest["boundary_side"]
    out = args.out or default_output_path().parent/"四图基准验证"/datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out.mkdir(parents=True, exist_ok=True)
    summary = {"baseline_type": "frozen algorithm contours reviewed visually; not dimensional ground truth",
               "boundary_side": boundary_side,
               "scope": "development regression on four supplied images; not an independent test set",
               "cases": [], "output": str(out.resolve())}
    previews = []
    for case in manifest["cases"]:
        path = args.images/case["filename"]
        entry = {"image": case["filename"], "status": "failed", "regression_pass": False}
        try:
            if file_sha256(path) != case["sha256"]:
                raise ValueError("Source image hash differs from the registered baseline; keep original images")
            report, overlay, rows = analyze_array(read_image(path), detection="outline", boundary_side=boundary_side)
            report["input_image"] = str(path.resolve())
            target = out/path.stem
            save_measurement(target, report, overlay, rows)
            expected = read_json(base/"baseline"/case["reference_file"])
            if expected["boundary_side"] != boundary_side:
                raise ValueError("Baseline boundary side differs from the selected target")
            iou = regression_iou(report["contour"]["points_px"], expected["points_px"], report["image_size"])
            delta = float(np.max(np.abs(np.asarray(report["contour"]["bbox_xywh_px"])-expected["bbox_xywh_px"])))
            entry.update({"status": report["status"], "sha256_verified": True,
                          "regression_mask_iou": iou, "maximum_bbox_change_px": delta,
                          "supported_fraction": report["contour"]["quality"]["supported_fraction"],
                          "point_count": report["contour"]["point_count"],
                          "regression_pass": iou >= 0.995 and delta <= 15,
                          "result_folder": str(target.resolve())})
            preview = cv2.resize(overlay, (800, 800), interpolation=cv2.INTER_AREA)
            cv2.putText(preview, case["id"], (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                        (0, 0, 255), 3, cv2.LINE_AA)
            previews.append(preview)
        except (ValueError, OSError, cv2.error) as exc:
            entry["error"] = str(exc)
        summary["cases"].append(entry)
        print(json.dumps(entry, ensure_ascii=False))
    summary["passed"] = sum(case["regression_pass"] for case in summary["cases"])
    summary["total"] = len(summary["cases"])
    write_json(out/"summary.json", summary)
    if len(previews) == 4:
        sheet = np.vstack([np.hstack(previews[:2]), np.hstack(previews[2:])])
        write_image(out/"四图轮廓总览.jpg", sheet)
    print(json.dumps({"passed": summary["passed"], "total": summary["total"], "output": str(out.resolve())},
                     ensure_ascii=False))
    return 0 if summary["passed"] == summary["total"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
