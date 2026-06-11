# src/services/image_processor.py
# 通用图像处理工具
# 职责: 提供 tile 纹理的预处理与后处理
#   - downscale():    将 512px SD 输出缩放到目标像素尺寸 (16/32/64/128)
#                      使用 NEAREST 插值以保持像素风格的锐利边缘
#   - nine_slice():   将 surface 纹理按 3×3 九宫格切割为 8 个子区域
#                      返回 {"TL","T","TR","L","R","BL","B","BR"}
#   - resize():       通用缩放
#   - ensure_rgba():  确保图像为 RGBA 模式
#   - validate_tile():校验 tile 尺寸是否符合预期

from PIL import Image


class ImageProcessor:
    """提供 tile 纹理的预处理与后处理"""

    # 支持的输出 tile 尺寸
    VALID_TILE_SIZES = {16, 32, 64, 128}

    @staticmethod
    def downscale(image: Image.Image, target_size: int) -> Image.Image:
        """
        将 512px 的 SD 输出缩放到目标像素尺寸 (16/32/64/128)。
        使用 NEAREST 插值保持像素艺术风格的锐利边缘。

        Args:
            image:       输入 PIL Image (通常为 512×512)
            target_size: 目标边长 (必须为 16, 32, 64, 128 之一)

        Returns:
            缩放后的方形 PIL Image

        Raises:
            ValueError: target_size 不在 VALID_TILE_SIZES 中时抛出
        """
        if target_size not in ImageProcessor.VALID_TILE_SIZES:
            raise ValueError(
                f"target_size 必须为 {ImageProcessor.VALID_TILE_SIZES} 之一, "
                f"收到: {target_size}"
            )
        return image.resize((target_size, target_size), Image.NEAREST)

    @staticmethod
    def nine_slice(image: Image.Image) -> dict[str, Image.Image]:
        """
        将 surface 纹理按 3×3 九宫格切割为 8 个子区域。

        输入图片被均匀切割:
        ┌─────────────┐
        │ TL │  T  │ TR │  ← 上排: 左上角、上边缘、右上角
        ├────┼─────┼────┤
        │ L  │(BG) │ R  │  ← 中排: 左边缘、(中心-被BG覆盖丢弃)、右边缘
        ├────┼─────┼────┤
        │ BL │  B  │ BR │  ← 下排: 左下角、下边缘、右下角
        └─────────────┘

        Args:
            image: 方形 surface 纹理

        Returns:
            {"TL": img, "T": img, "TR": img, "L": img,
             "R": img, "BL": img, "B": img, "BR": img}
             每个子区域 image 尺寸为原图的 1/3
        """
        w, h = image.size
        cell_w, cell_h = w // 3, h // 3

        return {
            "TL": image.crop((0, 0, cell_w, cell_h)),
            "T":  image.crop((cell_w, 0, cell_w * 2, cell_h)),
            "TR": image.crop((cell_w * 2, 0, w, cell_h)),
            "L":  image.crop((0, cell_h, cell_w, cell_h * 2)),
            # 中心区域 (cell_w, cell_h, cell_w*2, cell_h*2) 丢弃
            "R":  image.crop((cell_w * 2, cell_h, w, cell_h * 2)),
            "BL": image.crop((0, cell_h * 2, cell_w, h)),
            "B":  image.crop((cell_w, cell_h * 2, cell_w * 2, h)),
            "BR": image.crop((cell_w * 2, cell_h * 2, w, h)),
        }

    @staticmethod
    def resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
        """通用缩放 (使用 NEAREST 保持像素风格)"""
        return image.resize(size, Image.NEAREST)

    @staticmethod
    def ensure_rgba(image: Image.Image) -> Image.Image:
        """确保图像为 RGBA 模式 (便于图层叠加)"""
        if image.mode != "RGBA":
            return image.convert("RGBA")
        return image

    @staticmethod
    def validate_tile(
        image: Image.Image, expected_size: tuple[int, int]
    ) -> bool:
        """校验 tile 尺寸是否符合预期"""
        return image.size == expected_size
