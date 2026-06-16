from PIL import Image
from src.services.autotile_engine import AutotileEngine
from src.services.tileset_builder import TilesetBuilder

bg = Image.new('RGBA', (32, 32), (0, 255, 0, 255))
surface_parts = {
    "TL": Image.new('RGBA', (10, 10), (255, 0, 0, 255)),
    "T": Image.new('RGBA', (10, 10), (255, 0, 0, 255)),
    "TR": Image.new('RGBA', (10, 10), (255, 0, 0, 255)),
    "L": Image.new('RGBA', (10, 10), (255, 0, 0, 255)),
    "R": Image.new('RGBA', (10, 10), (255, 0, 0, 255)),
    "BL": Image.new('RGBA', (10, 10), (255, 0, 0, 255)),
    "B": Image.new('RGBA', (10, 10), (255, 0, 0, 255)),
    "BR": Image.new('RGBA', (10, 10), (255, 0, 0, 255)),
}

try:
    engine = AutotileEngine(bg, surface_parts, tile_size=32)
    tiles = engine.generate_all()
    print("generate_all success, tiles:", len(tiles))

    builder = TilesetBuilder(32)
    for mask, tile_img in tiles:
        builder.add_tile(mask, tile_img)
    print("build success")
    atlas, metadata = builder.build_with_metadata()
    print("metadata:", metadata)
except Exception as e:
    import traceback
    traceback.print_exc()
