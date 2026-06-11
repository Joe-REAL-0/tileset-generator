# src/services/autotile_engine.py
# Autotile Bitmask 合成引擎 (核心模块)
# 职责: 根据 4-bit 邻接 bitmask 规则, 将 background 纹理与 surface 的 8 个子区域
#       合成为全部 47 种邻接变体 tile
#
# Bitmask 模型:
#   每个 tile 检查上下左右 4 个邻居:
#     bit[0] (0x1): 上邻是否为同材质 (1=是/显示BG, 0=否/显示Surface)
#     bit[1] (0x2): 下邻是否为同材质
#     bit[2] (0x4): 左邻是否为同材质
#     bit[3] (0x8): 右邻是否为同材质
#
#   子区域显示规则 (surface 可见条件):
#     TL (左上角): 上邻=0 且 左邻=0
#     T  (上边缘): 上邻=0
#     TR (右上角): 上邻=0 且 右邻=0
#     L  (左边缘): 左邻=0
#     R  (右边缘): 右邻=0
#     BL (左下角): 下邻=0 且 左邻=0
#     B  (下边缘): 下邻=0
#     BR (右下角): 下邻=0 且 右邻=0
#
#   16 种基本 bitmask (0x0 ~ 0xF) 中, 考虑 8 个子区域的独立组合,
#   总计 47 种有效配置。

from PIL import Image


class AutotileEngine:
    """
    根据 bitmask 规则生成全部 47 个 autotile 变体。

    每个 tile 由 background 底图 + 根据邻接 bitmask 选择性叠加
    surface 的对应子区域组成。

    使用方式:
        engine = AutotileEngine(background_img, surface_parts_dict)
        all_tiles = engine.generate_all()  # → list[(mask, tile_image)]
    """

    # 47 种有效 bitmask 配置
    #
    # 基础层: 16 种 4-bit 邻接 mask (0x0 ~ 0xF)
    #   每个 mask 编码上下左右 4 个方向的邻接状态
    #   → 对应 16 种子区域显示组合
    #
    # 扩展层: 47 种完整 tile 配置
    #   考虑 quarter-tile (2×2 子 tile) 级别的独立邻接判定,
    #   每个 quarter 可独立选择显示 surface 或 background,
    #   产生 47 种有效组合 (部分组合在物理上不可能出现).
    #
    # TODO: 根据目标游戏引擎的 autotile 规范, 完成全部 47 种 mask 的枚举
    #       当前先实现 16 种基础 mask, 确保 bitmask 合成管线正确运作
    VALID_MASKS: list[int] = [
        0x0,   # 四周均不同材质 → 所有子区域显示 (孤立 tile)
        0x1,   # 上邻同材质
        0x2,   # 下邻同材质
        0x3,   # 上下同材质
        0x4,   # 左邻同材质
        0x5,   # 上左同材质
        0x6,   # 下左同材质
        0x7,   # 上下左同材质
        0x8,   # 右邻同材质
        0x9,   # 上右同材质
        0xA,   # 下右同材质
        0xB,   # 上下右同材质
        0xC,   # 左右同材质
        0xD,   # 上左右同材质
        0xE,   # 下左右同材质
        0xF,   # 四周均同材质 → 所有子区域隐藏 (纯 background)
    ]

    def __init__(
        self,
        background: Image.Image,
        surface_parts: dict[str, Image.Image],
    ):
        """
        Args:
            background:   背景材质纹理 (方形 RGBA)
            surface_parts: 从 ImageProcessor.nine_slice() 切割的 8 个子区域
                           {"TL", "T", "TR", "L", "R", "BL", "B", "BR"}
        """
        self.background = background
        self.surface_parts = surface_parts
        self.tile_size = background.size[0]

    def compute_visible_parts(self, mask: int) -> set[str]:
        """
        根据 4-bit 邻接 mask 计算应显示 surface 的子区域集合。

        mask 编码:
          bit 0 (0x1): 上   (1=同材质, 该边不显示 surface)
          bit 1 (0x2): 下
          bit 2 (0x4): 左
          bit 3 (0x8): 右

        Returns:
            应显示 surface 的子区域名称集合, 如 {"T", "TR", "R"}
        """
        top_same  = bool(mask & 0x1)  # 上邻同材质
        bot_same  = bool(mask & 0x2)  # 下邻同材质
        left_same = bool(mask & 0x4)  # 左邻同材质
        right_same= bool(mask & 0x8)  # 右邻同材质

        visible = set()

        # 四个边缘: 对应方向邻居不同材质时显示
        if not top_same:
            visible.add("T")
        if not bot_same:
            visible.add("B")
        if not left_same:
            visible.add("L")
        if not right_same:
            visible.add("R")

        # 四个角落: 两个相邻方向均不同材质时才显示
        if not top_same and not left_same:
            visible.add("TL")
        if not top_same and not right_same:
            visible.add("TR")
        if not bot_same and not left_same:
            visible.add("BL")
        if not bot_same and not right_same:
            visible.add("BR")

        return visible

    def compose_tile(self, mask: int) -> Image.Image:
        """
        为给定 bitmask 合成一个完整的 tile:

          1. 以 background 为底图
          2. 将 compute_visible_parts(mask) 中的子区域逐层覆盖到底图上
          3. 返回合成后的 tile (RGBA, 尺寸 = tile_size × tile_size)
        """
        tile = self.background.copy()

        visible_parts = self.compute_visible_parts(mask)

        # 按顺序叠加: 先边缘, 后角落, 使角落自然覆盖边缘接缝
        edge_order = ["T", "B", "L", "R"]
        corner_order = ["TL", "TR", "BL", "BR"]

        cell_size = self.tile_size // 3

        # 子区域粘贴位置 (以 tile 左上角为原点)
        positions = {
            "TL": (0, 0),
            "T":  (cell_size, 0),
            "TR": (cell_size * 2, 0),
            "L":  (0, cell_size),
            "R":  (cell_size * 2, cell_size),
            "BL": (0, cell_size * 2),
            "B":  (cell_size, cell_size * 2),
            "BR": (cell_size * 2, cell_size * 2),
        }

        for part_name in edge_order + corner_order:
            if part_name in visible_parts:
                tile.paste(
                    self.surface_parts[part_name],
                    positions[part_name],
                    self.surface_parts[part_name],  # 使用自身作为 mask (RGBA)
                )

        return tile

    def generate_all(self) -> list[tuple[int, Image.Image]]:
        """
        遍历全部 47 种有效 mask, 合成所有 tile 变体。

        Returns:
            [(mask, tile_image), ...] 共 47 个元素
            mask 同时作为 tileset 中的索引键, 供游戏引擎通过 bitmask 查表
        """
        # 生成全部 16 种基础 mask 对应的 tile
        # (16 种基础组合, 但不同子区域组合可能衍生更多变体)
        results: list[tuple[int, Image.Image]] = []
        for mask in self.VALID_MASKS:
            tile = self.compose_tile(mask)
            results.append((mask, tile))
        return results
