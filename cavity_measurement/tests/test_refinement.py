"""Regression for evidence-free centroid jumps and unchanged supported peaks."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cavity_measure import np
from cavity_measurement.contour import _refine_profile_offsets


class ProfileRefinementTests(unittest.TestCase):
    def test_zero_weight_keeps_tracked_offsets_and_marks_points_unsupported(self):
        offsets=np.arange(-75.,25.5,.5)
        path=np.array([10,180])
        gradient=np.zeros((2,len(offsets)),np.float32)
        refined,supported=_refine_profile_offsets(gradient,offsets,path,np.ones_like(gradient,bool))
        np.testing.assert_array_equal(refined,[-70.,15.])
        np.testing.assert_array_equal(supported,[False,False])

    def test_valid_symmetric_peak_retains_subpixel_location(self):
        offsets=np.arange(-75.,25.5,.5)
        gradient=(20*np.exp(-.5*((offsets-12.25)/.8)**2))[None,:]
        path=np.array([np.argmax(gradient[0])])
        refined,supported=_refine_profile_offsets(gradient,offsets,path,np.ones_like(gradient,bool))
        self.assertTrue(supported[0])
        self.assertAlmostEqual(refined[0],12.25,delta=.003)

    def test_invalid_sampling_cannot_supply_refinement_evidence(self):
        offsets=np.arange(-75.,25.5,.5)
        gradient=(20*np.exp(-.5*((offsets+35)/.8)**2))[None,:]
        path=np.array([np.argmax(gradient[0])])
        refined,supported=_refine_profile_offsets(gradient,offsets,path,np.zeros_like(gradient,bool))
        self.assertFalse(supported[0])
        self.assertEqual(refined[0],-35.)


if __name__=='__main__':
    unittest.main()
