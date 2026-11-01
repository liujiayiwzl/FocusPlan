# 简学 · FocusPlan

一款面向个人学习计划管理的 Android 应用，使用 Python、Flet 和 SQLite 开发。

## 📱 下载 Android 安装包

**[下载 FocusPlan v1.0.0 APK](https://github.com/liujiayiwzl/FocusPlan/releases/download/v1.0.0/FocusPlan_v1.0.0.apk)**

> 请注意：需要先由项目维护者在 GitHub Releases 中发布 `v1.0.0` 并上传同名 APK，上方直链才能生效。也可以前往 [所有发行版本](https://github.com/liujiayiwzl/FocusPlan/releases) 查看。

### 安装方式

1. 使用 Android 手机下载 APK 文件。
2. 打开下载的 APK，按照手机提示允许此来源安装应用。
3. 安装后即可开始创建学习计划。无需安装 Python 或 PyCharm。

该应用目前主要经过开发者个人的 Android 设备测试，其他机型的兼容性可能不同。建议在安装前确认文件来源。

## ✨ 主要功能

- 按日期创建学习计划，支持连续多天安排
- 设置、展开和勾选子任务
- 学习计时：开始、暂停、继续和完成
- 学习日历与日、周、月学习统计
- 查看学习记录，并支持选择多条记录批量删除
- 在首页滑动计划卡片，查看详情、修改和删除计划
- 使用 SQLite 在设备本地保存学习数据

## 🛠 开发环境

- Python 3.13（Android 打包使用）
- Flet 1.0.5
- flet-charts 1.0.5
- SQLite

依赖清单见 [requirements.txt](requirements.txt)，程序入口为 [main.py](main.py)。

## ⚠️ 数据与版本说明

- 学习计划和学习记录默认存储在设备本地，不会自动同步到 GitHub。
- 卸载应用或清除应用数据可能导致本地学习记录丢失。
- `v1.0.0` 是首个已归档版本的代码标签；对应 APK 应以发布页实际上传的文件为准。
- 本仓库尚未设置代码使用许可协议；公开代码不等于自动授予复制、修改或再分发权限。项目维护者可根据需要补充开源许可证。
