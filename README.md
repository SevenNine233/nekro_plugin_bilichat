# NekroAgent BiliChat 插件

[![License](https://img.shields.io/github/license/SevenNine233/nekro_plugin_bilichat)](LICENSE)
[![NekroAgent](https://img.shields.io/badge/NekroAgent-Compatible-blue)](https://github.com/KroMiose/nekro-agent)

B站UP主订阅推送插件，复刻自 [nonebot-plugin-bilichat](https://github.com/Well233/nonebot-plugin-bilichat) 的订阅推送功能。

## 功能特性

### 📋 YAML 配置
- 独立 YAML 配置文件存储订阅数据
- 配置变更自动检测与日志记录
- 支持热重载

### ⏰ 定时轮询
- 动态轮询（默认 300 秒）
- 直播轮询（默认 60 秒）
- 异步任务后台运行

### 📺 推送功能
- 动态推送（过滤广告、直播预告）
- 直播开播/下播通知
- 支持富媒体消息

### 🎛️ 推送方式
- `PUSH` - 正常推送
- `AT_ALL` - @全体成员
- `IGNORE` - 不推送

### 🔗 动态路由 API
- 订阅/取消订阅
- 查看订阅列表
- 设置推送方式
- 查询直播状态

## 依赖

本插件依赖 [bilichat-request](https://github.com/Well233/bilichat-request) 服务。

## 安装

将插件目录放入 NekroAgent 的插件目录中。

## 配置

配置文件位于 `{plugin_data_dir}/config.yaml`：

```yaml
version: '1.0.0'
api:
  url: http://192.168.0.102:40432
  token: your_token_here
subs:
  dynamic_interval: 300
  live_interval: 60
  push_delay: 3
  use_rich_media: true
  users:
    telegram:123456:
      chat_key: telegram:123456
      subscribes:
        546195:
          uid: 546195
          uname: 老番茄
          nickname: 番茄
          live: PUSH
          dynamic:
            DYNAMIC_TYPE_AV: PUSH
            DYNAMIC_TYPE_DRAW: PUSH
            DYNAMIC_TYPE_AD: IGNORE
```

### 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| api.url | string | `http://192.168.0.102:40432` | bilichat-request API 地址 |
| api.token | string | - | API Token |
| subs.dynamic_interval | int | `300` | 动态轮询间隔（秒） |
| subs.live_interval | int | `60` | 直播轮询间隔（秒） |
| subs.push_delay | int | `3` | 推送延迟（秒） |
| subs.use_rich_media | bool | `true` | 使用富媒体消息 |

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/plugins/SevenNine233.bilichat/` | API 首页 |
| GET | `/plugins/SevenNine233.bilichat/sub` | 查看订阅列表 |
| POST | `/plugins/SevenNine233.bilichat/sub` | 添加订阅 |
| DELETE | `/plugins/SevenNine233.bilichat/sub` | 取消订阅 |
| PUT | `/plugins/SevenNine233.bilichat/push` | 设置推送方式 |
| GET | `/plugins/SevenNine233.bilichat/live/{uid}` | 查询直播状态 |

### 使用示例

**添加订阅**
```bash
curl -X POST "http://localhost:8080/plugins/SevenNine233.bilichat/sub?chat_key=telegram:123456&keyword=老番茄&nickname=番茄"
```

**查看订阅**
```bash
curl "http://localhost:8080/plugins/SevenNine233.bilichat/sub?chat_key=telegram:123456"
```

**取消订阅**
```bash
curl -X DELETE "http://localhost:8080/plugins/SevenNine233.bilichat/sub?chat_key=telegram:123456&keyword=老番茄"
```

**设置推送方式**
```bash
curl -X PUT "http://localhost:8080/plugins/SevenNine233.bilichat/push?chat_key=telegram:123456&keyword=老番茄&push_type=AT_ALL&content_type=live"
```

**查询直播状态**
```bash
curl "http://localhost:8080/plugins/SevenNine233.bilichat/live/546195"
```

## 日志格式

```
[BiliChat] 插件初始化中...
[✅] 配置文件加载成功
[BiliChat] API 地址: http://192.168.0.102:40432
[✅] BiliChat API 连接正常
[🎉] telegram:123456 订阅 UP 老番茄(546195)
[Dynamic] UP 老番茄(546195) 发布新动态: 123456789
[Live] UP 老番茄(546195) 开播: 新视频发布
[♻️] telegram:123456 取消订阅 老番茄(546195)
```

## 致谢

- [nonebot-plugin-bilichat](https://github.com/Well233/nonebot-plugin-bilichat) - 原始插件
- [bilichat-request](https://github.com/Well233/bilichat-request) - 后端服务
- [NekroAgent](https://github.com/KroMiose/nekro-agent) - 插件框架

## License

MIT License
