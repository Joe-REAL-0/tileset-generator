# src/services/tileset_builder.py
# 47-tile Autotile 图集拼接器
# 职责: 将 AutotileEngine 生成的 47 个 tile 变体, 按标准布局拼接为最终的
#       autotile 图集 (sprite sheet), 供游戏引擎直接使用
#   - add_tile():            添加一个 autotile 变体 (mask → tile)
#   - build():               按标准 47-tile 布局拼接为一张紧密排列的大图
#   - build_with_metadata(): 拼接并返回元数据 (含 mask_map)
#   - save():                保存图集到文件

from pathlib import Path
from PIL import Image


class TilesetBuilder:
    """
    将 AutotileEngine 生成的 47 个 autotile 变体按标准布局拼接为 tileset 图集。

    布局规则:
      - tile 之间无缝隙 (紧密排列, padding = 0)
      - grid_layout 属性根据 tile 数量 (47) 自动计算最接近正方形的行列数
      - tile 按 mask 值从小到大排列
    """

    def __init__(self, tile_size: int):
        """
        Args:
            tile_size: 每个 tile 的像素尺寸 (如 16, 32, 64, 128)
        """
        self.tile_size = tile_size
        self.tiles: dict[int, Image.Image] = {}  # mask → tile

    def add_tile(self, mask: int, tile: Image.Image):
        """
        添加一个 autotile 变体

        Args:
            mask: bitmask 值 (作为 tileset 中的索引键)
            tile: 合成完成的 tile 图片
        """
        if tile.size != (self.tile_size, self.tile_size):
            raise ValueError(
                f"Tile 尺寸不匹配: 期望 {self.tile_size}×{self.tile_size}, "
                f"收到 {tile.size}"
            )
        self.tiles[mask] = tile

    @property
    def grid_layout(self) -> tuple[int, int]:
        """
        根据 tile 数量自动计算最接近正方形的 (columns, rows) 布局。

        Returns:
            (columns, rows): 列数和行数
        """
        n = len(self.tiles)
        # 取接近正方形: columns = ceil(sqrt(n))
        columns = int(n ** 0.5)
        if columns * columns < n:
            columns += 1
        rows = (n + columns - 1) // columns  # ceil division
        return columns, rows

    def build(self) -> Image.Image:
        """
        将所有 tile 拼接为一张紧密排列的大图 (无缝隙)。

        布局示例 (16 个 tile → 4 列 × 4 行):
        ┌────┬────┬────┬────┐
        │  0 │  1 │  2 │  3 │
        ├────┼────┼────┼────┤
        │  4 │  5 │  6 │  7 │
        ├────┼────┼────┼────┤
        │  8 │  9 │ 10 │ 11 │
        ├────┼────┼────┼────┤
        │ 12 │ 13 │ 14 │ 15 │
        └────┴────┴────┴────┘

        Returns:
            拼接完成的 RGBA 图集 Image
        """
        if not self.tiles:
            raise ValueError("没有添加任何 tile, 无法构建图集")

        columns, rows = self.grid_layout
        tile_size = self.tile_size

        atlas_w = columns * tile_size
        atlas_h = rows * tile_size
        atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))

        # 按 mask 值排序, 确保布局稳定可预测
        sorted_masks = sorted(self.tiles.keys())

        for idx, mask in enumerate(sorted_masks):
            col = idx % columns
            row = idx // columns
            x = col * tile_size
            y = row * tile_size
            atlas.paste(self.tiles[mask], (x, y))

        return atlas

    def build_with_metadata(self) -> tuple[Image.Image, dict]:
        """
        拼接并返回图集图片及其元数据。

        Returns:
            (atlas_image, metadata_dict)

        metadata 格式:
        {
            "tile_count": 47,
            "tile_size": 32,
            "columns": 8,
            "rows": 6,
            "image_size": [256, 192],
            "format": "png",
            "mask_map": {0x00: 0, 0x01: 1, ...}   # bitmask → tileset index
        }
        """
        atlas = self.build()
        columns, rows = self.grid_layout
        sorted_masks = sorted(self.tiles.keys())

        # 构建 mask_map: bitmask 值 → atlas 中的 index
        mask_map = {mask: idx for idx, mask in enumerate(sorted_masks)}

        metadata = {
            "tile_count": len(self.tiles),
            "tile_size": self.tile_size,
            "columns": columns,
            "rows": rows,
            "image_size": list(atlas.size),
            "format": "png",
            "mask_map": mask_map,
        }

        return atlas, metadata

    def save(self, filepath: str | Path):
        """
        保存拼接完成的图集到文件

        Args:
            filepath: 输出文件路径 (建议以 .png 结尾)
        """
        atlas = self.build()
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        atlas.save(filepath, format="PNG")
