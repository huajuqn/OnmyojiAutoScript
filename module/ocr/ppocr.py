from pathlib import Path
from typing import List

import numpy as np
import ppocronnx.predict_system
from ppocronnx.rec.predict_rec import TextRecognizer
from ppocronnx.rec.rec_decoder import CTCLabelDecode


class TextSystem(ppocronnx.predict_system.TextSystem):
    def __init__(
            self,
            use_angle_cls=False,
            box_thresh=0.6,
            unclip_ratio=1.6,
            rec_model_path=None,
            det_model_path=None,
            ort_providers=None
    ):
        super().__init__(
            use_angle_cls=use_angle_cls,
            box_thresh=box_thresh,
            unclip_ratio=unclip_ratio,
            rec_model_path=rec_model_path,
            det_model_path=det_model_path,
            ort_providers=ort_providers
        )


class RecognitionOnlyTextSystem:
    """只加载识别模型的轻量 OCR，供固定单行区域使用。"""

    def __init__(
            self,
            rec_model_path,
            character_dict_path,
            ort_providers=None
    ):
        self.text_recognizer = TextRecognizer(
            rec_model_path=str(rec_model_path),
            ort_providers=ort_providers
        )
        characters = Path(character_dict_path).read_text(encoding="utf-8").splitlines()
        self.text_recognizer.postprocess_op = CTCLabelDecode(
            character_dict=characters,
            character_type="ch",
            use_space_char=True
        )

    def ocr_lines(self, img_list: List[np.ndarray]):
        rotated_images = []
        for image in img_list:
            height, width = image.shape[:2]
            if height * 1.0 / width >= 1.5:
                image = np.rot90(image)
            rotated_images.append(image)
        results, _ = self.text_recognizer(rotated_images)
        return results

    def ocr_single_line(self, image):
        results = self.ocr_lines([image])
        if results:
            return results[0]
        return "", 0.0

    # def ocr_single_line(self, img):
    #     img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    #     return super().ocr_single_line(img)
    #
    # def detect_and_ocr(self, img: np.ndarray,**kwargs):
    #     img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    #     return super().detect_and_ocr(img, **kwargs)


def sorted_boxes(dt_boxes):
    """
    Sort text boxes in order from top to bottom, left to right
    args:
        dt_boxes(array):detected text boxes with shape [4, 2]
    return:
        sorted boxes(array) with shape [4, 2]
    """
    num_boxes = dt_boxes.shape[0]
    sorted_boxes = sorted(dt_boxes, key=lambda x: (x[0][1], x[0][0]))
    _boxes = list(sorted_boxes)

    for i in range(num_boxes - 1):
        for j in range(i, -1, -1):
            if abs(_boxes[j + 1][0][1] - _boxes[j][0][1]) < 10 and \
                    (_boxes[j + 1][0][0] < _boxes[j][0][0]):
                tmp = _boxes[j]
                _boxes[j] = _boxes[j + 1]
                _boxes[j + 1] = tmp
            else:
                break
    return _boxes

# sorted_boxes() from PaddleOCR 2.6, newer and better than the one in ppocr-onnx
ppocronnx.predict_system.sorted_boxes = sorted_boxes
