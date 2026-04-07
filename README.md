# Video Downloader

一个本地运行的最小化视频下载工具。

## 目录结构

```text
.
├─ src/                  # Python 后端包
├─ web/                  # 前端静态资源
├─ environment.yml       # Conda 环境定义
└─ README.md
```

## 依赖

运行依赖全部来自当前环境：

- `yt-dlp`
- `ffmpeg`
- `node`

项目本身不再内置任何二进制文件。

## 推荐安装

### 方式 1：手动创建

```powershell
conda create -n video-downloader -c conda-forge python=3.11 ffmpeg nodejs pip -y
conda activate video-downloader
python -m pip install "yt-dlp[default]==2026.3.17"
```

### 方式 2：使用 environment.yml

```powershell
conda env create -f .\environment.yml
conda activate video-downloader
```

## 启动

```powershell
conda activate video-downloader
python main.py
```

启动后终端会输出本地地址，例如：

```text
http://127.0.0.1:8765
```

## 默认下载路径

默认下载到系统 `Downloads` 目录。

Windows 下一般是：

```text
C:\Users\<用户名>\Downloads
```

也可以在界面中手动改下载路径。

## 当前功能

- 输入链接并解析格式
- 选择视频 / 音频规格
- 选择输出封装
- 选择下载路径
- 下载进度、暂停、继续、终止
- 打开输出文件位置
- 支持站点查询弹窗

## 依赖检查

```powershell
python -m yt_dlp --version
ffmpeg -version
node --version
```
