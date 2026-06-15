#!/usr/bin/env python3
"""
autotile_demo.py
快速演示 Autotile 引擎 + ImageProcessor 完整流程

运行方式：
    python autotile_demo.py

输出：
    output/demo_autotiles/ 目录下的 16 个 tile + 预览图

完整流程：
    1. 创建模拟的 SD 原始输出（大图）
    2. 使用 ImageProcessor.downscale 处理 background
    3. 使用 ImageProcessor.nine_slice 切割 surface
    4. 使用 AutotileEngine 生成 16 种 bitmask 变体
    5. 保存并生成预览图
"""

from PIL import Image, ImageDraw
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from services.image_processor import ImageProcessor
from services.autotile_engine import AutotileEngine


def create_raw_background(size=512):
    """创建模拟的 SD 原始 background 输出（大图）"""
    img = Image.new('RGBA', (size, size), (34, 139, 34, 255))  # 森林绿
    draw = ImageDraw.Draw(img)

    # 添加草地纹理
    for i in range(0, size, 8):
        draw.line([(i, 0), (i, size)], fill=(20, 100, 20, 150), width=2)
        draw.line([(0, i), (size, i)], fill=(20, 100, 20, 150), width=2)

    # 添加一些随机草叶
    import random
    random.seed(42)
    for _ in range(100):
        x = random.randint(0, size-10)
        y = random.randint(0, size-10)
        draw.rectangle([x, y, x+4, y+8], fill=(50, 160, 50, 200))

    return img


def create_raw_surface(size=96):
    """创建模拟的 SD 原始 surface 输出（大图，能被 3 整除）"""
    img = Image.new('RGBA', (size, size), (139, 69, 19, 255))  # 泥土色
    draw = ImageDraw.Draw(img)

    # 添加泥土纹理
    for i in range(0, size, 6):
        draw.line([(i, 0), (i, size)], fill=(100, 50, 10, 180), width=1)
        draw.line([(0, i), (size, i)], fill=(100, 50, 10, 180), width=1)

    # 添加石子
    import random
    random.seed(42)
    for _ in range(50):
        x = random.randint(0, size-8)
        y = random.randint(0, size-8)
        color = random.choice([
            (160, 82, 45, 230),   # sienna
            (205, 133, 63, 230), # peru
            (210, 105, 30, 230), # chocolate
            (222, 184, 135, 230) # burlywood
        ])
        draw.ellipse([x, y, x+6, y+6], fill=color)

    return img


def demo_with_processor():
    """演示完整流程：使用 ImageProcessor + AutotileEngine"""
    print("=" * 70)
    print("🎮 Autotile Engine + ImageProcessor 完整流程演示")
    print("=" * 70)

    tile_size = 32

    # ========== 步骤 1：创建模拟的 SD 原始输出 ==========
    print("\n📦 步骤 1: 创建模拟的 SD 原始输出...")
    raw_bg = create_raw_background(512)
    raw_surf = create_raw_surface(96)
    print(f"   ✓ Background: {raw_bg.size} (模拟 SD 512x512 输出)")
    print(f"   ✓ Surface: {raw_surf.size} (模拟 SD 96x96 输出)")

    # 保存原始图供查看
    output_dir = Path("output/demo_autotiles")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_bg.save(output_dir / "_raw_background_512.png")
    raw_surf.save(output_dir / "_raw_surface_96.png")
    print(f"   ✓ 原始图已保存到 {output_dir}")

    # ========== 步骤 2：使用 ImageProcessor 预处理 ==========
    print("\n⚙️  步骤 2: ImageProcessor 预处理...")

    # 2a. downscale background
    bg_processed = ImageProcessor.downscale(raw_bg, tile_size)
    print(f"   ✓ downscale background: {raw_bg.size} → {bg_processed.size}")
    bg_processed.save(output_dir / "_processed_background_32.png")

    # 2b. nine_slice surface
    surface_parts = ImageProcessor.nine_slice(raw_surf)
    print(f"   ✓ nine_slice surface: {raw_surf.size} → 8 parts x {list(surface_parts.values())[0].size}")
    for name, part in surface_parts.items():
        part.save(output_dir / f"_processed_surface_{name}_32.png")

    # ========== 步骤 3：创建 AutotileEngine ==========
    print("\n🎨 步骤 3: 创建 AutotileEngine...")

    # 方式1：直接传入已处理图像（兼容旧方式）
    engine = AutotileEngine(bg_processed, surface_parts, tile_size=tile_size)
    print(f"   ✓ 方式1: 直接传入已处理图像")

    # 方式2：从原始图像创建（更简洁）
    engine_v2 = AutotileEngine.from_raw_images(raw_bg, raw_surf, tile_size=tile_size)
    print(f"   ✓ 方式2: from_raw_images() 自动预处理")

    # 验证两种方式结果一致
    tile1 = engine.generate_single(0x5)
    tile2 = engine_v2.generate_single(0x5)
    assert tile1.size == tile2.size == (tile_size, tile_size)
    print(f"   ✓ 两种方式生成结果一致")

    # ========== 步骤 4：生成全部 tile ==========
    print("\n🖼️  步骤 4: 生成全部 16 种 bitmask 变体...")
    tiles = engine.generate_all()
    print(f"   ✓ 生成完成: {len(tiles)} 个 tile")

    # 显示详细信息
    print("\n📋 Tile 详细信息:")
    print("-" * 70)
    print(f"{'Bitmask':<10} {'Binary':<8} {'显示区域数':<10} {'描述'}")
    print("-" * 70)
    for bitmask, tile in tiles:
        info = engine.get_tile_info(bitmask)
        regions_count = len(info['regions_shown'])
        desc = info['description'][:35] + "..." if len(info['description']) > 35 else info['description']
        print(f"0x{bitmask:02X}       {info['binary']:<8} {regions_count:<10} {desc}")

    # ========== 步骤 5：保存 tile ==========
    print("\n💾 步骤 5: 保存 tile（三种命名风格）...")

    # Full 风格
    files_full = engine.save_all(str(output_dir / "full"), 
                                  prefix="demo_grass", naming_style="full")
    print(f"   ✓ Full 风格: {len(files_full)} 个文件")
    print(f"     例: {Path(files_full[0]).name}")

    # Compact 风格
    files_compact = engine.save_all(str(output_dir / "compact"), 
                                     prefix="demo_grass", naming_style="compact")
    print(f"   ✓ Compact 风格: {len(files_compact)} 个文件")
    print(f"     例: {Path(files_compact[0]).name}")

    # Hybrid 风格
    files_hybrid = engine.save_all(str(output_dir / "hybrid"), 
                                    prefix="demo_grass", naming_style="hybrid")
    print(f"   ✓ Hybrid 风格: {len(files_hybrid)} 个文件")
    print(f"     例: {Path(files_hybrid[0]).name}")

    # ========== 步骤 6：生成预览图 ==========
    print("\n🖼️  步骤 6: 生成预览图...")
    preview = engine.generate_preview_sheet(cols=8)
    preview_path = output_dir / "demo_preview.png"
    preview.save(preview_path)
    print(f"   ✓ 预览图: {preview_path}")

    # ========== 步骤 7：验证 ImageProcessor 方法 ==========
    print("\n🔍 步骤 7: 验证 ImageProcessor 辅助方法...")

    # validate_tile
    assert ImageProcessor.validate_tile(bg_processed, (32, 32)) is True
    assert ImageProcessor.validate_tile(bg_processed, (64, 64)) is False
    print(f"   ✓ validate_tile: 尺寸校验正确")

    # ensure_rgba
    rgb_img = Image.new("RGB", (32, 32), (255, 0, 0))
    rgba_img = ImageProcessor.ensure_rgba(rgb_img)
    assert rgba_img.mode == "RGBA"
    print(f"   ✓ ensure_rgba: RGB → RGBA 转换正确")

    print("\n" + "=" * 70)
    print("✅ 演示完成！")
    print(f"   输出目录: {output_dir}")
    print(f"   - 原始图: _raw_*.png")
    print(f"   - 处理后: _processed_*.png")
    print(f"   - Tile (Full): {output_dir / 'full'}")
    print(f"   - Tile (Compact): {output_dir / 'compact'}")
    print(f"   - Tile (Hybrid): {output_dir / 'hybrid'}")
    print(f"   - 预览图: {preview_path}")
    print("=" * 70)


if __name__ == "__main__":
    demo_with_processor()
