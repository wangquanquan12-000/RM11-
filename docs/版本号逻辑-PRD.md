# 版本号逻辑 · PRD

> **文档用途**：定义应用版本号的配置、展示与上线验证流程。
>
> **创建日期**：2025-03-02

---

## 一、需求背景与目标

### 1.1 背景

- 应用部署到 Streamlit Cloud 或自建服务器后，需要快速确认「线上代码是否已成功更新」。
- 每次发版后，若无法直观看到版本信息，难以判断当前环境是否为最新。

### 1.2 目标

- **可配置**：版本号由配置文件维护，上线前仅改配置即可，无需改业务代码。
- **可观测**：版本号在侧栏/设置页可见，便于用户与运维验证。
- **上线验证**：部署完成后，通过查看版本号即可确认发布是否生效。

---

## 二、功能需求

### 2.1 版本配置

| 项目 | 说明 |
|------|------|
| 配置文件 | `config/version.yaml` |
| 字段 | `version`（必填）、`build_time`（可选） |
| 格式 | version 建议：主版本.次版本.修订号 或 YYYY.MM.DD.N |
| 示例 | `version: "1.0.0"`、`build_time: "2025-03-02 14:00"` |

```yaml
# config/version.yaml
version: "1.0.0"
build_time: ""
```

### 2.2 展示位置

| 位置 | 说明 |
|------|------|
| 侧栏底部 | 主应用侧栏，在「高级」导航与底部分隔线之后，以 caption 形式展示 |
| 设置页 | 在设置页顶部或底部展示当前版本，便于集中查看 |

### 2.3 展示规则

| 规则 | 说明 |
|------|------|
| 有 version | 显示「版本: {version}」；若 build_time 非空，追加「 ({build_time})」 |
| 无 version | 不展示版本区域，避免空白占位 |
| 读取失败 | 静默返回空，不展示、不报错 |

### 2.4 文案配置

| 配置项 | 路径 | 默认值 |
|--------|------|--------|
| 版本标签 | `config/ui_texts.yaml` → `app.version_label` | 「版本」 |

---

## 三、非功能需求与验收标准

### 3.1 非功能需求

| 项 | 要求 |
|----|------|
| 性能 | 版本读取仅在渲染侧栏/设置页时执行，无额外请求 |
| 安全 | 不暴露内部路径或敏感信息，仅展示配置的 version/build_time |
| 容错 | 文件不存在或 YAML 解析异常时，返回空 dict，不崩溃 |

### 3.2 验收标准

| 编号 | 验收项 |
|------|--------|
| AC1 | 修改 `config/version.yaml` 中的 version 后，刷新页面即可看到新版本号 |
| AC2 | 侧栏底部展示「版本: x.x.x」或「版本: x.x.x (build_time)」 |
| AC3 | 设置页展示当前版本号 |
| AC4 | version 为空或文件不存在时，不展示版本区域 |
| AC5 | 文案「版本」可通过 ui_texts.yaml 配置 |

---

## 四、上线验证的使用流程

1. **发版前**：在 `config/version.yaml` 中更新 `version`（及可选的 `build_time`）。
2. **提交并推送**：将 `version.yaml` 与代码一并提交，推送到 Git 远程。
3. **部署**：Streamlit Cloud 或自建环境从 Git 拉取最新代码并重启。
4. **验证**：打开应用 → 查看侧栏底部或进入「设置」页 → 确认显示的版本号与本次发版一致。
5. **结论**：若版本号正确，说明线上代码已成功更新；若仍为旧版本，则需检查部署流程或缓存。

---

## 五、实现要点（供开发参考）

### 5.1 配置读取

```python
def _load_version() -> dict:
    """从 config/version.yaml 读取 version、build_time。"""
```

### 5.2 展示逻辑

```python
ver_info = _load_version()
ver_str = ver_info.get("version", "")
if ver_str:
    ver_label = _get_text(T, "app.version_label") or "版本"
    ver_display = f"{ver_label}: {ver_str}"
    if ver_info.get("build_time"):
        ver_display += f" ({ver_info['build_time']})"
    st.caption(ver_display)
```

### 5.3 文案配置

```yaml
# config/ui_texts.yaml
app:
  version_label: "版本"
```
