"""Independent geometry and end-to-end tests for actual contour dimensions."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cavity_measure import analyze_array, cv2, np, transform_points, write_image
from cavity_measurement.metrology import attach_contour_dimensions, ContourMeasurementSettings
from test_contour import scene


def analytic_contour(angle=0):
    # 1200 x 800 rectangle, radius 100. Points come from independent straight
    # segments and circular arcs, not from the detection or fitting functions.
    points = []
    for start, end, center, first_angle in [
        ((-500, -400), (500, -400), (500, -300), -90),
        ((600, -300), (600, 300), (500, 300), 0),
        ((500, 400), (-500, 400), (-500, 300), 90),
        ((-600, 300), (-600, -300), (-500, -300), 180),
    ]:
        count = int(np.linalg.norm(np.asarray(end)-start)/6)
        points.extend(np.linspace(start, end, count, endpoint=False))
        radians = np.deg2rad(np.linspace(first_angle, first_angle+90, 30, endpoint=False))
        points.extend(np.asarray(center)+100*np.column_stack([np.cos(radians), np.sin(radians)]))
    radians = np.deg2rad(angle)
    rotation = np.array([[np.cos(radians), -np.sin(radians)], [np.sin(radians), np.cos(radians)]])
    return np.asarray(points) @ rotation.T+[900, 800]


def measure_points(points, supported=None, calibration=None):
    if supported is None:
        supported = np.ones(len(points), dtype=bool)
    report = {"contour": {"points_px": points.tolist(), "directly_supported": supported.tolist(),
                          "boundary_side": "inner"}, "image_size": [1800, 1600],
              "calibration": calibration, "dimensions": None}
    return attach_contour_dimensions(report, np.zeros((1600, 1800, 3), np.uint8))[0]


class ContourMeasurementTests(unittest.TestCase):
    def test_analytic_rotated_rounded_cavities_have_independent_known_sizes(self):
        for angle in (0, 17, -36, 74):
            with self.subTest(angle=angle):
                points = analytic_contour(angle)
                points += np.random.default_rng(16).normal(0, .12, points.shape)
                report = measure_points(points)
                self.assertEqual(report["status"], "pixel_only", report["quality_reasons"])
                self.assertAlmostEqual(report["dimensions"]["length"], 1200, delta=.15)
                self.assertAlmostEqual(report["dimensions"]["width"], 800, delta=.15)
                self.assertEqual(len(report["edges"]), 4)

    def test_weak_points_do_not_pull_fits(self):
        points = analytic_contour()
        supported = np.ones(len(points), bool)
        supported[::40] = False
        points[~supported] += [60, -60]
        report = measure_points(points, supported)
        self.assertEqual(report["status"], "pixel_only", report["quality_reasons"])
        self.assertAlmostEqual(report["dimensions"]["length"], 1200, delta=1e-7)
        self.assertAlmostEqual(report["dimensions"]["width"], 800, delta=1e-7)

    def test_bowed_boundary_withholds_rectangular_dimensions(self):
        points = analytic_contour()
        top = points[:, 1] < 401
        points[top, 1] += 15*np.cos((points[top, 0]-900)*np.pi/1000)
        report = measure_points(points)
        self.assertEqual(report["status"], "review_required")
        self.assertIsNone(report["dimensions"])
        self.assertTrue(report["quality_reasons"])

    def test_perspective_requires_independent_calibration(self):
        original = analytic_contour()
        perspective = np.array([[1., .02, 30], [.01, 1., 20], [.00008, .00004, 1.]])
        observed = transform_points(original, perspective)
        raw = measure_points(observed)
        self.assertEqual(raw["status"], "review_required")
        self.assertIsNone(raw["dimensions"])
        corrected = measure_points(observed, calibration={"pixel_to_mm":
            (np.diag([.02, .02, 1.]) @ np.linalg.inv(perspective)).tolist()})
        self.assertEqual(corrected["status"], "measured", corrected["quality_reasons"])
        self.assertAlmostEqual(corrected["dimensions"]["length"], 24, places=6)
        self.assertAlmostEqual(corrected["dimensions"]["width"], 16, places=6)

    def test_textured_image_dimensions_match_independent_floor_mask(self):
        image, outer = scene()
        inner = cv2.erode(outer, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19)))
        y, x = np.nonzero(inner)
        expected = sorted([np.ptp(x)+1, np.ptp(y)+1], reverse=True)
        report, _, rows = analyze_array(image)
        self.assertEqual(report["status"], "pixel_only", report["quality_reasons"])
        self.assertAlmostEqual(report["dimensions"]["length"], expected[0], delta=.5)
        self.assertAlmostEqual(report["dimensions"]["width"], expected[1], delta=.5)
        self.assertTrue(rows)
        scaled, _, _ = analyze_array(image, calibration={"mm_per_pixel": .02})
        self.assertEqual(scaled["status"], "measured")
        self.assertAlmostEqual(scaled["dimensions"]["length"], expected[0]*.02, delta=.01)
        self.assertAlmostEqual(scaled["dimensions"]["width"], expected[1]*.02, delta=.01)
        self.assertEqual(scaled["pixel_dimensions"]["unit"], "px")

    def test_auto_does_not_fall_back_to_a_different_region(self):
        image = np.full((600, 900, 3), 200, np.uint8)
        cv2.rectangle(image, (150, 150), (750, 450), (20, 20, 20), -1)
        with self.assertRaisesRegex(ValueError, "No complete dark-rim"):
            analyze_array(image)

    def test_cli_writes_and_clears_dimension_exports(self):
        workspace = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix=".test_", dir=workspace) as temp:
            root = Path(temp)/"中文尺寸"
            image, _ = scene()
            path, out = root/"腔体.png", root/"结果"
            write_image(path, image)
            command = [sys.executable, "-X", "utf8", str(workspace/"cavity_measure.py"),
                       "measure", "--image", str(path), "--out", str(out)]
            completed = subprocess.run(command, capture_output=True, encoding="utf-8")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads((out/"result.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pixel_only")
            self.assertRegex((out/"尺寸结果.txt").read_text(encoding="utf-8-sig"), r"长度：1183\.\d{3} px")
            self.assertTrue((out/"edge_points.csv").is_file())
            write_image(path, np.full_like(image, 140))
            failed = subprocess.run(command, capture_output=True, encoding="utf-8")
            self.assertEqual(failed.returncode, 2)
            with (out/"dimensions.csv").open(encoding="utf-8-sig", newline="") as f:
                row = list(csv.DictReader(f))[0]
            self.assertEqual(row["status"], "failed")
            self.assertEqual(row["length"], "")
            self.assertNotIn("长度：1183.", (out/"尺寸结果.txt").read_text(encoding="utf-8-sig"))

    def test_batch_keeps_valid_sizes_and_records_failed_images(self):
        workspace = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix=".test_", dir=workspace) as temp:
            root = Path(temp)
            images, out = root/"图片", root/"结果"
            image, _ = scene()
            write_image(images/"正常.bmp", image)
            write_image(images/"空白.png", np.full_like(image, 140))
            command = [sys.executable, "-X", "utf8", str(workspace/"tools/measure_folder.py"),
                       "--images", str(images), "--out", str(out)]
            run = subprocess.run(command, capture_output=True, encoding="utf-8")
            self.assertEqual(run.returncode, 2, run.stderr)
            summary = json.loads((out/"summary.json").read_text(encoding="utf-8"))
            self.assertEqual((summary["passed"], summary["total"]), (1, 2))
            self.assertTrue((out/"尺寸汇总.csv").is_file())

    def test_invalid_measurement_settings_are_rejected(self):
        for values in ({"max_all_rms_px": float("nan")}, {"min_points": 3},
                       {"min_rejection_threshold_px": 5, "max_rejection_threshold_px": 4}):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    ContourMeasurementSettings(**values).validate()


if __name__ == "__main__":
    unittest.main()
