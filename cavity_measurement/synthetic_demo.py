"""Synthetic images for functional verification, not a physical accuracy claim."""
from pathlib import Path
import json

from cavity_measure import (Settings, cv2, np, measure_array, save_measurement,
                            transform_points, write_image, write_json, default_output_path)


def affine_mapping(angle_deg=17, scale_px_per_mm=10, center=(500, 380)):
    angle = np.deg2rad(angle_deg)
    c, s = np.cos(angle)*scale_px_per_mm, np.sin(angle)*scale_px_per_mm
    return np.array([[c,-s,center[0]], [s,c,center[1]], [0,0,1]], np.float64)


def render_cavity(world_to_pixel=None, length_mm=60, width_mm=40, radius_mm=4,
                  image_size=(1000, 760), noise_sigma=1.5, bright=False, seed=123):
    """Render an independently defined signed-distance rounded rectangle.

    2x antialiasing, blur, a mild illumination slope, and Gaussian sensor noise.
    Coordinates refer to pixel centers. Returned truth corners are virtual corners.
    """
    world_to_pixel = affine_mapping() if world_to_pixel is None else world_to_pixel
    inverse = np.linalg.inv(world_to_pixel)
    w, h = image_size
    ss = 2
    yy, xx = np.meshgrid((np.arange(h*ss)+.5)/ss-.5,
                         (np.arange(w*ss)+.5)/ss-.5, indexing="ij")
    denominator = inverse[2,0]*xx+inverse[2,1]*yy+inverse[2,2]
    wx = (inverse[0,0]*xx+inverse[0,1]*yy+inverse[0,2])/denominator
    wy = (inverse[1,0]*xx+inverse[1,1]*yy+inverse[1,2])/denominator
    qx = np.abs(wx)-(length_mm/2-radius_mm)
    qy = np.abs(wy)-(width_mm/2-radius_mm)
    sdf = np.hypot(np.maximum(qx,0), np.maximum(qy,0))+np.minimum(np.maximum(qx,qy),0)-radius_mm
    inside, outside = (190,55) if bright else (55,190)
    high = np.where(sdf <= 0, inside, outside).astype(np.float32)
    high += 8*xx/w + 5*yy/h
    gray = cv2.resize(high, (w,h), interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(gray, (0,0), .8)
    gray += np.random.default_rng(seed).normal(0,noise_sigma,(h,w)).astype(np.float32)
    image = cv2.cvtColor(np.clip(np.rint(gray),0,255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    world_corners = [[-length_mm/2,-width_mm/2], [length_mm/2,-width_mm/2],
                     [length_mm/2,width_mm/2], [-length_mm/2,width_mm/2]]
    corners = transform_points(world_corners, world_to_pixel)
    calibration = {"schema_version":1, "method":"synthetic_ground_truth",
                   "image_size":[w,h], "pixel_to_mm":inverse.tolist(),
                   "notes":["Synthetic calibration only; do not use for camera images."]}
    return image, corners, calibration


def run_demo(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    image, corners, calibration = render_cavity()
    write_image(out/"synthetic_input.png", image)
    write_json(out/"calibration_SYNTHETIC_ONLY.json", calibration)
    write_json(out/"seed_corners.json", {"corners_px":corners.tolist()})
    report, overlay, rows = measure_array(image, Settings(), calibration)
    report["input_image"] = str((out/"synthetic_input.png").resolve())
    save_measurement(out, report, overlay, rows)
    truth = {"data_type":"synthetic", "length_mm":60, "width_mm":40,
             "angle_deg":17, "radius_mm":4,
             "scope":"Functional check only. Not real cavity measurement validation."}
    if report["dimensions"]:
        truth["length_error_mm"] = report["dimensions"]["length"]-60
        truth["width_error_mm"] = report["dimensions"]["width"]-40
    write_json(out/"synthetic_truth.json", truth)
    print(json.dumps({"status":report["status"], "dimensions":report["dimensions"],
                      "synthetic_errors_mm":{k:v for k,v in truth.items() if "error" in k},
                      "output":str(out.resolve())}, ensure_ascii=False))
    return 2 if report["status"] == "review_required" else 0


if __name__ == "__main__":
    raise SystemExit(run_demo(default_output_path("demo")))
