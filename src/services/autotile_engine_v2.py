"""
autotile_engine.py
Autotile Bitmask 合成引擎（核心模块）

职责：
    根据 4-bit 邻接 bitmask 规则，将 background 纹理与 surface 的 8 个子区域
    合成为全部 47 种邻接变体 tile。

    每个 tile 由 background 底图 + 根据邻接 bitmask 选择性叠加 surface 的对应子区域组成。

    集成 ImageProcessor 进行图像预处理：
    - downscale: 将 SD 生成的大图缩放到目标 tile 尺寸
    - nine_slice: 将 surface 大图切割为 8 个子区域
    - ensure_rgba: 确保所有图像为 RGBA 模式

Bitmask 模型（4-bit）：
    bit[0] (0x1): 上邻是否为同材质 (1=是/显示BG, 0=否/显示Surface)
    bit[1] (0x2): 下邻是否为同材质
    bit[2] (0x4): 左邻是否为同材质
    bit[3] (0x8): 右邻是否为同材质

子区域（8个，假设 tile_size=32，每个子区域 16x16）：
    TL (左上角): 上邻=0 且 左邻=0 时显示
    T  (上边缘): 上邻=0 时显示
    TR (右上角): 上邻=0 且 右邻=0 时显示
    L  (左边缘): 左邻=0 时显示
    R  (右边缘): 右邻=0 时显示
    BL (左下角): 下邻=0 且 左邻=0 时显示
    B  (下边缘): 下邻=0 时显示
    BR (右下角): 下邻=0 且 右邻=0 时显示

命名规则：
    见 docs/autotile_naming_convention.md

使用示例：
    # 方式1：从原始 SD 输出创建（推荐）
    engine = AutotileEngine.from_raw_images(
        raw_background=bg_512x512,      # SD 生成的大图
        raw_surface=surface_96x96,    # SD 生成的大图
        tile_size=32
    )

    # 方式2：直接传入已处理的图像
    engine = AutotileEngine(bg_img, parts_dict, tile_size=32)

    # 生成
    all_tiles = engine.generate_all()  # -> list[(bitmask, tile_image)]
    engine.save_all(output_dir, prefix="grass")
"""

from PIL import Image
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import os

# 集成 ImageProcessor
from .image_processor import ImageProcessor


class AutotileEngine:
    """
    Autotile 合成引擎

    根据 4-bit bitmask 规则，将 background 和 surface 子区域合成为 16 种 tile 变体。

    支持两种初始化方式：
    1. 直接传入已处理的图像（background + surface_parts_dict）
    2. 从原始 SD 输出创建（from_raw_images 类方法）
    """

    # 8 个子区域在 tile 中的左上角粘贴位置
    # 根据 tile_size 动态计算坐标
    REGION_POSITIONS = {
        'TL': (0, 0),           # 左上角
        'T':  None,             # 上边缘 — 动态计算 (sub_size, 0)
        'TR': (0, 0),           # 右上角 — 与 TL 同位置，但 surface 贴图不同
        'L':  None,             # 左边缘 — 动态计算 (0, sub_size)
        'R':  None,             # 右边缘 — 动态计算 (sub_size, sub_size)
        'BL': (0, 0),           # 左下角 — 与 L 同位置
        'B':  None,             # 下边缘 — 动态计算 (sub_size, sub_size)
        'BR': None,             # 右下角 — 与 R 同位置
    }

    # 16 种有效 bitmask 配置
    VALID_BITMASKS = list(range(16))  # 0x0 ~ 0xF

    def __init__(self, 
                 background_img: Image.Image, 
                 surface_parts_dict: Dict[str, Image.Image],
                 tile_size: int = 32):
        """
        初始化 Autotile 引擎（方式1：传入已处理的图像）

        Args:
            background_img: 背景底图 (RGBA 模式，tile_size x tile_size)
            surface_parts_dict: surface 子区域图像字典
                格式: {
                    'TL': Image, 'T': Image, 'TR': Image,
                    'L': Image, 'R': Image,
                    'BL': Image, 'B': Image, 'BR': Image
                }
                每个子区域是 tile_size/2 x tile_size/2 的图像
            tile_size: 瓦片尺寸 (16, 32, 64, 128)，默认 32
        """
        self.tile_size = tile_size
        self.sub_size = tile_size // 2

        # 确保背景图尺寸正确，并使用 RGBA
        self.background = ImageProcessor.ensure_rgba(background_img)
        if self.background.size != (tile_size, tile_size):
            self.background = ImageProcessor.downscale(self.background, tile_size)

        # 确保所有子区域尺寸正确，并使用 RGBA
        self.surface_parts = {}
        for name, img in surface_parts_dict.items():
            img_rgba = ImageProcessor.ensure_rgba(img)
            if img_rgba.size != (self.sub_size, self.sub_size):
                img_rgba = ImageProcessor.downscale(img_rgba, self.sub_size)
            self.surface_parts[name] = img_rgba

        # 初始化区域位置（动态计算）
        self._init_region_positions()

    @classmethod
    def from_raw_images(cls,
                        raw_background: Image.Image,
                        raw_surface: Image.Image,
                        tile_size: int = 32) -> "AutotileEngine":
        """
        从原始 SD 输出创建引擎（方式2：推荐）

        自动完成以下预处理：
        1. ensure_rgba — 确保 RGBA 模式
        2. downscale — 将 background 缩放到 tile_size
        3. downscale + nine_slice — 将 surface 切割为 8 个子区域

        Args:
            raw_background: SD 生成的 background 大图（任意尺寸）
            raw_surface: SD 生成的 surface 大图（方形，尺寸能被 3 整除）
            tile_size: 目标瓦片尺寸

        Returns:
            初始化好的 AutotileEngine 实例

        示例：
            >>> bg = Image.open("sd_output/bg_512.png")
            >>> surf = Image.open("sd_output/surface_96.png")
            >>> engine = AutotileEngine.from_raw_images(bg, surf, tile_size=32)
        """
        # 1. 处理 background
        bg = ImageProcessor.ensure_rgba(raw_background)
        bg = ImageProcessor.downscale(bg, tile_size)

        # 2. 处理 surface
        surf = ImageProcessor.ensure_rgba(raw_surface)
        # surface 需要能被 3 整除用于 nine_slice
        # 如果尺寸不对，先缩放到合适的尺寸
        surf_size = surf.size[0]
        if surf_size % 3 != 0:
            # 缩放到最近的能被 3 整除的尺寸（如 96, 192）
            target_surf_size = ((surf_size // 3) + 1) * 3
            surf = ImageProcessor.downscale(surf, target_surf_size)

        # 切割为 8 个子区域
        surface_parts = ImageProcessor.nine_slice(surf)

        # 3. 子区域缩放到 sub_size
        sub_size = tile_size // 2
        for name, img in surface_parts.items():
            if img.size != (sub_size, sub_size):
                surface_parts[name] = ImageProcessor.downscale(img, sub_size)

        return cls(bg, surface_parts, tile_size)

    def _init_region_positions(self):
        """初始化子区域粘贴位置（根据 tile_size 动态计算）"""
        half = self.sub_size
        self.region_positions = {
            'TL': (0, 0),
            'T':  (half, 0),
            'TR': (0, 0),       # 与 TL 同位置，但 surface 贴图不同
            'L':  (0, half),
            'R':  (half, half),
            'BL': (0, half),    # 与 L 同位置
            'B':  (half, half), # 与 R 同位置
            'BR': (half, half), # 与 R 同位置
        }

    def generate_all(self) -> List[Tuple[int, Image.Image]]:
        """
        生成全部 16 种 bitmask 对应的 tile 变体

        Returns:
            List of tuples: [(bitmask, tile_image), ...]
            共 16 个元素（bitmask 0x0 ~ 0xF）
        """
        results = []
        for bitmask in self.VALID_BITMASKS:
            tile = self._generate_tile(bitmask)
            results.append((bitmask, tile))
        return results

    def generate_single(self, bitmask: int) -> Image.Image:
        """
        根据特定 bitmask 生成单个 tile

        Args:
            bitmask: 4-bit 值 (0x0 ~ 0xF)

        Returns:
            合成后的 tile 图像 (RGBA, tile_size x tile_size)
        """
        return self._generate_tile(bitmask)

    def _generate_tile(self, bitmask: int) -> Image.Image:
        """
        核心：根据 bitmask 合成单个 tile

        算法：
        1. 从 background 底图开始
        2. 解析 bitmask 确定哪些方向有同材质邻居
        3. 对没有同材质邻居的方向，叠加对应的 surface 子区域
        4. 返回合成后的 tile
        """
        # 创建新图像，从 background 开始
        tile = self.background.copy()

        # 解析 bitmask
        has_top = bool(bitmask & 0x1)      # bit0: 上邻
        has_bottom = bool(bitmask & 0x2)   # bit1: 下邻
        has_left = bool(bitmask & 0x4)    # bit2: 左邻
        has_right = bool(bitmask & 0x8)   # bit3: 右邻

        # 确定需要显示哪些子区域（没有同材质邻居的方向）
        regions_to_show = []

        # TL: 上邻=0 且 左邻=0
        if not has_top and not has_left:
            regions_to_show.append('TL')

        # T: 上邻=0
        if not has_top:
            regions_to_show.append('T')

        # TR: 上邻=0 且 右邻=0
        if not has_top and not has_right:
            regions_to_show.append('TR')

        # L: 左邻=0
        if not has_left:
            regions_to_show.append('L')

        # R: 右邻=0
        if not has_right:
            regions_to_show.append('R')

        # BL: 下邻=0 且 左邻=0
        if not has_bottom and not has_left:
            regions_to_show.append('BL')

        # B: 下邻=0
        if not has_bottom:
            regions_to_show.append('B')

        # BR: 下邻=0 且 右邻=0
        if not has_bottom and not has_right:
            regions_to_show.append('BR')

        # 叠加 surface 子区域
        for region_name in regions_to_show:
            if region_name in self.surface_parts:
                part = self.surface_parts[region_name]
                pos = self.region_positions[region_name]

                # 使用 alpha 通道透明粘贴
                if part.mode == 'RGBA':
                    tile.paste(part, pos, part)
                else:
                    tile.paste(part, pos)

        return tile

    def save_all(self, 
                 output_dir: str, 
                 prefix: str = "autotile",
                 naming_style: str = "full") -> List[str]:
        """
        保存全部 tile 到指定目录

        Args:
            output_dir: 输出目录路径
            prefix: 文件名前缀
            naming_style: 命名风格 (full/compact/hybrid)

        Returns:
            保存的文件路径列表
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        tiles = self.generate_all()
        saved_files = []

        for bitmask, tile in tiles:
            filename = self._generate_filename(bitmask, prefix, naming_style)
            filepath = output_path / filename
            tile.save(filepath, 'PNG')
            saved_files.append(str(filepath))

        return saved_files

    def _generate_filename(self, 
                            bitmask: int, 
                            prefix: str, 
                            style: str) -> str:
        """
        生成文件名

        命名规则：
        1. full 风格:   {prefix}_b{bitmask:02d}_{regions}_{tile_size}.png
        2. compact 风格: {prefix}_b{bitmask:02d}_{tile_size}.png
        3. hybrid 风格: {prefix}_b{bitmask:02d}_{region_count}r_{tile_size}.png
        """
        if style == "full":
            regions = self._get_regions_for_bitmask(bitmask)
            region_str = "_".join(regions) if regions else "NONE"
            return f"{prefix}_b{bitmask:02d}_{region_str}_{self.tile_size}.png"

        elif style == "compact":
            return f"{prefix}_b{bitmask:02d}_{self.tile_size}.png"

        elif style == "hybrid":
            regions = self._get_regions_for_bitmask(bitmask)
            return f"{prefix}_b{bitmask:02d}_{len(regions)}r_{self.tile_size}.png"

        else:
            raise ValueError(f"Unknown naming style: {style}")

    def _get_regions_for_bitmask(self, bitmask: int) -> List[str]:
        """根据 bitmask 确定显示哪些子区域（用于文件名生成）"""
        has_top = bool(bitmask & 0x1)
        has_bottom = bool(bitmask & 0x2)
        has_left = bool(bitmask & 0x4)
        has_right = bool(bitmask & 0x8)

        regions = []
        if not has_top and not has_left: regions.append('TL')
        if not has_top: regions.append('T')
        if not has_top and not has_right: regions.append('TR')
        if not has_left: regions.append('L')
        if not has_right: regions.append('R')
        if not has_bottom and not has_left: regions.append('BL')
        if not has_bottom: regions.append('B')
        if not has_bottom and not has_right: regions.append('BR')

        return regions

    def get_tile_info(self, bitmask: int) -> Dict:
        """
        获取指定 bitmask 的 tile 详细信息

        Returns:
            {
                'bitmask': int,
                'binary': str,
                'has_top': bool,
                'has_bottom': bool,
                'has_left': bool,
                'has_right': bool,
                'regions_shown': List[str],
                'regions_hidden': List[str],
                'description': str
            }
        """
        has_top = bool(bitmask & 0x1)
        has_bottom = bool(bitmask & 0x2)
        has_left = bool(bitmask & 0x4)
        has_right = bool(bitmask & 0x8)

        regions_shown = self._get_regions_for_bitmask(bitmask)
        all_regions = ['TL', 'T', 'TR', 'L', 'R', 'BL', 'B', 'BR']
        regions_hidden = [r for r in all_regions if r not in regions_shown]

        # 生成人类可读描述
        desc_parts = []
        if has_top: desc_parts.append("上邻同材质")
        if has_bottom: desc_parts.append("下邻同材质")
        if has_left: desc_parts.append("左邻同材质")
        if has_right: desc_parts.append("右邻同材质")

        if not desc_parts:
            description = "孤立瓦片（四邻皆不同材质）"
        elif len(desc_parts) == 4:
            description = "完全被同材质包围"
        else:
            description = "、".join(desc_parts) + "，其余方向显示 surface"

        return {
            'bitmask': bitmask,
            'binary': f"{bitmask:04b}",
            'has_top': has_top,
            'has_bottom': has_bottom,
            'has_left': has_left,
            'has_right': has_right,
            'regions_shown': regions_shown,
            'regions_hidden': regions_hidden,
            'description': description
        }

    def generate_preview_sheet(self, 
                               cols: int = 8,
                               bg_color: Tuple[int, int, int] = (50, 50, 50)) -> Image.Image:
        """
        生成预览图集（所有 16 种变体排列在一张图上）

        Args:
            cols: 每行显示的 tile 数量
            bg_color: 背景色

        Returns:
            预览图 (RGBA)
        """
        tiles = self.generate_all()
        num_tiles = len(tiles)
        rows = (num_tiles + cols - 1) // cols

        # 计算画布尺寸（加间距）
        spacing = 4
        sheet_w = cols * self.tile_size + (cols + 1) * spacing
        sheet_h = rows * self.tile_size + (rows + 1) * spacing

        sheet = Image.new('RGBA', (sheet_w, sheet_h), (*bg_color, 255))

        for idx, (bitmask, tile) in enumerate(tiles):
            row = idx // cols
            col = idx % cols
            x = col * self.tile_size + (col + 1) * spacing
            y = row * self.tile_size + (row + 1) * spacing
            sheet.paste(tile, (x, y), tile)

        return sheet
