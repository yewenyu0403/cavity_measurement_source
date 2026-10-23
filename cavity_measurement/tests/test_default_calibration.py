"""Default calibration selection and protection against applying it to resized images."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cavity_measure import MeasurementError,check_calibration,resolve_calibration


class DefaultCalibrationTests(unittest.TestCase):
    def setUp(self):
        workspace=Path(__file__).resolve().parents[1]
        self.directory=tempfile.TemporaryDirectory(prefix='.test_default_',dir=workspace)
        self.assertEqual(Path(self.directory.name).resolve().parent,workspace.resolve())
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.config=self.root/'config'/'calibration.json'
        self.config.parent.mkdir()
        self.calibration={'mm_per_pixel':.009683443764816625,'image_size':[7008,7000],
                          'quality_status':'provisional_single_frame_low_contrast'}
        self.config.write_text(json.dumps(self.calibration),encoding='utf-8')
        self.root_patch=patch('cavity_measurement.measurement.PROJECT_ROOT',self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_default_keeps_metadata_and_rejects_resized_image(self):
        calibration=resolve_calibration()
        self.assertEqual(calibration,self.calibration)
        self.assertAlmostEqual(check_calibration(calibration,[7008,7000])[0,0],.009683443764816625)
        with self.assertRaisesRegex(MeasurementError,'image_size differs'):
            check_calibration(calibration,[3504,3500])

    def test_explicit_file_and_scalar_override_default(self):
        other=self.root/'new_calibration.json'
        other.write_text(json.dumps({'mm_per_pixel':.02}),encoding='utf-8')
        self.assertEqual(resolve_calibration(other),{'mm_per_pixel':.02})
        self.assertEqual(resolve_calibration(mm_per_pixel=.03)['mm_per_pixel'],.03)

    def test_pixels_only_bypasses_even_invalid_default(self):
        self.config.write_text('not valid JSON',encoding='utf-8')
        self.assertIsNone(resolve_calibration(pixels_only=True))

    def test_invalid_default_is_not_silently_ignored(self):
        self.config.write_text('not valid JSON',encoding='utf-8')
        with self.assertRaises(ValueError):
            resolve_calibration()

    def test_missing_default_preserves_pixel_mode_and_conflicts_fail(self):
        self.config.unlink()
        self.assertIsNone(resolve_calibration())
        with self.assertRaises(MeasurementError):
            resolve_calibration(mm_per_pixel=.02,pixels_only=True)


if __name__=='__main__':
    unittest.main()
