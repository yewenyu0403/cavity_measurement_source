"""Measure independently fitted straight portions of the selected optical contour.

Pixel quality limits describe this image processing method, not part tolerances
or metrological uncertainty. Rounded corners and unsupported points are omitted.
"""
from dataclasses import asdict, dataclass
import math

from .measurement import (MeasurementError, Settings, calibration_caption, check_calibration, cv2,
                          fit_tls, format_dimension, geometry, np, order_corners, points_array,
                          robust_line, transform_points)


@dataclass
class ContourMeasurementSettings:
    corner_exclusion: float = 0.22
    min_points: int = 15
    min_direct_support: float = 0.95
    min_inlier_fraction: float = 0.80
    min_coverage: float = 0.85
    max_inlier_gap_fraction: float = 0.15
    rejection_sigma: float = 3.0
    min_rejection_threshold_px: float = 1.0
    max_rejection_threshold_px: float = 4.0
    max_inlier_rms_px: float = 1.5
    max_all_rms_px: float = 2.0
    max_all_p95_px: float = 4.0
    max_parallel_angle_deg: float = 0.20
    max_orthogonal_error_deg: float = 0.50
    seed: int = 20261011

    def validate(self):
        for name, value in asdict(self).items():
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise MeasurementError(f"Invalid contour measurement setting: {name}")
        if not 0.05 <= self.corner_exclusion < 0.45:
            raise MeasurementError("corner_exclusion must be in [0.05, 0.45)")
        if not isinstance(self.min_points, int) or self.min_points < 5:
            raise MeasurementError("min_points must be an integer >= 5")
        if not isinstance(self.seed, int):
            raise MeasurementError("seed must be an integer")
        for name in ("min_direct_support", "min_inlier_fraction", "min_coverage", "max_inlier_gap_fraction"):
            if not 0 < getattr(self, name) <= 1:
                raise MeasurementError(f"{name} must be in (0, 1]")
        if self.min_rejection_threshold_px > self.max_rejection_threshold_px:
            raise MeasurementError("Rejection threshold minimum exceeds maximum")


def fit_contour_sides(contour, settings=None, matrix=None):
    """Fit four sides without imposing parallelism or equal angles.

    The minimum-area box labels the sides and excludes their end regions only.
    RANSAC initializes each line; bounded MAD rejection and TLS refine it. All
    supported sample residuals, including rejected points, enter quality checks.
    """
    settings = settings or ContourMeasurementSettings()
    settings.validate()
    points = points_array(contour["points_px"])
    supported = np.asarray(contour["directly_supported"], dtype=bool)
    if supported.shape != (len(points),):
        raise MeasurementError("Contour support flags do not match the point count")
    if supported.sum() < 4:
        raise MeasurementError("Insufficient directly supported contour points")
    box = order_corners(cv2.boxPoints(cv2.minAreaRect(points[supported].astype(np.float32))))
    distances, fractions, normals = [], [], []
    for a, b in zip(box, np.roll(box, -1, axis=0)):
        length = np.linalg.norm(b-a)
        tangent = (b-a)/length
        normal = np.array([-tangent[1], tangent[0]])
        distances.append(np.abs((points-a) @ normal))
        fractions.append((points-a) @ tangent/length)
        normals.append(normal)
    side_ids = np.argmin(distances, axis=0)
    rng = np.random.default_rng(settings.seed)
    ransac = Settings(min_points=settings.min_points,
                      ransac_threshold_px=settings.max_rejection_threshold_px)
    edges, reasons = [], []
    for side in range(4):
        fraction = fractions[side]
        selected = ((side_ids == side) & (fraction >= settings.corner_exclusion)
                    & (fraction <= 1-settings.corner_exclusion))
        count = int(selected.sum())
        indices = np.flatnonzero(selected & supported)
        sample = points[indices]
        if len(sample) < settings.min_points:
            raise MeasurementError(f"Edge {side}: too few directly supported straight-edge points ({len(sample)})")
        line, inliers = robust_line(sample, normals[side], ransac, rng)
        for _ in range(12):
            residual = sample @ line[:2]+line[2]
            sigma = 1.4826*np.median(np.abs(residual-np.median(residual)))
            threshold = float(np.clip(settings.rejection_sigma*sigma,
                                      settings.min_rejection_threshold_px,
                                      settings.max_rejection_threshold_px))
            updated = np.abs(residual) <= threshold
            if updated.sum() < settings.min_points:
                raise MeasurementError(f"Edge {side}: no stable supported line")
            unchanged = np.array_equal(inliers, updated)
            inliers = updated
            line = fit_tls(sample[inliers], normals[side])
            if unchanged:
                break
        residual = sample @ line[:2]+line[2]
        span = 1-2*settings.corner_exclusion
        positions = np.sort(fraction[indices[inliers]])
        coverage = float(np.ptp(positions)/span)
        largest_gap = float(np.max(np.diff(np.r_[settings.corner_exclusion, positions,
                                                1-settings.corner_exclusion]))/span)
        world = sample if matrix is None else transform_points(sample, matrix)
        world_line = line if matrix is None else fit_tls(world[inliers])
        metrics = {
            "edge_index": side, "selected_contour_points": count,
            "accepted_profiles": len(sample), "direct_support_fraction": len(sample)/count,
            "inlier_count": int(inliers.sum()), "inlier_fraction": float(inliers.mean()),
            "coverage_of_sampled_straight_section": coverage,
            "maximum_inlier_gap_fraction": largest_gap,
            "rms_px": float(np.sqrt(np.mean(residual[inliers]**2))),
            "all_supported_rms_px": float(np.sqrt(np.mean(residual**2))),
            "all_supported_p95_absolute_residual_px": float(np.percentile(np.abs(residual), 95)),
            "rejection_threshold_px": threshold, "line_px_abc": line.tolist(),
            "method": "independent RANSAC initialization; bounded MAD rejection; TLS",
            "quality_reasons": [],
        }
        if matrix is not None:
            metrics["line_mm_abc"] = world_line.tolist()
            metrics["rms_mm"] = float(np.sqrt(np.mean((world[inliers] @ world_line[:2]+world_line[2])**2)))
        checks = [(metrics["direct_support_fraction"] < settings.min_direct_support, "insufficient direct grayscale support"),
                  (metrics["inlier_fraction"] < settings.min_inlier_fraction, "low inlier fraction"),
                  (coverage < settings.min_coverage, "insufficient straight-edge coverage"),
                  (largest_gap > settings.max_inlier_gap_fraction, "long unsupported or rejected gap"),
                  (metrics["rms_px"] > settings.max_inlier_rms_px, "excessive inlier fitting residual"),
                  (metrics["all_supported_rms_px"] > settings.max_all_rms_px, "excessive all-sample RMS residual"),
                  (metrics["all_supported_p95_absolute_residual_px"] > settings.max_all_p95_px, "excessive all-sample p95 residual")]
        for failed, reason in checks:
            if failed:
                metrics["quality_reasons"].append(reason)
                reasons.append(f"edge {side}: {reason}")
        edges.append((sample, inliers, world, line, world_line, metrics))
    return box, edges, reasons


def _geometry_reasons(parallel, orthogonal, settings):
    reasons = []
    if max(parallel) > settings.max_parallel_angle_deg:
        reasons.append("opposite edges not parallel within configured tolerance; check perspective or shape")
    if max(orthogonal) > settings.max_orthogonal_error_deg:
        reasons.append("adjacent edges not orthogonal within configured tolerance; check perspective or shape")
    return reasons


def _dimensions(sections, unit):
    a, b = [pair["spacings"][1] for pair in sections]
    return {"unit": unit, "length": max(a, b), "width": min(a, b),
            "pair_02_spacing": a, "pair_13_spacing": b,
            "definition": "center-section spacings between independently fitted straight optical boundaries; rounded corners excluded; length >= width"}


def attach_contour_dimensions(report, overlay, settings=None):
    """Preserve the contour on failure; never replace it with another region."""
    settings = settings or ContourMeasurementSettings()
    settings.validate()
    report.update({"schema_version": 3, "contour_status": "contour_detected",
                   "measurement_method": "selected_contour_independent_straight_sides",
                   "measurement_settings": asdict(settings), "pixel_dimensions": None})
    calibration = report.get("calibration")
    matrix = check_calibration(calibration, report["image_size"])
    unit = "px" if matrix is None else "mm"
    rows = []
    try:
        box, edges, reasons = fit_contour_sides(report["contour"], settings, matrix)
        pixel_lines = [edge[3] for edge in edges]
        world_lines = [edge[4] for edge in edges]
        virtual_px, sections_px, parallel_px, orthogonal_px = geometry(pixel_lines, box.mean(axis=0))
        center = box.mean(axis=0) if matrix is None else transform_points(box, matrix).mean(axis=0)
        virtual, sections, parallel, orthogonal = geometry(world_lines, center)
        pixel_reasons = reasons+_geometry_reasons(parallel_px, orthogonal_px, settings)
        reasons += _geometry_reasons(parallel, orthogonal, settings)
        for section in sections:
            section["unit"] = unit
        for section in sections_px:
            section["unit"] = "px"
        report.update({"edges": [edge[5] for edge in edges],
                       "seed_corners_px": box.tolist(), "virtual_corners_px": virtual_px.tolist(),
                       "virtual_corners_measurement": virtual.tolist(),
                       "section_spacings": sections, "section_spacings_px": sections_px,
                       "opposite_parallel_angles_deg": parallel,
                       "adjacent_orthogonal_errors_deg": orthogonal,
                       "pixel_geometry_reasons": pixel_reasons})
        if not pixel_reasons:
            report["pixel_dimensions"] = _dimensions(sections_px, "px")
        report["dimensions"] = None if reasons else _dimensions(sections, unit)
        for i, (sample, inliers, world, _, _, _) in enumerate(edges):
            for point, inside, mapped in zip(sample, inliers, world):
                rows.append([i, *point.tolist(), int(inside),
                             float(mapped[0]) if matrix is not None else "",
                             float(mapped[1]) if matrix is not None else ""])
        _draw_measurement(overlay, report, pixel_lines, world_lines, virtual, matrix, settings)
    except MeasurementError as exc:
        reasons = [str(exc)]
        report["dimensions"] = None
    status = "review_required" if reasons else ("pixel_only" if matrix is None else "measured")
    report.update({"status": status, "measurement_status": status, "unit": unit,
                   "quality_reasons": reasons})
    report["notes"] = [
        "Dimensions are center-section spacings of the selected optical inner or outer boundary; four sides are fitted independently, without forcing a rectangle.",
        "Rounded corners are excluded. No corner radius, depth, or wall thickness is measured.",
        "Fit residuals and repeated-image differences are not measurement uncertainty or absolute accuracy.",
        "The selected A edge is user-confirmed optically; a single image cannot independently establish its physical depth.",
        ("No metric calibration: dimensions are apparent image pixels, with no perspective or lens correction unless supplied."
         if matrix is None else
         "Calibration must be independently established at the selected boundary plane with unchanged imaging conditions. A supplied scale does not certify accuracy."),
    ]
    if calibration and "mm_per_pixel" in calibration:
        report["notes"].append("Scalar scale assumes a frontoparallel plane; it cannot compensate perspective.")
    if not calibration or "camera_matrix" not in calibration:
        report["notes"].append("No lens-distortion correction was applied.")
    width = overlay.shape[1]
    factor = max(1., width/1600)
    cv2.rectangle(overlay, (0, 0), (width, int(90*factor)), (20, 20, 20), -1)
    label = f"{report['contour']['boundary_side'].upper()}  {status}"
    dims = report["dimensions"]
    if dims:
        label += f"  L={format_dimension(dims['length'])}  W={format_dimension(dims['width'])} {unit}"
    color = (0, 220, 255) if reasons else (80, 240, 80)
    for text, y in [(label, 34), (calibration_caption(calibration), 69)]:
        cv2.putText(overlay, text, (int(12*factor), int(y*factor)), cv2.FONT_HERSHEY_SIMPLEX,
                    .7*factor, color, max(1, int(2*factor)), cv2.LINE_AA)
    return report, overlay, rows


def _draw_measurement(overlay, report, pixel_lines, world_lines, virtual, matrix, settings):
    factor = max(1., overlay.shape[1]/1600)
    virtual_px = np.asarray(report["virtual_corners_px"])
    for i in range(4):
        a, b = virtual_px[i], virtual_px[(i+1) % 4]
        ends = [a+settings.corner_exclusion*(b-a), b-settings.corner_exclusion*(b-a)]
        ends = np.rint(ends).astype(int)
        cv2.line(overlay, tuple(ends[0]), tuple(ends[1]), (255, 190, 0),
                 max(2, int(2*factor)), cv2.LINE_AA)
    if not report["dimensions"]:
        return
    center = virtual.mean(axis=0)
    lines = [line.copy() for line in world_lines]
    for line in lines:
        if line[:2] @ center+line[2] < 0:
            line *= -1
    for section in report["section_spacings"]:
        normal = np.asarray(section["direction"])
        tangent = np.array([-normal[1], normal[0]])
        location = center+(.5*(np.min(virtual @ tangent)+np.max(virtual @ tangent))-center @ tangent)*tangent
        ends = np.array([location-(lines[i][:2] @ location+lines[i][2])/(lines[i][:2] @ normal)*normal
                         for i in section["edge_pair"]])
        if matrix is not None:
            ends = transform_points(ends, np.linalg.inv(matrix))
        ends = np.rint(ends).astype(int)
        for a, b in (ends, ends[::-1]):
            cv2.arrowedLine(overlay, tuple(a), tuple(b), (0, 180, 255),
                           max(2, int(2*factor)), cv2.LINE_AA, tipLength=.025)
        value = section["spacings"][1]
        is_length = abs(value-report["dimensions"]["length"]) < 1e-8
        label = f"{'L' if is_length else 'W'} = {format_dimension(value)} {report['dimensions']['unit']}"
        midpoint = (ends[0]+ends[1])/2
        horizontal = abs(ends[1, 0]-ends[0, 0]) > abs(ends[1, 1]-ends[0, 1])
        offset = np.array([20, 40] if horizontal else [20, -25])*factor
        position = tuple(np.rint(midpoint+offset).astype(int))
        cv2.putText(overlay, label, position, cv2.FONT_HERSHEY_SIMPLEX, .7*factor,
                    (20, 20, 20), max(4, int(5*factor)), cv2.LINE_AA)
        cv2.putText(overlay, label, position, cv2.FONT_HERSHEY_SIMPLEX, .7*factor,
                    (0, 220, 255), max(2, int(2*factor)), cv2.LINE_AA)
