// src/static/js/chat.js
// 对话逻辑
// 职责: 协调用户输入、API 调用、WebSocket 连接和 UI 更新
//   - generateMaterial():  处理 "生成材质" 按钮 → POST /api/generate → WS 跟踪进度
//   - generateTileset():   处理 "生成 Autotile" 按钮 → POST /api/tileset → WS 跟踪进度
//   - 将服务端 WebSocket 推送的状态更新渲染到对话区

const Chat = {
    // ── 生成材质 (按钮1) ──

    async generateMaterial(prompt) {
        const input = UI.elements.promptInput;
        const name = prompt.length > 20 ? prompt.substring(0, 20) + '...' : prompt;
        input.value = '';
        input.focus();

        // 用户消息
        UI.addMessage('user', `生成材质: <b>${name}</b>`);

        // 助手进度消息
        const progress = UI.addProgressMessage();
        UI.updateProgress(progress.msgId, 5, '正在提交任务...');

        try {
            const resp = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: prompt,
                    negative_prompt: null,
                    seed: -1,
                }),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || '请求失败');
            }

            const data = await resp.json();
            const taskId = data.task_id;

            UI.updateProgress(progress.msgId, 10, 'SD 正在生成...');

            // 通过 WebSocket 跟踪进度
            wsClient.connect(
                taskId,
                // onMessage
                (msg) => {
                    if (msg.status === 'generating') {
                        UI.updateProgress(progress.msgId, 30 + Math.floor(msg.progress * 0.5), 'SD 采样中...');
                    } else if (msg.status === 'completed') {
                        UI.updateProgress(progress.msgId, 90, '生成完成!');
                        // 获取 image_paths 并显示
                        Chat._fetchAndDisplayImage(taskId, name, progress);
                    } else if (msg.status === 'failed') {
                        UI.completeProgressMessage(
                            progress.msgId, null,
                            `❌ 生成失败: ${msg.error || '未知错误'}`
                        );
                        wsClient.disconnect();
                    }
                },
                // onClose
                () => {}
            );
        } catch (e) {
            UI.completeProgressMessage(
                progress.msgId, null,
                `❌ 请求失败: ${e.message}`
            );
        }
    },

    async _fetchAndDisplayImage(taskId, name, progress) {
        try {
            const resp = await fetch(`/api/generate/${taskId}`);
            const data = await resp.json();

            if (data.status === 'completed' && data.image_paths && data.image_paths.length > 0) {
                // 构建图片 URL (通过 output 静态目录)
                const relativePath = data.image_paths[0];
                const filename = relativePath.split('/').pop();
                const imageUrl = `/output/textures/${filename}`;

                UI.completeProgressMessage(
                    progress.msgId, imageUrl,
                    `✅ 材质 <b>"${name}"</b> 已生成! (512×512)`,
                    '<div style="margin-top:6px;font-size:0.8rem;color:var(--text-secondary)">点击侧边栏选择为 Background 或 Surface</div>'
                );

                // 添加到已生成材质列表
                UI.addMaterial(`gen_${taskId.split('_').pop()}`, name, imageUrl);
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

    // ── 生成 Autotile (按钮2) ──

    async generateTileset() {
        const bgId = UI.state.selectedBgId;
        const sfId = UI.state.selectedSfId;
        const tileSize = UI.getTileSize();

        if (!bgId || !sfId) {
            UI.addMessage('system', '⚠️ 请先选择 1 张 Background 和 1 张 Surface 材质');
            return;
        }

        const bgName = UI.state.materials.find(m => m.id === bgId)?.name || bgId;
        const sfName = UI.state.materials.find(m => m.id === sfId)?.name || sfId;

        // 用户消息
        UI.addMessage('user', `生成 Autotile: BG=<b>${bgName}</b> + Surface=<b>${sfName}</b> (${tileSize}px)`);

        // 进度消息
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

            // WebSocket 跟踪进度
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

        // 元数据 HTML
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
            // 从 tileset URL 获取 (通过 REST)
            UI.completeProgressMessage(
                progress.msgId,
                null,
                `✅ Autotile 合成完成! 请通过 API 获取结果。`,
                metaHtml
            );
        }
    },
};
