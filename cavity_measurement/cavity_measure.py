"""Planar cavity-opening metrology. Python 3.10+, NumPy, OpenCV.

Run ``python cavity_measure.py --help``. All image coordinates use x,y order.
The four independent fitted lines describe the virtual sharp-corner opening,
not the corner arcs, chamfer depth, cavity bottom, or wall dimensions at depth.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

# A private dependency directory is optional; normal pip installations also work.
_deps = Path(__file__).resolve().parent / "_deps"
if _deps.is_dir():
    sys.path.insert(0, str(_deps))
try:
    import cv2
    import numpy as np
except ImportError as exc:
    raise SystemExit("Install dependencies: python -m pip install -r requirements.txt") from exc


class MeasurementError(ValueError):
    """The input does not provide sufficient trustworthy measurement data."""


@dataclass
class Settings:
    band_px: float = 12.0
    corner_exclusion: float = 0.22
    sample_spacing_px: float = 2.0
    profile_step_px: float = 0.25
    min_gradient: float = 5.0
    min_contrast: float = 12.0
    secondary_peak_ratio: float = 0.75
    ransac_threshold_px: float = 0.7
    ransac_iterations: int = 250
    min_points: int = 15
    min_valid_fraction: float = 0.55
    min_inlier_fraction: float = 0.65
    min_coverage: float = 0.60
    max_rms_px: float = 0.45
    max_parallel_angle_deg: float = 0.20
    max_orthogonal_error_deg: float = 0.50
    polarity: str = "dark"
    seed: int = 20261010

    def validate(self):
        for k, v in asdict(self).items():
            if isinstance(v, (int, float)) and not math.isfinite(v):
                raise MeasurementError(f"Non-finite setting: {k}")
        if not 3 <= self.band_px <= 200:
            raise MeasurementError("band_px must be between 3 and 200")
        if not 0.05 <= self.corner_exclusion < 0.45:
            raise MeasurementError("corner_exclusion must be in [0.05, 0.45)")
        for k in ("sample_spacing_px", "profile_step_px", "min_gradient",
                  "min_contrast", "ransac_threshold_px", "max_rms_px",
                  "max_parallel_angle_deg", "max_orthogonal_error_deg"):
            if getattr(self, k) <= 0:
                raise MeasurementError(f"{k} must be positive")
        if self.profile_step_px > 1:
            raise MeasurementError("profile_step_px must be <= 1")
        for k in ("min_valid_fraction", "min_inlier_fraction", "min_coverage",
                  "secondary_peak_ratio"):
            if not 0 < getattr(self, k) <= 1:
                raise MeasurementError(f"{k} must be in (0, 1]")
        if self.min_points < 5 or self.ransac_iterations < 20:
            raise MeasurementError("min_points >= 5 and ransac_iterations >= 20 required")
        if self.polarity not in ("dark", "bright", "auto"):
            raise MeasurementError("polarity must be dark, bright, or auto")


def read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def default_output_path(command="measure"):
    """Resolve the shared output setting, independent of the shell directory."""
    base = Path(__file__).resolve().parent
    config_file = base / "output_config.json"
    config = read_json(config_file) if config_file.is_file() else {}
    root = Path(config.get("output_root", "图片检测结果")).expanduser()
    if not root.is_absolute():
        root = base / root
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    if command == "demo":
        return root / "合成示例" / stamp
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


def detect_seed(gray, settings, roi=None):
    height, width = gray.shape
    if roi is None:
        x, y, w, h = 0, 0, width, height
    else:
        if len(roi) != 4:
            raise MeasurementError("ROI must be x y width height")
        x, y, w, h = map(int, roi)
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            raise MeasurementError("ROI outside image bounds")
    patch = gray[y:y+h, x:x+w]
    blur = cv2.GaussianBlur(patch, (5, 5), 1.0)
    polarities = [settings.polarity] if settings.polarity != "auto" else ["dark", "bright"]
    candidates = []
    for polarity in polarities:
        kind = cv2.THRESH_BINARY_INV if polarity == "dark" else cv2.THRESH_BINARY
        _, mask = cv2.threshold(blur, 0, 255, kind | cv2.THRESH_OTSU)
        # Closing is only for finding an initial region. Final edges use grayscale.
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            bx, by, bw, bh = cv2.boundingRect(contour)
            if not 0.01 * w * h <= area <= 0.85 * w * h:
                continue
            if bx < 2 or by < 2 or bx + bw >= w - 2 or by + bh >= h - 2:
                continue
            rect = cv2.minAreaRect(contour)
            rw, rh = rect[1]
            if min(rw, rh) < 30 or area / max(rw * rh, 1) < 0.65:
                continue
            corners = cv2.boxPoints(rect).astype(np.float64) + [x, y]
            candidates.append((area * area / (rw * rh), corners, polarity))
    if not candidates:
        raise MeasurementError("No isolated cavity found. Set --roi or --corners; check contrast/polarity")
    candidates.sort(key=lambda c: c[0], reverse=True)
    if len(candidates) > 1 and candidates[1][0] > 0.65 * candidates[0][0]:
        raise MeasurementError("Multiple plausible cavities. Specify a single-cavity --roi or --corners")
    return order_corners(candidates[0][1]), candidates[0][2]


def fit_tls(points, normal_hint=None):
    center = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - center, full_matrices=False)
    normal = vt[-1]
    if normal_hint is not None and normal @ normal_hint < 0:
        normal = -normal
    return np.r_[normal, -normal @ center]


def robust_line(points, normal_hint, settings, rng):
    if len(points) < settings.min_points:
        raise MeasurementError("Insufficient edge points for line fitting")
    best = None
    best_key = (-1, -math.inf)
    span = np.linalg.norm(np.ptp(points, axis=0))
    for _ in range(settings.ransac_iterations):
        a, b = points[rng.choice(len(points), 2, replace=False)]
        delta = b - a
        if np.linalg.norm(delta) < 0.25 * span:
            continue
        normal = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
        if abs(normal @ normal_hint) < math.cos(math.radians(15)):
            continue
        line = np.r_[normal, -normal @ a]
        residual = np.abs(points @ line[:2] + line[2])
        mask = residual < settings.ransac_threshold_px
        key = (int(mask.sum()), -float(np.mean(residual[mask] ** 2)))
        if key > best_key:
            best, best_key = mask, key
    if best is None or best.sum() < settings.min_points:
        raise MeasurementError("No stable line model found")
    for _ in range(6):
        line = fit_tls(points[best], normal_hint)
        mask = np.abs(points @ line[:2] + line[2]) < settings.ransac_threshold_px
        if mask.sum() < settings.min_points:
            raise MeasurementError("Line refinement lost support")
        if np.array_equal(mask, best):
            break
        best = mask
    line = fit_tls(points[best], normal_hint)
    return line, best


def extract_edge(gray, a, b, polarity, settings, rng):
    delta = b - a
    length = np.linalg.norm(delta)
    tangent = delta / length
    normal = np.array([-tangent[1], tangent[0]])
    count = min(1000, max(settings.min_points, int(
        length * (1 - 2 * settings.corner_exclusion) / settings.sample_spacing_px)))
    t = np.linspace(settings.corner_exclusion, 1-settings.corner_exclusion, count)
    bases = a + t[:, None] * delta
    offsets = np.linspace(-settings.band_px, settings.band_px,
                          int(math.ceil(2*settings.band_px/settings.profile_step_px)) + 1)
    step = offsets[1] - offsets[0]
    locations = bases[:, None, :] + offsets[None, :, None] * normal
    valid = ((locations[:, :, 0].min(axis=1) >= 1)
             & (locations[:, :, 0].max(axis=1) < gray.shape[1] - 2)
             & (locations[:, :, 1].min(axis=1) >= 1)
             & (locations[:, :, 1].max(axis=1) < gray.shape[0] - 2))
    profiles = cv2.remap(gray, locations[:, :, 0].astype(np.float32),
                         locations[:, :, 1].astype(np.float32), cv2.INTER_LINEAR)
    gradient = np.gradient(profiles, step, axis=1)
    if polarity == "auto":
        contrast = float(np.median(profiles[valid, -4:].mean(axis=1)
                                    - profiles[valid, :4].mean(axis=1))) if valid.any() else 0
        if abs(contrast) < settings.min_contrast:
            raise MeasurementError("Cannot determine edge polarity; choose --polarity dark or bright")
        polarity = "bright" if contrast > 0 else "dark"
    signed = gradient * (-1 if polarity == "dark" else 1)
    points, strengths, sample_indices = [], [], []
    rejected = {"image_border": 0, "low_contrast": 0, "weak_gradient": 0,
                "search_border": 0, "multiple_edges": 0}
    for i, profile in enumerate(profiles):
        if not valid[i]:
            rejected["image_border"] += 1
            continue
        if np.ptp(profile) < settings.min_contrast:
            rejected["low_contrast"] += 1
            continue
        g = signed[i]
        j = int(np.argmax(g))
        if g[j] < settings.min_gradient:
            rejected["weak_gradient"] += 1
            continue
        # Integrate the gradient over a full local window. Taking the maximum
        # derivative and interpolating its three neighbors is unstable on a
        # bilinearly sampled axis-aligned edge (piecewise-constant derivative).
        half_window = min(4.0, settings.band_px-1.0)
        if abs(offsets[j]) > settings.band_px-half_window:
            rejected["search_border"] += 1
            continue
        peaks = np.flatnonzero((g[1:-1] >= g[:-2]) & (g[1:-1] > g[2:])) + 1
        competing = [k for k in peaks if abs(offsets[k]-offsets[j]) > 2.0
                     and g[k] >= settings.secondary_peak_ratio * g[j]]
        if competing:
            rejected["multiple_edges"] += 1
            continue
        local = np.abs(offsets-offsets[j]) <= half_window
        baseline = float(np.median(g[~local])) if np.any(~local) else 0.0
        weights = np.maximum(g[local]-baseline,0)
        if weights.sum() <= 1e-9:
            rejected["weak_gradient"] += 1
            continue
        offset = float(np.sum(offsets[local]*weights)/weights.sum())
        points.append(bases[i] + offset * normal)
        strengths.append(float(g[j]))
        sample_indices.append(i)
    points = np.asarray(points, np.float64).reshape(-1, 2)
    if len(points) < settings.min_points or len(points)/count < settings.min_valid_fraction:
        raise MeasurementError(f"Too few trustworthy edge profiles: {len(points)}/{count}; rejected={rejected}")
    line, inliers = robust_line(points, normal, settings, rng)
    residual = points[inliers] @ line[:2] + line[2]
    coverage = np.ptp(points[inliers] @ tangent) / (length*(1-2*settings.corner_exclusion))
    metrics = {
        "attempted_profiles": count, "accepted_profiles": len(points),
        "inlier_count": int(inliers.sum()), "inlier_fraction": float(inliers.mean()),
        "valid_profile_fraction": len(points)/count,
        "coverage_of_sampled_straight_section": float(coverage),
        "rms_px": float(np.sqrt(np.mean(residual**2))),
        "p95_absolute_residual_px": float(np.percentile(np.abs(residual), 95)),
        "median_gradient_gray_per_px": float(np.median(strengths)),
        "rejected_profiles": rejected, "polarity": polarity,
        "subpixel_method": "background-corrected local gradient centroid",
    }
    reasons = []
    if inliers.mean() < settings.min_inlier_fraction:
        reasons.append("low inlier fraction")
    if coverage < settings.min_coverage:
        reasons.append("insufficient longitudinal coverage")
    if metrics["rms_px"] > settings.max_rms_px:
        reasons.append("excessive fitting residual")
    return line, points, inliers, metrics, reasons


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


def measure_array(image, settings=None, calibration=None, corners=None, roi=None):
    """Return (JSON-compatible report, overlay BGR image, edge-point CSV rows).

    ``corners`` and ``roi`` refer to the original full image, before undistortion.
    Calibration's pixel_to_mm maps UNDISTORTED pixels when intrinsics are supplied.
    A 'measured' status passes the configured image checks; it is not a certificate
    of dimensional accuracy, uncertainty, calibration validity, or part conformity.
    """
    settings = settings or Settings()
    settings.validate()
    if image is None or image.dtype != np.uint8 or image.ndim not in (2, 3):
        raise MeasurementError("Expected an 8-bit grayscale or BGR image")
    height, width = image.shape[:2]
    if min(height, width) < 50:
        raise MeasurementError("Image too small")
    h_mm = check_calibration(calibration, [width, height])
    raw_corners = None if corners is None else points_array(corners)
    if raw_corners is not None and (np.any(raw_corners < 0)
            or np.any(raw_corners >= np.array([width, height]))):
        raise MeasurementError("Seed corners outside original image")
    if calibration and "camera_matrix" in calibration:
        k = np.asarray(calibration["camera_matrix"], np.float64)
        d = np.asarray(calibration["dist_coeffs"], np.float64)
        image = cv2.undistort(image, k, d, None, k)
        if roi is not None:
            x, y, w, h = map(int, roi)
            if x < 0 or y < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
                raise MeasurementError("ROI outside original image")
            rr = undistort_points([[x,y], [x+w,y], [x+w,y+h], [x,y+h]], calibration)
            lo = np.maximum(np.floor(rr.min(axis=0)), 0).astype(int)
            hi = np.minimum(np.ceil(rr.max(axis=0)), [width,height]).astype(int)
            roi = [*lo.tolist(), *(hi-lo).tolist()]
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if raw_corners is None:
        seed, polarity = detect_seed(gray, settings, roi)
        initialization = "automatic_threshold_region"
    else:
        seed = order_corners(undistort_points(raw_corners, calibration))
        polarity = settings.polarity
        initialization = "user_seed_corners"
    smooth = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 0.8)
    rng = np.random.default_rng(settings.seed)
    edge_data, pixel_lines, world_lines, reasons = [], [], [], []
    for i in range(4):
        try:
            line, points, inliers, metrics, edge_reasons = extract_edge(
                smooth, seed[i], seed[(i+1) % 4], polarity, settings, rng)
        except MeasurementError as exc:
            raise MeasurementError(f"Edge {i}: {exc}") from exc
        pixel_lines.append(line)
        world_points = points if h_mm is None else transform_points(points, h_mm)
        world_line = fit_tls(world_points[inliers])
        world_lines.append(world_line)
        metrics["edge_index"] = i
        metrics["line_px_abc"] = line.tolist()
        if h_mm is not None:
            metrics["line_mm_abc"] = world_line.tolist()
            residual_mm = world_points[inliers] @ world_line[:2] + world_line[2]
            metrics["rms_mm"] = float(np.sqrt(np.mean(residual_mm**2)))
        edge_data.append((points, inliers, world_points, metrics))
        reasons.extend(f"edge {i}: {reason}" for reason in edge_reasons)
    virtual_px, _, _, _ = geometry(pixel_lines, seed.mean(axis=0))
    mapped_seed = seed if h_mm is None else transform_points(seed, h_mm)
    virtual, sections, parallel, orthogonal = geometry(world_lines, mapped_seed.mean(axis=0))
    if max(parallel) > settings.max_parallel_angle_deg:
        reasons.append("opposite edges not parallel within configured tolerance")
    if max(orthogonal) > settings.max_orthogonal_error_deg:
        reasons.append("adjacent edges not orthogonal within configured tolerance")
    unit = "px" if h_mm is None else "mm"
    dimensions = None
    if not reasons:
        pair02, pair13 = sections[0]["spacings"][1], sections[1]["spacings"][1]
        dimensions = {"unit": unit, "length": max(pair02, pair13),
                      "width": min(pair02, pair13), "pair_02_spacing": pair02,
                      "pair_13_spacing": pair13,
                      "definition": "center-section spacings along opposite-normal bisectors; length >= width"}
    notes = ["No depth, wall dimensions at depth, corner radius, or chamfer size is measured.",
             "Residuals describe fit consistency, not measurement uncertainty or absolute accuracy.",
             "A consistently wrong optical edge can pass these checks. Inspect overlay against the physical edge."]
    if h_mm is None:
        notes.append("No metric calibration: pixel results only.")
    elif "mm_per_pixel" in calibration:
        notes.append("Scalar scale assumes a frontoparallel plane and stable magnification; it cannot correct tilt.")
    else:
        notes.append("Planar homography applies only at the calibration plane and unchanged camera/workpiece pose.")
    if not calibration or "camera_matrix" not in calibration:
        notes.append("No lens-distortion correction was applied.")
    report = {
        "schema_version": 1,
        "status": "review_required" if reasons else ("pixel_only" if h_mm is None else "measured"),
        "unit": unit, "dimensions": dimensions, "quality_reasons": reasons, "notes": notes,
        "image_size": [width, height], "initialization": initialization,
        "coordinate_system": "undistorted_full_image_px" if calibration and "camera_matrix" in calibration
                             else "original_full_image_px",
        "seed_corners_px": seed.tolist(), "virtual_corners_px": virtual_px.tolist(),
        "virtual_corners_measurement": virtual.tolist(), "section_spacings": sections,
        "opposite_parallel_angles_deg": parallel, "adjacent_orthogonal_errors_deg": orthogonal,
        "edges": [e[3] for e in edge_data], "settings": asdict(settings),
        "calibration": calibration, "software": {"opencv": cv2.__version__, "numpy": np.__version__},
    }
    overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    cv2.polylines(overlay, [np.rint(seed).astype(np.int32)], True, (180,180,0), 1)
    colors = [(40,210,40), (255,170,40), (220,80,200), (30,220,230)]
    rows = []
    for i, (points, inliers, world_points, metrics) in enumerate(edge_data):
        for point, inside, world_point in zip(points, inliers, world_points):
            cv2.circle(overlay, tuple(np.rint(point).astype(int)), 1,
                       colors[i] if inside else (0,0,255), -1)
            rows.append([i, float(point[0]), float(point[1]), int(inside),
                         float(world_point[0]) if h_mm is not None else "",
                         float(world_point[1]) if h_mm is not None else ""])
        a, b = virtual_px[i], virtual_px[(i+1) % 4]
        if np.max(np.abs([a,b])) < 10*max(width,height):
            cv2.line(overlay, tuple(np.rint(a).astype(int)), tuple(np.rint(b).astype(int)), colors[i], 2)
        midpoint = np.rint((a+b)/2).astype(int)
        cv2.putText(overlay, f"E{i} rms={metrics['rms_px']:.3f}px", tuple(midpoint),
                    cv2.FONT_HERSHEY_SIMPLEX, .45, colors[i], 1, cv2.LINE_AA)
    label = report["status"]
    if dimensions:
        label += f"  L={dimensions['length']:.4f} W={dimensions['width']:.4f} {unit}"
    cv2.rectangle(overlay, (0,0), (width,40), (20,20,20), -1)
    cv2.putText(overlay, label, (10,27), cv2.FONT_HERSHEY_SIMPLEX, .62,
                (0,220,255) if reasons else (80,240,80), 1, cv2.LINE_AA)
    return report, overlay, rows


def save_measurement(out, report, overlay, rows):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "result.json", report)
    write_image(out / "overlay.png", overlay)
    with open(out / "edge_points.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["edge", "x_px", "y_px", "ransac_inlier", "x_mm", "y_mm"])
        writer.writerows(rows)


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
                   "image_size": [width,height], "plane": "cavity opening plane"}
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
        "Keep reference and cavity opening coplanar; keep image size, lens, focus, and camera pose unchanged.",
        "Four points can fit exactly; zero fitting residual does not establish accuracy.",
        "Verify using independent known lengths across the field of view before production use.",
    ]
    return calibration


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("measure", help="Measure one cavity opening")
    m.add_argument("--image", required=True, type=Path)
    m.add_argument("--out", type=Path, help="Override output_config.json destination")
    c = m.add_mutually_exclusive_group()
    c.add_argument("--calibration", type=Path)
    c.add_argument("--mm-per-pixel", type=float)
    m.add_argument("--roi", nargs=4, type=int, metavar=("X","Y","W","H"))
    m.add_argument("--corners", type=Path, help="JSON with corners_px: four approximate virtual corners")
    m.add_argument("--config", type=Path, help="JSON object of Settings overrides")
    m.add_argument("--polarity", choices=["dark","bright","auto"])
    m.add_argument("--band-px", type=float)
    c = sub.add_parser("calibrate", help="Fit planar pixel-to-mm mapping from independent reference points")
    c.add_argument("--image", required=True, type=Path)
    c.add_argument("--points", required=True, type=Path)
    c.add_argument("--intrinsics", type=Path, help="Optional calibrated camera_matrix and dist_coeffs JSON")
    c.add_argument("--out", type=Path, help="Override output_config.json destination")
    d = sub.add_parser("demo", help="Generate a synthetic 60x40 mm cavity and measure it")
    d.add_argument("--out", type=Path, help="Override output_config.json destination")
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
        if args.command == "demo":
            from synthetic_demo import run_demo
            return run_demo(args.out)
        config = read_json(args.config) if args.config else {}
        unknown = set(config)-set(Settings.__dataclass_fields__)
        if unknown:
            raise MeasurementError(f"Unknown settings: {sorted(unknown)}")
        if args.polarity:
            config["polarity"] = args.polarity
        if args.band_px is not None:
            config["band_px"] = args.band_px
        calibration = read_json(args.calibration) if args.calibration else None
        if args.mm_per_pixel is not None:
            calibration = {"method":"user_scalar_scale", "mm_per_pixel":args.mm_per_pixel}
        corners = read_json(args.corners)["corners_px"] if args.corners else None
        report, overlay, rows = measure_array(read_image(args.image), Settings(**config),
                                              calibration, corners, args.roi)
        report["input_image"] = str(args.image.resolve())
        save_measurement(args.out, report, overlay, rows)
        print(json.dumps({"status":report["status"], "dimensions":report["dimensions"],
                          "quality_reasons":report["quality_reasons"], "output":str(args.out.resolve())},
                         ensure_ascii=False, allow_nan=False))
        return 2 if report["status"] == "review_required" else 0
    except (ValueError, OSError, KeyError, TypeError, cv2.error) as exc:
        error = {"status":"failed", "dimensions":None, "error":str(exc)}
        # The current result must never retain dimensions from an earlier run.
        if args.out is not None:
            target = args.out.parent if args.command == "calibrate" else args.out
            try:
                write_json(Path(target)/("failure.json" if args.command == "calibrate" else "result.json"), error)
            except OSError:
                pass
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
