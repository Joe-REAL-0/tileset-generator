// src/static/js/ws.js
// WebSocket 客户端封装
// 职责: 管理与服务端的 WebSocket 连接, 接收生成进度推送
//   - connect(task_id): 连接指定任务的 WebSocket 端点
//   - onMessage 回调: 将服务端推送的状态消息分发给 UI 层
//   - 自动处理 ping/pong 心跳保持连接活跃
//   - 任务完成后自动关闭连接

class WSClient {
    constructor() {
        /** @type {WebSocket|null} */
        this.ws = null;
        /** @type {string|null} */
        this.currentTaskId = null;
        /** @type {Function|null} */
        this.onMessage = null;
        /** @type {Function|null} */
        this.onClose = null;
        /** @type {number} */
        this.pingInterval = null;
    }

    /**
     * 连接到指定 task_id 的 WebSocket 进度推送
     * @param {string} taskId
     * @param {Function} onMessage - (data: object) => void
     * @param {Function} onClose - () => void
     */
    connect(taskId, onMessage, onClose) {
        // 先断开旧连接
        this.disconnect();

        this.currentTaskId = taskId;
        this.onMessage = onMessage;
        this.onClose = onClose;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws/${taskId}`;

        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            console.log(`[WS] 已连接: ${taskId}`);
            // 启动心跳 (每 30 秒发送 ping)
            this.pingInterval = setInterval(() => {
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send('ping');
                }
            }, 30000);
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'pong') return;  // 忽略心跳回复
                if (this.onMessage) {
                    this.onMessage(data);
                }
            } catch (e) {
                console.error('[WS] 消息解析失败:', e);
            }
        };

        this.ws.onerror = (error) => {
            console.error('[WS] 连接错误:', error);
        };

        this.ws.onclose = () => {
            console.log(`[WS] 连接关闭: ${taskId}`);
            this._cleanup();
            if (this.onClose) {
                this.onClose();
            }
        };
    }

    /** 断开当前 WebSocket 连接 */
    disconnect() {
        this._cleanup();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.currentTaskId = null;
    }

    /** 清理心跳定时器 */
    _cleanup() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }
}

// 全局单例
const wsClient = new WSClient();
