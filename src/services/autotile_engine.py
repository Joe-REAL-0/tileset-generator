"""
autotile_engine.py
47-tile 自动图块生成引擎

功能：输入一张 background 和一张 surface，使用旋转复用模式生成完整的 47 个 tile。

编码规则（8位二进制，顺时针方向）：
  bit0 = 左上角 (TL)     bit1 = 上 (T)       bit2 = 右上角 (TR)
  bit7 = 左 (L)          [中心]               bit3 = 右 (R)
  bit6 = 左下角 (BL)     bit5 = 下 (B)       bit4 = 右下角 (BR)

  1 = 该方向有邻接图块（不显示 surface 边缘）
  0 = 该方向无邻接图块（显示 surface 边缘）

旋转复用模式：
  先将 surface 复制四份，分别旋转到四个方向并叠加，
  然后裁剪出 8 个部分的边缘素材，保证四边风格统一并保留所有方向的细节。
"""

from pathlib import Path
from PIL import Image, ImageChops


# ==================== 常量定义 ====================

# 8个方向的位索引与名称映射（顺时针，从左上角开始）
BIT_TL = 0  # 左上角
BIT_T  = 1  # 上
BIT_TR = 2  # 右上角
BIT_R  = 3  # 右
BIT_BR = 4  # 右下角
BIT_B  = 5  # 下
BIT_BL = 6  # 左下角
BIT_L  = 7  # 左

# 角方向与其依赖的两个相邻边
CORNER_DEPS = {
    BIT_TL: (BIT_T, BIT_L),  # 左上角要求：上 + 左
    BIT_TR: (BIT_T, BIT_R),  # 右上角要求：上 + 右
    BIT_BR: (BIT_B, BIT_R),  # 右下角要求：下 + 右
    BIT_BL: (BIT_B, BIT_L),  # 左下角要求：下 + 左
}

def get_project_root() -> Path:
    """动态向上查找 src 目录，以精确定位项目根目录"""
    path = Path(__file__).resolve()
    while path.name != 'src' and path.parent != path:
        path = path.parent
    return path.parent if path.name == 'src' else Path(__file__).resolve().parent.parent.parent

# 输出目录（相对于项目根目录：output/tiles/）
OUTPUT_DIR = get_project_root() / "output" / "tiles"


class AutotileEngine:
    """
    47-tile 自动图块生成引擎。

    使用方式：
        engine = AutotileEngine(background_img, surface_img, tile_size=32)
        saved_files = engine.generate_all()
    """

    def __init__(
        self,
        background: Image.Image,
        surface: Image.Image,
        tile_size: int = 32,
        output_dir: str | None = None
    ):
        """
        Args:
            background: 背景材质 PIL Image（从前端获取）
            surface:    表面/边缘材质 PIL Image（从前端获取）
            tile_size:  tile 像素尺寸（默认32）
            output_dir: 输出目录路径（默认为 src/services/image/）
        """
        self.tile_size = tile_size
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR

        # 预处理材质图（确保 RGBA + 缩放到目标尺寸）
        self.bg_img = background.convert("RGBA").resize(
            (tile_size, tile_size), Image.NEAREST
        )
        surface_img = surface.convert("RGBA").resize(
            (tile_size, tile_size), Image.NEAREST
        )

        # 准备 surface 四个方向的图层及内角图层
        self._prepare_surface_layers(surface_img)

        # 生成 47 种有效掩码
        self.valid_masks = self._generate_valid_47_masks()

    # ==================== 掩码生成 ====================

    @staticmethod
    def _generate_valid_47_masks() -> list[int]:
        """
        生成标准 47 种有效 8 邻接掩码。

        过滤规则：角方向有邻居的前提是，相邻的两个边方向都有邻居。
        例如：左上角(bit0)=1 要求 上(bit1)=1 且 左(bit7)=1。
        """
        valid_masks = []
        for mask in range(256):
            valid = True
            for corner_bit, (edge_a, edge_b) in CORNER_DEPS.items():
                if (mask >> corner_bit) & 1:
                    if not ((mask >> edge_a) & 1 and (mask >> edge_b) & 1):
                        valid = False
                        break
            if valid:
                valid_masks.append(mask)

        assert len(valid_masks) == 47, (
            f"有效掩码数量错误，应为47，实际为{len(valid_masks)}"
        )
        return valid_masks

    @staticmethod
    def mask_to_binary(mask: int) -> str:
        """
        将掩码整数转换为 8 位二进制字符串。

        编码顺序：bit0(TL) 在最左边，bit7(L) 在最右边。
        例如：mask=0b10000010 → "01000001"
        """
        return "".join(str((mask >> i) & 1) for i in range(8))

    # ==================== Surface 图层准备 ====================

    def _prepare_surface_layers(self, surface_img: Image.Image):
        """
        新算法：
        1. 将四个方向的surface视作四个图层。
        2. 计算四个方向两两叠加并保留严格重叠部分的内角图层。
        """
        # 1. 生成四个方向的 surface
        self.s_T = surface_img
        self.s_L = surface_img.rotate(90, resample=Image.NEAREST)
        self.s_B = surface_img.rotate(180, resample=Image.NEAREST)
        self.s_R = surface_img.rotate(270, resample=Image.NEAREST)

        # 2. 生成四个角落的“严格重叠”图层（inner corners）
        # 左上：上 + 左
        self.inner_TL = self._get_intersection(self.s_T, self.s_L)
        # 右上：上 + 右
        self.inner_TR = self._get_intersection(self.s_T, self.s_R)
        # 右下：下 + 右
        self.inner_BR = self._get_intersection(self.s_B, self.s_R)
        # 左下：下 + 左
        self.inner_BL = self._get_intersection(self.s_B, self.s_L)

    def _get_intersection(self, img1: Image.Image, img2: Image.Image) -> Image.Image:
        """
        将两个图层叠加，并裁剪保留两者严格重叠的部分（alpha 交集）。
        """
        # 1. 把 img1 和 img2 叠加
        comp = Image.alpha_composite(img1, img2)
        # 2. 取两者的 alpha 通道
        a1 = img1.split()[3]
        a2 = img2.split()[3]
        # 3. 严格重叠：取两者的 alpha 较小值（只有两者都有 alpha 时，结果才有 alpha）
        a_inter = ImageChops.darker(a1, a2)
        # 4. 将叠加后的图像的 alpha 替换为相交后的 alpha
        comp.putalpha(a_inter)
        return comp

    # ==================== Tile 合成 ====================

    def compose_tile(self, mask: int) -> Image.Image:
        """
        根据邻接掩码合成单张 tile。

        掩码位为 0（无邻接）→ 显示 surface
        掩码位为 1（有邻接）→ 不显示 surface
        """
        tile = self.bg_img.copy()

        show_T = (mask >> BIT_T) & 1 == 0
        show_R = (mask >> BIT_R) & 1 == 0
        show_B = (mask >> BIT_B) & 1 == 0
        show_L = (mask >> BIT_L) & 1 == 0

        show_TL = (mask >> BIT_TL) & 1 == 0
        show_TR = (mask >> BIT_TR) & 1 == 0
        show_BR = (mask >> BIT_BR) & 1 == 0
        show_BL = (mask >> BIT_BL) & 1 == 0

        # 1. 如果上下左右某个方向上的surface应该存在，就先将某个方向上的surface图层显示出来
        if show_T: tile = Image.alpha_composite(tile, self.s_T)
        if show_R: tile = Image.alpha_composite(tile, self.s_R)
        if show_B: tile = Image.alpha_composite(tile, self.s_B)
        if show_L: tile = Image.alpha_composite(tile, self.s_L)

        # 2. 对于角存在，且对应的两个边不存在时（即只有角落显示surface），使用严格重叠的内角图层
        if show_TL and not show_T and not show_L:
            tile = Image.alpha_composite(tile, self.inner_TL)
        if show_TR and not show_T and not show_R:
            tile = Image.alpha_composite(tile, self.inner_TR)
        if show_BR and not show_B and not show_R:
            tile = Image.alpha_composite(tile, self.inner_BR)
        if show_BL and not show_B and not show_L:
            tile = Image.alpha_composite(tile, self.inner_BL)

        return tile

    # ==================== 批量生成与保存 ====================

    def generate_all(self) -> list[str]:
        """
        生成完整的 47 个 autotile 并保存到输出目录。

        每个 tile 以 8 位二进制编码命名（如 "01010101.png"）。

        Returns:
            所有已保存文件的路径列表
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for mask in self.valid_masks:
            tile = self.compose_tile(mask)

            filename = f"{self.mask_to_binary(mask)}.png"
            save_path = self.output_dir / filename
            tile.save(save_path, "PNG")
            saved_files.append(str(save_path))

        print(f"✅ 生成完成！全部 {len(saved_files)} 个 tile 已保存到: {self.output_dir}")
        return saved_files


# ==================== 直接执行入口（仅供本地调试） ====================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("用法: python autotile_engine.py <background_path> <surface_path> [tile_size]")
        print("示例: python autotile_engine.py bg.png surface.png 32")
        sys.exit(1)

    bg = Image.open(sys.argv[1])
    sf = Image.open(sys.argv[2])
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 32

    engine = AutotileEngine(bg, sf, tile_size=size)
    engine.generate_all()
