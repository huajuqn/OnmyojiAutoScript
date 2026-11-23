"""组队页两种等级外观任一命中即可，标题不能单独通过。"""
import unittest
import cv2
import numpy as np
from tasks.GameUi.assets import GameUiAssets


class TeamPageVariantsTest(unittest.TestCase):
    def test_either_bottom_left_variant(self):
        rule = GameUiAssets.I_CHECK_TEAM
        for candidate in [rule.image] + rule.alternate_images:
            image = np.zeros((720, 1280, 3), np.uint8)
            h, w = candidate.shape[:2]
            image[580:580+h, 25:25+w] = candidate
            self.assertTrue(rule.match(image))
            self.assertEqual(rule.roi_front, [25, 580, w, h])

    def test_title_alone_does_not_match(self):
        image = np.zeros((720, 1280, 3), np.uint8)
        cv2.putText(image, 'TEAM', (90, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        self.assertFalse(GameUiAssets.I_CHECK_TEAM.match(image))

    def test_variant_outside_bottom_left_does_not_match(self):
        rule = GameUiAssets.I_CHECK_TEAM
        for candidate in [rule.image] + rule.alternate_images:
            image = np.zeros((720, 1280, 3), np.uint8)
            h, w = candidate.shape[:2]
            image[200:200+h, 500:500+w] = candidate
            self.assertFalse(rule.match(image))


if __name__ == '__main__':
    unittest.main()
