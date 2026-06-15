// src/static/js/ui.js
// UI 交互逻辑
// 职责: 管理前端 UI 状态与用户交互
//   - 页面Tab切换 (生成材质 / 材质库 / 生成图集)
//   - 生成模式切换 (Background / Surface)
//   - 系统提示词 / 模型列表加载
//   - Surface 模式背景图选择器
//   - 材质库图片浏览与上传
//   - 图集页面 BG/SF 选择与按钮状态
//   - 对话消息渲染 (消息、进度条、图片)

const UI = {
    // ── DOM 引用 ──
    elements: {
        // 导航
        navTabs: document.querySelectorAll('.nav-tab'),
        pages: document.querySelectorAll('.page-content'),

        // 生成页面
        modeTabs: document.querySelectorAll('.mode-tab'),
        systemPositivePrompt: document.getElementById('systemPositivePrompt'),
        systemNegativePrompt: document.getElementById('systemNegativePrompt'),
        materialPrompt: document.getElementById('materialPrompt'),
        promptHistoryList: document.getElementById('promptHistoryList'),
        checkpointSelect: document.getElementById('checkpointSelect'),
        loraSelect: document.getElementById('loraSelect'),
        bgSelectorGroup: document.getElementById('bgSelectorGroup'),
        bgSelectorGrid: document.getElementById('bgSelectorGrid'),
        btnGenerate: document.getElementById('btnGenerate'),

        // 材质库页面
        btnRefreshLibrary: document.getElementById('btnRefreshLibrary'),
        btnUploadBg: document.getElementById('btnUploadBg'),
        btnUploadSf: document.getElementById('btnUploadSf'),
        uploadBgInput: document.getElementById('uploadBgInput'),
        uploadSfInput: document.getElementById('uploadSfInput'),
        libraryGrid: document.getElementById('libraryGrid'),
        libraryInfo: document.getElementById('libraryInfo'),
        libFilterType: document.getElementById('libFilterType'),
        libSortTime: document.getElementById('libSortTime'),

        // 图集页面
        atlasBgGrid: document.getElementById('atlasBgGrid'),
        atlasSfGrid: document.getElementById('atlasSfGrid'),
        tileSize: document.getElementById('tileSize'),
        btnTileset: document.getElementById('btnTileset'),
        atlasHint: document.getElementById('atlasHint'),

        // 对话区
        chatMessages: document.getElementById('chatMessages'),

        // 图片预览 Modal
        imageModal: document.getElementById('imageModal'),
        imageModalClose: document.getElementById('imageModalClose'),
        imageModalImg: document.getElementById('imageModalImg'),
    },

    // ── 状态 ──
    state: {
        /** @type {Array<Object>} 材质库加载的所有原始数据 */
        libraryRawData: [],
        /** @type {Array<{id: string, name: string, url: string}>} */
        materials: [],
        /** @type {Object<string, 'background'|'surface'>} 材质类型追踪 */
        materialTypes: {},
        /** @type {'background'|'surface'} 当前生成模式 */
        generationMode: 'background',
        /** @type {string|null} Surface 模式选中的背景图 ID */
        surfaceSelectedBgId: null,
        /** @type {string} */
        currentPage: 'generate',
        /** @type {Array<string>} 历史提示词 */
        promptHistory: [],
        /** @type {string|null} 图集页面选中的背景图 ID */
        atlasSelectedBgId: null,
        /** @type {string|null} 图集页面选中的表面图 ID */
        atlasSelectedSfId: null,
    },

    // ── 初始化 ──
    async init() {
        this.bindEvents();
        await Promise.all([
            this.loadPromptsConfig(),
            this.loadModels(),
            this.loadBackgroundMaterials(),
        ]);
    },

    // ── 事件绑定 ──
    bindEvents() {
        // ── 导航Tab切换 ──
        this.elements.navTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                this.switchPage(tab.dataset.page);
            });
        });

        // ── 生成模式切换 ──
        this.elements.modeTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                this.switchMode(tab.dataset.mode);
            });
        });

        // ── 生成按钮 ──
        this.elements.btnGenerate.addEventListener('click', () => {
            const materialPrompt = this.elements.materialPrompt.value.trim();
            if (!materialPrompt) {
                this.addMessage('system', '⚠️ 请输入材质提示词');
                return;
            }
            if (this.state.generationMode === 'surface' && !this.state.surfaceSelectedBgId) {
                this.addMessage('system', '⚠️ 请在下方面板中选择一张背景图');
                return;
            }
            Chat.generateTexture();
        });

        // ── Enter 键触发生成 ──
        this.elements.materialPrompt.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.elements.btnGenerate.click();
            }
        });

        // ── 材质库刷新 ──
        if (this.elements.btnRefreshLibrary) {
            this.elements.btnRefreshLibrary.addEventListener('click', () => {
                this.loadLibraryImages();
            });
        }

        // ── 材质库过滤与排序 ──
        if (this.elements.libFilterType) {
            this.elements.libFilterType.addEventListener('change', () => {
                this.renderLibraryImages();
            });
        }
        if (this.elements.libSortTime) {
            this.elements.libSortTime.addEventListener('change', () => {
                this.renderLibraryImages();
            });
        }

        // ── 材质库上传 (Background / Surface) ──
        if (this.elements.btnUploadBg && this.elements.uploadBgInput) {
            this.elements.btnUploadBg.addEventListener('click', () => {
                this.elements.uploadBgInput.click();
            });
            this.elements.uploadBgInput.addEventListener('change', () => {
                this.handleUpload('background', this.elements.uploadBgInput);
            });
        }
        if (this.elements.btnUploadSf && this.elements.uploadSfInput) {
            this.elements.btnUploadSf.addEventListener('click', () => {
                this.elements.uploadSfInput.click();
            });
            this.elements.uploadSfInput.addEventListener('change', () => {
                this.handleUpload('surface', this.elements.uploadSfInput);
            });
        }

        // ── 图集页面选择变更 ──
        // (在渲染 grid 时绑定事件)

        // ── Autotile 按钮 ──
        if (this.elements.btnTileset) {
            this.elements.btnTileset.addEventListener('click', () => {
                Chat.generateTileset();
            });
        }

        // ── 图片预览 Modal 关闭 ──
        if (this.elements.imageModal) {
            this.elements.imageModalClose.addEventListener('click', () => {
                this.elements.imageModal.classList.remove('active');
            });
            this.elements.imageModal.addEventListener('click', (e) => {
                if (e.target === this.elements.imageModal) {
                    this.elements.imageModal.classList.remove('active');
                }
            });
        }
    },

    // ── 页面切换 ──
    switchPage(page) {
        this.state.currentPage = page;

        this.elements.navTabs.forEach(t => {
            t.classList.toggle('active', t.dataset.page === page);
        });

        this.elements.pages.forEach(p => {
            p.classList.toggle('active', p.id === `page-${page}`);
        });

        if (page === 'atlas') {
            this.populateAtlasSelectors();
        }
        if (page === 'library') {
            this.loadLibraryImages();
        }
    },

    // ── 生成模式切换 ──
    switchMode(mode) {
        this.state.generationMode = mode;

        this.elements.modeTabs.forEach(t => {
            t.classList.toggle('active', t.dataset.mode === mode);
        });

        this.elements.bgSelectorGroup.style.display =
            (mode === 'surface') ? 'block' : 'none';

        const btn = this.elements.btnGenerate;
        if (mode === 'background') {
            btn.textContent = '🎨 生成 Background 纹理';
            btn.className = 'btn btn-primary btn-large';
        } else {
            btn.textContent = '🗻 生成 Surface 纹理';
            btn.className = 'btn btn-accent btn-large';
        }

        if (mode === 'surface') {
            this.loadBackgroundMaterials();
        }
    },

    // ── 加载配置 ──

    async loadPromptsConfig() {
        try {
            const resp = await fetch('/api/generate/config/prompts');
            const data = await resp.json();
            this.elements.systemPositivePrompt.value = data.system_positive || '';
            this.elements.systemNegativePrompt.value = data.system_negative || '';
        } catch (e) {
            console.error('加载系统提示词失败:', e);
        }
    },

    async loadModels() {
        try {
            const resp = await fetch('/api/generate/models');
            const data = await resp.json();
            this._populateSelect(this.elements.checkpointSelect, data.checkpoints || []);
            this._populateSelect(this.elements.loraSelect, data.loras || []);
        } catch (e) {
            console.error('加载模型列表失败:', e);
        }
    },

    _populateSelect(selectEl, items) {
        const defaultOpt = selectEl.querySelector('option[value=""]');
        selectEl.innerHTML = '';
        if (defaultOpt) {
            selectEl.appendChild(defaultOpt.cloneNode(true));
        } else {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = '-- 使用默认 --';
            selectEl.appendChild(opt);
        }
        items.forEach(name => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            selectEl.appendChild(opt);
        });
    },

    // ── 材质库: 图片加载 ──

    async loadLibraryImages() {
        const grid = this.elements.libraryGrid;
        const info = this.elements.libraryInfo;
        if (!grid) return;

        grid.innerHTML = '<p class="placeholder-text">加载中...</p>';
        if (info) info.textContent = '';

        try {
            const resp = await fetch('/api/generate/comfy-outputs?prefix=tgen-background,tgen-surface');
            const data = await resp.json();
            this.state.libraryRawData = data.images || [];

            this.renderLibraryImages();
        } catch (e) {
            console.error('加载材质库失败:', e);
            grid.innerHTML = '<p class="placeholder-text">加载失败，请确认 comfy_file_path 已正确配置</p>';
        }
    },

    renderLibraryImages() {
        const grid = this.elements.libraryGrid;
        const info = this.elements.libraryInfo;
        if (!grid) return;

        let images = [...this.state.libraryRawData];

        if (images.length === 0) {
            grid.innerHTML = '<p class="placeholder-text">ComfyUI 输出目录为空</p>';
            if (info) info.textContent = '';
            return;
        }

        // 1. 过滤
        const filterType = this.elements.libFilterType?.value || 'all';
        if (filterType !== 'all') {
            images = images.filter(img => img.filename.includes(filterType));
        }

        // 2. 排序分组
        const sortTime = this.elements.libSortTime?.value || 'desc';
        
        images.sort((a, b) => {
            const typeA = a.filename.includes('background') ? 0 : 1;
            const typeB = b.filename.includes('background') ? 0 : 1;
            
            // 先按类型分组 (background 在前, surface 在后)
            if (typeA !== typeB) {
                return typeA - typeB;
            }

            // 类型相同，按时间排序
            const indexA = this.state.libraryRawData.indexOf(a);
            const indexB = this.state.libraryRawData.indexOf(b);
            
            if (sortTime === 'desc') {
                return indexA - indexB;
            } else {
                return indexB - indexA;
            }
        });

        if (info) info.textContent = `共 ${images.length} 张图片`;

        grid.innerHTML = '';
        images.forEach(img => {
            const isBackground = img.filename.includes('background');
            const typeLabel = isBackground ? 'Background' : 'Surface';
            const typeClass = isBackground ? 'type-background' : 'type-surface';

            const card = document.createElement('div');
            card.className = 'library-card';
            card.innerHTML = `
                <div class="library-card-type ${typeClass}">${typeLabel}</div>
                <img src="${img.url}" alt="${img.filename}" loading="lazy">
                <div class="library-card-info">
                    <span class="library-card-name" title="${img.filename}">${img.filename}</span>
                    <span class="library-card-size">${img.size_kb} KB</span>
                </div>
            `;
            card.addEventListener('click', () => {
                this.showImageModal(img.url);
            });
            grid.appendChild(card);
        });
    },

    // ── 材质库: 本地上传 ──

    async handleUpload(textureType, input) {
        if (!input || !input.files || input.files.length === 0) return;

        const files = Array.from(input.files);
        const total = files.length;
        let uploaded = 0;
        let failed = 0;

        const typeLabel = textureType === 'background' ? 'Background' : 'Surface';
        this.addMessage('system', `📤 正在上传 ${total} 张 ${typeLabel} 图片...`);

        for (const file of files) {
            try {
                const formData = new FormData();
                formData.append('file', file);

                const resp = await fetch(`/api/generate/comfy-outputs/upload?texture_type=${textureType}`, {
                    method: 'POST',
                    body: formData,
                });

                if (resp.ok) {
                    uploaded++;
                } else {
                    const err = await resp.json();
                    console.error(`上传 ${file.name} 失败:`, err.detail);
                    failed++;
                }
            } catch (e) {
                console.error(`上传 ${file.name} 失败:`, e);
                failed++;
            }
        }

        // 清空文件选择
        input.value = '';

        if (failed === 0) {
            this.addMessage('system', `✅ ${typeLabel} 上传完成: ${uploaded} 张图片`);
        } else {
            this.addMessage('system', `⚠️ ${typeLabel} 上传完成: ${uploaded} 成功, ${failed} 失败`);
        }

        // 刷新材质库列表
        this.loadLibraryImages();
    },

    // ── 图集页面: 材质选择器 ──

    /** 填充图集页面的 BG/SF 选择器 */
    async populateAtlasSelectors() {
        const bgGrid = this.elements.atlasBgGrid;
        const sfGrid = this.elements.atlasSfGrid;
        if (!bgGrid || !sfGrid) return;

        bgGrid.innerHTML = '<p class="placeholder-text">加载中...</p>';
        sfGrid.innerHTML = '<p class="placeholder-text">加载中...</p>';

        try {
            const resp = await fetch('/api/generate/comfy-outputs?prefix=tgen-background,tgen-surface');
            const data = await resp.json();
            const images = data.images || [];

            const bgs = images.filter(img => img.filename.includes('background'));
            const sfs = images.filter(img => img.filename.includes('surface'));

            this._renderAtlasGrid(bgGrid, bgs, 'background');
            this._renderAtlasGrid(sfGrid, sfs, 'surface');
        } catch (e) {
            console.error('加载图集材质选择器失败:', e);
            bgGrid.innerHTML = '<p class="placeholder-text">加载失败</p>';
            sfGrid.innerHTML = '<p class="placeholder-text">加载失败</p>';
        }
    },

    _renderAtlasGrid(grid, materials, type) {
        grid.innerHTML = '';
        if (materials.length === 0) {
            grid.innerHTML = `<p class="placeholder-text">尚未生成任何 ${type} 纹理</p>`;
            return;
        }

        materials.forEach(mat => {
            const card = document.createElement('div');
            card.className = 'bg-selector-card';
            card.title = mat.filename;
            
            const selectedId = type === 'background' ? this.state.atlasSelectedBgId : this.state.atlasSelectedSfId;
            if (mat.filename === selectedId) {
                card.classList.add('selected');
            }

            card.innerHTML = `<img src="${mat.url}" alt="${mat.filename}" loading="lazy">`;

            card.addEventListener('click', () => {
                if (type === 'background') {
                    this.state.atlasSelectedBgId = this.state.atlasSelectedBgId === mat.filename ? null : mat.filename;
                } else {
                    this.state.atlasSelectedSfId = this.state.atlasSelectedSfId === mat.filename ? null : mat.filename;
                }
                this._renderAtlasGrid(grid, materials, type);
                this.updateTilesetButton();
            });

            grid.appendChild(card);
        });
    },

    /** 根据图集页面选择更新按钮状态 */
    updateTilesetButton() {
        const btn = this.elements.btnTileset;
        const hint = this.elements.atlasHint;
        if (!btn) return;

        const canGenerate = this.state.atlasSelectedBgId && this.state.atlasSelectedSfId;
        btn.disabled = !canGenerate;
        if (hint) {
            hint.textContent = canGenerate
                ? '已就绪，点击生成 Autotile 图集'
                : '请在上方选择 1 张 Background 和 1 张 Surface 材质';
        }
    },

    // ── 图集页面: 获取当前选择 ──

    getAtlasSelection() {
        return {
            bgId: this.state.atlasSelectedBgId,
            sfId: this.state.atlasSelectedSfId,
        };
    },

    getTileSize() {
        return parseInt(this.elements.tileSize?.value || '32');
    },

    // ── 材质状态追踪 ──

    addMaterial(id, name, url) {
        if (this.state.materials.find(m => m.id === id)) return;
        this.state.materials.push({ id, name, url });
    },

    setMaterialType(id, type) {
        this.state.materialTypes[id] = type;
    },

    // ── Surface 模式背景图选择器 ──

    async loadBackgroundMaterials() {
        try {
            // 从材质库 (ComfyUI 输出目录) 加载所有 Background
            const resp = await fetch('/api/generate/comfy-outputs?prefix=tgen-background');
            const data = await resp.json();
            
            const materials = (data.images || []).map(img => ({
                id: img.filename, // 必须传文件名，后端才能直接通过文件查找
                image_url: img.url
            }));
            this._renderBgSelector(materials);
        } catch (e) {
            console.error('加载背景材质列表失败:', e);
        }
    },

    _renderBgSelector(materials) {
        const grid = this.elements.bgSelectorGrid;
        grid.innerHTML = '';

        if (materials.length === 0) {
            grid.innerHTML = '<p class="placeholder-text">尚未生成任何 Background 纹理</p>';
            return;
        }

        materials.forEach(mat => {
            const card = document.createElement('div');
            card.className = 'bg-selector-card';
            card.dataset.bgId = mat.id;
            card.title = mat.id;

            if (mat.id === this.state.surfaceSelectedBgId) {
                card.classList.add('selected');
            }

            card.innerHTML = `<img src="${mat.image_url}" alt="${mat.id}" loading="lazy">`;

            card.addEventListener('click', () => {
                if (this.state.surfaceSelectedBgId === mat.id) {
                    this.state.surfaceSelectedBgId = null;
                } else {
                    this.state.surfaceSelectedBgId = mat.id;
                }
                this._renderBgSelector(materials);
            });

            grid.appendChild(card);
        });
    },

    // ── 模型选择 ──

    getModelSelection() {
        return {
            checkpoint: this.elements.checkpointSelect?.value || null,
            lora: this.elements.loraSelect?.value || null,
        };
    },

    // ── 提示词 ──

    getCombinedPositivePrompt() {
        const systemPos = this.elements.systemPositivePrompt.value.trim();
        const material = this.elements.materialPrompt.value.trim();
        if (systemPos && material) {
            return systemPos + ', ' + material;
        }
        return systemPos + material;
    },

    getNegativePrompt() {
        return this.elements.systemNegativePrompt.value.trim() || null;
    },

    // ── 提示词历史 ──

    addPromptToHistory(prompt) {
        if (!prompt) return;
        // 如果已经存在，移到最前面
        const index = this.state.promptHistory.indexOf(prompt);
        if (index > -1) {
            this.state.promptHistory.splice(index, 1);
        }
        this.state.promptHistory.unshift(prompt);
        // 限制最多保存20条
        if (this.state.promptHistory.length > 20) {
            this.state.promptHistory.pop();
        }
        this._renderPromptHistory();
    },

    _renderPromptHistory() {
        if (!this.elements.promptHistoryList) return;
        this.elements.promptHistoryList.innerHTML = '';
        this.state.promptHistory.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p;
            this.elements.promptHistoryList.appendChild(opt);
        });
    },

    // ── 对话消息渲染 ──

    addMessage(role, content, msgId = null) {
        const id = msgId || `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.id = id;
        div.innerHTML = `<div class="message-content">${content}</div>`;
        this.elements.chatMessages.appendChild(div);
        this._scrollToBottom();
        return id;
    },

    addProgressMessage() {
        const id = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const div = document.createElement('div');
        div.className = 'message assistant';
        div.id = id;
        div.innerHTML = `
            <div class="message-content">
                <span class="progress-text">正在排队...</span>
                <div class="progress-bar">
                    <div class="progress-bar-fill" style="width: 0%"></div>
                </div>
            </div>
        `;
        this.elements.chatMessages.appendChild(div);
        this._scrollToBottom();
        return {
            msgId: id,
            progressBar: div.querySelector('.progress-bar-fill'),
            progressText: div.querySelector('.progress-text'),
            contentDiv: div.querySelector('.message-content'),
        };
    },

    updateProgress(msgId, percent, text) {
        const msg = document.getElementById(msgId);
        if (!msg) return;
        const bar = msg.querySelector('.progress-bar-fill');
        const txt = msg.querySelector('.progress-text');
        if (bar) bar.style.width = `${percent}%`;
        if (txt) txt.textContent = text;
    },

    completeProgressMessage(msgId, imageUrl, altText, extraHtml = '') {
        const msg = document.getElementById(msgId);
        if (!msg) return;
        const content = msg.querySelector('.message-content');
        if (!content) return;

        let imageHtml = '';
        if (imageUrl) {
            imageHtml = `<img src="${imageUrl}" alt="${altText}" class="message-image large" loading="lazy">`;
        }

        content.innerHTML = `
            <div>${altText}</div>
            ${imageHtml}
            ${extraHtml}
        `;
    },

    showImageModal(url) {
        if (!this.elements.imageModal || !this.elements.imageModalImg) return;
        this.elements.imageModalImg.src = url;
        this.elements.imageModal.classList.add('active');
    },

    _scrollToBottom() {
        const msgs = this.elements.chatMessages;
        setTimeout(() => {
            msgs.scrollTop = msgs.scrollHeight;
        }, 50);
    },
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => UI.init());
