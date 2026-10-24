"""Independent regions, per-plane units, partial failures and export clearing."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cavity_measure import analyze_array, cv2, np, write_image
from cavity_measurement import measurement
from cavity_measurement.dual import FOLDERS
from cavity_measurement.contour import _continuous_path
from test_contour import scene


class DualTests(unittest.TestCase):
    def test_both_match_independent_masks_and_preserve_inner(self):
        image, outer_truth = scene()
        inner_truth = cv2.erode(outer_truth, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19)))
        report, _, _ = analyze_array(image, boundary_side="both", calibration={"mm_per_pixel": .02})
        self.assertEqual(report["status"], "completed", report["quality_reasons"])
        self.assertEqual(report["relationship"]["status"], "nested")
        for side, truth in (("inner", inner_truth), ("outer", outer_truth)):
            child = report["boundaries"][side]
            mask = np.zeros(truth.shape, np.uint8)
            cv2.fillPoly(mask, [np.rint(child["contour"]["points_px"]).astype(np.int32)], 1)
            iou = np.count_nonzero((mask > 0) & (truth > 0))/np.count_nonzero((mask > 0) | (truth > 0))
            self.assertGreater(iou, .99)
        single, _, _ = analyze_array(image, calibration={"mm_per_pixel": .02})
        self.assertEqual(report["boundaries"]["inner"]["contour"]["points_px"], single["contour"]["points_px"])
        self.assertEqual(report["boundaries"]["inner"]["dimensions"], single["dimensions"])
        self.assertEqual(report["boundaries"]["outer"]["dimensions"]["unit"], "px")
        self.assertNotIn("points_mm", report["boundaries"]["outer"]["contour"])

    def test_outline_has_no_dimensions(self):
        report, _, _ = analyze_array(scene()[0], boundary_side="both", detection="outline")
        self.assertEqual(report["status"], "completed")
        for child in report["boundaries"].values():
            self.assertEqual(child["status"], "contour_detected")
            self.assertIsNone(child["dimensions"])

    def test_seed_without_image_evidence_never_becomes_a_measurement(self):
        image, truth = scene()
        contours, _ = cv2.findContours(truth, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        seed = contours[0].reshape(-1, 2).astype(float)
        if cv2.contourArea(seed.astype(np.float32), oriented=True) < 0:
            seed = seed[::-1]
        image[:] = 140
        with patch("cavity_measurement.contour._seed", return_value=(seed, {"method": "independent_test_geometry"})):
            report, _, _ = analyze_array(image, boundary_side="both")
        self.assertEqual(report["status"], "review_required")
        inner = report["boundaries"]["inner"]
        self.assertIn("contour", inner)
        self.assertEqual(inner["status"], "review_required")
        self.assertIsNone(inner["dimensions"])
        self.assertTrue(inner["quality_reasons"])

    def test_clipped_image_never_produces_accepted_dimensions(self):
        report, _, _ = analyze_array(scene(clipped=True)[0], boundary_side="both")
        self.assertIn(report["status"], ("failed", "review_required"))
        for child in report["boundaries"].values():
            self.assertIsNone(child["dimensions"])

    def test_outer_failure_preserves_inner_result(self):
        original = measurement.contour_array
        def fail_outer(image, calibration=None, roi=None, boundary_side="inner", **kwargs):
            if boundary_side == "outer":
                raise ValueError("No supported outer edge")
            return original(image, calibration, roi, boundary_side, **kwargs)
        with patch("cavity_measurement.dual.contour_array", side_effect=fail_outer):
            report, _, _ = analyze_array(scene()[0], boundary_side="both")
        self.assertEqual(report["status"], "review_required")
        self.assertIsNotNone(report["boundaries"]["inner"]["dimensions"])
        self.assertIsNone(report["boundaries"]["outer"]["dimensions"])

    def test_non_nested_pair_withholds_both_sizes(self):
        original = measurement.contour_array
        def shifted(image, calibration=None, roi=None, boundary_side="inner", **kwargs):
            result, overlay, rows = original(image, calibration, roi, boundary_side, **kwargs)
            if boundary_side == "outer":
                result["contour"]["points_px"] = (np.asarray(result["contour"]["points_px"])+[60, 0]).tolist()
            return result, overlay, rows
        with patch("cavity_measurement.dual.contour_array", side_effect=shifted):
            report, _, _ = analyze_array(scene()[0], boundary_side="both")
        self.assertEqual(report["relationship"]["status"], "review_required")
        for child in report["boundaries"].values():
            self.assertIsNone(child["dimensions"])

    def test_shared_distortion_correction_does_not_transfer_metric_scale(self):
        image, _ = scene()
        calibration = {"mm_per_pixel": .02, "image_size": [1400, 1400],
                       "camera_matrix": [[1800, 0, 700], [0, 1800, 700], [0, 0, 1]], "dist_coeffs": [0]*5}
        report, _, _ = analyze_array(image, calibration=calibration, boundary_side="both")
        self.assertEqual(report["status"], "completed")
        for child in report["boundaries"].values():
            self.assertEqual(child["coordinate_system"], "undistorted_full_image_px")
            self.assertNotIn("No lens-distortion correction was applied.", child["notes"])
        self.assertIsNone(report["boundaries"]["outer"]["calibration"])
        with self.assertRaisesRegex(ValueError, "image_size differs"):
            analyze_array(image, calibration=dict(calibration, image_size=[7008, 7000]), boundary_side="both")

    def test_cyclic_tracker_enforces_neighbor_limit_across_seam(self):
        gradient = np.full((120, 80), -1., np.float32)
        for i in range(120):
            gradient[i, int(10+50*i/119)] = 20
        path = _continuous_path(gradient, .5, close_cycle=True)
        self.assertLessEqual(abs(int(path[-1])-int(path[0])), 6)
        self.assertLessEqual(np.abs(np.diff(path)).max(), 6)

    def test_cli_clears_all_sizes_on_blank_and_invalid_calibration(self):
        workspace = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix=".test_dual_", dir=workspace) as temp:
            root = Path(temp); path, out = root/"腔体.png", root/"结果"
            image, _ = scene(); write_image(path, image)
            command = [sys.executable, "-X", "utf8", str(workspace/"cavity_measure.py"), "measure",
                       "--image", str(path), "--out", str(out), "--boundary-side", "both"]
            result = subprocess.run(command+["--pixels-only"], capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out/"overlay_preview.jpg").is_file())
            write_image(path, np.full_like(image, 140))
            for args in (["--pixels-only"], []):
                result = subprocess.run(command+args, capture_output=True, encoding="utf-8")
                self.assertEqual(result.returncode, 2, result.stderr)
                for target in (out, *(out/folder for folder in FOLDERS.values())):
                    report = json.loads((target/"result.json").read_text(encoding="utf-8"))
                    self.assertIsNone(report["dimensions"])
                    with (target/"dimensions.csv").open(encoding="utf-8-sig", newline="") as f:
                        for row in csv.DictReader(f):
                            self.assertEqual(row["length"], "")
                            self.assertEqual(row["width"], "")

    def test_batch_keeps_each_boundary_unit_and_failure(self):
        workspace = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix=".test_dual_", dir=workspace) as temp:
            root = Path(temp); images, out = root/"图片", root/"结果"
            image, _ = scene()
            write_image(images/"正常.bmp", image); write_image(images/"空白.png", np.full_like(image, 140))
            result = subprocess.run([sys.executable, "-X", "utf8", str(workspace/"tools/measure_folder.py"),
                                     "--images", str(images), "--out", str(out), "--mm-per-pixel", ".02",
                                     "--boundary-side", "both"], capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 2, result.stderr)
            summary = json.loads((out/"summary.json").read_text(encoding="utf-8"))
            self.assertEqual((summary["passed"], summary["total"]), (1, 2))
            with (out/"尺寸汇总.csv").open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 4)
            self.assertEqual({r["单位"] for r in rows if r["图片"] == "正常.bmp"}, {"px", "mm"})

    def test_outer_cli_does_not_implicitly_use_inner_default_calibration(self):
        workspace = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix=".test_dual_", dir=workspace) as temp:
            root = Path(temp); path, out = root/"image.png", root/"result"
            write_image(path, scene()[0])
            result = subprocess.run([sys.executable, "-X", "utf8", str(workspace/"cavity_measure.py"),
                                     "measure", "--image", str(path), "--out", str(out), "--boundary-side", "outer"],
                                    capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((out/"result.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pixel_only")
            self.assertEqual(report["dimensions"]["unit"], "px")


if __name__ == "__main__":
    unittest.main()
