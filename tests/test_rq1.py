import unittest

import numpy as np

from arsc_eval.rq1 import rationale_jaccard_components


class RQ1Tests(unittest.TestCase):
    def test_jaccard_reports_empty_empty_separately(self):
        clean = np.array([[0.1, 0.2], [0.9, 0.1]])
        perturbed = np.array([[0.2, 0.1], [0.9, 0.9]])
        result = rationale_jaccard_components(
            clean, perturbed, threshold=0.5
        )
        self.assertEqual(result["empty_empty_fraction"], 0.5)
        self.assertAlmostEqual(result["union_nonempty_conditional"], 0.5)
        self.assertAlmostEqual(result["unconditional"], 0.75)


if __name__ == "__main__":
    unittest.main()
