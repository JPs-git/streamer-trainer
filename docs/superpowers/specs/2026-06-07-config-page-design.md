# 前端配置页面设计

## 背景

为 streamer-trainer 添加一个独立的前端配置页面，与现有弹幕显示页面分离，允许用户通过 Web UI 修改系统配置并持久化。

## 文件结构

```
frontend/
├── index.html      ← 弹幕显示（不变）
├── config.html     ← 新增：配置页面
├── config.js       ← 新增：配置页逻辑
└── style.css       ← 追加配置页样式

backend/
└── main.py         ← 新增 GET/POST /api/config, POST /api/config/reset

config.default.yaml ← 新增：出厂默认配置
```

## 后端 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/config` | 返回当前配置（JSON），API key 返回 masked 值 |
| `POST` | `/api/config` | 接收新配置，写回 `config.yaml`，触发重启 |
| `POST` | `/api/config/reset` | 用 `config.default.yaml` 覆盖 `config.yaml` 后重启 |

### GET /api/config 响应格式

```json
{
  "llm": {
    "base_url": "https://api.moonshot.cn/v1",
    "api_key": "sk-****abcd"
  },
  "viewer": {
    "min_active": 3,
    "max_active": 8,
    "entry_interval_sec": 180,
    "cooldown_sec": 300,
    "tick_interval_sec": 15,
    "engagement_threshold": 20
  }
}
```

### POST /api/config 请求格式

```json
{
  "llm": {
    "base_url": "https://api.moonshot.cn/v1",
    "api_key": "sk-xxx..."
  },
  "viewer": {
    "min_active": 5,
    "max_active": 10,
    "entry_interval_sec": 120,
    "cooldown_sec": 240,
    "tick_interval_sec": 10,
    "engagement_threshold": 15
  }
}
```

API key 只在用户显式提交新值时更新；如果提交 masked 值（"sk-****abcd"）则保留原值。

### 自动重启机制

- uvicorn `reload=True` + `reload_includes=["config.yaml"]`
- `POST /api/config` 写文件后 uvicorn 检测到 `config.yaml` 变更自动重启
- 前端 WS 重连逻辑已有，重启后会自动恢复连接

## 配置页面布局

- 标题栏："系统配置" + 导航到弹幕页面的链接
- LLM 分组：base_url 输入框，API key 输入框
- 观众分组：每个参数一个带 label 的数字输入框（含 min/max/step）
- 底部操作按钮：保存 | 恢复默认

## 可配置项

| 分组 | 配置键 | 类型 | 默认值 | 范围 |
|------|--------|------|--------|------|
| LLM | base_url | string | https://api.moonshot.cn/v1 | - |
| LLM | api_key | string (password) | - | - |
| 观众 | min_active | int | 3 | 0~20 |
| 观众 | max_active | int | 8 | 1~50 |
| 观众 | entry_interval_sec | int | 180 | 10~600 |
| 观众 | cooldown_sec | int | 300 | 10~3600 |
| 观众 | tick_interval_sec | int | 15 | 3~120 |
| 观众 | engagement_threshold | int | 20 | 1~100 |

## 错误处理

- 配置验证由后端实现，前端显示错误消息
- 写文件失败 / 重启前返回错误给前端
- 前端保存按钮 disabled 状态直到请求完成

## 依赖变更

- 无新增 Python 依赖（已有 yaml/pyyaml）
- 配置文件写回使用 `yaml.safe_dump`
