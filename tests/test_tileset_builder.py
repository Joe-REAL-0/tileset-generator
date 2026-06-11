# tests/test_tileset_builder.py
# TilesetBuilder 单元测试
# 测试目标: 47-tile autotile 图集拼接的正确性
#   - add_tile() 正常存储 tile
#   - build() 按标准布局拼接 47 个 tile 为一张大图, 紧密排列无缝隙
#   - build_with_metadata() 返回 mask_map (bitmask → tileset 索引)
#   - save() 保存图集到文件
#   - 验证输出图集尺寸、tile_count=47、行列数计算正确

import pytest
from PIL import Image
from src.services.tileset_builder import TilesetBuilder


class TestTilesetBuilder:
    """TilesetBuilder 单元测试"""

    @pytest.fixture
    def sample_tile(self):
        """创建一个 32×32 的纯色 mock tile"""
        return Image.new("RGBA", (32, 32), (0, 255, 0, 255))

    @pytest.fixture
    def builder(self):
        """创建一个 TilesetBuilder 实例 (tile_size=32)"""
        return TilesetBuilder(tile_size=32)

    def test_add_tile_stores_correctly(self, builder, sample_tile):
        """测试: add_tile 应正确存储 (mask, tile) 对"""
        builder.add_tile(0x00, sample_tile)
        assert 0x00 in builder.tiles
        assert builder.tiles[0x00] is sample_tile

    def test_build_output_size(self, builder, sample_tile):
        """测试: build 输出图集尺寸应正确 (tile_size × cols, tile_size × rows)"""
        # 添加全部 47 个 tile
        for i in range(47):
            builder.add_tile(i, sample_tile.copy())

        atlas = builder.build()
        # 验证输出为有效图片
        assert isinstance(atlas, Image.Image)
        # 验证尺寸: 47 tiles, 紧密排列
        cols, rows = builder.grid_layout
        assert atlas.size == (32 * cols, 32 * rows)
        assert cols * rows >= 47  # 必须装下 47 个 tile

    def test_build_with_metadata_contains_mask_map(self, builder, sample_tile):
        """测试: build_with_metadata 返回的元数据应包含完整 mask_map"""
        for i in range(47):
            builder.add_tile(i, sample_tile.copy())

        atlas, metadata = builder.build_with_metadata()

        assert metadata["tile_count"] == 47
        assert metadata["tile_size"] == 32
        assert "mask_map" in metadata
        assert len(metadata["mask_map"]) == 47

    def test_save_creates_file(self, builder, sample_tile, tmp_path):
        """测试: save 应将图集保存为 PNG 文件"""
        for i in range(47):
            builder.add_tile(i, sample_tile.copy())

        filepath = tmp_path / "test_tileset.png"
        builder.build()  # 必须先 build 再 save
        builder.save(str(filepath))

        assert filepath.exists()
        saved = Image.open(filepath)
        assert saved.size == builder._atlas.size
