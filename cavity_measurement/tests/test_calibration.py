"""Planar calibration, calibration checks and robust line fitting; run with unittest discover."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cavity_measure import (MeasurementError, build_planar_calibration, check_calibration, cv2, np,
                            robust_line, transform_points, undistort_points, write_image, write_json)

# Independent reference lies outside the 60 x 40 mm cavity; its virtual corners are only check points.
REFERENCE = np.array([[-35,-25],[35,-25],[35,25],[-35,25],[0,-25],[0,25]], np.float64)
CHECK = np.array([[-30,-20],[30,-20],[30,20],[-30,20],[0,0]], np.float64)


def affine_mapping(angle_deg=17, scale_px_per_mm=10, center=(500, 380)):
    angle = np.deg2rad(angle_deg)
    c, s = np.cos(angle)*scale_px_per_mm, np.sin(angle)*scale_px_per_mm
    return np.array([[c,-s,center[0]], [s,c,center[1]], [0,0,1]], np.float64)


class CalibrationTests(unittest.TestCase):
    image = np.zeros((760,1000,3), np.uint8)

    def test_perspective_compensated_by_independent_reference(self):
        world = np.array([[-30,-20],[30,-20],[30,20],[-30,20]],np.float32)
        pixels = np.array([[190,155],[800,205],[730,650],[250,590]],np.float32)
        h = cv2.getPerspectiveTransform(world,pixels)
        cal = build_planar_calibration(self.image,{"image_points_px":transform_points(REFERENCE,h).tolist(),
                                                   "world_points_mm":REFERENCE.tolist()})
        mapped = transform_points(transform_points(CHECK,h), cal["pixel_to_mm"])
        np.testing.assert_allclose(mapped, CHECK, atol=1e-4)
        self.assertEqual(cal["image_size"], [1000,760])

    def test_lens_distortion_points_are_corrected_consistently(self):
        mapping = affine_mapping(17)
        k = np.array([[950.,0,500.],[0,950.,380.],[0,0,1.]])
        d = np.array([-.22,.04,.001,-.001,0.])

        def distort_points(p):
            normalized = np.column_stack([(p[:,0]-500)/950,(p[:,1]-380)/950,np.ones(len(p))])
            return cv2.projectPoints(normalized,np.zeros(3),np.zeros(3),k,d)[0].reshape(-1,2)

        calibration = build_planar_calibration(self.image,
            {"image_points_px":distort_points(transform_points(REFERENCE,mapping)).tolist(),
             "world_points_mm":REFERENCE.tolist()},
            {"camera_matrix":k.tolist(),"dist_coeffs":d.tolist()})
        raw_check = distort_points(transform_points(CHECK,mapping))
        mapped = transform_points(undistort_points(raw_check,calibration), calibration["pixel_to_mm"])
        np.testing.assert_allclose(mapped, CHECK, atol=.01)

    def test_invalid_reference_points_fail(self):
        line = [[100,100],[200,100],[300,100],[400,100]]
        for spec in ({"image_points_px":line,"world_points_mm":[[0,0],[10,0],[20,0],[30,0]]},
                     {"image_points_px":[[100,100],[300,100],[300,300],[100,300],[200,200]],
                      "world_points_mm":[[0,0],[10,0],[10,10],[0,10]]},
                     {"image_points_px":[[-5,0],[200,0],[200,200],[0,200]],
                      "world_points_mm":[[0,0],[10,0],[10,10],[0,10]]}):
            with self.subTest(spec=str(spec)):
                with self.assertRaises(MeasurementError):
                    build_planar_calibration(self.image, spec)

    def test_calibration_cli_from_independent_reference(self):
        workspace = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix=".test_",dir=workspace) as temp:
            self.assertEqual(Path(temp).resolve().parent,workspace.resolve())
            root = Path(temp)/"中文目录"
            pixels = transform_points(REFERENCE,affine_mapping())
            write_image(root/"reference.png",self.image)
            write_json(root/"points.json",{"image_points_px":pixels.tolist(),
                                           "world_points_mm":REFERENCE.tolist()})
            command = [sys.executable,"-X","utf8",str(workspace/"cavity_measure.py"),"calibrate",
                       "--image",str(root/"reference.png"),"--points",str(root/"points.json"),
                       "--out",str(root/"cal.json")]
            run = subprocess.run(command,capture_output=True,encoding="utf-8")
            self.assertEqual(run.returncode,0,run.stderr)
            calibration = json.loads((root/"cal.json").read_text(encoding="utf-8"))
            mapped = transform_points(transform_points(CHECK,affine_mapping()), calibration["pixel_to_mm"])
            np.testing.assert_allclose(mapped, CHECK, atol=1e-4)
            self.assertLess(calibration["reference_fit_rms_mm"], 1e-4)

    def test_wrong_calibration_size_and_nonfinite_scale_fail(self):
        for bad in ({"image_size":[100,100],"mm_per_pixel":.1},{"mm_per_pixel":0},
                    {"mm_per_pixel":float("nan")},{"pixel_to_mm":[[1,0,0],[0,0,0],[0,0,1]]},
                    {"mm_per_pixel":.1,"pixel_to_mm":np.eye(3).tolist()}):
            with self.subTest(bad=str(bad)):
                with self.assertRaises(MeasurementError):
                    check_calibration(bad,[1000,760])

    def test_ransac_ignores_large_outliers(self):
        rng = np.random.default_rng(3)
        x = np.linspace(0,200,150)
        points = np.column_stack([x,30+.2*x+rng.normal(0,.1,len(x))])
        outliers = np.column_stack([rng.uniform(0,200,50),rng.uniform(-100,150,50)])
        all_points = np.vstack([points,outliers])
        hint = np.array([-.2,1])/np.hypot(.2,1)
        line,mask = robust_line(all_points,hint,15,.7,rng)
        residual = np.abs(points @ line[:2]+line[2])
        self.assertLess(residual.mean(),.12)
        self.assertGreater(mask[:150].mean(),.95)


if __name__ == "__main__":
    unittest.main(verbosity=2)
