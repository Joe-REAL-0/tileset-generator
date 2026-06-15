# Autotile 命名规则约定

> 版本: v1.0  
> 更新日期: 2026-06-14  
> 适用范围: tileset-generator 项目 autotile 模块

---

## 一、设计目标

1. **可读性**: 从文件名即可判断 tile 的 bitmask 配置和显示状态
2. **可解析性**: Builder 模块可通过正则表达式从文件名提取关键信息
3. **一致性**: 所有 tile 遵循统一的命名格式
4. **可扩展性**: 支持不同 tile_size、不同材质前缀

---

## 二、基础命名格式

```
{prefix}_b{bitmask}_{regions}_{tile_size}.png
```

### 字段说明

| 字段 | 格式 | 说明 | 示例 |
|------|------|------|------|
| `prefix` | 小写字母+下划线 | 材质/类型标识 | `grass`, `dirt`, `stone_wall` |
| `b` | 固定前缀 | bitmask 标记 | `b` |
| `bitmask` | 2位十六进制 | 4-bit 邻接状态 (0x00 ~ 0x0F) | `00`, `0F`, `05` |
| `regions` | 大写字母+下划线 | 显示的子区域列表（按 TL→T→TR→L→R→BL→B→BR 顺序） | `TL_T_L_BL` |
| `tile_size` | 整数 | 瓦片尺寸（像素） | `32`, `64` |
| `.png` | 固定后缀 | 图像格式 | `.png` |

---

## 三、命名风格

### 3.1 Full 风格（推荐用于调试和开发）

包含完整的区域信息，最直观。

```
grass_b00_TL_T_TR_L_R_BL_B_BR_32.png    # bitmask=0x00, 显示所有子区域
grass_b01_TL_T_TR_L_R_BL_B_32.png       # bitmask=0x01, 上邻同材质，不显示 T/TL/TR
grass_b0F_NONE_32.png                    # bitmask=0x0F, 四邻同材质，纯背景
```

**适用场景**: 
- 开发调试时快速识别 tile 配置
- 手动检查生成结果
- 文档和演示

### 3.2 Compact 风格（推荐用于生产环境）

仅保留 bitmask，最简洁。

```
grass_b00_32.png
grass_b0F_32.png
```

**适用场景**:
- 生产环境部署
- 前端资源加载（减少文件名长度）
- 大量 tile 管理

### 3.3 Hybrid 风格（折中方案）

包含 bitmask 和区域数量。

```
grass_b00_8r_32.png     # 8 个区域显示
grass_b01_5r_32.png     # 5 个区域显示
grass_b0F_0r_32.png     # 0 个区域显示（纯背景）
```

**适用场景**:
- 需要快速了解复杂度但不需完整区域信息

---

## 四、Bitmask 与文件名对照表

| Bitmask | 二进制 | 上邻 | 下邻 | 左邻 | 右邻 | 显示的区域 | 文件名示例 (Full) |
|---------|--------|------|------|------|------|-----------|-------------------|
| 0x0 | 0000 | 0 | 0 | 0 | 0 | TL, T, TR, L, R, BL, B, BR | `grass_b00_TL_T_TR_L_R_BL_B_BR_32.png` |
| 0x1 | 0001 | 1 | 0 | 0 | 0 | L, R, BL, B, BR | `grass_b01_L_R_BL_B_BR_32.png` |
| 0x2 | 0010 | 0 | 1 | 0 | 0 | TL, T, TR, L, R | `grass_b02_TL_T_TR_L_R_32.png` |
| 0x3 | 0011 | 1 | 1 | 0 | 0 | L, R | `grass_b03_L_R_32.png` |
| 0x4 | 0100 | 0 | 0 | 1 | 0 | T, TR, R, B, BR | `grass_b04_T_TR_R_B_BR_32.png` |
| 0x5 | 0101 | 1 | 0 | 1 | 0 | R, B, BR | `grass_b05_R_B_BR_32.png` |
| 0x6 | 0110 | 0 | 1 | 1 | 0 | T, TR, R | `grass_b06_T_TR_R_32.png` |
| 0x7 | 0111 | 1 | 1 | 1 | 0 | R | `grass_b07_R_32.png` |
| 0x8 | 1000 | 0 | 0 | 0 | 1 | TL, T, L, BL, B | `grass_b08_TL_T_L_BL_B_32.png` |
| 0x9 | 1001 | 1 | 0 | 0 | 1 | L, BL, B | `grass_b09_L_BL_B_32.png` |
| 0xA | 1010 | 0 | 1 | 0 | 1 | TL, T, L | `grass_b0A_TL_T_L_32.png` |
| 0xB | 1011 | 1 | 1 | 0 | 1 | L | `grass_b0B_L_32.png` |
| 0xC | 1100 | 0 | 0 | 1 | 1 | T, B | `grass_b0C_T_B_32.png` |
| 0xD | 1101 | 1 | 0 | 1 | 1 | B | `grass_b0D_B_32.png` |
| 0xE | 1110 | 0 | 1 | 1 | 1 | T | `grass_b0E_T_32.png` |
| 0xF | 1111 | 1 | 1 | 1 | 1 | NONE | `grass_b0F_NONE_32.png` |

> **注意**: 上表假设 `1` 表示"有同材质邻居"（显示背景），`0` 表示"无同材质邻居"（显示 surface）。
> 这与 autotile_engine.py 中的 `has_top = bool(bitmask & 0x1)` 逻辑一致。

---

## 五、Builder 读取规则

Builder 模块通过正则表达式解析文件名：

```python
import re

# Full 风格解析
PATTERN_FULL = re.compile(
    r'^(?P<prefix>[a-z_]+)_b(?P<bitmask>[0-9A-Fa-f]{2})_(?P<regions>[A-Z_]+)_(?P<tile_size>\d+)\.png$'
)

# Compact 风格解析
PATTERN_COMPACT = re.compile(
    r'^(?P<prefix>[a-z_]+)_b(?P<bitmask>[0-9A-Fa-f]{2})_(?P<tile_size>\d+)\.png$'
)

# 使用示例
match = PATTERN_FULL.match("grass_b00_TL_T_TR_L_R_BL_B_BR_32.png")
if match:
    prefix = match.group("prefix")      # "grass"
    bitmask = int(match.group("bitmask"), 16)  # 0
    regions = match.group("regions").split("_")  # ["TL", "T", "TR", ...]
    tile_size = int(match.group("tile_size"))  # 32
```

---

## 六、目录结构

生成的 tile 文件按以下结构存放：

```
output/
└── autotiles/
    ├── grass/
    │   ├── grass_b00_TL_T_TR_L_R_BL_B_BR_32.png
    │   ├── grass_b01_L_R_BL_B_BR_32.png
    │   └── ...
    ├── dirt/
    │   ├── dirt_b00_TL_T_TR_L_R_BL_B_BR_32.png
    │   └── ...
    └── stone/
        └── ...
```

---

## 七、版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-06-14 | 初始版本，定义 Full/Compact/Hybrid 三种命名风格 |

---

## 八、相关文件

- `src/services/autotile_engine.py` — 命名规则生成实现
- `src/routers/tileset.py` — API 路由（供前端调用）
- `tests/test_autotile_engine.py` — 单元测试
