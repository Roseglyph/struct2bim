from pathlib import Path

import cv2
import ezdxf
import numpy as np
import pytest

from struct2bim.inputs import prepare_document


def test_prepare_image_normalizes_to_png(tmp_path: Path) -> None:
    source = tmp_path / "drawing.jpg"
    cv2.imwrite(str(source), np.full((40, 60, 3), 255, dtype=np.uint8))

    prepared = prepare_document(source, tmp_path / "prepared")

    assert len(prepared) == 1
    assert prepared[0].suffix == ".png"
    assert cv2.imread(str(prepared[0])).shape[:2] == (40, 60)


def test_prepare_basic_dxf_renders_geometry(tmp_path: Path) -> None:
    source = tmp_path / "drawing.dxf"
    document = ezdxf.new("R2018")
    document.modelspace().add_lwpolyline([(0, 0), (1000, 0), (1000, 500), (0, 500)], close=True)
    document.saveas(source)

    prepared = prepare_document(source, tmp_path / "prepared")

    assert prepared[0].is_file()
    assert cv2.imread(str(prepared[0])).min() < 255


def test_prepare_dwg_has_explicit_conversion_guidance(tmp_path: Path) -> None:
    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"placeholder")

    with pytest.raises(ValueError, match="export.*DXF or PDF"):
        prepare_document(source, tmp_path / "prepared")
