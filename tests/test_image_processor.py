# tests/test_image_processor.py
# ImageProcessor 单元测试
# 测试目标: 图像缩放与 nine_slice 切割的正确性
#   - downscale() 缩放到各目标尺寸, NEAREST 插值
#   - nine_slice() 将方形图片正确切割为 8 个等大子区域
#   - validate_tile() 尺寸校验
#   - ensure_rgba() RGBA 转换

import pytest
from PIL import Image
from src.services.image_processor import ImageProcessor


class TestDownscale:
    """downscale 缩放测试"""

    def test_downscale_512_to_32(self):
        """测试: 512×512 → 32×32"""
        img = Image.new("RGBA", (512, 512), (255, 0, 0, 255))
        result = ImageProcessor.downscale(img, 32)
        assert result.size == (32, 32)

    def test_downscale_512_to_16(self):
        """测试: 512×512 → 16×16"""
        img = Image.new("RGBA", (512, 512), (0, 255, 0, 255))
        result = ImageProcessor.downscale(img, 16)
        assert result.size == (16, 16)

    def test_downscale_invalid_size_raises(self):
        """测试: 非法 target_size 应抛出 ValueError"""
        img = Image.new("RGBA", (512, 512))
        with pytest.raises(ValueError):
            ImageProcessor.downscale(img, 48)

    def test_downscale_preserves_nearest(self):
        """测试: NEAREST 插值保持颜色不变 (同色图片缩放后颜色不变)"""
        img = Image.new("RGBA", (512, 512), (100, 150, 200, 255))
        result = ImageProcessor.downscale(img, 16)
        pixel = result.getpixel((0, 0))
        assert pixel == (100, 150, 200, 255)


class TestNineSlice:
    """nine_slice 切割测试"""

    def test_nine_slice_returns_8_parts(self):
        """测试: 应返回 8 个子区域"""
        img = Image.new("RGBA", (96, 96))
        parts = ImageProcessor.nine_slice(img)
        assert len(parts) == 8
        assert set(parts.keys()) == {"TL", "T", "TR", "L", "R", "BL", "B", "BR"}

    def test_nine_slice_correct_sizes(self):
        """测试: 96×96 图片切割后每个子区域应为 32×32"""
        img = Image.new("RGBA", (96, 96))
        parts = ImageProcessor.nine_slice(img)
        for part in parts.values():
            assert part.size == (32, 32)

    def test_nine_slice_maps_correctly(self):
        """测试: 不同区域应包含不同像素 (验证位置映射)"""
        # 创建 4 个颜色象限的图片来验证切割正确性
        img = Image.new("RGBA", (96, 96))
        # 左上红色
        for x in range(48):
            for y in range(48):
                img.putpixel((x, y), (255, 0, 0, 255))
        # 右上绿色
        for x in range(48, 96):
            for y in range(48):
                img.putpixel((x, y), (0, 255, 0, 255))

        parts = ImageProcessor.nine_slice(img)
        # TL 应为红色
        assert parts["TL"].getpixel((0, 0)) == (255, 0, 0, 255)
        # TR 应为绿色
        assert parts["TR"].getpixel((0, 0)) == (0, 255, 0, 255)


class TestValidateTile:
    """validate_tile 测试"""

    def test_matching_size_returns_true(self):
        img = Image.new("RGBA", (32, 32))
        assert ImageProcessor.validate_tile(img, (32, 32)) is True

    def test_mismatched_size_returns_false(self):
        img = Image.new("RGBA", (64, 64))
        assert ImageProcessor.validate_tile(img, (32, 32)) is False


class TestEnsureRGBA:
    """ensure_rgba 测试"""

    def test_rgb_converted_to_rgba(self):
        img = Image.new("RGB", (32, 32), (255, 0, 0))
        result = ImageProcessor.ensure_rgba(img)
        assert result.mode == "RGBA"
