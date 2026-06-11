# Tileset Generator — 开发规划文档

> 本科人工智能专业课程设计  
> 基于 Stable Diffusion + ComfyUI 的自动 Tileset 生成系统

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈](#2-技术栈)
3. [系统架构](#3-系统架构)
4. [目录结构规划](#4-目录结构规划)
5. [模块详细设计](#5-模块详细设计)
   - [5.1 配置管理](#51-配置管理)
   - [5.2 ComfyUI 集成层](#52-comfyui-集成层)
   - [5.3 图像处理模块](#53-图像处理模块)
   - [5.4 FastAPI 服务层](#54-fastapi-服务层)
   - [5.5 WebSocket 实时通信](#55-websocket-实时通信)
   - [5.6 前端界面](#56-前端界面)
6. [API 接口设计](#6-api-接口设计)
7. [数据流与交互流程](#7-数据流与交互流程)
8. [分阶段实施计划](#8-分阶段实施计划)
9. [风险与注意事项](#9-风险与注意事项)

---

## 1. 项目概述

### 1.1 项目目标

构建一套自动化工具链，使用 Stable Diffusion 生成完整的 **47-tile 自动瓦片集（Autotile Set）**，输出可直接用于游戏引擎（如 RPG Maker、Unity、Godot）的 tileset 图集。

### 1.2 核心功能

| 功能 | 描述 |
|------|------|
| **材质生成** | 用户输入自然语言提示词，系统调用 ComfyUI + SD 生成基础材质纹理（background + surface） |
| **Autotile 合成** | 基于 bitmask 自动瓦片算法，将材质纹理合成为包含全部 47 种邻接变体的完整 autotile 图集 |
| **对话式交互** | 通过 Web 对话界面完成所有操作，降低使用门槛 |
| **实时反馈** | 通过 WebSocket 推送生成进度，用户可实时查看生成状态 |

### 1.3 47-Tile Autotile 格式说明

#### 双层 Tile 结构

每个 tile 由 **两个图层** 组成：

```
┌──────────────────────┐
│      Surface         │  ← 表面层（边缘过渡材质，如草地边缘）
│   ┌──────────────┐   │
│   │              │   │
│   │  Background  │   │  ← 背景层（核心填充材质，如泥土）
│   │              │   │
│   └──────────────┘   │
│                      │
└──────────────────────┘
```

- **Background（背景层）**：tile 的基础填充材质，占据 tile 中心区域
- **Surface（表面层）**：包裹在 background 周围，负责处理与相邻 tile 的过渡

#### 表面层 8 子区域划分

Surface 层被切割为 **8 个独立子区域**：

```
         左上角      上边缘      右上角
       ┌─────────┬─────────┬─────────┐
       │  sub[0] │  sub[1] │  sub[2] │
       │  (TL)   │  (T)    │  (TR)   │
       ├─────────┼─────────┼─────────┤
       │  sub[3] │         │  sub[4] │
左边缘  │  (L)    │  BG     │  (R)    │  右边缘
       ├─────────┼─────────┼─────────┤
       │  sub[5] │  sub[6] │  sub[7] │
       │  (BL)   │  (B)    │  (BR)   │
       └─────────┴─────────┴─────────┘
         左下角      下边缘      右下角
```

| 索引 | 名称 | 位置 | 显示条件 |
|------|------|------|---------|
| sub[0] | TL (Top-Left) | 左上角 | 上邻和左邻均为同材质时隐藏，否则显示 |
| sub[1] | T (Top) | 上边缘 | 上邻为同材质时隐藏，否则显示 |
| sub[2] | TR (Top-Right) | 右上角 | 上邻和右邻均为同材质时隐藏，否则显示 |
| sub[3] | L (Left) | 左边缘 | 左邻为同材质时隐藏，否则显示 |
| sub[4] | R (Right) | 右边缘 | 右邻为同材质时隐藏，否则显示 |
| sub[5] | BL (Bottom-Left) | 左下角 | 下邻和左邻均为同材质时隐藏，否则显示 |
| sub[6] | B (Bottom) | 下边缘 | 下邻为同材质时隐藏，否则显示 |
| sub[7] | BR (Bottom-Right) | 右下角 | 下邻和右邻均为同材质时隐藏，否则显示 |

#### Bitmask 规则

对每个 tile 检查其 **上下左右 4 个邻居**（4-bit 邻接）：

```
      [上]
       │
[左]── TILE ──[右]
       │
      [下]
```

- 若某方向邻居为**同材质** → 该方向 bit = 1 → 对应边缘和相邻两角**隐藏**（显示 background）
- 若某方向邻居为**不同材质** → 该方向 bit = 0 → 对应边缘和相邻两角**显示**（显示 surface）

**4 个方向 × 每个 tile 8 个子区域 = 2^4 = 16 种基本邻接配置。**  
考虑子区域级别的独立性（角与边的组合），总计 **47 种有效组合**，涵盖所有可能的邻接过渡情况。

#### 47-Tile 布局示意

最终的 autotile 图集将 47 个变体 tile 按固定标准布局排列。游戏引擎通过 bitmask 索引查找对应位置的 tile，实现自动边缘过渡。

```
   col0   col1   col2   col3   col4   col5   col6   ...
  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐
  │  0   │  1   │  2   │  3   │ ...  │ ...  │  46  │  ← 47 tiles total
  └──────┴──────┴──────┴──────┴──────┴──────┴──────┘
  (紧密排列，无缝隙，tile 之间间距为 0)
```

> **注意**：具体的 47-tile 布局标准将在实现阶段参考目标游戏引擎的 autotile 规范确定。常见参考：RPG Maker VX/Ace Autotile 格式（使用 3×2 子 tile 结构，但核心原理相同）。

---

## 2. 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **AI 推理引擎** | ComfyUI | 作为 Stable Diffusion 的工作流执行引擎 |
| **SD 模型** | SD3.5 Medium | 基础图像生成模型 |
| **LoRA** | pixel_art_style_z_image_turbo | 像素风格化 LoRA（见 `comfy/sdgen-api.json`） |
| **后端框架** | FastAPI (Python 3.10+) | 提供 REST API + WebSocket |
| **异步任务** | asyncio + background tasks | 处理长时间运行的生成任务 |
| **图像处理** | Pillow / OpenCV | tile 拼接、裁切、缩放、格式转换 |
| **HTTP 客户端** | httpx / aiohttp | 与 ComfyUI API 通信 |
| **前端** | 原生 HTML + CSS + JavaScript | 轻量对话界面，无需前端框架 |
| **实时通信** | WebSocket | 推送生成进度到前端 |
| **配置管理** | YAML / .env | 存储 ComfyUI 地址等可配置项 |

---

## 3. 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         用户浏览器                                │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                   对话界面 (Chat UI)                         │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────────┐  │  │
│  │  │ 生成材质  │  │ 生成     │  │  消息 / 图片展示区        │  │  │
│  │  │ (按钮1)   │  │ Tileset  │  │                          │  │  │
│  │  │           │  │ (按钮2)   │  │  [512px 原始图预览]      │  │  │
│  │  └──────────┘  └──────────┘  │  [47-tile Autotile 预览]  │  │  │
│  │                               └──────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────┬────────────────────────────┬──────────────────────┘
               │  HTTP REST + WebSocket      │
               ▼                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                       FastAPI 服务层                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ /api/chat   │  │ /api/generate│  │ /api/tileset           │  │
│  │ (对话接口)   │  │ (材质生成)    │  │ (Autotile 47-tile合成) │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────────────┘  │
│         │                │                   │                   │
│  ┌──────┴────────────────┴───────────────────┴────────────────┐  │
│  │                   核心业务逻辑层                             │  │
│  │  ┌────────────┐  ┌──────────────┐  ┌────────────────────┐ │  │
│  │  │ ComfyUI    │  │ Autotile     │  │ Image              │ │  │
│  │  │ Client     │  │ Engine       │  │ Processor          │ │  │
│  │  │ (SD 调用)   │  │ (Bitmask合成) │  │ (缩放/裁切/拼接)    │ │  │
│  │  └─────┬──────┘  └──────────────┘  └────────────────────┘ │  │
│  └────────┼───────────────────────────────────────────────────┘  │
└───────────┼──────────────────────────────────────────────────────┘
            │  HTTP (REST API)
            ▼
┌──────────────────────────────────────────────────────────────────┐
│                       ComfyUI 服务                                │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  /api/prompt   │  /api/history   │  /api/view             │    │
│  │  (递交工作流)    │  (查询历史)      │  (获取图片)             │    │
│  └──────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                SD3.5 Medium + LoRA                        │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### 架构说明

- **前后端分离**：FastAPI 提供 REST API，前端为纯静态页面，通过 AJAX + WebSocket 通信
- **ComfyUI 作为独立服务**：ComfyUI 在本地或远端独立运行，FastAPI 通过其 REST API 递交工作流并获取结果
- **异步非阻塞**：图像生成是长时间任务，使用 WebSocket 推送进度，避免 HTTP 超时
- **Autotile Engine**：核心模块，负责根据 bitmask 规则将 SD 生成的材质纹理合成为 47-tile autotile 图集

---

## 4. 目录结构规划

```
tileset-generator/
├── comfy/                          # ComfyUI 工作流文件
│   └── sdgen-api.json              # 现有: 单 tile 纹理生成工作流
│   # 未来可扩展:
│   # └── tileset-variation.json    # tileset 变体生成工作流
│
├── config/                         # 配置文件目录
│   ├── config.yaml                 # 主配置: ComfyUI地址、模型参数等
│   └── config.example.yaml         # 配置模板 (提交到 git)
│
├── src/                            # 源代码主目录
│   ├── __init__.py
│   ├── main.py                     # FastAPI 应用入口
│   ├── config.py                   # 配置加载模块
│   ├── schemas/                    # Pydantic 数据模型
│   │   ├── __init__.py
│   │   ├── chat.py                 # 对话消息模型
│   │   ├── generate.py             # 生成请求/响应模型
│   │   └── tileset.py              # Tileset 请求/响应模型
│   ├── routers/                    # API 路由
│   │   ├── __init__.py
│   │   ├── chat.py                 # /api/chat 对话路由
│   │   ├── generate.py             # /api/generate 材质生成路由
│   │   ├── tileset.py              # /api/tileset tileset 拼合路由
│   │   └── ws.py                   # WebSocket 路由
│   ├── services/                   # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── comfy_client.py         # ComfyUI API 客户端
│   │   ├── workflow_editor.py      # 工作流 JSON 动态编辑器
│   │   ├── autotile_engine.py      # Autotile Bitmask 合成引擎 (核心)
│   │   ├── tileset_builder.py      # 47-tile 图集拼接
│   │   └── image_processor.py      # 通用图像处理工具
│   └── static/                     # 前端静态资源
│       ├── index.html              # 对话界面主页
│       ├── css/
│       │   └── style.css           # 样式表
│       └── js/
│           ├── chat.js             # 对话逻辑
│           ├── ws.js               # WebSocket 客户端
│           └── ui.js               # UI 交互逻辑
│
├── output/                         # 生成输出目录 (gitignore)
│   ├── textures/                   # SD 生成的原始 512px 纹理
│   └── tilesets/                   # 最终 47-tile autotile 图集
│
├── tests/                          # 测试目录
│   ├── __init__.py
│   ├── test_comfy_client.py
│   ├── test_tileset_builder.py
│   └── test_image_processor.py
│
├── doc/                            # 文档目录
│   └── dev-plan.md                 # 本文件
│
├── requirements.txt                # Python 依赖
├── .gitignore                      # Git 忽略规则
├── .env                            # 环境变量 (敏感信息, gitignore)
├── .env.example                    # 环境变量模板
└── README.md                       # 项目说明
```

---

## 5. 模块详细设计

### 5.1 配置管理

**设计要点**：用户需要在配置文件中设置 ComfyUI 的 API 地址，方便在不同环境（本地/远端服务器）间切换。

#### 配置文件 `config/config.yaml`

```yaml
# ComfyUI 服务配置
comfyui:
  base_url: "http://127.0.0.1:8188"     # ComfyUI API 地址 (可被 .env 覆盖)
  timeout: 300                            # 生成超时 (秒)
  poll_interval: 1.0                      # 轮询间隔 (秒)

# 生成默认参数
generation:
  default_width: 512
  default_height: 512
  default_steps: 20
  default_cfg: 8.0
  default_sampler: "euler"
  default_scheduler: "simple"

# Tileset 拼合参数
tileset:
  output_format: "png"                    # 输出格式

# 输出 tile 尺寸选项 (SD 生成 512px 后缩放到目标尺寸)
output_tile_sizes: [16, 32, 64, 128]     # 可选像素尺寸列表
default_tile_size: 32                      # 默认输出 tile 尺寸 (px)

# 服务配置
server:
  host: "127.0.0.1"
  port: 8000
  cors_origins: ["*"]
```

#### 配置加载 `src/config.py`

```python
# 伪代码
import os
import yaml
from pydantic import BaseModel

class ComfyUIConfig(BaseModel):
    base_url: str
    timeout: int = 300
    poll_interval: float = 1.0

class AppConfig(BaseModel):
    comfyui: ComfyUIConfig
    generation: GenerationConfig
    tileset: TilesetConfig
    server: ServerConfig

def load_config(config_path: str = "config/config.yaml") -> AppConfig:
    """加载 YAML 配置，环境变量优先级高于配置文件"""
    # 1. 读取 YAML
    # 2. .env 覆盖 (如 COMFYUI_BASE_URL)
    # 3. 校验并返回 AppConfig 实例
```

#### 环境变量 `.env` (优先级最高)

```env
COMFYUI_BASE_URL=http://192.168.1.50:8188
SERVER_PORT=8000
```

---

### 5.2 ComfyUI 集成层

#### 5.2.1 ComfyUI API 客户端 (`src/services/comfy_client.py`)

封装与 ComfyUI 服务端的 REST API 通信。

**ComfyUI API 端点**（ComfyUI 原生提供）：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/prompt` | POST | 提交工作流 JSON 开始生成 |
| `/history/{prompt_id}` | GET | 查询生成历史与状态 |
| `/view?filename={name}&type={type}` | GET | 下载生成的图片 |

**客户端核心方法**：

```python
class ComfyClient:
    def __init__(self, base_url: str, timeout: int = 300):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def queue_prompt(self, workflow: dict) -> str:
        """提交工作流，返回 prompt_id"""

    async def get_history(self, prompt_id: str) -> dict:
        """根据 prompt_id 查询生成状态与结果"""

    async def get_image(self, filename: str, subfolder: str, type: str) -> bytes:
        """下载生成的图片二进制数据"""

    async def wait_for_completion(self, prompt_id: str,
                                   poll_interval: float = 1.0
                                   ) -> dict:
        """轮询直到生成完成，返回包含图片信息的 history 对象"""

    async def generate(self, workflow: dict) -> list[bytes]:
        """一站式接口: 提交 → 等待完成 → 下载所有图片"""
```

#### 5.2.2 工作流编辑器 (`src/services/workflow_editor.py`)

动态修改工作流 JSON，注入用户的提示词和参数，而无需手动编辑 JSON。

> **关键设计**: ComfyUI 的 API 格式工作流（`comfy/sdgen-api.json`）中，每个节点有唯一的 `id`，节点的可调参数通过 `inputs` 字段暴露。工作流编辑器通过节点 ID 定位并修改对应参数。

```python
class WorkflowEditor:
    """加载模板工作流并动态修改参数"""

    def __init__(self, template_path: str = "comfy/sdgen-api.json"):
        self.template = self._load_template(template_path)

    def set_prompt(self, positive: str, negative: str | None = None):
        """修改正向/反向提示词 (节点 2 和 5)"""

    def set_seed(self, seed: int):
        """修改随机种子 (节点 4 - KSampler)"""

    def set_resolution(self, width: int, height: int):
        """修改输出分辨率 (节点 11 - EmptyLatentImage)"""

    def set_sampler_params(self, steps: int, cfg: float,
                           sampler: str, scheduler: str):
        """修改采样器参数 (节点 4)"""

    def get_workflow(self) -> dict:
        """返回修改后的工作流 dict，可直接提交到 ComfyUI"""
```

**节点 ID 映射表**（依据 `comfy/sdgen-api.json`）：

| 节点 ID | 类型 | 可修改参数 |
|---------|------|-----------|
| 2 | `CLIPTextEncodeLumina2` | `text` (正向提示词) |
| 5 | `CLIPTextEncodeLumina2` | `text` (反向提示词) |
| 4 | `KSampler` | `seed`, `steps`, `cfg`, `sampler_name`, `scheduler` |
| 11 | `EmptyLatentImage` | `width`, `height`, `batch_size` |
| 7 | `SaveImage` | `filename_prefix` |

---

### 5.3 图像处理模块

#### 5.3.1 通用图像处理器 (`src/services/image_processor.py`)

> **关键流程**: SD 生成固定 512×512 的原始纹理，然后通过 `downscale()` 缩放到目标像素尺寸（16/32/64/128）。使用 NEAREST 插值以保持像素风格的锐利边缘。

```python
class ImageProcessor:
    """提供 tile 纹理的预处理与后处理"""

    # 支持的输出 tile 尺寸
    VALID_TILE_SIZES = {16, 32, 64, 128}

    @staticmethod
    def downscale(image: Image, target_size: int) -> Image:
        """
        将 512px 的 SD 输出缩放到目标像素尺寸。
        使用 NEAREST 插值保持像素艺术风格的锐利边缘。
        target_size 必须为 16, 32, 64, 128 之一。
        """

    @staticmethod
    def nine_slice(image: Image) -> dict[str, Image]:
        """
        将 surface 纹理按 3×3 九宫格切割为 8 个子区域。
        
        输入: surface 纹理 (方形图片)
        ┌─────────────┐
        │ TL │  T  │ TR │
        ├────┼─────┼────┤
        │ L  │(BG) │ R  │  ← 中心区域被 background 覆盖，丢弃
        ├────┼─────┼────┤
        │ BL │  B  │ BR │
        └─────────────┘
        
        返回: {"TL": img, "T": img, "TR": img, "L": img, 
                "R": img, "BL": img, "B": img, "BR": img}
        """

    @staticmethod
    def resize(image: Image, size: tuple[int, int]) -> Image:
        """通用缩放（使用 NEAREST 保持像素风格）"""

    @staticmethod
    def ensure_rgba(image: Image) -> Image:
        """确保图像为 RGBA 模式"""

    @staticmethod
    def validate_tile(image: Image, expected_size: tuple[int, int]) -> bool:
        """校验 tile 尺寸是否符合预期"""
```

#### 5.3.2 Autotile 合成引擎 (`src/services/autotile_engine.py`)

**核心功能**：基于 bitmask 邻接规则，将 background 纹理与 surface 的 8 个子区域组合为 **47 种邻接变体**。

**Bitmask 模型**：

```
每个 tile 的邻接状态由 4 bit 表示 (上/下/左/右):

  bit[0] = 上邻是否为同材质 (1=是, 0=否)
  bit[1] = 下邻是否为同材质
  bit[2] = 左邻是否为同材质
  bit[3] = 右邻是否为同材质

  4-bit → 16 种邻接掩码 (0b0000 ~ 0b1111)
  但考虑 8 个子区域的独立显示逻辑 → 总计 47 种有效组合
```

**子区域显示规则**：

| 子区域 | 显示条件（surface 可见） |
|--------|------------------------|
| TL (左上角) | 上邻=0 **且** 左邻=0 |
| T (上边缘) | 上邻=0 |
| TR (右上角) | 上邻=0 **且** 右邻=0 |
| L (左边缘) | 左邻=0 |
| R (右边缘) | 右邻=0 |
| BL (左下角) | 下邻=0 **且** 左邻=0 |
| B (下边缘) | 下邻=0 |
| BR (右下角) | 下邻=0 **且** 右邻=0 |

```python
class AutotileEngine:
    """
    根据 bitmask 规则生成全部 47 个 autotile 变体。

    输入:
      - background: 背景材质纹理 (方形, 如草地中心的泥土)
      - surface_parts: 从 nine_slice 切割出的 8 个子区域
                        {"TL", "T", "TR", "L", "R", "BL", "B", "BR"}

    输出:
      - 47 个 tile 变体, 每个 tile = background + 根据 bitmask 
        选择性地叠加对应 surface 子区域
    """

    # 47 种有效 bitmask 配置
    # 每种配置定义了哪些子区域显示 surface (其余区域显示 background)
    VALID_MASKS: list[int]  # 47 个 bitmask 值

    def __init__(self, background: Image, surface_parts: dict[str, Image]):
        self.background = background
        self.surface_parts = surface_parts

    def compute_visible_parts(self, mask: int) -> set[str]:
        """
        根据 bitmask 计算应显示的子区域集合。
        
        mask 编码:
          bit 0 (0x1): 上   bit 1 (0x2): 下
          bit 2 (0x4): 左   bit 3 (0x8): 右

        返回值如: {"T", "TR", "R"} (表示上、右上、右显示 surface)
        """

    def compose_tile(self, mask: int) -> Image:
        """
        为给定 bitmask 合成一个完整的 tile:
          1. 以 background 为底图
          2. 将 compute_visible_parts(mask) 中的子区域覆盖到底图上
          3. 返回合成后的 tile
        """

    def generate_all(self) -> list[tuple[int, Image]]:
        """
        遍历全部 47 种有效 mask, 返回 (mask, tile_image) 列表。
        mask 同时作为 tileset 中的索引键, 供游戏引擎查表。
        """
```

#### 5.3.3 Tileset 拼合器 (`src/services/tileset_builder.py`)

**核心功能**：将 `AutotileEngine` 生成的 47 个 tile 变体，按固定标准布局拼接为最终的 **47-tile autotile 图集**。

```python
class TilesetBuilder:
    """
    将 47 个 autotile 变体按标准布局拼接为 tileset 图集。
    
    布局: 紧密排列，tile 之间无缝隙 (padding = 0)
    由 tile 数量 (47) 和标准布局规则确定列数/行数
    """

    def __init__(self, tile_size: int):
        self.tile_size = tile_size
        self.tiles: dict[int, Image] = {}  # mask → tile

    def add_tile(self, mask: int, tile: Image):
        """添加一个 autotile 变体"""

    def build(self) -> Image:
        """
        按标准 47-tile 布局拼接为完整图集。
        
        输出示例 (假设 47 tiles, 具体列数依标准而定):
        ┌────┬────┬────┬────┬────┬────┬───┐
        │  0 │  1 │  2 │  3 │  4 │  5 │...│  ← 47 tiles, 紧密排列
        └────┴────┴────┴────┴────┴────┴───┘
        """

    def build_with_metadata(self) -> tuple[Image, dict]:
        """
        返回 (图集图片, 元数据):
        {
            "tile_count": 47,
            "tile_size": 32,
            "columns": X,
            "rows": Y,
            "image_size": [W, H],
            "format": "png",
            "mask_map": {0x00: 0, 0x01: 1, ...}  # bitmask → tileset index
        }
        """

    def save(self, filepath: str):
        """保存最终 autotile 图集"""
```

#### 5.3.4 完整处理管线

```
SD 生成 512×512 原始纹理
         │
         ▼
┌──────────────────────────┐
│ 1. ImageProcessor         │
│    downscale(512→target)  │  缩放到目标像素尺寸 (16/32/64/128)
└──────────┬───────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
  background   surface
  (背景材质)   (表面材质)
     │           │
     │    ┌──────┴──────┐
     │    │ nine_slice()│  将 surface 切割为 8 个子区域
     │    │ → 8 parts   │
     │    └──────┬──────┘
     │           │
     ▼           ▼
┌──────────────────────────┐
│ 2. AutotileEngine         │
│    compute_visible_parts()│  对 47 种 bitmask 分别计算可见子区域
│    compose_tile() ×47     │  合成 47 个 tile 变体
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 3. TilesetBuilder         │
│    build()                │  按标准布局拼接 47 tiles → 最终 autotile 图集
└──────────────────────────┘
```

---

### 5.4 FastAPI 服务层

#### 5.4.1 应用入口 (`src/main.py`)

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Tileset Generator API", version="0.1.0")

# CORS 配置
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# 注册路由
app.include_router(chat.router, prefix="/api")
app.include_router(generate.router, prefix="/api")
app.include_router(tileset.router, prefix="/api")
app.include_router(ws.router)

# 挂载静态文件 (前端)
app.mount("/", StaticFiles(directory="src/static", html=True))

# 启动时验证 ComfyUI 连通性
@app.on_event("startup")
async def startup():
    await check_comfyui_connection()
```

#### 5.4.2 数据模型 (`src/schemas/`)

```python
# schemas/generate.py
from pydantic import BaseModel, Field

class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="正向提示词 (描述要生成的材质, 如'草地')")
    negative_prompt: str | None = Field(None, description="反向提示词")
    seed: int | None = Field(None, description="随机种子 (-1表示随机)")
    # SD 固定生成 512×512 原始纹理

class GenerateResponse(BaseModel):
    task_id: str
    status: str                           # "queued"
    websocket_url: str

# schemas/tileset.py
class TilesetRequest(BaseModel):
    background_image_id: str              # background 纹理 ID
    surface_image_id: str                 # surface 纹理 ID
    tile_size: int = 32                   # 目标 tile 尺寸 (16|32|64|128)

class TilesetResponse(BaseModel):
    task_id: str
    status: str
    tileset_url: str | None = None
    metadata: dict | None = None
    # metadata 包含: tile_count(47), tile_size, columns, rows, image_size, mask_map

# schemas/chat.py
class ChatMessage(BaseModel):
    role: str                             # "user" | "assistant" | "system"
    content: str
    image_url: str | None = None
    timestamp: str
```

#### 5.4.3 路由设计

```python
# routers/generate.py
@router.post("/generate", response_model=GenerateResponse)
async def generate_texture(request: GenerateRequest):
    """
    按钮1: 生成材质

    1. 接收用户提示词 (描述一种材质, 如 "草地"、"沙地")
    2. 用 WorkflowEditor 注入参数到工作流
    3. 提交到 ComfyUI, SD 生成 512×512 原始纹理
    4. 返回 task_id, 前端通过 WebSocket 获取进度
    5. 生成完成后, 返回的图片即为该材质的 surface/background 纹理
    """

# routers/tileset.py
@router.post("/tileset", response_model=TilesetResponse)
async def build_tileset(request: TilesetRequest):
    """
    按钮2: 生成 Autotile Tileset

    处理管线:
    1. 根据 ID 加载 background 和 surface 纹理
    2. ImageProcessor.downscale() → 缩放到 target_size
    3. ImageProcessor.nine_slice(surface) → 切割为 8 个子区域
    4. AutotileEngine.generate_all() → 合成 47 个 tile 变体
    5. TilesetBuilder.build() → 拼接为完整 autotile 图集
    6. 返回 tileset URL + 元数据 (含 mask_map)
    """

# routers/chat.py
@router.get("/chat/history")
async def get_chat_history(session_id: str):
    """获取对话历史"""

@router.post("/chat/message")
async def send_message(message: ChatMessage):
    """发送对话消息 (REST 备用方案)"""

# routers/ws.py
@router.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    WebSocket 连接: 前端通过此连接接收生成进度推送

    推送消息格式:
    {
        "type": "progress",
        "task_id": "...",
        "status": "generating",    // queued | generating | composing | completed | failed
        "progress": 45,            // 0-100
        "message": "Composing tile 23/47...",
        "image_url": null,
        "error": null
    }
    """
```

---

### 5.5 WebSocket 实时通信

#### 消息协议

```json
// 服务端 → 客户端
{
  "type": "status",
  "task_id": "abc123",
  "status": "generating",       // "queued" → "generating" → "completed" | "failed"
  "progress": 60,                // 0-100
  "message": "Step 12/20...",
  "image_data": null,           // base64 (仅 completed 时)
  "image_url": "/output/textures/tile_001.png",  // 图片静态 URL
  "error": null
}
```

#### 状态流转

```
queued ──► generating ──► completed
                │
                └──────────► failed
```

---

### 5.6 前端界面

#### 页面布局 (`src/static/index.html`)

```
┌──────────────────────────────────────────────────────────────────────┐
│  🎨 Tileset Generator                                  [设置 ⚙️]    │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                                                            │     │
│  │            💬 对话消息区域                                   │     │
│  │  ┌─────────────────────────────────────────────────┐      │     │
│  │  │ 👤 用户: 生成草地材质                             │      │     │
│  │  └─────────────────────────────────────────────────┘      │     │
│  │  ┌─────────────────────────────────────────────────┐      │     │
│  │  │ 🤖 助手: SD 正在生成中... ⏳                      │      │     │
│  │  │        [进度条 ████████░░ 80%]                   │      │     │
│  │  │        ┌────────────┐                           │      │     │
│  │  │        │ [512×512] │ ← 原始纹理                 │      │     │
│  │  │        └────────────┘                           │      │     │
│  │  │        类型: surface / background               │      │     │
│  │  │        ✅ 材质"草地"已生成!                      │      │     │
│  │  └─────────────────────────────────────────────────┘      │     │
│  │                                                            │     │
│  │  ┌─────────────────────────────────────────────────┐      │     │
│  │  │ 🤖 助手: 🧩 Autotile 合成完成!                   │      │     │
│  │  │        ┌────────────────────────────┐           │      │     │
│  │  │        │  [47-tile Autotile 图集]    │           │      │     │
│  │  │        │  32×32 px, 47 tiles        │           │      │     │
│  │  │        │  [📥 下载]                  │           │      │     │
│  │  │        └────────────────────────────┘           │      │     │
│  │  └─────────────────────────────────────────────────┘      │     │
│  │                                                            │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  ┌─────────────────────────────────────────┐               │     │
│  │  │ 已生成材质: [草地] [沙地] [水面] [岩石]   │ ← 点击选择    │     │
│  │  │ ↕ 选择 BG 和 Surface                     │               │     │
│  │  └─────────────────────────────────────────┘               │     │
│  │                                                             │     │
│  │  输入提示词...                                  │  📎      │     │
│  │                                                 │          │     │
│  │  Tile尺寸: [32px ▼]  [🎨 生成材质]  [🧩 生成 Autotile]    │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

#### 按钮行为

| 按钮 | 触发条件 | 行为 |
|------|---------|------|
| **🎨 生成材质** | 输入框有文本 | 调用 `POST /api/generate`，SD 固定生成 512×512 纹理，通过 WebSocket 跟踪进度，完成后在对话区显示原始大图。每次生成产生一张纹理（可作为 background 或 surface）。 |
| **🧩 生成 Autotile** | 用户已选择 **1 张 background** + **1 张 surface** 纹理 | 完整处理管线：<br>1. 将两张纹理缩放到 Tile 尺寸（16/32/64/128）<br>2. `nine_slice(surface)` → 切割为 8 个子区域<br>3. `AutotileEngine` → 合成 47 个 tile 变体<br>4. `TilesetBuilder` → 拼接为 autotile 图集<br>5. 展示图集 + mask_map + 下载链接 |

#### 交互流程

```
1. 用户输入 "草地" → 点击 [🎨 生成材质]
2. SD 生成 512×512 草地纹理 → 命名为"草地"→ 保存到已生成材质列表
3. 用户输入 "泥土" → 点击 [🎨 生成材质]
4. SD 生成 512×512 泥土纹理 → 命名为"泥土"→ 保存到已生成材质列表
5. 用户在已生成材质中分别点击选择:
     Background: [泥土]  ← 背景材质
     Surface:   [草地]  ← 表面材质 (草地包裹在泥土周围)
6. 用户在 Tile 尺寸下拉框选择 32px
7. 用户点击 [🧩 生成 Autotile]
8. 前端: POST /api/tileset (background_image_id + surface_image_id + tile_size=32)
9. 后端处理:
   a. 加载两张 512px 纹理
   b. downscale → 32px
   c. nine_slice(surface) → 8 个子区域
   d. AutotileEngine → 对 47 种 bitmask 逐个合成 tile
   e. TilesetBuilder → 拼接为完整 autotile 图集
10. 前端: 显示 47-tile Autotile 图集 + mask_map 表 + 下载链接
```

#### 已生成材质管理

前端维护 **已生成材质列表**，每张纹理标注类型。用户需要选择 **1 张 background** 和 **1 张 surface** 后，才能点击"生成 Autotile"。

```
已生成材质 (单击选为 Background, 双击选为 Surface):
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ 🌿 草地   │ │ 🟫 泥土   │ │ 🏖️ 沙地   │ │ 🪨 岩石   │
│ [Surface]│ │  [BG]    │ │          │ │          │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
```

> 注: 同一张纹理既可以作为 background 也可以作为 surface。例如"草地"作为 surface 包裹在"泥土" background 周围，形成泥土上长草的自然过渡效果。

---

## 6. API 接口设计

### 6.1 完整 API 列表

| 方法 | 路径 | 描述 | 请求体 | 响应体 |
|------|------|------|--------|--------|
| `POST` | `/api/generate` | 提交材质纹理生成任务 | `GenerateRequest` | `GenerateResponse` |
| `GET` | `/api/generate/{task_id}` | 查询生成任务状态 | - | `TaskStatus` |
| `POST` | `/api/tileset` | 提交 autotile 合成任务 (bg+surface → 47 tiles) | `TilesetRequest` | `TilesetResponse` |
| `GET` | `/api/tileset/{tileset_id}` | 查询合成状态 | - | `TilesetStatus` |
| `GET` | `/api/images` | 列出所有已生成纹理 | - | `list[ImageInfo]` |
| `GET` | `/api/images/{image_id}` | 获取单张纹理图片 | - | `image/png` |
| `DELETE` | `/api/images/{image_id}` | 删除纹理图片 | - | `{"ok": true}` |
| `GET` | `/api/tilesets` | 列出所有已生成的 tileset | - | `list[TilesetInfo]` |
| `GET` | `/api/tilesets/{id}/download` | 下载 tileset 文件 | - | `image/png` |
| `WS` | `/ws/{task_id}` | WebSocket 进度推送 | - | 流式 JSON |

### 6.2 请求/响应示例

#### 生成材质

```json
// POST /api/generate
{
  "prompt": "2D game asset, single square tile texture, top-down view of lush green grass with small flowers, 16-bit retro game style, flat lighting, sharp pixel edges, white background, masterpiece, high quality",
  "negative_prompt": "3D render, blurry, gradients, noise, text, watermark",
  "seed": -1
}

// Response
{
  "task_id": "task_abc123",
  "status": "queued",
  "websocket_url": "ws://127.0.0.1:8000/ws/task_abc123"
}

// WebSocket complete message:
{
  "type": "status",
  "task_id": "task_abc123",
  "status": "completed",
  "image_id": "img_grass_001",
  "image_url": "/api/images/img_grass_001",
  "message": "材质"草地"生成完成 (512×512)"
}
```

#### 合成 Autotile Tileset

```json
// POST /api/tileset
{
  "background_image_id": "img_dirt_001",    // background: 泥土
  "surface_image_id": "img_grass_001",      // surface: 草地 (包裹在泥土周围)
  "tile_size": 32
}

// Response
{
  "task_id": "ts_autotile_001",
  "status": "completed",
  "tileset_url": "/api/tilesets/ts_autotile_001/download",
  "metadata": {
    "tile_count": 47,
    "tile_size": 32,
    "columns": 8,
    "rows": 6,
    "image_size": [256, 192],
    "format": "png",
    "background": "img_dirt_001",
    "surface": "img_grass_001",
    "mask_map": {
      "0x00": 0, "0x01": 1, "0x02": 2, "0x03": 3, ...
    }
  }
}
```

---

## 7. 数据流与交互流程

### 7.1 材质生成完整流程

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  前端     │     │ FastAPI   │     │ ComfyUI   │     │ 文件系统  │
│ (Browser)│     │ (Python)  │     │ (SD)      │     │ (output/) │
└────┬─────┘     └─────┬─────┘     └─────┬─────┘     └─────┬─────┘
     │                  │                │                  │
     │ 1. POST /generate│                │                  │
     │  (prompt)        │                │                  │
     │─────────────────►│                │                  │
     │                  │                │                  │
     │                  │ 2. WorkflowEditor.set_prompt()   │
     │                  │    加载模板 + 注入参数             │
     │                  │                │                  │
     │                  │ 3. POST /prompt│                  │
     │                  │  (workflow)    │                  │
     │                  │───────────────►│                  │
     │                  │                │                  │
     │                  │ 4. prompt_id   │                  │
     │                  │◄───────────────│                  │
     │                  │                │                  │
     │ 5. task_id +     │                │                  │
     │    ws_url        │                │                  │
     │◄─────────────────│                │                  │
     │                  │                │                  │
     │ 6. WS Connect    │                │                  │
     │─────────────────►│                │                  │
     │                  │                │                  │
     │                  │ 7. 轮询 GET /history/{prompt_id} │
     │                  │◄──────────────►│                  │
     │                  │   (每1秒一次)    │                  │
     │                  │                │                  │
     │ 8. WS push:      │                │                  │
     │    status/step   │                │                  │
     │◄─────────────────│                │                  │
     │   (多次)          │                │                  │
     │                  │                │                  │
     │                  │ 9. GET /view   │                  │
     │                  │  (下载图片)     │                  │
     │                  │───────────────►│                  │
     │                  │                │                  │
     │                  │ 10. 保存到      │                  │
     │                  │   output/textures/               │
     │                  │───────────────────────────────►  │
     │                  │                │                  │
     │ 11. WS push:     │                │                  │
     │    completed +   │                │                  │
     │    image_url     │                │                  │
     │◄─────────────────│                │                  │
     │                  │                │                  │
```

### 7.2 Autotile 合成完整流程

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  前端     │     │ FastAPI   │     │ 文件系统  │
│ (Browser)│     │ (Python)  │     │ (output/) │
└────┬─────┘     └─────┬─────┘     └─────┬─────┘
     │                  │                │
     │ 1. POST /tileset │                │
     │  (bg_id, sf_id,  │                │
     │   tile_size=32)  │                │
     │─────────────────►│                │
     │                  │                │
     │                  │ 2. 加载bg+sf    │
     │                  │    512px纹理    │
     │                  │◄───────────────│
     │                  │                │
     │                  │ 3. downscale() │
     │                  │  512→32 NEAREST│
     │                  │                │
     │                  │ 4. nine_slice(surface)
     │                  │   切割为8个子区域│
     │                  │                │
     │                  │ 5. AutotileEngine
     │                  │   ×47: compose_tile()
     │                  │   (bitmask → tile)
     │                  │                │
     │                  │ 6. TilesetBuilder.build()
     │                  │   拼接47-tile图集 │
     │                  │                │
     │                  │ 7. 保存 Tileset │
     │                  │────────────────►│
     │                  │   output/tilesets/
     │                  │                │
     │ 8. tileset_url + │                │
     │    metadata      │                │
     │    (含 mask_map) │                │
     │◄─────────────────│                │
     │                  │                │
     │ 9. GET /tilesets/{id}/download    │
     │─────────────────►│                │
     │                  │                │
     │ 10. 图片文件      │                │
     │◄─────────────────│                │
     │                  │                │
```

---

## 8. 分阶段实施计划

### Phase 1: 项目骨架搭建 (第1-2天)

- [ ] 初始化 Python 项目结构
- [ ] 编写 `.gitignore`
- [ ] 编写 `requirements.txt`
  ```
  fastapi>=0.110.0
  uvicorn[standard]>=0.27.0
  httpx>=0.27.0
  pillow>=10.0.0
  pydantic>=2.0.0
  pydantic-settings>=2.0.0
  python-dotenv>=1.0.0
  pyyaml>=6.0
  websockets>=12.0
  python-multipart>=0.0.9
  aiofiles>=23.0.0
  ```
- [ ] 实现 `src/config.py` — 配置加载模块
- [ ] 创建 `config/config.yaml` 和 `config/config.example.yaml`
- [ ] 创建 `.env.example`
- [ ] 实现 `src/main.py` — FastAPI 最小可运行骨架（含 CORS、静态文件挂载、启动连通性检查）
- [ ] 验证: `uvicorn src.main:app --reload` 可启动

### Phase 2: ComfyUI 集成 (第2-3天)

- [ ] 实现 `src/services/comfy_client.py` — ComfyUI API 客户端
  - `queue_prompt()` / `get_history()` / `get_image()` / `wait_for_completion()`
- [ ] 实现 `src/services/workflow_editor.py` — 工作流编辑器
  - 加载 `comfy/sdgen-api.json`
  - 实现 `set_prompt()` / `set_seed()` / `set_resolution()` / `set_sampler_params()`
- [ ] 编写 `tests/test_comfy_client.py` — 单元测试 (mock ComfyUI 响应)
- [ ] 手动集成测试: 用真实 ComfyUI 跑一次完整生成流程

### Phase 3: 图像处理与 Autotile 引擎 (第3-5天)

- [ ] 实现 `src/services/image_processor.py`
  - `downscale()` — 512px → 目标尺寸 (16/32/64/128)，使用 NEAREST 插值
  - `nine_slice()` — 将 surface 纹理按 3×3 九宫格切割为 8 个子区域
  - resize / ensure_rgba / validate_tile
- [ ] 实现 `src/services/autotile_engine.py` — **核心模块**
  - 定义 47 种有效 bitmask 配置
  - `compute_visible_parts(mask)` — 根据 4-bit 邻接计算应显示的子区域集合
  - `compose_tile(mask)` — 合成单个 tile: background + 对应 surface 子区域
  - `generate_all()` — 遍历全部 47 种 mask，返回完整 tile 列表
- [ ] 实现 `src/services/tileset_builder.py`
  - `add_tile` / `build` / `build_with_metadata` / `save`
  - 按标准 47-tile 布局拼接，紧密排列，无缝隙
  - `build_with_metadata()` 返回 `mask_map`（bitmask → tileset 索引）
- [ ] 编写测试:
  - `tests/test_image_processor.py` — 验证 nine_slice 切割正确性
  - `tests/test_autotile_engine.py` — 使用纯色 mock 图片验证 47 个 tile 的 bitmask 逻辑
  - `tests/test_tileset_builder.py` — 验证拼接布局和元数据正确性

### Phase 4: API 路由与 WebSocket (第4-6天)

- [ ] 编写 Pydantic schemas (`src/schemas/`)
  - `generate.py` / `tileset.py` / `chat.py`
- [ ] 实现 `src/routers/generate.py`
  - `POST /api/generate` 端点
  - 后台异步任务启动 ComfyUI 生成
- [ ] 实现 `src/routers/ws.py`
  - WebSocket 端点，按 task_id 分组推送进度
  - 实现 `ConnectionManager` 类管理活跃连接
- [ ] 实现 `src/routers/tileset.py`
  - `POST /api/tileset` + `GET /api/tilesets` 系列端点
- [ ] 实现 `src/routers/chat.py`
  - 对话历史管理 (内存存储，session 级别)
- [ ] 实现 `GET /api/images` 系列 (图片管理 CRUD)

### Phase 5: 前端界面 (第7-9天)

- [ ] 编写 `src/static/index.html` — 页面骨架
- [ ] 编写 `src/static/css/style.css` — 样式
  - 深色主题，消息气泡，图片网格，进度条动画
- [ ] 编写 `src/static/js/ws.js` — WebSocket 客户端封装
  - 自动重连，消息分发
- [ ] 编写 `src/static/js/chat.js` — 对话逻辑
  - 消息渲染，图片懒加载，生成进度条更新
- [ ] 编写 `src/static/js/ui.js` — UI 交互
  - 两个按钮的事件绑定
  - 已生成材质列表管理（单击选为 Background，再次单击选为 Surface）
  - Tile 尺寸选择器 (16/32/64/128)
  - Autotile 图集预览与 mask_map 展示
- [ ] 端到端测试: 前端 → API → ComfyUI → Autotile → 图片展示

### Phase 6: 完善与测试 (第9-11天)

- [ ] 错误处理完善
  - ComfyUI 连接失败 / 生成超时
  - nine_slice 切割尺寸校验
  - 图片尺寸不匹配 (bg 与 surface 尺寸不一致)
  - bitmask 配置完整性校验（必须恰好 47 种）
  - 前端网络断开重连
- [ ] 添加日志系统 (Python `logging` 模块)
- [ ] 编写集成测试:
  - `test_full_pipeline.py` — 端到端: 从两张 mock 纹理到最终 autotile 图集
- [ ] 编写 `README.md` 使用说明（含 autotile 格式说明）
- [ ] 项目打包与部署文档

---

## 9. 风险与注意事项

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| ComfyUI API 兼容性变化 | 集成失败 | 锁定 ComfyUI 版本，在文档中注明兼容版本 |
| SD 生成时间长 (>30s) | 用户体验差 | WebSocket 实时推送进度 + 进度条动画缓解等待感 |
| GPU 资源不足 | 生成排队或 OOM | 在配置中控制 batch_size 和分辨率上限 |
| 像素风格 LoRA 不稳定 | 部分生成结果不可用 | 前端允许用户删除不满意的结果，重新生成 |
| background 与 surface 风格不匹配 | 合成效果差 | 前端预览合成结果，支持重新选择材质组合 |
| Surface 纹理 nine_slice 切割不精确 | 边缘过渡生硬 | 在 ImageProcessor 中增加边缘检测辅助定位切割线 |
| bitmask 逻辑实现错误 | tile 邻接过渡不正确 | 为 AutotileEngine 编写充分的单元测试，覆盖全部 47 种 mask |
| 前端同时打开多个 WebSocket | 连接数压力 | 实现心跳检测，超时自动关闭闲置连接 |

---

## 附录 A: ComfyUI 环境要求

- ComfyUI 版本: 最新 release
- 必需模型:
  - `sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors` (放入 `ComfyUI/models/checkpoints/`)
  - `pixel_art_style_z_image_turbo.safetensors` (放入 `ComfyUI/models/loras/`)
- ComfyUI 启动参数: `--listen 0.0.0.0` (允许外部 API 调用)

## 附录 B: 未来扩展方向

1. **多工作流支持**: 除材质生成外，增加法线贴图、高度图生成工作流
2. **批量材质对生成**: 用户一次选择多组 (bg, surface) 对，批量合成多个 autotile 图集
3. **47-tile 布局预览**: 前端提供交互式 mask 预览，鼠标悬停查看每个 tile 对应的 bitmask 配置
4. **多格式导出**: 支持 Unity Sprite Atlas、Godot TileSet、Tiled TMX、RPG Maker 等游戏引擎格式
5. **自动生成 background 变体**: 基于 surface，用 img2img 反向推导合适的 background 纹理
6. **历史记录持久化**: 使用 SQLite 替换内存存储，支持跨会话查看生成历史
7. **ComfyUI 工作流模板库**: 支持切换不同的工作流模板以适配不同的美术风格（像素风/手绘风/写实风）
