# NekroAgent BiliChat 插件

[![License](https://img.shields.io/github/license/SevenNine233/nekro_plugin_bilichat)](LICENSE)
[![NekroAgent](https://img.shields.io/badge/NekroAgent-Compatible-blue)](https://github.com/KroMiose/nekro-agent)

B站内容解析与UP主订阅推送插件，复刻自 [nonebot-plugin-bilichat](https://github.com/Well233/nonebot-plugin-bilichat)。

## 功能特性

### 🔗 内容解析
- 自动识别并解析B站链接（视频、动态、专栏）
- 生成 b23 短链接
- 支持配置解析开关和截图质量

### 📺 订阅管理
- 订阅UP主获取动态和直播推送
- 自定义UP主昵称
- 灵活的推送方式配置（正常推送/@全体/忽略）

### 🔴 动态推送
- 自动检测UP主新动态并推送
- 过滤广告、直播预告等类型
- 可配置轮询间隔

### 📺 直播推送
- 开播/下播通知
- 实时直播状态查询
- 可配置轮询间隔

## 依赖

本插件依赖 [bilichat-request](https://github.com/Well233/bilichat-request) 服务。

请先部署 bilichat-request 服务，然后在插件配置中填写 API 地址和 Token。

## 安装

将插件目录放入 NekroAgent 的插件目录中，或通过 WebUI 安装。

## 配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| api_url | string | `http://192.168.0.102:40432` | bilichat-request API 地址 |
| api_token | string | - | API 访问令牌 |
| parse_video | bool | `true` | 是否解析视频链接 |
| parse_dynamic | bool | `true` | 是否解析动态链接 |
| parse_column | bool | `true` | 是否解析专栏链接 |
| screenshot_quality | int | `75` | 截图质量 (10-100) |
| enable_push | bool | `true` | 是否启用推送功能 |
| dynamic_interval | int | `300` | 动态轮询间隔（秒） |
| live_interval | int | `60` | 直播轮询间隔（秒） |
| use_rich_media | bool | `true` | 推送时是否发送图片 |

## 使用方法

### 内容解析

```
解析这个视频：https://www.bilibili.com/video/BV1xx...
```

### 订阅UP主

```
订阅UP主老番茄
订阅UP主546195，昵称番茄
```

### 查看订阅

```
查看B站订阅列表
```

### 取消订阅

```
取消订阅老番茄
取消订阅全部
```

### 设置推送方式

```
设置老番茄的直播推送方式为@全体
设置546195的动态推送方式为忽略
```

### 查询直播状态

```
查询546195的直播状态
```

## API 方法

| 方法名 | 类型 | 说明 |
|--------|------|------|
| `bilibili_parse` | AGENT | 解析B站链接内容 |
| `bilibili_search_up` | TOOL | 搜索B站UP主 |
| `bilibili_subscribe` | AGENT | 订阅UP主 |
| `bilibili_unsubscribe` | AGENT | 取消订阅 |
| `bilibili_list_subscriptions` | TOOL | 查看订阅列表 |
| `bilibili_set_push_type` | AGENT | 设置推送方式 |
| `bilibili_get_live_status` | TOOL | 获取直播状态 |
| `bilibili_b23_generate` | TOOL | 生成短链接 |

## 推送方式说明

| 方式 | 说明 |
|------|------|
| `PUSH` | 正常推送 |
| `AT_ALL` | 推送时@全体成员（需要权限） |
| `IGNORE` | 不推送 |

## 开发

基于 NekroAgent 插件开发框架开发。

参考文档：[NekroAgent 插件开发指南](https://docs.nekroagent.com/docs/04_plugin_dev/00_introduction)

## 致谢

- [nonebot-plugin-bilichat](https://github.com/Well233/nonebot-plugin-bilichat) - 原始插件
- [bilichat-request](https://github.com/Well233/bilichat-request) - 后端服务
- [NekroAgent](https://github.com/KroMiose/nekro-agent) - 插件框架

## License

MIT License
