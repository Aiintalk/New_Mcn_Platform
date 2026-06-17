# M2 Sprint 1 · kol-intake PDF 跨平台字体 v1 · 修复Bug

> 状态：✅ 已完成（2026-06-17）
> 前序文档：`M2_Sprint1_kol_intake_报告展示与下载修复.md`
> 修复类型：跨平台兼容 bug（PDF 中文显示为黑块）

---

## 一、修复背景

### 现象

测试服（Ubuntu）下载 `/workspace/kol-intake/chat` 生成的入驻报告 PDF 后，打开发现内容是**一片片黑色方块**，文字完全不可读。

本地 Windows 开发环境生成的 PDF 正常。

### 根因分析

`backend/app/services/intake_report.py` 的 `generate_pdf()` 用 reportlab 生成 PDF。原代码只尝试注册 Windows 字体：

```python
# 原代码（只支持 Windows）
font_name = "Helvetica"
if os.path.exists("C:/Windows/Fonts/msyh.ttc"):
    pdfmetrics.registerFont(TTFont("MsYaHei", "C:/Windows/Fonts/msyh.ttc"))
    font_name = "MsYaHei"
```

**Ubuntu 服务器没有 `C:/Windows/Fonts/msyh.ttc`，字体注册失败 → `font_name` 保持默认 `Helvetica` → reportlab 用 Helvetica 渲染中文 → 中文字符没有对应字形 → 输出黑色方块**。

**佐证**：
- 本地 Windows PDF 大小 32 KB（字体嵌入成功）
- 服务器 PDF 大小 2.7 KB（没有嵌入字体，只剩结构）

---

## 二、修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/services/intake_report.py` | `generate_pdf()` 中文字体注册增加 Linux / macOS 路径 |

---

## 三、具体改动

### 跨平台字体注册

```python
# 尝试注册中文字体（跨平台：Windows / Linux / macOS）
font_name = "Helvetica"
for font_path, name in [
    # Windows
    ("C:/Windows/Fonts/msyh.ttc",               "MsYaHei"),
    ("C:/Windows/Fonts/simhei.ttf",              "SimHei"),
    # Linux（需安装：sudo apt install fonts-wqy-microhei 或 fonts-noto-cjk）
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",         "WQYMicrohei"),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",           "WQYZenhei"),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "NotoSansCJK"),
    # macOS
    ("/System/Library/Fonts/PingFang.ttc",       "PingFang"),
]:
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont(name, font_path))
            font_name = name
            break
        except Exception:
            continue
```

**逻辑**：按优先级遍历三个系统的常见中文字体路径，找到第一个可注册的就用，全找不到才回退到 Helvetica（拉丁字符正常，中文仍异常）。

---

## 四、部署前置条件

### Ubuntu 服务器必须装中文字体包

测试服 / 生产服首次部署 PDF 功能前必须执行：

```bash
# 方案 A：文泉驿微米黑（体积小，推荐测试服）
sudo apt update
sudo apt install -y fonts-wqy-microhei

# 方案 B：思源 Noto CJK（更完整，推荐生产服）
sudo apt install -y fonts-noto-cjk
```

**验证安装**：

```bash
ls /usr/share/fonts/truetype/wqy/wqy-microhei.ttc
# 或
ls /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
```

文件存在即注册成功。**不装字体包的话，跨平台字体逻辑也救不了**——所有路径都不存在，会回退到 Helvetica。

### 已加入部署文档

`deploy/README.md` §1 环境要求已补中文字体包安装命令（如有缺，待补）。

---

## 五、测试验证

### 本地 Windows 验证

下载的 PDF 内容正常显示中文，文件大小 32 KB（字体嵌入成功）。

### 服务器验证（待用户执行）

部署代码 + 装字体后，重新走 kol-intake 流程并下载 PDF，应看到：
- 文件大小 ≥ 30 KB（字体嵌入）
- 中文内容正常显示，无黑块

---

## 六、不涉及

- 不改 Word（docx）生成逻辑（python-docx 用系统默认字体，跨平台问题小）
- 不改 API、契约
- 不改 PDF 内容/样式，只改字体注册
- 不引入新 Python 依赖（reportlab 已有）

---

## 七、相关延伸（未做，记录待办）

如果未来 PDF 还有其他字体问题，可考虑：

1. **打包字体进项目**：在 `backend/assets/fonts/` 放一个开源中文字体（如思源黑体子集），跨平台一致。代价：仓库变大（10MB+）
2. **统一字体管理**：所有 PDF 生成（含 `benchmark_report.py`、`word_export.py`）共用一个 `_get_cjk_font()` 工具函数
3. **健康检查加字体探测**：`/api/health` 返回字体是否注册成功，部署时可一眼看出

当前不做，记录于此供后续评估。
