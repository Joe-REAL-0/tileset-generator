# 🎨 Tileset Generator

基于 Stable Diffusion + ComfyUI 的自动 47-tile Autotile 图集生成系统。本科人工智能专业课程设计。

输入材质描述（如"草地"、"沙地"），自动生成纹理并合成为游戏引擎可用的 autotile 图集。

## 工作流程

```
用户输入提示词 → ComfyUI SD 生成纹理 → 缩放 → 九宫格切割 → Bitmask 合成 → 47-tile 图集输出
```

1. **生成材质** — 输入正向提示词描述材质，通过 ComfyUI 调用 Stable Diffusion 生成 512×512 纹理
2. **选择材质** — 从已生成列表中分别选择一张 Background（背景）和一张 Surface（表面）纹理
3. **生成 Autotile** — 将 Background 与 Surface 按 bitmask 规则合成为 47 种邻接变体 tile 的完整图集

## 环境要求

- **Python** ≥ 3.10
- **ComfyUI** — 需要独立安装并运行，且已加载至少一个 SD checkpoint（如 SD 1.5 / SDXL）
- ComfyUI API 需在 `8188` 端口可访问（默认）

## 快速开始

### 1. 克隆项目

```bash
git clone <repo-url>
cd tileset-generator
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置文件

```bash
# 从模板创建配置文件
cp config/config.example.yaml config/config.yaml

# 从模板创建环境变量文件
cp .env.example .env
```

### 4. 启动 ComfyUI

确保 ComfyUI 已在运行，并且 API 端点可访问：

```bash
# 在 ComfyUI 目录下启动（需带 --enable-cors-header 以允许跨域）
python main.py --enable-cors-header --listen 127.0.0.1 --port 8188
```

### 5. 导入工作流模板

将 `comfy/sdgen-api.json` 导入 ComfyUI，确保工作流中的 checkpoint 名称与你实际使用的模型一致。

### 6. 启动服务

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

启动后访问 **http://127.0.0.1:8000** 进入 Web 界面。

## 配置说明

项目通过 **配置文件** + **环境变量** 两层机制管理配置，优先级为：

```
.env 环境变量 > config/config.yaml > Pydantic 默认值
```

### 主配置文件 — `config/config.yaml`

| 配置项 | 默认值 | 说明 |
|---|---|---|
| **`comfyui.base_url`** | `http://127.0.0.1:8188` | ComfyUI API 地址 |
| **`comfyui.timeout`** | `300` | 单次 SD 生成超时时间（秒） |
| **`comfyui.poll_interval`** | `1.0` | 轮询 ComfyUI 生成状态的间隔（秒） |
| **`generation.default_steps`** | `20` | SD 采样步数，值越大质量越高但越慢 |
| **`generation.default_cfg`** | `8.0` | CFG Scale（提示词引导强度），控制生成对提示词的遵循程度 |
| **`generation.default_sampler`** | `euler` | SD 采样器名称（如 `euler`、`euler_ancestral`、`dpmpp_2m` 等） |
| **`generation.default_scheduler`** | `simple` | SD 调度器名称（如 `simple`、`normal`、`karras` 等） |
| **`tileset.output_format`** | `png` | 输出图集文件格式 |
| **`output_tile_sizes`** | `[16, 32, 64, 128]` | 可选的目标 tile 像素尺寸列表，SD 生成 512px 纹理会缩放至目标尺寸 |
| **`default_tile_size`** | `32` | 前端默认选择的 tile 尺寸（px） |
| **`server.host`** | `127.0.0.1` | FastAPI 监听地址 |
| **`server.port`** | `8000` | FastAPI 监听端口 |
| **`server.cors_origins`** | `["*"]` | CORS 允许的跨域来源 |

### 环境变量 — `.env`

| 环境变量 | 说明 |
|---|---|
| **`COMFYUI_BASE_URL`** | 覆盖 ComfyUI 服务地址 |
| **`SERVER_PORT`** | 覆盖服务端口 |

### ComfyUI 工作流模板 — `comfy/sdgen-api.json`

这是 ComfyUI API 格式的工作流 JSON 文件。程序运行时会加载此模板，动态注入用户提示词、种子、采样参数等，然后提交到 ComfyUI 执行。

**注意**：请确保模板中的 checkpoint 节点 `ckpt_name` 与 ComfyUI 中实际加载的模型名称一致。

## API 接口

### 材质生成

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/generate` | 提交材质纹理生成任务 |
| `GET` | `/api/generate/{task_id}` | 查询生成任务状态 |

**POST /api/generate 请求体：**

```json
{
  "prompt": "草地",
  "negative_prompt": "3D render, realistic, shadows",
  "seed": 42
}
```

### Autotile 合成

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/tileset` | 提交 autotile 合成任务 |
| `GET` | `/api/tileset/{tileset_id}` | 查询合成任务状态 |
| `GET` | `/api/tilesets` | 列出所有已生成的 tileset |
| `GET` | `/api/tilesets/{tileset_id}/download` | 下载 tileset PNG 文件 |

**POST /api/tileset 请求体：**

```json
{
  "background_image_id": "gen_a1b2c3d4e5f6",
  "surface_image_id": "gen_f6e5d4c3b2a1",
  "tile_size": 32
}
```

### WebSocket

| 路径 | 说明 |
|---|---|
| `ws://127.0.0.1:8000/ws/{task_id}` | 连接后可实时接收生成进度推送 |

### 其他

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/health` | 健康检查 |

## 项目结构

```
tileset-generator/
├── config/
│   ├── config.example.yaml    # 配置文件模板
│   └── config.yaml            # 实际配置文件 (需自行创建)
├── comfy/
│   └── sdgen-api.json         # ComfyUI 工作流 API 模板
├── src/
│   ├── main.py                # FastAPI 应用入口
│   ├── config.py              # 配置加载 (YAML + .env)
│   ├── static/                # 前端静态文件
│   │   ├── index.html
│   │   ├── css/style.css
│   │   └── js/
│   ├── routers/
│   │   ├── generate.py        # 材质生成 API
│   │   ├── tileset.py         # Autotile 合成 API
│   │   ├── chat.py            # 对话接口
│   │   └── ws.py              # WebSocket 实时推送
│   ├── schemas/
│   │   ├── generate.py        # 生成请求/响应模型
│   │   ├── tileset.py         # Tileset 请求/响应模型
│   │   └── chat.py            # 对话模型
│   └── services/
│       ├── comfy_client.py    # ComfyUI API 异步客户端
│       ├── workflow_editor.py # 工作流参数注入
│       ├── image_processor.py # 图像缩放/九宫格切割
│       ├── autotile_engine.py # Bitmask 合成引擎 (核心)
│       └── tileset_builder.py # 图集拼接与元数据
├── output/                    # 生成产物输出目录
│   ├── textures/              # 生成的原始纹理
│   └── tilesets/              # 合成的 autotile 图集
├── tests/
├── requirements.txt
├── .env.example               # 环境变量模板
└── README.md
```

## Bitmask Autotile 原理

每个 tile 按 4-bit 编码上下左右 4 个方向的邻接状态：

| Bit | 掩码 | 含义 |
|---|---|---|
| bit 0 | `0x1` | 上方邻居是否为同一材质 |
| bit 1 | `0x2` | 下方邻居是否为同一材质 |
| bit 2 | `0x4` | 左方邻居是否为同一材质 |
| bit 3 | `0x8` | 右方邻居是否为同一材质 |

Surface 纹理被九宫格切割为 8 个子区域（TL、T、TR、L、R、BL、B、BR），根据 bitmask 选择性叠加到 Background 上。例如：上方邻居不同（bit 0 = 0）→ 显示 T（上边缘）子区域，上方和左方均不同 → 显示 TL（左上角）子区域。共产生 47 种有效 tile 变体，拼接为完整图集供游戏引擎使用。

## 常见问题

**Q: 启动时报 "无法连接到 ComfyUI 服务"？**

请确认 ComfyUI 已启动并监听在 `config.yaml` 中配置的地址和端口。

**Q: 生成 prompt 提交后一直处于 generating 状态？**

检查 ComfyUI 是否正确加载了 SD checkpoint 模型，以及 `comfy/sdgen-api.json` 中的 `ckpt_name` 是否与实际模型名称匹配。

**Q: 如何修改输出的 tile 尺寸？**

在 `config/config.yaml` 中修改 `output_tile_sizes` 列表，或在前端下拉菜单中选择。可选值：16 / 32 / 64 / 128 px。
