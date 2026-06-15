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
                () => {}
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

                const actionHtml = `
                    <div class="material-actions" style="margin-top: 10px; display: flex; gap: 10px;">
                        <button class="btn btn-success btn-sm" onclick="Chat.saveMaterial('${taskId}', '${name}', '${imageUrl}', '${type}', this)">💾 保存</button>
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

    async saveMaterial(taskId, name, imageUrl, type, btnEl) {
        try {
            const resp = await fetch(`/api/generate/${taskId}/save`, { method: 'POST' });
            if (!resp.ok) throw new Error('保存失败');
            
            const actionsDiv = btnEl.parentElement;
            actionsDiv.innerHTML = '<span style="color: var(--success-color); font-size: 0.9rem;">✅ 已保存，可在「材质库」中使用</span>';
            
            // 记录材质状态
            UI.addMaterial(taskId, name, imageUrl);
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
            const imgEl = contentDiv.querySelector('img.message-image');
            if (imgEl) {
                imgEl.style.opacity = '0.4';
                imgEl.style.filter = 'grayscale(100%)';
            }
        } catch (e) {
            UI.addMessage('system', `❌ 丢弃失败: ${e.message}`);
        }
    },

    async generateTileset() {
        const { bgId, sfId } = UI.getAtlasSelection();
        const tileSize = UI.getTileSize();

        if (!bgId || !sfId) {
            UI.addMessage('system', '⚠️ 请先选择 Background 和 Surface 材质');
            return;
        }

        const bgName = bgId; // UI._renderAtlasGrid now uses filenames directly
        const sfName = sfId;

        UI.addMessage('user', `🧩 生成 Autotile: BG=<b>${bgName}</b> + Surface=<b>${sfName}</b> (${tileSize}px)`);

        const progress = UI.addProgressMessage();
        UI.updateProgress(progress.msgId, 100, '完成');
        UI.completeProgressMessage(
            progress.msgId, null,
            `✅ 已记录图集生成任务。`,
            `
            <div style="color:var(--accent-blue);font-weight:bold;margin-top:8px;">
                TODO: 图集生成的具体逻辑暂时没开发完成，敬请期待！
            </div>
            `
        );
    },
};
