# 元素定位工具箱

写爬虫时最费时间的不是发请求，是"这个元素到底怎么定位"。
这个工具让你**点一下就能拿到能用的选择器**。

## 运行

双击 `index.html`，或：

```bash
python -m http.server 8000
# 打开 http://localhost:8000/03-selector-toolbox/
```

## 用法

1. 把目标页面的 HTML 源码粘到左边
2. 右边会实时渲染出页面
3. 在预览里点任意元素
4. 下方直接给出：

| 输出 | 用途 |
|------|------|
| XPath | 逐层带索引的绝对路径，`lxml` / `Selenium` 直接用 |
| CSS 选择器 | 做了唯一性处理，`querySelector` 直接命中 |
| 元素文本 | 判断是不是要抓的那段内容 |
| 元素 HTML | 看结构、找规律 |
| 元素属性 | 拿 `src` / `href` / `data-*` |

## 技术说明

- 纯前端：HTML + 原生 JavaScript，无框架、无构建
- XPath 生成走 `parentNode` 递归，带同名兄弟节点索引，避免"看起来对但选不中"
- CSS 选择器优先用 `id`，其次 `class` + `nth-of-type`，保证唯一
- 页面内容只在浏览器内存里，不上传

## 文件

```
index.html    # 全部内容（结构、样式、逻辑）
```

> 图标引用了 cdnjs 的 Font Awesome，断网时图标不显示，功能不受影响。