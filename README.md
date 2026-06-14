# nekro_plugin_bilichat

> NekroAgent B站直播/动态推送插件，复刻 nonebot-plugin-bilichat 核心功能。

## 功能

- **直播推送**：订阅 UP 主后，自动推送开播/下播通知
- **动态推送**：自动推送 UP 主的新动态（图文、转发、视频投稿等）
- **AT 全体**：支持对特定 UP 的直播或动态开启 AT 全体成员
- **WebUI 管理**：提供可视化管理界面，可查看/管理订阅、修改推送配置
- **富文本推送**：开播推送封面图，动态推送截图

## 配置说明

### bilichat-request API

插件依赖 [bilichat-request](https://github.com/KroMiose/bilichat-request) 提供 B站 API 数据。
部署 bilichat-request 后，在插件配置中设置 API 地址和 Token。

### 插件配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| API_URL | http://192.168.1.102:40432 | bilichat-request 服务地址 |
| API_TOKEN | - | API 访问 Token |
| LIVE_INTERVAL | 60 | 直播状态检查间隔（秒） |
| DYNAMIC_INTERVAL | 300 | 动态检查间隔（秒） |
| BROWSER_SHOT_QUALITY | 75 | 动态截图质量 (10-100) |
| USE_RICH_MEDIA | true | 是否使用富文本推送（含图片） |

## 使用命令

所有命令以 /bilichat 为前缀，在 QQ 群/频道中使用：

| 命令 | 说明 | 示例 |
|------|------|------|
| /bilichat sub <名称> | 订阅 UP 主 | /bilichat sub 泠鸢yousa |
| /bilichat unsub <名称/UID> | 取消订阅 | /bilichat unsub 泠鸢yousa |
| /bilichat unsub all | 取消全部订阅 | /bilichat unsub all |
| /bilichat check | 查看当前频道订阅 | /bilichat check |
| /bilichat atall <名称> live on | 开启直播 AT 全体 | /bilichat atall 泠鸢yousa live on |
| /bilichat atall <名称> live off | 关闭直播 AT 全体 | /bilichat atall 泠鸢yousa live off |

## WebUI 管理界面

访问 /plugins/nekro_plugin_bilichat/bilichat/ 打开管理面板。

提供以下功能：
- 添加/删除订阅
- 查看所有频道的订阅状态
- 修改推送配置
- 查看 UP 主播运行状态

## 推送消息格式

开播: {主播名称} 开播了: {标题} + 封面图 + 直播链接
下播: {主播名称} 下播了 + 直播时长
动态: {主播名称} 发布了新动态 + 截图 + 短链接

> 若关闭富文本推送，则不发送图片，只发送纯文本。

## 数据存储

订阅数据: {DATA_DIR}/plugins/nekro_plugin_bilichat/subscriptions.json

## 依赖

- nekro-agent >= 2.0.0
- httpx >= 0.27.0
- pydantic >= 2.0.0
- fastapi >= 0.104.0
- [bilichat-request](https://github.com/KroMiose/bilichat-request)（独立部署）

## 许可

MIT
