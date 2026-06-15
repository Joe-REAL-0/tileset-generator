# 前端页面重写开发规划: 两阶段 Background → Surface 生成流程

## Context

当前项目生成 tileset 的流程为: 先生成 Background 纹理, 用户选择一个 Backgroud 作为输入, 再生成 Surface 纹理, 最后合成 Autotile。两个 ComfyUI 工作流 (`sd-gen-background.json` 和 `sd-gen-surface.json`) 已经准备就绪, 但当前前端和后端只支持单一步骤的 "生成材质", 缺少区分 Background 和 Surface 生成的能力。

本规划旨在重写 `src/static/index.html` 及相关前后端代码, 确保两步生成流程可以正确实现。

---

## 两个 ComfyUI 工作流的关键差异

### sd-gen-background.json (纯文生图)
- KSampler (Node 4) 的 `latent_image` 连接到 EmptyLatentImage (Node 11) → **从噪声生成**
- 包含 Node 21/22/24/25 (LoadImage, LoadImageMask, VAEEncode, SetLatentNoiseMask) 但为孤立节点, KSampler 不使用它们
- 可编辑参数: Node 19 (正向提示词, `text` 字段), Node 20 (反向提示词, `text` 字段), Node 4 (seed, steps, cfg, sampler, scheduler), Node 11 (width, height, batch_size), Node 7 (filename_prefix)

### sd-gen-surface.json (图生图 + 遮罩修补)
- KSampler (Node 4) 的 `latent_image` 连接到 SetLatentNoiseMask (Node 25) → **在编码后的背景图上做遮罩修补**
- 额外的关键节点链: LoadImage(Node 21) → VAEEncode(Node 24) → SetLatentNoiseMask(Node 25), 配合 LoadImageMask(Node 22)
- **没有** EmptyLatentImage (Node 11)
- 可编辑参数: 同 Background, 外加 Node 21 的 `image` 字段 (需设为用户选中的背景图文件名)

---

## Part 1: 后端改动

### 1.1 重写 `src/services/workflow_editor.py`

当前 WorkflowEditor 加载 `comfy/sdgen-api.json` (一个不存在的模板), 引用了错误的节点 ID (CLIPTextEncodeLumina2 的 `user_prompt`)。需要完全重写:

```python
class WorkflowEditor:
    """
    支持两种模板类型:
    - "background": 加载 comfy/sd-gen-background.json, KSampler→EmptyLatentImage
    - "surface":    加载 comfy/sd-gen-surface.json,    KSampler→SetLatentNoiseMask
    """
    def __init__(self, template_type: Literal["background", "surface"]): ...
    def set_prompt(self, positive, negative):          # Node 19/20, 字段 "text"
    def set_seed(self, seed):                          # Node 4, 字段 "seed"
    def set_resolution(self, width, height):            # Node 11 (仅 background)
    def set_sampler_params(self, steps, cfg, sampler, scheduler):  # Node 4
    def set_background_image(self, filename):           # Node 21 (仅 surface)
    def set_filename_prefix(self, prefix):              # Node 7
    def get_workflow(self) -> dict:                     # 返回修改后的工作流
```

**关键变化**:
- `set_prompt` 写入 `text` 字段 (CLIPTextEncode), 不再用 `user_prompt` (CLIPTextEncodeLumina2)
- 新增 `set_background_image(filename)` — 设置 surface 工作流中 Node 21 的 `image` 字段
- `set_resolution` 仅在 background 类型时有效 (surface 无 Node 11)

### 1.2 更新 `src/schemas/generate.py`

在 `GenerateRequest` 中新增两个字段:
```python
generate_type: str = Field("background", description="生成类型: background | surface")
background_image_id: str | None = Field(None, description="Surface 生成时使用的背景图 ID")
```

### 1.3 更新 `src/routers/generate.py`

1. **修改 `_build_comfy_prompt`** 函数: 接受 `generate_type` 和 `background_filename` 参数, 根据类型创建对应的 WorkflowEditor
2. **新增 Surface 生成的图片预处理逻辑**: 当 `generate_type == "surface"` 时, 将选中的背景图 (`output/textures/{background_image_id}_0.png`) 复制到 ComfyUI 的 `input/` 目录, 使 LoadImage 节点可以加载
3. **在 `_task_store` 中记录 `generate_type`**, 方便前端区分材质类型
4. **验证逻辑**: `generate_type == "surface"` 时必须提供 `background_image_id`, 且对应的文件必须存在

### 1.4 新增 ComfyUI 输入目录配置

在 `config/config.yaml` 和 `src/config.py` 中新增:
```yaml
comfyui:
  input_dir: "/path/to/ComfyUI/input"  # 默认值: 从 base_url 推断
```

---

## Part 2: 前端改动

### 2.1 重写 `src/static/index.html`

**底部输入栏重新设计**, 支持两步流程:

```
┌─────────────────────────────────────────────────┐
│  📍 Step 1: 输入提示词，生成背景纹理              │  ← mode-indicator
├─────────────────────────────────────────────────┤
│  [输入提示词描述材质...]                          │  ← prompt input
├─────────────────────────────────────────────────┤
│  Tile: [32px ▼]  [🎨 生成背景] [🖌️ 生成表面] [🧩 生成 Autotile] │
│                  使用已选背景: 泥土材质           │  ← surface hint
└─────────────────────────────────────────────────┘
```

**HTML 结构变化**:
- 原 `btnGenerate` 拆分为 `btnGenerateBg` 和 `btnGenerateSf`
- 新增 `modeIndicator` div — 显示当前处于哪一步
- 新增 `surfaceHint` div — 当 BG 已选但 SF 未选时, 提示用户将为哪个背景生成表面
- 更新欢迎消息, 明确三步流程

### 2.2 更新 `src/static/js/ui.js`

**新增状态**:
- `generationMode`: `'background'` | `'surface'` | `'autotile'` — 当前模式
- `materialTypes`: `{materialId: 'background' | 'surface'}` — 追踪每个材质的类型

**新增方法**:
- `updateMode()`: 根据选中状态更新模式指示器、按钮启用/禁用、Surface 提示
- `setMaterialType(id, type)`: 设置材质类型标签
- `onSelectionChanged()`: 统一的选择变化处理 (替代散落的 `updateTilesetButton` 调用)

**事件绑定变化**:
- `btnGenerateBg.click` → `Chat.generateBackground(prompt)`
- `btnGenerateSf.click` → `Chat.generateSurface(prompt, selectedBgId)`
- Enter 键根据当前模式智能选择调用哪个按钮

**材质列表渲染增强**: 每个卡片显示类型标签 ("背景" / "表面")

### 2.3 更新 `src/static/js/chat.js`

**拆分 `generateMaterial` 为两个函数**:
- `generateBackground(prompt)`: POST 时带 `generate_type: "background"`, 生成后自动设为 BG
- `generateSurface(prompt, backgroundImageId)`: POST 时带 `generate_type: "surface"` + `background_image_id`, 生成后添加到材质列表

**修复 Bug**: `_fetchAndDisplayImage` 中 `data.image_paths` → `data.image_urls` (与后端字段名一致)

**新增 `type` 参数**: `_fetchAndDisplayImage(taskId, name, progress, type)` 根据类型显示不同的标签和提示

### 2.4 更新 `src/static/css/style.css`

新增样式:
- `.mode-indicator` — 模式指示器
- `.surface-hint` — 表面提示条
- `.btn-accent` — "生成表面" 按钮 (使用 `--accent` 色)
- `.card-type-label` / `.type-background` / `.type-surface` — 材质类型标签
- `.button-row` 添加 `flex-wrap: wrap` 支持窄屏

---

## Part 3: 实施顺序

| 步骤 | 文件 | 操作 |
|------|------|------|
| 1 | `src/services/workflow_editor.py` | 完全重写: 支持两种模板类型, 修正节点 ID, 新增 `set_background_image` |
| 2 | `src/schemas/generate.py` | 新增 `generate_type`, `background_image_id` 字段 |
| 3 | `src/routers/generate.py` | 修改 `_build_comfy_prompt`, 新增 Surface 背景图复制逻辑 |
| 4 | `src/config.py` + `config/config.yaml` | 新增 `comfyui.input_dir` 配置 |
| 5 | `src/static/index.html` | 重写底部输入栏, 拆分按钮, 新增模式指示器和 Surface 提示 |
| 6 | `src/static/js/ui.js` | 新增模式管理, 材质类型追踪, 更新事件绑定 |
| 7 | `src/static/js/chat.js` | 拆分 BG/SF 生成函数, 修复 `image_urls` bug |
| 8 | `src/static/css/style.css` | 新增模式指示器、按钮、类型标签样式 |
| 9 | 端到端测试 | 完整走一遍 BG→SF→Autotile 流程 |

---

## Part 4: 验证方案

1. **启动服务**: `uvicorn src.main:app --reload --host 127.0.0.1 --port 8000` (确保 ComfyUI 也在运行)
2. **测试 Background 生成**: 输入 "dirt texture" → 点击 "生成背景" → 验证进度条、WebSocket 推送、图片显示、侧边栏出现带 "背景" 标签的材质
3. **测试模式切换**: 验证模式指示器随 BG 选择状态变化 (Step 1 → Step 2), 表面按钮从禁用变为启用
4. **测试 Surface 生成**: 选中一个背景 → 输入 "grass texture" → 点击 "生成表面" → 验证表面图片生成并带 "表面" 标签
5. **测试 Autotile 合成**: 同时选中 BG + SF → 点击 "生成 Autotile" → 验证 47-tile 图集生成
6. **测试错误处理**: Surface 生成时不选 BG 点击按钮 → 验证提示消息
