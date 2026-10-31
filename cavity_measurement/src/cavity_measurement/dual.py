"""Two optical edges of one rim, with independent statuses and measurement units."""
from pathlib import Path
import csv
from .measurement import (MeasurementError, calibration_caption, check_calibration,
                          contour_array, cv2, format_dimension, np,
                          save_measurement, save_result_summary, write_image, write_json)

SIDES = ("inner", "outer")
LABELS = {"inner": "底面候选边缘（A 内沿）", "outer": "外边缘（黑边外沿）"}
FOLDERS = {"inner": "底面边缘", "outer": "外边缘"}
COLORS = {"inner": (0, 240, 0), "outer": (255, 0, 255)}
ERRORS = (ValueError, OSError, KeyError, TypeError, cv2.error)


def failed_both(message, input_image=""):
    return {"schema_version": 3, "boundary_side": "both", "status": "failed",
            "dimensions": None, "input_image": input_image, "error": message,
            "quality_reasons": [message], "boundaries": {
                side: {"status": "failed", "dimensions": None, "error": message,
                       "quality_reasons": [message]} for side in SIDES}}


def boundary_cases(report):
    return [{"boundary_side": side, "boundary_label": LABELS[side],
             "status": report["boundaries"][side]["status"],
             "dimensions": report["boundaries"][side].get("dimensions"),
             "quality_reasons": report["boundaries"][side].get("quality_reasons", []),
             "error": report["boundaries"][side].get("error", "")}
            for side in SIDES]


def analyze_both(image, calibration=None, roi=None, detection="auto", measurement_settings=None):
    if image is None or image.dtype != np.uint8 or image.ndim not in (2, 3):
        raise MeasurementError("Expected an 8-bit grayscale or BGR image")
    check_calibration(calibration, list(image.shape[1::-1]))
    boundaries, payload = {}, {}
    for side in SIDES:
        try:
            seed = boundaries.get("inner", {}).get("contour", {}).get("points_px") if side == "outer" else None
            result, overlay, rows = contour_array(image, calibration, roi, side,
                                                  metric_coordinates=side == "inner",
                                                  texture_seed=True, seed_override=seed,
                                                  keep_review_candidates=True)
            if detection != "outline" and result["status"] != "review_required":
                from .metrology import attach_contour_dimensions
                result, overlay, rows = attach_contour_dimensions(result, overlay, measurement_settings)
            if side == "outer":
                result["notes"].append("Outer edge is pixel-only: the inner-plane metric scale is not transferred to another height. Shared lens correction is retained when supplied.")
            boundaries[side] = result
            payload[side] = (overlay, rows)
        except ERRORS as exc:
            boundaries[side] = {"status": "failed", "dimensions": None,
                                "quality_reasons": [str(exc)], "error": str(exc)}
    relationship = {"status": "not_checked"}
    if all("contour" in boundaries[s] and not boundaries[s]["contour"]["quality"].get("review_reasons") for s in SIDES):
        outer = np.asarray(boundaries["outer"]["contour"]["points_px"], np.float32)
        inner = np.asarray(boundaries["inner"]["contour"]["points_px"], np.float32)
        distances = np.array([cv2.pointPolygonTest(outer, tuple(map(float, p)), True) for p in inner])
        nested = bool(distances.min() >= -1.5 and np.median(distances) > 1.5
                      and abs(cv2.contourArea(outer)) > abs(cv2.contourArea(inner)))
        relationship = {"status": "nested" if nested else "review_required",
                        "definition": "2D containment only; not physical wall thickness or depth"}
        if not nested:
            for result in boundaries.values():
                result.update({"status": "review_required", "measurement_status": "review_required",
                               "dimensions": None, "pixel_dimensions": None})
                result.setdefault("quality_reasons", []).append("Contours do not form a nested pair of one rim")
            payload = {}
    bad = [s for s in SIDES if boundaries[s]["status"] in ("failed", "review_required")]
    status = "completed" if not bad else ("failed" if all(boundaries[s]["status"] == "failed" for s in SIDES) else "review_required")
    report = {"schema_version": 3, "boundary_side": "both", "status": status, "dimensions": None,
              "image_size": list(image.shape[1::-1]), "boundaries": boundaries, "relationship": relationship,
              "quality_reasons": [f"{LABELS[s]}: "+"; ".join(boundaries[s].get("quality_reasons", [])) for s in bad],
              "notes": ["Inner = user-selected A dark-to-bright edge, treated as a floor candidate; physical depth is unverified.",
                        "Outer = exterior-to-dark edge of the same visible rim; no depth or wall thickness is inferred.",
                        "The existing metric calibration applies to the inner edge only; the outer edge is pixel-only."]}
<<<<<<< HEAD
    measured_inner = payload.get("inner", (None, []))[0] if boundaries["inner"].get("dimensions") else None
    overlay = comparison_overlay(image, report, calibration, measurement_overlay=measured_inner)
=======
    overlay = comparison_overlay(image, report, calibration)
>>>>>>> ca0e77ee125e049605093452d1724d6d6f28137f
    for side in SIDES:
        if side not in payload:
            payload[side] = (comparison_overlay(image, dict(report, boundaries={side: boundaries[side]}), calibration), [])
    return report, overlay, payload


<<<<<<< HEAD
def comparison_overlay(image, report, calibration=None, measurement_overlay=None):
    if measurement_overlay is not None:
        # Preserve accepted A-edge dimensions and arrows in the main comparison.
        overlay = measurement_overlay.copy()
    else:
        if calibration and "camera_matrix" in calibration:
            k = np.asarray(calibration["camera_matrix"], np.float64)
            image = cv2.undistort(image, k, np.asarray(calibration["dist_coeffs"], np.float64), None, k)
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
=======
def comparison_overlay(image, report, calibration=None):
    if calibration and "camera_matrix" in calibration:
        k = np.asarray(calibration["camera_matrix"], np.float64)
        image = cv2.undistort(image, k, np.asarray(calibration["dist_coeffs"], np.float64), None, k)
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
>>>>>>> ca0e77ee125e049605093452d1724d6d6f28137f
    factor = max(1., overlay.shape[1]/1600)
    thickness = max(2, int(round(factor)))
    for side, result in report["boundaries"].items():
        if "contour" not in result:
            continue
        points = np.rint(result["contour"]["points_px"]).astype(np.int32)
        if result["contour"]["closed"]:
            cv2.polylines(overlay, [points], True, COLORS[side], thickness, cv2.LINE_AA)
        else:
            for i, point in enumerate(points):
                following = points[(i+1) % len(points)]
                if np.linalg.norm(following-point) <= 3*result["contour"]["settings"]["sample_spacing_px"]:
                    cv2.line(overlay, tuple(point), tuple(following), COLORS[side], thickness, cv2.LINE_AA)
        for i, good in enumerate(result["contour"]["directly_supported"]):
            if not good and np.linalg.norm(points[(i+1) % len(points)]-points[i]) <= 3*result["contour"]["settings"]["sample_spacing_px"]:
                cv2.line(overlay, tuple(points[i]), tuple(points[(i+1) % len(points)]),
                         (0, 220, 255), thickness+1, cv2.LINE_AA)
    cv2.rectangle(overlay, (0, 0), (overlay.shape[1], int(120*factor)), (20, 20, 20), -1)
    for i, (side, result) in enumerate(report["boundaries"].items()):
        name = "INNER A / FLOOR CANDIDATE (green)" if side == "inner" else "OUTER (magenta)"
        text = f"{name}: {result['status']}"
        dims = result.get("dimensions")
        if dims:
            text += f"  L={format_dimension(dims['length'])} W={format_dimension(dims['width'])} {dims['unit']}"
        cv2.putText(overlay, text, (int(12*factor), int((30+32*i)*factor)), cv2.FONT_HERSHEY_SIMPLEX,
                    .57*factor, COLORS[side], max(1, int(1.5*factor)), cv2.LINE_AA)
    cv2.putText(overlay, calibration_caption(calibration), (int(12*factor), int(105*factor)),
                cv2.FONT_HERSHEY_SIMPLEX, .6*factor, (180, 210, 240), max(1, int(1.5*factor)), cv2.LINE_AA)
    return overlay


def save_both_summary(out, report):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lines = ["外边缘与底面候选边缘检测", f"整体状态：{report['status']}",
             "绿色：底面候选边缘（A 内沿）；品红色：外边缘；黄色轮廓段：灰度支持不足。",
             "底面候选边缘沿用用户指定的 A 内沿，实际高度尚未验证。"]
    if report.get("input_image"):
        lines.append(f"图片：{report['input_image']}")
    with (out/"dimensions.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "boundary_side", "boundary_label", "status", "unit", "length", "width", "check_info"])
        for case in boundary_cases(report):
            dims = case["dimensions"] or {}
            reasons = case["quality_reasons"] or ([case["error"]] if case["error"] else [])
            info = "; ".join(reasons)
            writer.writerow([report.get("input_image", ""), case["boundary_side"], case["boundary_label"],
                             case["status"], dims.get("unit", ""), format_dimension(dims.get("length")),
                             format_dimension(dims.get("width")), info])
            lines += ["", f"{case['boundary_label']}：{case['status']}"]
            if dims:
                lines += [f"长度：{format_dimension(dims['length'])} {dims['unit']}",
                          f"宽度：{format_dimension(dims['width'])} {dims['unit']}"]
            else:
                lines.append("没有可接受的长度、宽度结果。")
            if info:
                lines.append(f"检查信息：{info}")
    lines += ["", "现有标定仅用于 A 内沿；外边缘输出像素，不能直接与毫米值相减。",
              "初步标定尚需独立精度验证；两条轮廓的间距不代表壁厚或腔深。"]
    (out/"尺寸结果.txt").write_text("\n".join(lines)+"\n", encoding="utf-8-sig")


def save_both(out, report, overlay, payload):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for side, child in report["boundaries"].items():
        child["input_image"] = report.get("input_image", "")
        target = out/FOLDERS[side]
        if side in payload:
            picture, rows = payload[side]
            save_measurement(target, child, picture, rows)
        else:
            write_json(target/"result.json", child)
            save_result_summary(target, child)
    write_json(out/"result.json", report)
    save_both_summary(out, report)
    if overlay is not None:
        write_image(out/"overlay.png", overlay)
        scale = min(1., 1600/max(overlay.shape[:2]))
        write_image(out/"overlay_preview.jpg", cv2.resize(overlay, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA))
