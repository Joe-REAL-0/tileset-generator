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

        // 清空材质输入
        UI.elements.materialPrompt.value = '';

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

                UI.completeProgressMessage(
                    progress.msgId, imageUrl,
                    `${emoji} ${typeLabel} <b>"${name}"</b> 已生成! (512×512)`,
                    '<div style="margin-top:6px;font-size:0.8rem;color:var(--text-secondary)">可在「材质库」和「生成图集」页面中使用此材质</div>'
                );

                // 记录材质状态
                UI.addMaterial(taskId, name, imageUrl);
                UI.setMaterialType(taskId, type);

                // 刷新 Surface 模式的背景图选择器
                if (type === 'background') {
                    UI.loadBackgroundMaterials();
                }
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

    // ── 生成 Autotile (从图集页面) ──

    async generateTileset() {
        const { bgId, sfId } = UI.getAtlasSelection();
        const tileSize = UI.getTileSize();

        if (!bgId || !sfId) {
            UI.addMessage('system', '⚠️ 请先选择 Background 和 Surface 材质');
            return;
        }

        const bgName = UI.state.materials.find(m => m.id === bgId)?.name || bgId;
        const sfName = UI.state.materials.find(m => m.id === sfId)?.name || sfId;

        UI.addMessage('user', `🧩 生成 Autotile: BG=<b>${bgName}</b> + Surface=<b>${sfName}</b> (${tileSize}px)`);

        const progress = UI.addProgressMessage();
        UI.updateProgress(progress.msgId, 5, '提交 autotile 合成任务...');

        try {
            const resp = await fetch('/api/tileset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    background_image_id: bgId,
                    surface_image_id: sfId,
                    tile_size: tileSize,
                }),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || '请求失败');
            }

            const data = await resp.json();
            const taskId = data.task_id;

            wsClient.connect(
                taskId,
                (msg) => {
                    UI.updateProgress(progress.msgId, msg.progress || 0, msg.message || '处理中...');

                    if (msg.status === 'completed') {
                        wsClient.disconnect();
                        Chat._displayTileset(progress, msg);
                    } else if (msg.status === 'failed') {
                        UI.completeProgressMessage(
                            progress.msgId, null,
                            `❌ Autotile 合成失败: ${msg.error || '未知错误'}`
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

    _displayTileset(progress, msg) {
        const imageUrl = msg.image_url;
        const meta = msg.metadata || {};

        const metaHtml = meta.tile_count ? `
            <table class="meta-table">
                <tr><td>Tile 数量</td><td>${meta.tile_count}</td></tr>
                <tr><td>Tile 尺寸</td><td>${meta.tile_size}×${meta.tile_size} px</td></tr>
                <tr><td>网格</td><td>${meta.columns}×${meta.rows}</td></tr>
                <tr><td>图集尺寸</td><td>${meta.image_size?.join('×')} px</td></tr>
            </table>
        ` : '';

        if (imageUrl) {
            UI.completeProgressMessage(
                progress.msgId,
                imageUrl,
                `✅ <b>47-Tile Autotile 图集合成完成!</b> (${meta.tile_size || '?'}px)`,
                `
                ${metaHtml}
                <a href="${imageUrl}" download class="download-link">📥 下载 Autotile 图集</a>
                `
            );
        } else {
            UI.completeProgressMessage(
                progress.msgId,
                null,
                `✅ Autotile 合成完成! 请通过 API 获取结果。`,
                metaHtml
            );
        }
    },
};
