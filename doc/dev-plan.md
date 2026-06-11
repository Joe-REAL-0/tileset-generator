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

构建一套自动化工具链，使用 Stable Diffusion 生成游戏 tile（瓦片）纹理，并将多个 tile 自动拼接为游戏引擎可直接使用的完整 tileset 图集（sprite sheet / texture atlas）。

### 1.2 核心功能

| 功能 | 描述 |
|------|------|
| **材质生成** | 用户输入自然语言提示词，系统调用 ComfyUI + SD 生成单张 tile 纹理 |
| **Tileset 拼合** | 将多张已生成的 tile 纹理自动拼接为符合规范的 tileset 图集 |
| **对话式交互** | 通过 Web 对话界面完成所有操作，降低使用门槛 |
| **实时反馈** | 通过 WebSocket 推送生成进度，用户可实时查看生成状态 |

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
┌──────────────────────────────────────────────────────────┐
│                      用户浏览器                            │
│  ┌────────────────────────────────────────────────────┐  │
│  │              对话界面 (Chat UI)                      │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │  │
│  │  │ 生成材质  │  │ 生成     │  │  消息/图片展示区   │ │  │
│  │  │ (按钮1)   │  │ Tileset  │  │                  │ │  │
│  │  │           │  │ (按钮2)   │  │  [图片预览]      │ │  │
│  │  └──────────┘  └──────────┘  └──────────────────┘ │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────┬────────────────────────────┬──────────────┘
               │  HTTP REST + WebSocket      │
               ▼                             ▼
┌──────────────────────────────────────────────────────────┐
│                    FastAPI 服务层                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ /api/chat   │  │ /api/generate│  │ /api/tileset   │  │
│  │ (对话接口)   │  │ (材质生成)    │  │ (Tileset拼合)  │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
│         │                │                   │           │
│  ┌──────┴────────────────┴───────────────────┴────────┐  │
│  │              核心业务逻辑层                          │  │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────┐ │  │
│  │  │ ComfyUI    │  │ Tileset    │  │ Image        │ │  │
│  │  │ Client     │  │ Builder    │  │ Processor    │ │  │
│  │  └─────┬──────┘  └────────────┘  └──────────────┘ │  │
│  └────────┼───────────────────────────────────────────┘  │
└───────────┼──────────────────────────────────────────────┘
            │  HTTP (REST API)
            ▼
┌──────────────────────────────────────────────────────────┐
│                    ComfyUI 服务                            │
│  ┌──────────────────────────────────────────────────┐    │
│  │  /api/prompt  │  /api/history  │  /api/view      │    │
│  │  (递交工作流)   │  (查询历史)     │  (获取图片)      │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────┐    │
│  │              SD3.5 Medium + LoRA                  │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### 架构说明

- **前后端分离**：FastAPI 提供 REST API，前端为纯静态页面，通过 AJAX + WebSocket 通信
- **ComfyUI 作为独立服务**：ComfyUI 在本地或远端独立运行，FastAPI 通过其 REST API 递交工作流并获取结果
- **异步非阻塞**：图像生成是长时间任务，使用 WebSocket 推送进度，避免 HTTP 超时

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
│   │   ├── tileset_builder.py      # Tileset 拼合逻辑
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
│   ├── textures/                   # 单张 tile 纹理
│   └── tilesets/                   # 拼接完成的 tileset 图集
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

# Tileset 默认参数
tileset:
  default_columns: 4                      # 默认列数
  default_tile_size: 512                  # 每个 tile 的尺寸 (px)
  output_format: "png"                    # 输出格式
  padding: 0                              # tile 间距 (px)

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

```python
class ImageProcessor:
    """提供 tile 纹理的预处理与后处理"""

    @staticmethod
    def resize(image: Image, size: tuple[int, int]) -> Image:
        """缩放图像到指定尺寸（使用 NEAREST 保持像素风格）"""

    @staticmethod
    def trim_transparent(image: Image) -> Image:
        """裁切透明边缘"""

    @staticmethod
    def add_border(image: Image, border_size: int,
                   color: tuple[int, int, int, int] = (0,0,0,0)
                   ) -> Image:
        """为 tile 添加边框"""

    @staticmethod
    def ensure_rgba(image: Image) -> Image:
        """确保图像为 RGBA 模式"""

    @staticmethod
    def validate_tile(image: Image, expected_size: tuple[int, int]) -> bool:
        """校验 tile 尺寸是否符合预期"""
```

#### 5.3.2 Tileset 拼合器 (`src/services/tileset_builder.py`)

**核心功能**：将多张独立的 tile 纹理拼接为一张完整的 tileset 图集。

```python
class TilesetBuilder:
    """将多张 tile 纹理拼接为 tileset 图集"""

    def __init__(self, tile_size: int = 512, columns: int = 4,
                 padding: int = 0):
        self.tile_size = tile_size
        self.columns = columns
        self.padding = padding

    def add_tile(self, image: Image, position: int | None = None):
        """添加一个 tile 到指定位置（或自动追加）"""

    def remove_tile(self, position: int):
        """移除指定位置的 tile"""

    def build(self) -> Image:
        """
        将所有 tile 拼接为一张大图。

        布局:
        ┌────┬────┬────┬────┐
        │ 0  │ 1  │ 2  │ 3  │  ← 每行 columns 个 tile
        ├────┼────┼────┼────┤
        │ 4  │ 5  │ 6  │ 7  │
        └────┴────┴────┴────┘

        输出尺寸 = (columns * tile_size, ceil(n/columns) * tile_size)
        """

    def build_with_metadata(self) -> tuple[Image, dict]:
        """
        拼接并返回元数据:
        {
            "tile_count": 8,
            "columns": 4,
            "rows": 2,
            "tile_size": 512,
            "image_size": [2048, 1024],
            "format": "png"
        }
        """

    def save(self, filepath: str, format: str = "PNG"):
        """保存拼接结果到文件"""
```

**Tileset 布局示意**：

```
       tile_size
    ├──────────┤
  ┌─────────────────────────────────────┐
  │ tile[0] │ tile[1] │ tile[2] │ ...   │  ← Row 0
  ├─────────┼─────────┼─────────┼───────┤
  │ tile[4] │ tile[5] │   ...   │ ...   │  ← Row 1
  ├─────────┼─────────┼─────────┼───────┤
  │   ...   │   ...   │   ...   │ ...   │  ← Row N
  └─────────────────────────────────────┘
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
    prompt: str = Field(..., description="正向提示词 (描述要生成的材质)")
    negative_prompt: str | None = Field(None, description="反向提示词")
    seed: int | None = Field(None, description="随机种子 (-1表示随机)")
    width: int = Field(512, ge=64, le=2048, multiple_of=64)
    height: int = Field(512, ge=64, le=2048, multiple_of=64)

class GenerateResponse(BaseModel):
    task_id: str                          # 异步任务 ID
    status: str                           # "queued"
    websocket_url: str                    # 前端连接 WebSocket 获取进度的地址

# schemas/tileset.py
class TilesetRequest(BaseModel):
    image_ids: list[str]                  # 已生成纹理的 ID 列表
    columns: int = 4
    tile_size: int = 512
    padding: int = 0

class TilesetResponse(BaseModel):
    task_id: str
    status: str
    tileset_url: str | None = None
    metadata: dict | None = None

# schemas/chat.py
class ChatMessage(BaseModel):
    role: str                             # "user" | "assistant" | "system"
    content: str
    image_url: str | None = None          # 图片 URL (assistant 消息中携带)
    timestamp: str
```

#### 5.4.3 路由设计

```python
# routers/generate.py
@router.post("/generate", response_model=GenerateResponse)
async def generate_texture(request: GenerateRequest):
    """
    按钮1: 生成材质

    1. 接收用户提示词
    2. 用 WorkflowEditor 注入参数到工作流
    3. 提交到 ComfyUI
    4. 返回 task_id，前端通过 WebSocket 获取进度
    """

# routers/tileset.py
@router.post("/tileset", response_model=TilesetResponse)
async def build_tileset(request: TilesetRequest):
    """
    按钮2: 生成 Tileset

    1. 接收用户选择的图片 ID 列表
    2. 用 TilesetBuilder 拼合为图集
    3. 返回 tileset 图片 URL 和元数据
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
        "type": "progress",        # 消息类型
        "task_id": "...",
        "status": "generating",    # queued | generating | completed | failed
        "progress": 45,            # 百分比 (估算)
        "message": "Sampling...",
        "image_url": null,         # 完成后携带图片 URL
        "error": null              # 失败时携带错误信息
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
┌───────────────────────────────────────────────────────┐
│  🎨 Tileset Generator                    [设置 ⚙️]    │
├───────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │                                             │     │
│  │            💬 对话消息区域                    │     │
│  │  ┌──────────────────────────────────┐      │     │
│  │  │ 👤 用户: 生成一个草地纹理的tile    │      │     │
│  │  └──────────────────────────────────┘      │     │
│  │  ┌──────────────────────────────────┐      │     │
│  │  │ 🤖 助手: 正在生成... ⏳           │      │     │
│  │  │        [进度条 ████████░░ 80%]    │      │     │
│  │  │        ┌────────┐                │      │     │
│  │  │        │  [图片] │ ← 生成结果      │      │     │
│  │  │        └────────┘                │      │     │
│  │  │        ✅ tile_"草地" 已生成!     │      │     │
│  │  └──────────────────────────────────┘      │     │
│  │                                             │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │  输入提示词...                     │  📎     │     │
│  │                                     │         │     │
│  │  [🎨 生成材质]   [🧩 生成Tileset]    │  发送   │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
└───────────────────────────────────────────────────────┘
```

#### 按钮行为

| 按钮 | 触发条件 | 行为 |
|------|---------|------|
| **🎨 生成材质** | 输入框有文本 | 调用 `POST /api/generate`，通过 WebSocket 跟踪进度，完成后显示图片 |
| **🧩 生成Tileset** | 用户已选中 ≥2 张已生成的纹理 | 调用 `POST /api/tileset`，拼合图集并展示下载链接 |

#### 交互流程

```
1. 用户在输入框输入 "一个石头地面的tile纹理，16-bit像素风格"
2. 用户点击 [🎨 生成材质]
3. 前端: 输入框清空，对话区显示用户消息 + "正在生成..." 的助手消息
4. 前端: POST /api/generate → 获取 task_id → 连接 ws://host/ws/{task_id}
5. WebSocket 逐步推送进度: queued → generating (step 5/20...) → completed
6. 前端: 替换 "正在生成..." 为生成的图片预览
7. 用户重复 1-6，生成更多 tile (草地、水面、沙地...)
8. 用户在对话区勾选已生成的 tile 图片 (如选中4张)
9. 用户点击 [🧩 生成Tileset]
10. 前端: POST /api/tileset → 获取拼合后的 tileset 图集 → 显示并提供下载
```

#### 已生成图片管理

前端维护一个 **已生成图片列表**（展示在侧边栏或对话区顶部），每张图片有复选框。用户勾选需要拼合的 tile 后点击 "生成Tileset"。

```
已生成的 Tile (点击勾选以拼合):
┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
│ ☑️   │ │ ☑️   │ │ ☑️   │ │ ☐   │
│ 草地 │ │ 沙地 │ │ 水面 │ │ 岩石 │
└─────┘ └─────┘ └─────┘ └─────┘
```

---

## 6. API 接口设计

### 6.1 完整 API 列表

| 方法 | 路径 | 描述 | 请求体 | 响应体 |
|------|------|------|--------|--------|
| `POST` | `/api/generate` | 提交材质生成任务 | `GenerateRequest` | `GenerateResponse` |
| `GET` | `/api/generate/{task_id}` | 查询任务状态 | - | `TaskStatus` |
| `POST` | `/api/tileset` | 提交 tileset 拼合任务 | `TilesetRequest` | `TilesetResponse` |
| `GET` | `/api/tileset/{tileset_id}` | 查询拼合状态 | - | `TilesetStatus` |
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
  "prompt": "2D game asset, single square tile texture, side view of a stone path, gray cobblestones, 16-bit retro game style, flat lighting, sharp pixel edges, white background, masterpiece, high quality",
  "negative_prompt": "3D render, blurry, gradients, noise, text, watermark",
  "seed": -1,
  "width": 512,
  "height": 512
}

// Response
{
  "task_id": "task_abc123",
  "status": "queued",
  "websocket_url": "ws://127.0.0.1:8000/ws/task_abc123"
}
```

#### 拼合 Tileset

```json
// POST /api/tileset
{
  "image_ids": ["img_001", "img_002", "img_003", "img_004"],
  "columns": 4,
  "tile_size": 512,
  "padding": 0
}

// Response
{
  "task_id": "ts_def456",
  "status": "completed",
  "tileset_url": "/api/tilesets/ts_def456/download",
  "metadata": {
    "tile_count": 4,
    "columns": 4,
    "rows": 1,
    "tile_size": 512,
    "image_size": [2048, 512],
    "format": "png"
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

### 7.2 Tileset 拼合完整流程

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  前端     │     │ FastAPI   │     │ 文件系统  │
│ (Browser)│     │ (Python)  │     │ (output/) │
└────┬─────┘     └─────┬─────┘     └─────┬─────┘
     │                  │                │
     │ 1. POST /tileset │                │
     │  (image_ids)     │                │
     │─────────────────►│                │
     │                  │                │
     │                  │ 2. 加载图片      │
     │                  │◄───────────────│
     │                  │    (按ID读取)   │
     │                  │                │
     │                  │ 3. TilesetBuilder.build()
     │                  │    校验尺寸 → 按布局拼接
     │                  │                │
     │                  │ 4. 保存 Tileset │
     │                  │────────────────►│
     │                  │   到 output/tilesets/
     │                  │                │
     │ 5. tileset_url + │                │
     │    metadata      │                │
     │◄─────────────────│                │
     │                  │                │
     │ 6. GET /tilesets/{id}/download    │
     │─────────────────►│                │
     │                  │                │
     │ 7. 图片文件       │                │
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

### Phase 3: 图像处理模块 (第3-4天)

- [ ] 实现 `src/services/image_processor.py`
  - resize / trim / add_border / ensure_rgba / validate_tile
- [ ] 实现 `src/services/tileset_builder.py`
  - add_tile / build / build_with_metadata / save
- [ ] 编写 `tests/test_tileset_builder.py` — 使用纯色测试图片验证拼接逻辑
- [ ] 确认 tileset 布局算法正确（行优先，自动换行）

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

### Phase 5: 前端界面 (第6-8天)

- [ ] 编写 `src/static/index.html` — 页面骨架
- [ ] 编写 `src/static/css/style.css` — 样式
  - 深色主题，消息气泡，图片网格，进度条动画
- [ ] 编写 `src/static/js/ws.js` — WebSocket 客户端封装
  - 自动重连，消息分发
- [ ] 编写 `src/static/js/chat.js` — 对话逻辑
  - 消息渲染，图片懒加载，生成进度条更新
- [ ] 编写 `src/static/js/ui.js` — UI 交互
  - 两个按钮的事件绑定
  - 已生成图片的选择/勾选管理
  - 拖拽排序（可选）
- [ ] 端到端测试: 前端 → API → ComfyUI → 图片展示

### Phase 6: 完善与测试 (第8-10天)

- [ ] 错误处理完善
  - ComfyUI 连接失败
  - 生成超时
  - 图片尺寸不匹配
  - 前端网络断开
- [ ] 添加日志系统 (Python `logging` 模块)
- [ ] 编写集成测试
- [ ] 编写 `README.md` 使用说明
- [ ] 项目打包与部署文档

---

## 9. 风险与注意事项

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| ComfyUI API 兼容性变化 | 集成失败 | 锁定 ComfyUI 版本，在文档中注明兼容版本 |
| SD 生成时间长 (>30s) | 用户体验差 | WebSocket 实时推送进度 + 进度条动画缓解等待感 |
| GPU 资源不足 | 生成排队或 OOM | 在配置中控制 batch_size 和分辨率上限 |
| 像素风格 LoRA 不稳定 | 部分生成结果不可用 | 前端允许用户删除不满意的结果，重新生成 |
| 大尺寸 tileset 内存占用 | 服务端 OOM | 限制单次拼合 tile 数量上限 (如 max 64 个) |
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
2. **自动补全/变异**: 基于已有 tile，用 img2img 自动生成相邻 tile 变体
3. **无缝拼接**: 使用 border-reflection 技术让相邻 tile 边缘无缝过渡
4. **多格式导出**: 支持 Unity Sprite Atlas、Godot TileSet、Tiled TMX 等格式
5. **批量生成队列**: 支持一次性提交多个提示词，排队生成
6. **历史记录持久化**: 使用 SQLite 替换内存存储，支持跨会话查看历史
