"""Independent geometric truths and failure tests; run with unittest discover."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cavity_measure import (MeasurementError, Settings, build_planar_calibration,
                            cv2, np, measure_array, robust_line, transform_points,
                            write_image, write_json)
from cavity_measurement.synthetic import affine_mapping, render_cavity


class MeasurementTests(unittest.TestCase):
    def assert_dimensions(self, report, tolerance=.06):
        self.assertEqual(report["status"], "measured", report["quality_reasons"])
        self.assertAlmostEqual(report["dimensions"]["length"],60,delta=tolerance)
        self.assertAlmostEqual(report["dimensions"]["width"],40,delta=tolerance)

    def test_rotations_noise_and_auto_initialization(self):
        for angle in (0,17,-36,74):
            with self.subTest(angle=angle):
                image, _, cal = render_cavity(affine_mapping(angle), noise_sigma=2)
                report, _, _ = measure_array(image, calibration=cal)
                self.assert_dimensions(report)

    def test_perspective_compensated_by_independent_reference(self):
        world = np.array([[-30,-20],[30,-20],[30,20],[-30,20]],np.float32)
        pixels = np.array([[190,155],[800,205],[730,650],[250,590]],np.float32)
        h = cv2.getPerspectiveTransform(world,pixels)
        image, corners, _ = render_cavity(h)
        # Independent reference lies outside the cavity; cavity nominal dimensions
        # are NOT used by the calibration procedure.
        reference = np.array([[-35,-25],[35,-25],[35,25],[-35,25],[0,-25],[0,25]])
        reference_pixels = transform_points(reference,h)
        cal = build_planar_calibration(image,{"image_points_px":reference_pixels.tolist(),
                                              "world_points_mm":reference.tolist()})
        report, _, _ = measure_array(image, calibration=cal, corners=corners)
        self.assert_dimensions(report)

    def test_scalar_scale(self):
        image, _, _ = render_cavity(affine_mapping(-15))
        report, _, _ = measure_array(image,calibration={"mm_per_pixel":.1})
        self.assert_dimensions(report)

    def test_lens_distortion_points_and_image_are_corrected_consistently(self):
        mapping = affine_mapping(17)
        ideal, corners, _ = render_cavity(mapping)
        k = np.array([[950.,0,500.],[0,950.,380.],[0,0,1.]])
        d = np.array([-.22,.04,.001,-.001,0.])
        yy,xx = np.indices(ideal.shape[:2],dtype=np.float32)
        grid = np.column_stack([xx.ravel(),yy.ravel()]).reshape(-1,1,2)
        source = cv2.undistortPoints(grid,k,d,P=k).reshape(*xx.shape,2)
        raw = cv2.remap(ideal,source[:,:,0],source[:,:,1],cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_REPLICATE)

        def distort_points(p):
            normalized = np.column_stack([(p[:,0]-500)/950,(p[:,1]-380)/950,np.ones(len(p))])
            return cv2.projectPoints(normalized,np.zeros(3),np.zeros(3),k,d)[0].reshape(-1,2)

        reference = np.array([[-35,-25],[35,-25],[35,25],[-35,25],[0,-25],[0,25]])
        raw_reference = distort_points(transform_points(reference,mapping))
        calibration = build_planar_calibration(raw,
            {"image_points_px":raw_reference.tolist(),"world_points_mm":reference.tolist()},
            {"camera_matrix":k.tolist(),"dist_coeffs":d.tolist()})
        report,_,_ = measure_array(raw,calibration=calibration,corners=distort_points(corners))
        self.assert_dimensions(report,tolerance=.07)
        self.assertEqual(report["coordinate_system"],"undistorted_full_image_px")

    def test_calibration_cli_from_independent_reference(self):
        workspace = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix=".test_",dir=workspace) as temp:
            self.assertEqual(Path(temp).resolve().parent,workspace.resolve())
            root = Path(temp)
            image,_,_ = render_cavity()
            reference = np.array([[-35,-25],[35,-25],[35,25],[-35,25]])
            pixels = transform_points(reference,affine_mapping())
            write_image(root/"reference.png",image)
            write_json(root/"points.json",{"image_points_px":pixels.tolist(),
                                           "world_points_mm":reference.tolist()})
            command = [sys.executable,"-X","utf8",str(workspace/"cavity_measure.py"),"calibrate",
                       "--image",str(root/"reference.png"),"--points",str(root/"points.json"),
                       "--out",str(root/"cal.json")]
            run = subprocess.run(command,capture_output=True,encoding="utf-8")
            self.assertEqual(run.returncode,0,run.stderr)
            calibration = json.loads((root/"cal.json").read_text(encoding="utf-8"))
            report,_,_ = measure_array(image,calibration=calibration)
            self.assert_dimensions(report)

    def test_without_calibration_is_pixels_only(self):
        image, _, _ = render_cavity()
        report, _, rows = measure_array(image)
        self.assertEqual(report["status"],"pixel_only")
        self.assertEqual(report["unit"],"px")
        self.assertAlmostEqual(report["dimensions"]["length"],600,delta=.6)
        self.assertNotIn("length_mm",report["dimensions"])
        self.assertTrue(all(row[4] == "" and row[5] == "" for row in rows))

    def test_bright_cavity_and_auto_polarity(self):
        image, corners, cal = render_cavity(bright=True)
        report, _, _ = measure_array(image, Settings(polarity="auto"), cal, corners)
        self.assert_dimensions(report)

    def test_blank_and_low_contrast_fail(self):
        for val in (0,127,255):
            with self.subTest(val=val):
                image = np.full((400,600,3),val,np.uint8)
                with self.assertRaises(MeasurementError):
                    measure_array(image)
        image, corners, cal = render_cavity()
        image = np.clip(image.astype(float)/30+100,0,255).astype(np.uint8)
        with self.assertRaises(MeasurementError):
            measure_array(image,calibration=cal,corners=corners)

    def test_multiple_cavities_need_roi(self):
        image = np.full((400,800,3),190,np.uint8)
        cv2.rectangle(image,(50,90),(300,300),(55,55,55),-1)
        cv2.rectangle(image,(480,90),(730,300),(55,55,55),-1)
        with self.assertRaisesRegex(MeasurementError,"Multiple"):
            measure_array(image)
        report, _, _ = measure_array(image,roi=[20,60,330,280])
        self.assertEqual(report["status"],"pixel_only")
        self.assertAlmostEqual(report["dimensions"]["length"],251,delta=.6)

    def test_uncorrected_trapezoid_does_not_become_rectangle(self):
        world = np.array([[-30,-20],[30,-20],[30,20],[-30,20]],np.float32)
        pixels = np.array([[190,155],[800,205],[730,650],[250,590]],np.float32)
        image,corners,_ = render_cavity(cv2.getPerspectiveTransform(world,pixels))
        report, _, _ = measure_array(image,calibration={"mm_per_pixel":.1},corners=corners)
        self.assertEqual(report["status"],"review_required")
        self.assertIsNone(report["dimensions"])
        self.assertTrue(report["section_spacings"])

    def test_wrong_calibration_size_and_nonfinite_scale_fail(self):
        image, _, cal = render_cavity()
        cal["image_size"] = [100,100]
        for bad in (cal,{"mm_per_pixel":0},{"mm_per_pixel":float("nan")},
                    {"pixel_to_mm":[[1,0,0],[0,0,0],[0,0,1]]}):
            with self.subTest(bad=str(bad)):
                with self.assertRaises(MeasurementError):
                    measure_array(image,calibration=bad)

    def test_ransac_ignores_large_outliers(self):
        rng = np.random.default_rng(3)
        x = np.linspace(0,200,150)
        points = np.column_stack([x,30+.2*x+rng.normal(0,.1,len(x))])
        outliers = np.column_stack([rng.uniform(0,200,50),rng.uniform(-100,150,50)])
        all_points = np.vstack([points,outliers])
        hint = np.array([-.2,1])/np.hypot(.2,1)
        line,mask = robust_line(all_points,hint,Settings(),rng)
        residual = np.abs(points @ line[:2]+line[2])
        self.assertLess(residual.mean(),.12)
        self.assertGreater(mask[:150].mean(),.95)

    def test_wrong_seed_and_invalid_settings_fail(self):
        image, corners, cal = render_cavity()
        with self.assertRaises(MeasurementError):
            measure_array(image,calibration=cal,corners=corners+[30,30])
        with self.assertRaises(MeasurementError):
            measure_array(image,Settings(corner_exclusion=.5))

    def test_unicode_paths_cli_success_and_failure(self):
        workspace = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix=".test_",dir=workspace) as temp:
            # Check the absolute cleanup target before TemporaryDirectory removes it.
            self.assertEqual(Path(temp).resolve().parent,workspace.resolve())
            root = Path(temp)/"中文目录"
            root.mkdir()
            image, _, _ = render_cavity()
            path = root/"方腔.png"
            write_image(path,image)
            script = str(Path(__file__).resolve().parents[1]/"cavity_measure.py")
            command = [sys.executable,"-X","utf8",script,"measure","--image",str(path),
                       "--mm-per-pixel","0.1","--out",str(root/"结果")]
            result = subprocess.run(command,capture_output=True,encoding="utf-8")
            self.assertEqual(result.returncode,0,result.stderr)
            data = json.loads((root/"结果"/"result.json").read_text(encoding="utf-8"))
            self.assert_dimensions(data)
            # Reusing the output directory on failure must not expose stale dimensions.
            write_image(path,np.full_like(image,127))
            result = subprocess.run(command,capture_output=True,encoding="utf-8")
            self.assertEqual(result.returncode,2)
            data = json.loads((root/"结果"/"result.json").read_text(encoding="utf-8"))
            self.assertEqual(data["status"],"failed")
            self.assertIsNone(data["dimensions"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
