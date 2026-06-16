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

BLOB_TEMPLATE = [
  [
    "00010100", "00010101", "00000101", "00000100", "00011100", "00011111", "00000111", "00011101", "00010111", "01111111"
  ],
  [
    "01010100", "01010101", "01000101", "01000100", "01111100", "11111111", "11000111", "01011100", "01110100", "11011111"
  ],
  [
    "01010000", "01010001", "01000001", "01000000", "01110000", "11110001", "11000001", "01110001", "11010001", "11111101"
  ],
  [
    "00010000", "00010001", "00000001", "00000000", "01000111", "11000101", "11110111", "01011111", "11110101", "01111101"
  ],
  [
    None,       None,       None,       "01011101", "01010111", "01110101", "11010101", "11010111", "01110111", "11011101"
  ]
]


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
        self.tiles: dict[str, Image.Image] = {}  # mask (str) → tile

    def add_tile(self, mask: str | int, tile: Image.Image):
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
        if isinstance(mask, int):
            mask = f"{mask:08b}"
        self.tiles[mask] = tile

    @property
    def grid_layout(self) -> tuple[int, int]:
        """
        根据 BLOB_TEMPLATE 自动计算布局。

        Returns:
            (columns, rows): 列数和行数
        """
        rows = len(BLOB_TEMPLATE)
        columns = max(len(row) for row in BLOB_TEMPLATE) if rows > 0 else 0
        return columns, rows

    def build(self) -> Image.Image:
        """
        将所有 tile 按 BLOB_TEMPLATE 拼接为一张紧密排列的大图 (无缝隙)。
        如果模板中的位置为 None，则留出透明空白 tile 占位。
        
        Returns:
            拼接完成的 RGBA 图集 Image
        """
        columns, rows = self.grid_layout
        if columns == 0 or rows == 0:
            raise ValueError("BLOB_TEMPLATE 不能为空")

        tile_size = self.tile_size
        atlas_w = columns * tile_size
        atlas_h = rows * tile_size
        atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))

        for r, row in enumerate(BLOB_TEMPLATE):
            for c, mask in enumerate(row):
                if mask is not None:
                    tile = self.tiles.get(mask)
                    if tile is None:
                        # 容错：如果用户传入的是int而不是str
                        try:
                            # Try integer if available
                            tile = self.tiles.get(f"{int(mask, 2):08b}")
                        except ValueError:
                            pass
                    
                    if tile:
                        x = c * tile_size
                        y = r * tile_size
                        atlas.paste(tile, (x, y))
                    else:
                        print(f"Warning: tile with mask {mask} was not added, skipping.")

        return atlas

    def build_with_metadata(self) -> tuple[Image.Image, dict]:
        """
        拼接并返回图集图片及其元数据。

        Returns:
            (atlas_image, metadata_dict)
        """
        atlas = self.build()
        columns, rows = self.grid_layout

        # 构建 mask_map: bitmask 值 → atlas 中的 (col, row)
        mask_map = {}
        for r, row in enumerate(BLOB_TEMPLATE):
            for c, mask in enumerate(row):
                if mask is not None:
                    mask_map[mask] = {"col": c, "row": r}

        metadata = {
            "tile_count": sum(1 for row in BLOB_TEMPLATE for m in row if m is not None),
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
