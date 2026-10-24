"""Complete cavity-opening contour detection and planar line metrology.

Run ``python cavity_measure.py --help``. All image coordinates use x,y order.
The four independent fitted lines describe the selected optical boundary at
its measurement plane. Corner radius, cavity depth and wall thickness are not
measured. Default inner mode uses the user-confirmed wall-floor optical edge.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

from . import PROJECT_ROOT

try:
    import cv2
    import numpy as np
except ImportError as exc:
    raise SystemExit("Install dependencies: python -m pip install -r requirements.txt") from exc


def format_dimension(value):
    """Format displayed sizes; keep computational and JSON values unrounded."""
    return "" if value is None else f"{value:.3f}"


class MeasurementError(ValueError):
    """The input does not provide sufficient trustworthy measurement data."""


def read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def resolve_calibration(calibration_path=None, mm_per_pixel=None, pixels_only=False):
    """CLI calibration: explicit selection overrides the shared default file.

    Library callers still pass calibration explicitly to analyze_array. Missing
    default files preserve pixel-only use; invalid files must not be ignored.
    """
    if sum((calibration_path is not None, mm_per_pixel is not None, bool(pixels_only))) > 1:
        raise MeasurementError("Choose one of calibration file, scalar scale, or pixels-only")
    if pixels_only:
        return None
    if mm_per_pixel is not None:
        return {"method": "user_scalar_scale", "mm_per_pixel": mm_per_pixel}
    if calibration_path is not None:
        return read_json(calibration_path)
    default_file = PROJECT_ROOT / "config" / "calibration.json"
    return read_json(default_file) if default_file.is_file() else None


def calibration_caption(calibration):
    if calibration is None:
        return "NO METRIC CALIBRATION - IMAGE PIXELS ONLY"
    if str(calibration.get("quality_status", "")).startswith("provisional"):
        return "INITIAL CALIBRATION SCALE - ACCURACY NOT VERIFIED"
    return "CALIBRATED PLANE - VERIFY ACCURACY INDEPENDENTLY"


def default_output_path(command="measure"):
    """Resolve the shared output setting, independent of the shell directory."""
    base = PROJECT_ROOT
    config_file = base / "config" / "output_config.json"
    config = read_json(config_file) if config_file.is_file() else {}
    root = Path(config.get("output_root", "图片检测结果")).expanduser()
    if not root.is_absolute():
        root = base / root
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    if command == "calibrate":
        return root / "标定" / stamp / "calibration.json"
    return root / stamp


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
                    encoding="utf-8")


def read_image(path):
    try:
        image = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    except (OSError, cv2.error) as exc:
        raise MeasurementError(f"Cannot read image: {path}") from exc
    if image is None:
        raise MeasurementError(f"Cannot decode image: {path}")
    return image


def write_image(path, image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, data = cv2.imencode(path.suffix, image)
    if not ok:
        raise MeasurementError(f"Cannot encode image: {path}")
    data.tofile(str(path))


def points_array(value, min_count=4):
    a = np.asarray(value, dtype=np.float64)
    if a.ndim != 2 or a.shape[1] != 2 or len(a) < min_count or not np.isfinite(a).all():
        raise MeasurementError(f"Expected at least {min_count} finite [x,y] points")
    return a


def order_corners(points):
    p = points_array(points)
    if len(p) != 4:
        raise MeasurementError("Exactly four seed corners required")
    center = p.mean(axis=0)
    p = p[np.argsort(np.arctan2(p[:, 1] - center[1], p[:, 0] - center[0]))]
    p = np.roll(p, -int(np.argmin(p.sum(axis=1))), axis=0)
    if (not cv2.isContourConvex(p.astype(np.float32))
            or abs(cv2.contourArea(p.astype(np.float32))) < 100
            or np.min(np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1)) < 20):
        raise MeasurementError("Seed corners must form a convex quadrilateral with sides >=20 px")
    return p


def transform_points(points, matrix):
    p = points_array(points, min_count=1)
    h = np.asarray(matrix, dtype=np.float64)
    if h.shape != (3, 3) or not np.isfinite(h).all() or np.linalg.matrix_rank(h) < 3:
        raise MeasurementError("Invalid pixel_to_mm homography")
    q = np.column_stack((p, np.ones(len(p)))) @ h.T
    w = q[:, 2]
    if np.any(np.abs(w) < 1e-10) or np.any(np.sign(w) != np.sign(w[0])):
        raise MeasurementError("Homography horizon intersects measurement points")
    return q[:, :2] / w[:, None]


def check_calibration(calibration, image_size):
    if calibration is None:
        return None
    if "image_size" in calibration and list(calibration["image_size"]) != list(image_size):
        raise MeasurementError("Calibration image_size differs from input; do not resize calibrated images")
    has_h = "pixel_to_mm" in calibration
    has_s = "mm_per_pixel" in calibration
    if has_h == has_s:
        raise MeasurementError("Calibration must contain exactly one of pixel_to_mm or mm_per_pixel")
    if has_s:
        s = float(calibration["mm_per_pixel"])
        if not math.isfinite(s) or s <= 0:
            raise MeasurementError("mm_per_pixel must be finite and positive")
        h = np.diag([s, s, 1.0])
    else:
        h = np.asarray(calibration["pixel_to_mm"], np.float64)
    transform_points([[0, 0], [image_size[0], 0], image_size,
                      [0, image_size[1]]], h)
    if ("camera_matrix" in calibration) != ("dist_coeffs" in calibration):
        raise MeasurementError("camera_matrix and dist_coeffs must be provided together")
    if "camera_matrix" in calibration:
        k = np.asarray(calibration["camera_matrix"], np.float64)
        d = np.asarray(calibration["dist_coeffs"], np.float64).reshape(-1)
        if (k.shape != (3, 3) or not np.isfinite(k).all() or k[0, 0] <= 0
                or k[1, 1] <= 0 or len(d) not in (4, 5, 8, 12, 14)
                or not np.isfinite(d).all()):
            raise MeasurementError("Invalid camera_matrix or distortion coefficients")
    return h


def undistort_points(points, calibration):
    if calibration is None or "camera_matrix" not in calibration:
        return np.asarray(points, np.float64)
    k = np.asarray(calibration["camera_matrix"], np.float64)
    d = np.asarray(calibration["dist_coeffs"], np.float64)
    return cv2.undistortPoints(np.asarray(points, np.float64).reshape(-1, 1, 2),
                               k, d, P=k).reshape(-1, 2)


def fit_tls(points, normal_hint=None):
    center = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - center, full_matrices=False)
    normal = vt[-1]
    if normal_hint is not None and normal @ normal_hint < 0:
        normal = -normal
    return np.r_[normal, -normal @ center]


def robust_line(points, normal_hint, min_points, threshold_px, rng, iterations=250):
    if len(points) < min_points:
        raise MeasurementError("Insufficient edge points for line fitting")
    best = None
    best_key = (-1, -math.inf)
    span = np.linalg.norm(np.ptp(points, axis=0))
    for _ in range(iterations):
        a, b = points[rng.choice(len(points), 2, replace=False)]
        delta = b - a
        if np.linalg.norm(delta) < 0.25 * span:
            continue
        normal = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
        if abs(normal @ normal_hint) < math.cos(math.radians(15)):
            continue
        line = np.r_[normal, -normal @ a]
        residual = np.abs(points @ line[:2] + line[2])
        mask = residual < threshold_px
        key = (int(mask.sum()), -float(np.mean(residual[mask] ** 2)))
        if key > best_key:
            best, best_key = mask, key
    if best is None or best.sum() < min_points:
        raise MeasurementError("No stable line model found")
    for _ in range(6):
        line = fit_tls(points[best], normal_hint)
        mask = np.abs(points @ line[:2] + line[2]) < threshold_px
        if mask.sum() < min_points:
            raise MeasurementError("Line refinement lost support")
        if np.array_equal(mask, best):
            break
        best = mask
    line = fit_tls(points[best], normal_hint)
    return line, best


def intersect(line_a, line_b):
    matrix = np.stack((line_a[:2], line_b[:2]))
    if abs(np.linalg.det(matrix)) < 1e-8:
        raise MeasurementError("Adjacent fitted lines are nearly parallel")
    return np.linalg.solve(matrix, -np.array([line_a[2], line_b[2]]))


def angle_between(line_a, line_b):
    return math.degrees(math.acos(float(np.clip(abs(line_a[:2] @ line_b[:2]), 0, 1))))


def geometry(lines, center):
    # Normals point toward the center so opposite inward normals can be averaged.
    lines = [line.copy() for line in lines]
    for line in lines:
        if line[:2] @ center + line[2] < 0:
            line *= -1
    corners = np.array([intersect(lines[(i-1) % 4], lines[i]) for i in range(4)])
    if not cv2.isContourConvex(corners.astype(np.float32)):
        raise MeasurementError("Fitted lines do not enclose a convex cavity")
    center = corners.mean(axis=0)
    sections = []
    for ia, ib in ((0, 2), (1, 3)):
        normal = lines[ia][:2] - lines[ib][:2]
        normal /= np.linalg.norm(normal)
        tangent = np.array([-normal[1], normal[0]])
        low, high = np.min(corners @ tangent), np.max(corners @ tangent)
        values = []
        for fraction in (0.25, 0.50, 0.75):
            location = center + (low+(high-low)*fraction-center @ tangent)*tangent
            distances = [-(lines[i][:2] @ location+lines[i][2]) /
                         (lines[i][:2] @ normal) for i in (ia, ib)]
            values.append(float(abs(distances[1]-distances[0])))
        sections.append({"edge_pair": [ia, ib], "fractions_along_opening": [0.25, 0.5, 0.75],
                         "spacings": values, "direction": normal.tolist()})
    parallel = [angle_between(lines[0], lines[2]), angle_between(lines[1], lines[3])]
    orthogonal = [90-angle_between(lines[i], lines[(i+1) % 4]) for i in range(4)]
    return corners, sections, parallel, orthogonal


def contour_array(image, calibration=None, roi=None, boundary_side="inner", metric_coordinates=True,
                  texture_seed=False, seed_override=None, keep_review_candidates=False):
    """Identify the complete opening outline; dimensional validation is separate."""
    from .contour import ContourSettings, find_opening
    if image is None or image.dtype != np.uint8 or image.ndim not in (2, 3):
        raise MeasurementError("Expected an 8-bit grayscale or BGR image")
    height, width = image.shape[:2]
    h_mm = check_calibration(calibration, [width, height])
    if not metric_coordinates:
        h_mm = None
    if calibration and "camera_matrix" in calibration:
        k = np.asarray(calibration["camera_matrix"], np.float64)
        d = np.asarray(calibration["dist_coeffs"], np.float64)
        image = cv2.undistort(image, k, d, None, k)
        if roi is not None:
            x, y, w, h = map(int, roi)
            if min(x, y) < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
                raise MeasurementError("ROI outside original image")
            rr = undistort_points([[x,y], [x+w,y], [x+w,y+h], [x,y+h]], calibration)
            lo = np.maximum(np.floor(rr.min(axis=0)), 0).astype(int)
            hi = np.minimum(np.ceil(rr.max(axis=0)), [width,height]).astype(int)
            roi = [*lo.tolist(), *(hi-lo).tolist()]
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    contour = find_opening(gray, roi, ContourSettings(boundary_side=boundary_side),
                           allow_texture_seed=texture_seed, seed_override=seed_override,
                           keep_review_candidates=keep_review_candidates)
    points = np.asarray(contour["points_px"], np.float64)
    if h_mm is not None:
        contour["points_mm"] = transform_points(points, h_mm).tolist()
    report = {
        "schema_version": 2, "status": "contour_detected", "dimensions": None,
        "unit": "px", "measurement_status": "not_performed", "quality_reasons": [],
        "image_size": [width, height], "initialization": "automatic_dark_rim",
        "coordinate_system": "undistorted_full_image_px" if calibration and "camera_matrix" in calibration
                             else "original_full_image_px",
        "contour": contour, "calibration": calibration if metric_coordinates else None,
        "notes": [
            "Complete selected boundary detected, including rounded corners. Dimensional measurement was not performed.",
            "Inner mode follows target A confirmed by the user: dark band to brighter cavity. Single-view optics do not establish depth or metric accuracy.",
            "Convexity initializes the search only. Continuity tracking regularizes the result; weak segments are marked yellow.",
            "Pixel contours and successful regression checks do not establish metric accuracy or uncertainty.",
        ],
        "software": {"opencv": cv2.__version__, "numpy": np.__version__},
    }
    if contour["quality"].get("review_reasons"):
        report.update({"status": "review_required", "measurement_status": "review_required",
                       "quality_reasons": contour["quality"]["review_reasons"]})
        report["notes"][0] = "Unverified contour candidate only: grayscale or continuity checks failed. No dimensions are accepted."
    overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    integer_points = np.rint(points).astype(np.int32)
    line_width = max(2, int(round(max(width, height)/1400*2)))
    if contour["closed"]:
        cv2.polylines(overlay, [integer_points], True, (0, 240, 0), line_width, cv2.LINE_AA)
    else:
        for i, point in enumerate(integer_points):
            following = integer_points[(i+1) % len(points)]
            if np.linalg.norm(following-point) <= 3*contour["settings"]["sample_spacing_px"]:
                cv2.line(overlay, tuple(point), tuple(following), (0, 240, 0), line_width, cv2.LINE_AA)
    supported = contour["directly_supported"]
    for i, good in enumerate(supported):
        if not good and np.linalg.norm(integer_points[(i+1) % len(points)]-integer_points[i]) <= 3*contour["settings"]["sample_spacing_px"]:
            cv2.line(overlay, tuple(integer_points[i]), tuple(integer_points[(i+1) % len(points)]),
                     (0, 220, 255), line_width+1, cv2.LINE_AA)
    factor = max(1., width/1600)
    cv2.rectangle(overlay, (0, 0), (width, int(55*factor)), (20, 20, 20), -1)
    label = f"{boundary_side.upper()} CONTOUR  support={contour['quality']['supported_fraction']:.1%}  dimensions=not measured"
    if report["status"] == "review_required":
        label = f"{boundary_side.upper()} REVIEW CANDIDATE - NO ACCEPTED DIMENSIONS"
    cv2.putText(overlay, label, (int(12*factor), int(36*factor)), cv2.FONT_HERSHEY_SIMPLEX,
                0.7*factor, (80, 240, 80), max(1, int(2*factor)), cv2.LINE_AA)
    return report, overlay, []


def analyze_array(image, calibration=None, roi=None, detection="auto", boundary_side="inner", measurement_settings=None):
    """Measure the selected dark-rim boundary; outline mode stops after the contour."""
    if detection not in ("auto", "outline", "contour"):
        raise MeasurementError("detection must be auto, outline, or contour")
    if boundary_side == "both":
        from .dual import analyze_both
        return analyze_both(image, calibration, roi, detection, measurement_settings)
    if boundary_side not in ("inner", "outer"):
        raise MeasurementError("boundary_side must be inner, outer, or both")
    report, overlay, rows = contour_array(image, calibration, roi, boundary_side)
    if detection == "outline":
        return report, overlay, rows
    from .metrology import attach_contour_dimensions
    return attach_contour_dimensions(report, overlay, measurement_settings)


def save_result_summary(out, report):
    """Write human-readable sizes and a one-row CSV, also clearing failed sizes."""
    if report.get("boundary_side") == "both":
        from .dual import save_both_summary
        return save_both_summary(out, report)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dims = report.get("dimensions") or {}
    label = {"pixel_only": "像素尺寸测量完成（未标定）", "measured": "已按输入标定换算尺寸",
             "contour_detected": "仅识别轮廓，未执行尺寸测量", "review_required": "尺寸检查未通过，需要复核",
             "failed": "检测失败"}.get(report["status"], report["status"])
    lines = [label, f"状态：{report['status']}"]
    if report.get("input_image"):
        lines.append(f"图片：{report['input_image']}")
    if "contour" in report:
        side = report["contour"]["boundary_side"]
        lines.append("边界：A 内边框（外围黑边靠腔内的一沿）" if side == "inner" else "边界：黑边外侧轮廓")
    if dims:
        lines += [f"长度：{format_dimension(dims['length'])} {dims['unit']}", f"宽度：{format_dimension(dims['width'])} {dims['unit']}",
                  "定义：四条直边独立拟合后的中央截面对边间距；圆角不参与拟合，长度取较大值。"]
    else:
        lines.append("没有可接受的长度、宽度结果。")
    lines += [f"检查信息：{reason}" for reason in report.get("quality_reasons", [])]
    if report.get("error"):
        lines.append(f"错误：{report['error']}")
    if not dims or dims.get("unit") == "px":
        lines.append("未得到毫米尺寸；需要所选边缘所在测量平面的独立标定。")
    calibration = report.get("calibration")
    if calibration and str(calibration.get("quality_status", "")).startswith("provisional"):
        if "mm_per_pixel" in calibration:
            lines.append(f"默认初步标定比例：{calibration['mm_per_pixel']:.12f} mm/像素。")
        lines.append("当前标定为初步结果，尚需独立精度验证。")
    lines.append("拟合残差不是测量不确定度；此结果不证明实际尺寸精度或工件合格。")
    (out/"尺寸结果.txt").write_text("\n".join(lines)+"\n", encoding="utf-8-sig")
    with (out/"dimensions.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "status", "unit", "length", "width", "pair_02_spacing", "pair_13_spacing"])
        writer.writerow([report.get("input_image", ""), report["status"], dims.get("unit", ""),
                         *[format_dimension(dims.get(key)) for key in ("length", "width", "pair_02_spacing", "pair_13_spacing")]])


def save_measurement(out, report, overlay, rows):
    if report.get("boundary_side") == "both":
        from .dual import save_both
        return save_both(out, report, overlay, rows)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "result.json", report)
    save_result_summary(out, report)
    write_image(out / "overlay.png", overlay)
    if "contour" in report:
        contour = report["contour"]
        mask = np.zeros(overlay.shape[:2], np.uint8)
        if contour["closed"]:
            cv2.fillPoly(mask, [np.rint(contour["points_px"]).astype(np.int32)], 255)
        write_image(out / "contour_mask.png", mask)
        with open(out / "contour_points.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["index", "x_px", "y_px", "gradient_gray_per_px", "directly_supported", "x_mm", "y_mm"])
            for i, (point, gradient, supported) in enumerate(zip(contour["points_px"],
                    contour["gradient_gray_per_px"], contour["directly_supported"])):
                world = contour.get("points_mm")
                writer.writerow([i, *point, gradient, int(supported),
                                 world[i][0] if world else "", world[i][1] if world else ""])
    if "edges" in report:
        with open(out / "edge_points.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["edge", "x_px", "y_px", "fit_inlier", "x_mm", "y_mm"])
            writer.writerows(rows)
    scale = min(1., 1600/max(overlay.shape[:2]))
    preview = cv2.resize(overlay, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    write_image(out / "overlay_preview.jpg", preview)


def build_planar_calibration(image, point_spec, intrinsics=None):
    pixels = points_array(point_spec["image_points_px"])
    world = points_array(point_spec["world_points_mm"])
    height, width = image.shape[:2]
    if len(pixels) != len(world):
        raise MeasurementError("Pixel and world point counts must match")
    if np.any(pixels < 0) or np.any(pixels >= [width,height]):
        raise MeasurementError("Reference pixels outside image")
    for p in (pixels, world):
        hull = cv2.convexHull(p.astype(np.float32))
        if cv2.contourArea(hull) <= 1e-6:
            raise MeasurementError("Reference points must not be collinear")
    calibration = {"schema_version": 1, "method": "planar_homography",
                    "image_size": [width,height], "plane": "selected optical boundary measurement plane"}
    if intrinsics:
        for key in ("camera_matrix", "dist_coeffs"):
            calibration[key] = intrinsics[key]
        # Validate intrinsics before using them.
        check_calibration({**calibration, "mm_per_pixel": 1.0}, [width,height])
        pixels = undistort_points(pixels, calibration)
    matrix, _ = cv2.findHomography(pixels, world, method=0)
    if matrix is None:
        raise MeasurementError("Homography fit failed")
    calibration["pixel_to_mm"] = matrix.tolist()
    check_calibration(calibration, [width,height])
    residuals = np.linalg.norm(transform_points(pixels, matrix)-world, axis=1)
    calibration["reference_point_count"] = len(pixels)
    calibration["reference_fit_rms_mm"] = float(np.sqrt(np.mean(residuals**2)))
    calibration["reference_fit_max_mm"] = float(residuals.max())
    calibration["notes"] = [
        "Coordinates must come from an independent reference, not the nominal cavity being inspected.",
        "Keep reference and selected boundary measurement plane coplanar; keep image size, lens, focus, and camera pose unchanged.",
        "Four points can fit exactly; zero fitting residual does not establish accuracy.",
        "Verify using independent known lengths across the field of view before production use.",
    ]
    return calibration


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("measure", help="Measure one cavity opening")
    m.add_argument("--image", required=True, type=Path)
    m.add_argument("--out", type=Path, help="Override config/output_config.json destination")
    c = m.add_mutually_exclusive_group()
    c.add_argument("--calibration", type=Path)
    c.add_argument("--mm-per-pixel", type=float)
    c.add_argument("--pixels-only", action="store_true", help="Ignore the default calibration and output pixels")
    m.add_argument("--roi", nargs=4, type=int, metavar=("X","Y","W","H"))
    m.add_argument("--detection", choices=["auto", "outline", "contour"], default="auto",
                   help="auto/contour: selected dark-rim contour and dimensions; outline: contour only")
    m.add_argument("--measurement-config", type=Path, help="JSON overrides for ContourMeasurementSettings")
    m.add_argument("--boundary-side", choices=["inner", "outer", "both"], default="inner",
                   help="inner (default): target A; outer: exterior rim; both: separate results and comparison overlay")
    c = sub.add_parser("calibrate", help="Fit planar pixel-to-mm mapping from independent reference points")
    c.add_argument("--image", required=True, type=Path)
    c.add_argument("--points", required=True, type=Path)
    c.add_argument("--intrinsics", type=Path, help="Optional calibrated camera_matrix and dist_coeffs JSON")
    c.add_argument("--out", type=Path, help="Override config/output_config.json destination")
    args = parser.parse_args(argv)
    try:
        if args.out is None:
            args.out = default_output_path(args.command)
        if args.command == "calibrate":
            result = build_planar_calibration(read_image(args.image), read_json(args.points),
                                              read_json(args.intrinsics) if args.intrinsics else None)
            write_json(args.out, result)
            print(json.dumps({"calibration_file": str(args.out),
                              "reference_fit_rms_mm": result["reference_fit_rms_mm"]}, ensure_ascii=False))
            return 0
        outer_pixels = args.boundary_side == "outer" and args.calibration is None and args.mm_per_pixel is None
        calibration = resolve_calibration(args.calibration, args.mm_per_pixel, args.pixels_only or outer_pixels)
        measurement_settings = None
        if args.measurement_config:
            if args.detection == "outline":
                raise MeasurementError("--measurement-config applies to --detection auto or contour")
            from .metrology import ContourMeasurementSettings
            measurement_settings = ContourMeasurementSettings(**read_json(args.measurement_config))
            measurement_settings.validate()
        report, overlay, rows = analyze_array(read_image(args.image), calibration, args.roi,
                                              args.detection, args.boundary_side, measurement_settings)
        report["input_image"] = str(args.image.resolve())
        save_measurement(args.out, report, overlay, rows)
        summary = {"status": report["status"], "dimensions": report["dimensions"],
                   "quality_reasons": report["quality_reasons"], "output": str(args.out.resolve())}
        if args.boundary_side == "both":
            from .dual import boundary_cases
            summary.update({"boundary_side": "both", "boundaries": boundary_cases(report),
                            "message": "外边缘与底面候选边缘已分别处理；请分别查看状态和单位。"})
        if "contour" in report:
            boundary = "A 内边框" if args.boundary_side == "inner" else "黑边外侧轮廓"
            if report["status"] == "contour_detected":
                message = f"{boundary}识别成功（含圆角）；本次仅识别轮廓。"
            elif report["status"] == "review_required":
                message = f"{boundary}已识别，但尺寸检查未通过；请查看检查信息。"
            elif report["unit"] == "px":
                message = f"{boundary}像素尺寸测量完成；未标定，不输出毫米尺寸。"
            else:
                message = f"{boundary}尺寸计算完成，已按输入标定换算为毫米。"
            summary.update({"message": message, "boundary_side": args.boundary_side,
                            "contour_point_count": report["contour"]["point_count"],
                            "supported_fraction": report["contour"]["quality"]["supported_fraction"]})
        print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
        return 2 if report["status"] in ("review_required", "failed") else 0
    except (ValueError, OSError, KeyError, TypeError, cv2.error) as exc:
        error = {"status":"failed", "dimensions":None, "error":str(exc)}
        if args.command == "measure" and args.boundary_side == "both":
            from .dual import failed_both
            error = failed_both(str(exc), str(args.image.resolve()))
        # The current result must never retain dimensions from an earlier run.
        if args.out is not None:
            target = args.out.parent if args.command == "calibrate" else args.out
            try:
                if args.command == "measure" and args.boundary_side == "both":
                    save_measurement(target, error, None, {})
                else:
                    write_json(Path(target)/("failure.json" if args.command == "calibrate" else "result.json"), error)
                if args.command == "measure" and args.boundary_side != "both":
                    save_result_summary(target, error)
            except OSError:
                pass
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
