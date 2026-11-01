<div align="center">

# 简学 · FocusPlan

**让每一天的计划，都有迹可循。**

轻量、简洁的 Android 学习计划与专注计时应用。  
将 **计划安排 → 专注学习 → 学习复盘** 整合在一个地方。

<p>
  <img alt="Android" src="https://img.shields.io/badge/Android-App-3DDC84?logo=android&logoColor=white" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white" />
  <img alt="Flet" src="https://img.shields.io/badge/Flet-1.0.5-0175C2" />
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-Local-003B57?logo=sqlite&logoColor=white" />
  <a href="https://github.com/liujiayiwzl/FocusPlan/releases/tag/v1.0.0"><img alt="Release" src="https://img.shields.io/badge/Release-v1.0.0-blue" /></a>
</p>

### [📥 下载 Android APK](https://github.com/liujiayiwzl/FocusPlan/releases/download/v1.0.0/FocusPlan_v1.0.0.apk) · [查看版本发布页](https://github.com/liujiayiwzl/FocusPlan/releases/tag/v1.0.0)

<sub>当前公开版本：v1.0.0 · 下载后在 Android 手机上安装，无需 Python 开发环境</sub>

</div>

---

## ✨ 功能介绍

| 模块 | 你可以做什么 |
| --- | --- |
| 📋 学习计划 | 为指定日期创建计划，也可以一次安排连续多天；随时查看、修改和删除 |
| ✅ 子任务 | 给计划添加子任务，在首页展开、勾选并查看完成情况 |
| ⏱️ 专注计时 | 开始、暂停、继续和完成学习；保存真实学习时长 |
| 📅 学习日历 | 按日期回顾学习情况，查看有学习记录的日期 |
| 📊 学习统计 | 按天、周、月查看学习时间和不同计划的时间分布 |
| 🗂️ 学习记录 | 查看历史记录，支持单条删除或批量选择删除 |
| 💾 本地存储 | 使用 SQLite 保存计划、子任务和学习记录 |

> FocusPlan 面向个人学习场景，目前以 Android 使用体验为主。项目仍可能存在未发现的兼容性问题。

## 📱 下载与安装

**推荐下载：** [FocusPlan v1.0.0 APK（Android）](https://github.com/liujiayiwzl/FocusPlan/releases/download/v1.0.0/FocusPlan_v1.0.0.apk)

1. 用 Android 手机点击上面的下载链接，或前往 [Releases](https://github.com/liujiayiwzl/FocusPlan/releases) 页面。
2. 下载 `FocusPlan_v1.0.0.apk`。
3. 打开下载的安装包，按照 Android 系统提示完成安装。
4. 打开「简学」，创建你的第一个学习计划。

> **提示：** APK 是 Android 安装包。Windows、macOS 也能下载这个文件，但不能直接当作电脑软件运行；iPhone 不能安装 APK。通过浏览器安装时，系统可能要求允许该来源安装应用。

## 🧩 使用流程

**01 · 安排计划** — 创建今天或未来某段日期的学习计划，并设置子任务。  
**02 · 开始专注** — 点击开始计划，按需暂停、继续，完成后保存学习时长。  
**03 · 回顾进度** — 通过日历、统计图和学习记录了解实际学习情况。

## 🛠️ 技术栈

| 技术 | 用途 |
| --- | --- |
| Python | 应用业务逻辑 |
| Flet | 跨平台界面 |
| flet-charts | 学习统计图表 |
| SQLite | 本地持久化存储 |

### 本地运行源代码

要求：建议使用 Python 3.13。项目所用 Python 依赖参见 [requirements.txt](requirements.txt)。

```bash
git clone https://github.com/liujiayiwzl/FocusPlan.git
cd FocusPlan
python -m pip install -r requirements.txt
python main.py
```

以上用于开发环境运行；**普通 Android 用户直接下载 APK 即可**。

## 📂 项目结构

```text
FocusPlan/
├── main.py             # 应用入口与主要功能
├── requirements.txt    # Python 依赖
├── pyproject.toml      # 项目与 Flet 配置
├── .gitignore          # 忽略本地缓存、数据库及打包产物
└── README.md           # 项目说明
```

## 🔐 数据保存与隐私

- 计划、子任务和学习记录保存在设备本地的 SQLite 数据库中。
- 当前版本**没有账号同步或云端备份功能**。
- 卸载应用或清除应用数据，可能导致已有学习记录无法恢复。
- APK 通过 [GitHub Releases](https://github.com/liujiayiwzl/FocusPlan/releases) 分发；源代码仓库不包含个人学习数据库。

## 📌 版本与反馈

- **当前版本：** [v1.0.0](https://github.com/liujiayiwzl/FocusPlan/releases/tag/v1.0.0)
- **版本历史：** [Releases](https://github.com/liujiayiwzl/FocusPlan/releases)
- **问题反馈：** [Issues](https://github.com/liujiayiwzl/FocusPlan/issues)

## 📄 使用许可

本仓库目前**尚未添加 LICENSE 文件**。仓库公开可见不等于自动授权他人复制、修改或再分发代码。如需将本项目作为可自由使用的开源项目，请先由项目维护者选择并添加合适的开源许可证。

---

<div align="center">
  <sub>FocusPlan · 让计划更清晰，让努力看得见。</sub>
</div>
