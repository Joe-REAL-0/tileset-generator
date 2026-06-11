// src/static/js/ui.js
// UI 交互逻辑
// 职责: 管理前端 UI 状态与用户交互
//   - 已生成材质列表的渲染与选择 (单击选 Background, 双击选 Surface)
//   - 两个按钮事件绑定与启用/禁用逻辑
//   - 对话消息的 DOM 操作 (添加消息、更新进度条、渲染图片)
//   - Tile 尺寸选择器

const UI = {
    // ── DOM 引用 ──
    elements: {
        promptInput: document.getElementById('promptInput'),
        btnGenerate: document.getElementById('btnGenerate'),
        btnTileset: document.getElementById('btnTileset'),
        tileSize: document.getElementById('tileSize'),
        chatMessages: document.getElementById('chatMessages'),
        materialList: document.getElementById('materialList'),
        selectedBg: document.getElementById('selectedBg'),
        selectedSf: document.getElementById('selectedSf'),
    },

    // ── 状态 ──
    state: {
        /** @type {Array<{id: string, name: string, url: string}>} */
        materials: [],
        /** @type {string|null} */
        selectedBgId: null,
        /** @type {string|null} */
        selectedSfId: null,
        /** @type {string|null} */
        activeTaskId: null,
    },

    // ── 初始化 ──
    init() {
        this.bindEvents();
    },

    bindEvents() {
        const { btnGenerate, btnTileset, promptInput } = this.elements;

        // 按钮1: 生成材质
        btnGenerate.addEventListener('click', () => {
            const prompt = promptInput.value.trim();
            if (!prompt) return;
            Chat.generateMaterial(prompt);
        });

        // 按钮2: 生成 Autotile
        btnTileset.addEventListener('click', () => {
            Chat.generateTileset();
        });

        // Enter 键快捷发送
        promptInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                btnGenerate.click();
            }
        });

        // 自动更新按钮状态
        this.updateTilesetButton();
    },

    // ── 材质列表管理 ──

    /**
     * 添加新生成的材质到侧边栏
     * @param {string} id - 材质 ID
     * @param {string} name - 用户输入的提示词 (截取作为名称)
     * @param {string} url - 图片 URL
     */
    addMaterial(id, name, url) {
        this.state.materials.push({ id, name, url });
        this.renderMaterialList();
    },

    /** 渲染侧边栏材质列表 */
    renderMaterialList() {
        const list = this.elements.materialList;
        list.innerHTML = '';

        if (this.state.materials.length === 0) {
            list.innerHTML = '<p class="placeholder-text">尚未生成任何材质</p>';
            return;
        }

        this.state.materials.forEach((mat) => {
            const card = document.createElement('div');
            card.className = 'material-card';
            card.dataset.id = mat.id;

            if (mat.id === this.state.selectedBgId) {
                card.classList.add('selected-bg');
            }
            if (mat.id === this.state.selectedSfId) {
                card.classList.add('selected-sf');
            }

            card.innerHTML = `
                <img src="${mat.url}" alt="${mat.name}" loading="lazy">
                <div class="card-name">${mat.name}</div>
                ${mat.id === this.state.selectedBgId ? '<span class="card-badge badge-bg">BG</span>' : ''}
                ${mat.id === this.state.selectedSfId ? '<span class="card-badge badge-sf">SF</span>' : ''}
            `;

            // 单击选为 Background，再次单击选为 Surface
            card.addEventListener('click', () => this.selectMaterial(mat.id));

            list.appendChild(card);
        });
    },

    /**
     * 材质选择逻辑:
     *   - 首次单击 → 选为 Background
     *   - 该材质已是 Background → 切换为 Surface
     *   - 该材质已是 Surface → 取消选择
     */
    selectMaterial(id) {
        if (this.state.selectedBgId === id) {
            // 当前是 BG → 切换为 Surface
            this.state.selectedBgId = null;
            this.state.selectedSfId = id;
        } else if (this.state.selectedSfId === id) {
            // 当前是 Surface → 取消
            this.state.selectedSfId = null;
        } else if (!this.state.selectedBgId) {
            // 未选 BG → 选为 BG
            this.state.selectedBgId = id;
        } else if (!this.state.selectedSfId) {
            // 已有 BG 无 SF → 选为 SF
            this.state.selectedSfId = id;
        } else {
            // 两者都已有 → 替换 BG
            this.state.selectedBgId = id;
            this.state.selectedSfId = null;
        }

        this.renderMaterialList();
        this.updateSelectionInfo();
        this.updateTilesetButton();
    },

    updateSelectionInfo() {
        const { selectedBg, selectedSf } = this.elements;
        const findName = (id) => {
            const mat = this.state.materials.find(m => m.id === id);
            return mat ? mat.name : '未选择';
        };
        selectedBg.textContent = findName(this.state.selectedBgId);
        selectedSf.textContent = findName(this.state.selectedSfId);
    },

    /** 生成 Autotile 按钮启用条件: BG 和 SF 均已选择 */
    updateTilesetButton() {
        this.elements.btnTileset.disabled = !(
            this.state.selectedBgId && this.state.selectedSfId
        );
    },

    // ── 对话消息渲染 ──

    /**
     * 添加消息到对话区域
     * @param {'user'|'assistant'|'system'} role
     * @param {string} content - HTML 内容
     * @param {string|null} msgId - 消息 ID (用于后续更新)
     * @returns {string} msgId
     */
    addMessage(role, content, msgId = null) {
        const id = msgId || `msg_${Date.now()}`;
        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.id = id;
        div.innerHTML = `<div class="message-content">${content}</div>`;
        this.elements.chatMessages.appendChild(div);
        this._scrollToBottom();
        return id;
    },

    /**
     * 添加带进度条的消息, 返回进度条元素引用
     * @returns {{ msgId: string, progressBar: HTMLElement, progressText: HTMLElement }}
     */
    addProgressMessage() {
        const id = `msg_${Date.now()}`;
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

    /**
     * 更新进度消息
     */
    updateProgress(msgId, percent, text) {
        const msg = document.getElementById(msgId);
        if (!msg) return;
        const bar = msg.querySelector('.progress-bar-fill');
        const txt = msg.querySelector('.progress-text');
        if (bar) bar.style.width = `${percent}%`;
        if (txt) txt.textContent = text;
    },

    /**
     * 将进度消息替换为完成的图片 + 信息
     */
    completeProgressMessage(msgId, imageUrl, altText, extraHtml = '') {
        const msg = document.getElementById(msgId);
        if (!msg) return;
        const content = msg.querySelector('.message-content');
        if (!content) return;

        content.innerHTML = `
            <div>${altText}</div>
            <img src="${imageUrl}" alt="${altText}" class="message-image large" loading="lazy">
            ${extraHtml}
        `;
    },

    _scrollToBottom() {
        const msgs = this.elements.chatMessages;
        setTimeout(() => {
            msgs.scrollTop = msgs.scrollHeight;
        }, 50);
    },

    /** 获取当前选中的 Tile 尺寸 */
    getTileSize() {
        return parseInt(this.elements.tileSize.value);
    },
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => UI.init());
