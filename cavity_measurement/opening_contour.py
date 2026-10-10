"""Trace the exterior optical transition of a dark, rounded opening rim.

Convexity is used ONLY to initialize the search strip. The returned contour is
supported by original-resolution grayscale profiles, with a continuity prior.
It is neither a CAD rectangle nor a dimensional ground truth.
"""
from dataclasses import asdict, dataclass

import cv2
import numpy as np


class NoContourFound(ValueError):
    pass


@dataclass
class ContourSettings:
    coarse_max_size: int = 1400
    blackhat_kernel: int = 25
    blackhat_threshold: float = 25.0
    min_area_fraction: float = 0.06
    min_rectangularity: float = 0.85
    min_solidity: float = 0.94
    sample_spacing_px: float = 6.0
    outward_search_fraction: float = 0.0107
    inward_search_fraction: float = 0.0036
    profile_step_px: float = 0.5
    min_gradient: float = 2.0
    min_contrast: float = 8.0
    min_supported_fraction: float = 0.95
    min_side_supported_fraction: float = 0.85
    max_weak_arc_fraction: float = 0.03

    def validate(self):
        for name, value in asdict(self).items():
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid contour setting: {name}")
        if not 200 <= self.coarse_max_size <= 3000:
            raise ValueError("coarse_max_size must be in [200, 3000]")
        if self.blackhat_kernel < 3 or self.blackhat_kernel % 2 != 1:
            raise ValueError("blackhat_kernel must be an odd integer >= 3")
        if self.profile_step_px > 1 or self.sample_spacing_px < 1:
            raise ValueError("profile_step_px <= 1 and sample_spacing_px >= 1 required")
        for name in ("min_area_fraction", "min_rectangularity", "min_solidity",
                     "min_supported_fraction", "min_side_supported_fraction",
                     "max_weak_arc_fraction"):
            if getattr(self, name) >= 1:
                raise ValueError(f"{name} must be below 1")


def _roi(gray, roi):
    height, width = gray.shape
    x, y, w, h = (0, 0, width, height) if roi is None else map(int, roi)
    if min(x, y) < 0 or min(w, h) < 50 or x+w > width or y+h > height:
        raise ValueError("ROI outside image bounds or smaller than 50 pixels")
    return x, y, w, h


def _seed(gray, roi, settings):
    x, y, w, h = _roi(gray, roi)
    # Resize only the initialization. Refinement uses original image pixels.
    scale = min(1.0, settings.coarse_max_size / max(w, h))
    coarse = cv2.resize(gray[y:y+h, x:x+w], None, fx=scale, fy=scale,
                        interpolation=cv2.INTER_AREA)
    sy, sx = coarse.shape[0]/h, coarse.shape[1]/w
    blurred = cv2.GaussianBlur(coarse, (5, 5), 0.9)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                       (settings.blackhat_kernel,)*2)
    dark_band = cv2.morphologyEx(blurred, cv2.MORPH_BLACKHAT, kernel)
    _, mask = cv2.threshold(dark_band, settings.blackhat_threshold, 255,
                            cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    candidates = []
    for i, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        bx, by, bw, bh = cv2.boundingRect(contour)
        if not settings.min_area_fraction*coarse.size < area < 0.90*coarse.size:
            continue
        if min(bx, by) < 3 or bx+bw >= coarse.shape[1]-3 or by+bh >= coarse.shape[0]-3:
            continue  # Reject a cavity clipped by either the image or the ROI.
        # An odd-depth contour is the hole enclosed by the dark band, even when
        # the band itself connects to exterior marks and the image border.
        depth, parent = 0, int(hierarchy[0, i, 3])
        while parent >= 0:
            depth += 1
            parent = int(hierarchy[0, parent, 3])
        if depth % 2 != 1:
            continue
        rect = cv2.minAreaRect(contour)
        rw, rh = rect[1]
        hull = cv2.convexHull(contour)
        solidity = area/max(cv2.contourArea(hull), 1)
        rectangularity = area/max(rw*rh, 1)
        if (min(rw, rh) < 40 or rectangularity < settings.min_rectangularity
                or solidity < settings.min_solidity):
            continue
        candidates.append((area*rectangularity, hull, {
            "coarse_area_fraction": area/coarse.size,
            "coarse_rectangularity": rectangularity,
            "coarse_solidity": solidity,
        }))
    if not candidates:
        raise NoContourFound("No complete dark-rim opening found; specify a single-cavity ROI, "
                             "or check that the entire dark boundary is visible")
    candidates.sort(key=lambda item: item[0], reverse=True)
    if len(candidates) > 1 and candidates[1][0] > 0.65*candidates[0][0]:
        raise ValueError("Multiple complete openings found; specify a single-cavity --roi")
    _, hull, metadata = candidates[0]
    seed = hull.reshape(-1, 2).astype(np.float64)/[sx, sy]+[x, y]
    if cv2.contourArea(seed.astype(np.float32), oriented=True) < 0:
        seed = seed[::-1]
    metadata.update({"candidate_count": len(candidates), "coarse_scale_xy": [sx, sy],
                     "roi_px": [x, y, w, h]})
    return seed, metadata


def _resample(seed, spacing):
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.roll(seed, -1, axis=0)-seed, axis=1))]
    count = max(100, int(arc[-1]/spacing))
    t = np.linspace(0, arc[-1], count, endpoint=False)
    points = np.column_stack([np.interp(t, arc, np.r_[seed[:, j], seed[0, j]])
                              for j in range(2)])
    weights = cv2.getGaussianKernel(13, 2).ravel()
    points = sum(weight*np.roll(points, j-6, axis=0) for j, weight in enumerate(weights))
    tangent = np.roll(points, -3, axis=0)-np.roll(points, 3, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    return points, np.column_stack([-tangent[:, 1], tangent[:, 0]])


def _continuous_path(gradient, step):
    """Two cyclic passes of Viterbi tracking; bounded shifts suppress tool marks."""
    count, states = gradient.shape
    scores = np.clip(gradient/np.maximum(np.percentile(gradient, 99, axis=1)[:, None], 3),
                     -1, 1.5)
    radius = max(1, int(round(3/step)))
    jumps = np.arange(-radius, radius+1)
    penalty = 0.065*(jumps*step)**2
    best = np.zeros(states, np.float32)
    back = np.zeros((count, states), np.int32)
    indices = np.arange(states)
    for cycle in range(2):
        for i in range(count):
            padded = np.pad(best, (radius, radius), constant_values=-1e6)
            alternatives = np.stack([padded[radius+j:radius+j+states]-p
                                     for j, p in zip(jumps, penalty)])
            choice = alternatives.argmax(axis=0)
            best = scores[i]+alternatives[choice, indices]
            best -= best.max()
            if cycle:
                back[i] = indices+jumps[choice]
    state = int(best.argmax())
    path = np.empty(count, int)
    for i in range(count-1, -1, -1):
        path[i] = state
        state = int(back[i, state])
    return path


def _longest_false_arc(supported):
    longest = run = 0
    for good in np.r_[supported, supported]:
        run = 0 if good else run+1
        longest = max(longest, run)
    return min(longest, len(supported))/len(supported)


def find_opening(gray, roi=None, settings=None):
    """Return a closed contour and evidence in full-resolution x,y coordinates."""
    settings = settings or ContourSettings()
    settings.validate()
    seed, initialization = _seed(gray, roi, settings)
    bases, normals = _resample(seed, settings.sample_spacing_px)
    short_side = min(cv2.minAreaRect(seed.astype(np.float32))[1])
    outward = max(12, settings.outward_search_fraction*min(gray.shape), short_side*0.015)
    inward = max(6, settings.inward_search_fraction*min(gray.shape))
    step = settings.profile_step_px
    offsets = np.arange(-outward, inward+step/2, step)
    locations = bases[:, None, :]+normals[:, None, :]*offsets[None, :, None]
    valid_locations = ((locations[:, :, 0] >= 1) & (locations[:, :, 0] < gray.shape[1]-2)
                       & (locations[:, :, 1] >= 1) & (locations[:, :, 1] < gray.shape[0]-2))
    smooth = cv2.GaussianBlur(gray, (0, 0), 1.2)
    profiles = cv2.remap(smooth, locations[:, :, 0].astype(np.float32),
                         locations[:, :, 1].astype(np.float32), cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    # Smooth along profile offsets only, never along unrelated profile rows.
    profiles = cv2.GaussianBlur(profiles, (0, 0), 0.75/step, sigmaY=0.01)
    gradient = -np.gradient(profiles, step, axis=1)  # exterior -> dark rim
    gradient[~valid_locations] = -1000
    path = _continuous_path(gradient, step)
    center_offsets = offsets[path]
    strength = gradient[np.arange(len(path)), path]
    # A local derivative centroid refines the tracked edge, without assuming a
    # straight wall or fitting a circle through the rounded corners.
    local = np.abs(offsets[None, :]-center_offsets[:, None]) <= 3
    baseline = np.median(gradient, axis=1)[:, None]
    weights = np.maximum(gradient-baseline, 0)*local*valid_locations
    refined_offsets = np.sum(weights*offsets, axis=1)/np.maximum(weights.sum(axis=1), 1e-9)
    points = bases+refined_offsets[:, None]*normals
    supported = ((strength >= settings.min_gradient)
                 & (np.ptp(profiles, axis=1) >= settings.min_contrast)
                 & (path > 6) & (path < len(offsets)-7))
    weak_arc = _longest_false_arc(supported)
    rect = cv2.minAreaRect(seed.astype(np.float32))
    box = cv2.boxPoints(rect).astype(float)
    distances = []
    for i in range(4):
        a, b = box[i], box[(i+1) % 4]
        delta = b-a
        normal = np.array([-delta[1], delta[0]])/np.linalg.norm(delta)
        distances.append(np.abs((bases-a) @ normal))
    side_indices = np.argmin(distances, axis=0)
    side_support = [float(supported[side_indices == i].mean()) for i in range(4)]
    neighbor_steps = np.linalg.norm(np.roll(points, -1, axis=0)-points, axis=1)
    reasons = []
    if supported.mean() < settings.min_supported_fraction:
        reasons.append("insufficient grayscale support around the complete contour")
    if min(side_support) < settings.min_side_supported_fraction:
        reasons.append("one wall has insufficient grayscale support")
    if weak_arc > settings.max_weak_arc_fraction:
        reasons.append("a long boundary segment lacks direct grayscale support")
    if neighbor_steps.max() > 3*settings.sample_spacing_px:
        reasons.append("tracked contour has a discontinuity, including at the closing seam")
    if reasons:
        raise ValueError("Contour requires review: "+"; ".join(reasons))
    lo, hi = points.min(axis=0), points.max(axis=0)
    return {
        "closed": True, "point_count": len(points),
        "boundary_definition": "exterior-to-dark transition of the visible opening rim",
        "points_px": points.tolist(), "gradient_gray_per_px": strength.tolist(),
        "directly_supported": supported.tolist(),
        "bbox_xywh_px": [*lo.tolist(), *(hi-lo).tolist()],
        "enclosed_area_px2": float(abs(cv2.contourArea(points.astype(np.float32)))),
        "perimeter_px": float(neighbor_steps.sum()),
        "quality": {"supported_fraction": float(supported.mean()),
                    "side_supported_fractions": side_support,
                    "longest_weak_arc_fraction": float(weak_arc),
                    "median_gradient_gray_per_px": float(np.median(strength)),
                    "maximum_neighbor_step_px": float(neighbor_steps.max())},
        "initialization": initialization, "settings": asdict(settings),
        "method": "black-hat dark band; convex seed; continuous grayscale profile tracking; local centroid",
    }
