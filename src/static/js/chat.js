// src/static/js/chat.js
// 对话逻辑
// 职责: 协调用户输入、API 调用、WebSocket 连接和 UI 更新
//   - generateTexture(): 根据当前模式 (background/surface) 提交生成任务
//   - generateTileset():  提交 Autotile 合成任务 (从图集页面选择)
//   - WebSocket 进度推送 → 实时更新对话区

const Chat = {
    // ── 通用: 生成纹理 (Background 或 Surface) ──

    async generateTexture() {
        const mode = UI.state.generationMode;
        const materialPrompt = UI.elements.materialPrompt.value.trim();
        const combinedPrompt = UI.getCombinedPositivePrompt();
        const negativePrompt = UI.getNegativePrompt();
        const { checkpoint, lora } = UI.getModelSelection();
        const bgImageId = (mode === 'surface') ? UI.state.surfaceSelectedBgId : null;
        const surfaceTolerance = UI.elements.surfaceTolerance ? parseInt(UI.elements.surfaceTolerance.value, 10) : null;

        const emoji = mode === 'background' ? '🎨' : '🖌️';
        const typeLabel = mode === 'background' ? 'Background' : 'Surface';
        const shortName = materialPrompt.length > 24
            ? materialPrompt.substring(0, 24) + '...'
            : materialPrompt;

        // 记录历史提示词
        UI.addPromptToHistory(materialPrompt);
        // 不再清空材质输入，保留供用户反复生成
        // UI.elements.materialPrompt.value = '';

        // 用户消息
        let userMsg = `${emoji} 生成 ${typeLabel}: <b>${shortName}</b>`;
        if (bgImageId) {
            userMsg += ` (基于背景: ${bgImageId})`;
        }
        UI.addMessage('user', userMsg);

        // 如果是生成 background，提醒用户等待时间
        if (mode === 'background') {
            UI.addMessage('system', '⏳ 提示：由于设备性能不同，Background 纹理生成大约需要 1 到 2 分钟，请耐心等待...');
        }

        // 进度消息
        const progress = UI.addProgressMessage();
        UI.updateProgress(progress.msgId, 5, `正在提交 ${typeLabel} 生成任务...`);

        try {
            const body = {
                prompt: combinedPrompt,
                negative_prompt: negativePrompt,
                seed: -1,
                generate_type: mode,
                checkpoint: checkpoint,
                lora: lora,
            };

            if (mode === 'surface' && bgImageId) {
                body.background_image_id = bgImageId;
                if (!isNaN(surfaceTolerance) && surfaceTolerance !== null) {
                    body.surface_background_tolerance = surfaceTolerance;
                }
            }

            const resp = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || '请求失败');
            }

            const data = await resp.json();
            const taskId = data.task_id;

            UI.updateProgress(progress.msgId, 10, 'SD 正在生成中...');

            // WebSocket 跟踪进度
            wsClient.connect(
                taskId,
                (msg) => {
                    if (msg.status === 'generating') {
                        UI.updateProgress(progress.msgId, msg.progress || 0, msg.message || 'SD 采样中...');
                    } else if (msg.status === 'completed') {
                        Chat._fetchAndDisplayImage(taskId, shortName, progress, mode);
                    } else if (msg.status === 'failed') {
                        UI.completeProgressMessage(
                            progress.msgId, null,
                            `❌ ${typeLabel} 生成失败: ${msg.error || '未知错误'}`
                        );
                        wsClient.disconnect();
                    }
                },
                () => { }
            );
        } catch (e) {
            UI.completeProgressMessage(
                progress.msgId, null,
                `❌ 请求失败: ${e.message}`
            );
        }
    },

    // ── 获取并显示生成结果 ──

    async _fetchAndDisplayImage(taskId, name, progress, type) {
        try {
            const resp = await fetch(`/api/generate/${taskId}`);
            const data = await resp.json();

            if (data.status === 'completed' && data.image_urls && data.image_urls.length > 0) {
                const imageUrl = data.image_urls[0];

                const typeLabel = type === 'background' ? 'Background' : 'Surface';
                const emoji = type === 'background' ? '🎨' : '🖌️';

                let extraControls = '';
                if (type === 'surface') {
                    const defaultTol = UI.elements.surfaceTolerance ? UI.elements.surfaceTolerance.value : 32;
                    extraControls = `
                        <div class="surface-adjust" style="margin-top: 10px; display: flex; align-items: center; gap: 10px; background: rgba(0,0,0,0.05); padding: 8px; border-radius: 4px;">
                            <label style="font-size: 0.9rem;">容差重新去背: <span id="tol_val_${taskId}">${defaultTol}</span></label>
                            <input type="range" min="0" max="255" value="${defaultTol}" oninput="document.getElementById('tol_val_${taskId}').textContent = this.value">
                            <button class="btn btn-accent btn-sm" onclick="Chat.adjustTolerance('${taskId}', this.previousElementSibling.value, this)">更新预览</button>
                        </div>
                    `;
                }

                const actionHtml = `
                    ${extraControls}
                    <div class="material-actions" style="margin-top: 10px; display: flex; gap: 10px;">
                        <button class="btn btn-success btn-sm" onclick="Chat.saveMaterial('${taskId}', '${name}', '${type}', this)">💾 保存</button>
                        <button class="btn btn-danger btn-sm" onclick="Chat.discardMaterial('${taskId}', this)">🗑️ 丢弃</button>
                    </div>
                `;

                UI.completeProgressMessage(
                    progress.msgId, imageUrl,
                    `${emoji} ${typeLabel} <b>"${name}"</b> 预览生成成功! (未保存)`,
                    actionHtml
                );

                // 等待用户手动保存后，再添加到材质库和背景图选择器中
            } else if (data.status === 'failed') {
                UI.completeProgressMessage(
                    progress.msgId, null,
                    `❌ 生成失败: ${data.error || '未知错误'}`
                );
            }
        } catch (e) {
            UI.completeProgressMessage(
                progress.msgId, null,
                `❌ 获取结果失败: ${e.message}`
            );
        } finally {
            wsClient.disconnect();
        }
    },

    async saveMaterial(taskId, name, type, btnEl) {
        try {
            const resp = await fetch(`/api/generate/${taskId}/save`, { method: 'POST' });
            if (!resp.ok) throw new Error('保存失败');

            const actionsDiv = btnEl.parentElement;
            const contentDiv = actionsDiv.parentElement;
            const imgEl = contentDiv.querySelector('img.message-image');
            const finalImageUrl = imgEl ? imgEl.src : '';

            // hide adjust controls if it's surface
            const adjustDiv = contentDiv.querySelector('.surface-adjust');
            if (adjustDiv) {
                adjustDiv.style.display = 'none';
            }

            actionsDiv.innerHTML = '<span style="color: var(--success-color); font-size: 0.9rem;">✅ 已保存，可在「材质库」中使用</span>';

            // 记录材质状态
            UI.addMaterial(taskId, name, finalImageUrl);
            UI.setMaterialType(taskId, type);

            // 刷新 Surface 模式的背景图选择器
            if (type === 'background') {
                UI.loadBackgroundMaterials();
            }
        } catch (e) {
            UI.addMessage('system', `❌ 保存失败: ${e.message}`);
        }
    },

    async discardMaterial(taskId, btnEl) {
        try {
            const resp = await fetch(`/api/generate/${taskId}/discard`, { method: 'POST' });
            if (!resp.ok) throw new Error('丢弃失败');

            const actionsDiv = btnEl.parentElement;
            actionsDiv.innerHTML = '<span style="color: var(--danger-color); font-size: 0.9rem;">🗑️ 已丢弃</span>';

            // 使图片变灰，表明已不可用
            const contentDiv = actionsDiv.parentElement;

            const adjustDiv = contentDiv.querySelector('.surface-adjust');
            if (adjustDiv) {
                adjustDiv.style.display = 'none';
            }

            const imgEl = contentDiv.querySelector('img.message-image');
            if (imgEl) {
                imgEl.style.opacity = '0.4';
                imgEl.style.filter = 'grayscale(100%)';
            }
        } catch (e) {
            UI.addMessage('system', `❌ 丢弃失败: ${e.message}`);
        }
    },

    async adjustTolerance(taskId, tolerance, btnEl) {
        const originalText = btnEl.textContent;
        btnEl.disabled = true;
        btnEl.textContent = '计算中...';
        try {
            const resp = await fetch(`/api/generate/${taskId}/reprocess`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tolerance: parseInt(tolerance, 10) })
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || '重新计算失败');
            }
            const data = await resp.json();

            const contentDiv = btnEl.closest('.message-content') || btnEl.parentElement.parentElement;
            if (contentDiv) {
                let imgEl = contentDiv.querySelector('img.message-image') || contentDiv.querySelector('img');

                // 终极兜底方案：在整个文档里找包含这个 taskId 的图片
                if (!imgEl) {
                    imgEl = document.querySelector(`img[src*="${taskId}"]`);
                }

                if (imgEl) {
                    imgEl.src = data.image_url;
                } else {
                    UI.addMessage('system', `❌ 错误: 找不到图片元素。DOM内容: ${contentDiv.innerHTML.substring(0, 100)}...`);
                }
            } else {
                UI.addMessage('system', '❌ 错误: 找不到消息框元素');
            }
        } catch (e) {
            UI.addMessage('system', `❌ 重新处理失败: ${e.message}`);
        } finally {
            btnEl.disabled = false;
            btnEl.textContent = originalText;
        }
    },

    async generateTileset() {
        const { bgId, sfId } = UI.getAtlasSelection();
        const tileSize = UI.getTileSize();

        if (!bgId || !sfId) {
            UI.addMessage('system', '⚠️ 请先选择 Background 和 Surface 材质');
            return;
        }

        const bgName = bgId;
        const sfName = sfId;

        // 生成过程中禁用按钮并更改文本
        if (UI.elements.btnTileset) {
            UI.elements.btnTileset.disabled = true;
            UI.elements.btnTileset.textContent = '⏳ 生成中...';
        }

        const restoreButton = () => {
            if (UI.elements.btnTileset) {
                UI.elements.btnTileset.textContent = '🧩 生成 Autotile';
                UI.updateTilesetButton();
            }
        };

        UI.addMessage('user', `🧩 生成 Autotile: BG=<b>${bgName}</b> + Surface=<b>${sfName}</b> (${tileSize}px)`);

        const progress = UI.addProgressMessage();
        UI.updateProgress(progress.msgId, 5, '正在提交图集生成任务...');

        try {
            const resp = await fetch('/api/tileset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    background_image_id: bgName,
                    surface_image_id: sfName,
                    tile_size: tileSize
                }),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || '请求失败');
            }

            const data = await resp.json();
            const taskId = data.task_id;

            UI.updateProgress(progress.msgId, 10, '正在生成图集...');

            // WebSocket 跟踪进度
            wsClient.connect(
                taskId,
                (msg) => {
                    if (msg.status === 'processing' || msg.status === 'composing' || msg.status === 'loading') {
                        UI.updateProgress(progress.msgId, msg.progress || 0, msg.message || '处理中...');
                    } else if (msg.status === 'completed') {
                        // 在对话框里显示结果
                        UI.completeProgressMessage(
                            progress.msgId, msg.image_url,
                            `✅ ${msg.message || '图集生成完成!'}`,
                            `<a href="${msg.image_url}" download class="btn btn-success btn-sm" style="margin-top:8px;display:inline-block;">⬇️ 下载图集</a>`
                        );

                        // 更新生成图集页面的展示区并滚动
                        UI.loadTilesets().then(() => {
                            const grid = document.getElementById('atlasResultGrid');
                            if (grid) {
                                grid.scrollIntoView({ behavior: 'smooth', block: 'end' });
                            }
                        });

                        // 全屏展示图片
                        UI.showImageModal(msg.image_url);

                        restoreButton();
                        wsClient.disconnect();
                    } else if (msg.status === 'failed') {
                        UI.completeProgressMessage(
                            progress.msgId, null,
                            `❌ 图集生成失败: ${msg.error || '未知错误'}`
                        );
                        restoreButton();
                        wsClient.disconnect();
                    }
                },
                () => {
                    restoreButton();
                }
            );

        } catch (e) {
            UI.completeProgressMessage(
                progress.msgId, null,
                `❌ 请求失败: ${e.message}`
            );
            restoreButton();
        }
    },
};
