# 📚 新华三杯题库搜索系统

2026"新华三杯"全国大学生数字技术大赛（网络赛道）备考题库搜索系统。支持语义搜索、精确搜索和混合搜索。

## ✨ 功能特性

- **语义搜索** — 基于 sentence-transformers 向量化，用自然语言描述即可找到相关题目
- **精确搜索** — 基于 SQLite FTS5 全文索引，关键词精确匹配
- **混合搜索** — 语义 + 精确结合，两种结果去重合并
- **782 道题目** — 从 697 页 PDF 自动解析，覆盖单选（244）、多选（538）
- **现代 Web UI** — 响应式设计，深色/浅色主题，正确答案高亮，解析折叠展开
- **轻量部署** — 纯 Python + SQLite，无需外部数据库服务

## 📸 截图

启动后访问 `http://localhost:8765`

## 🏗️ 技术架构

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  PDF 题库    │ ──▶ │  parse_pdf.py │ ──▶ │ questions.json  │
│ (697 页)     │     │  PyMuPDF 解析 │     │ (结构化 JSON)    │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                                                   ▼
                                          ┌──────────────┐
                                          │  build_db.py  │
                                          │ 向量化 + 入库  │
                                          └────────┬─────┘
                                                   │
                                                   ▼
                    ┌──────────────────────────────────────────┐
                    │              exam.db (SQLite)             │
                    │  ┌────────────┬──────────┬─────────────┐ │
                    │  │ questions  │ FTS5 索引 │ vec0 向量索引│ │
                    │  └────────────┴──────────┴─────────────┘ │
                    └──────────────────┬───────────────────────┘
                                       │
                                       ▼
                              ┌──────────────┐
                              │  server.py    │
                              │  Flask API    │──▶ Web UI (index.html)
                              └──────────────┘
```

### 核心组件

| 组件 | 技术 | 说明 |
|------|------|------|
| PDF 解析 | PyMuPDF (fitz) | 提取文本 + 正则解析题目结构 |
| 向量化 | sentence-transformers | `paraphrase-multilingual-MiniLM-L12-v2`，384 维 |
| 向量存储 | sqlite-vec | SQLite 原生向量搜索扩展 |
| 全文搜索 | SQLite FTS5 | 内置全文索引，BM25 排序 |
| Web 后端 | Flask + Flask-CORS | RESTful API |
| Web 前端 | 原生 HTML/CSS/JS | 零依赖，单文件 |

## 📋 环境要求

- **Python** 3.10+
- **操作系统** Windows / macOS / Linux
- **磁盘** ~500MB（模型首次下载）+ ~5MB（数据库）
- **内存** ~1GB（模型加载时）

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/SeimoDev/h3c-exam-search.git
cd h3c-exam-search
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 准备 PDF 题库

将 PDF 题库文件放到项目根目录，命名为 `exam_bank.pdf`：

```bash
# 确保文件存在
ls exam_bank.pdf
```

### 4. 解析 PDF

```bash
python parse_pdf.py
```

输出：
- `questions.json` — 结构化题目数据（782 题）

### 5. 构建向量数据库

```bash
python build_db.py
```

首次运行会自动下载 sentence-transformers 模型（~90MB），输出：
- `exam.db` — SQLite 数据库（~4.5MB），包含原始数据 + FTS5 索引 + 向量索引

### 6. 启动服务器

```bash
python server.py
```

首次启动需要 ~15 秒加载模型，之后访问：
- **http://localhost:8765**

## 📁 项目结构

```
h3c-exam-search/
├── README.md              # 本文件
├── requirements.txt       # Python 依赖
├── parse_pdf.py          # PDF 解析脚本
├── build_db.py           # 向量化入库脚本
├── server.py             # Flask Web 服务器
├── web/
│   └── index.html        # 前端页面（单文件）
├── exam_bank.pdf         # PDF 题库（需自行放入，不含在仓库中）
├── questions.json        # 解析后的题目 JSON（由 parse_pdf.py 生成）
└── exam.db               # SQLite 向量数据库（由 build_db.py 生成）
```

## 🔌 API 文档

### 搜索

```
GET /api/search?q={query}&mode={mode}&limit={limit}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string | 必填 | 搜索关键词或描述 |
| `mode` | string | `semantic` | 搜索模式：`semantic` / `keyword` / `both` |
| `limit` | int | `20` | 返回结果数量（最大 100） |

**响应示例：**

```json
{
  "results": [
    {
      "id": 106,
      "number": 106,
      "difficulty": 2,
      "type": "多选题",
      "content": "在如图所示的交换网络中...",
      "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
      "answer": "BD",
      "section": "",
      "explanation": "...",
      "score": 0.72,
      "match_type": "semantic"
    }
  ],
  "total": 20,
  "query": "VLAN配置",
  "mode": "semantic"
}
```

### 统计信息

```
GET /api/stats
```

```json
{
  "total": 782,
  "by_difficulty": {"★": 506, "★★": 259, "★★★": 4, "未标注": 13},
  "by_type": {"单选题": 244, "多选题": 538}
}
```

### 获取单题

```
GET /api/question/{id}
```

## ⚙️ 高级配置

### 更换端口

编辑 `server.py` 最后一行：

```python
app.run(host='0.0.0.0', port=8765)  # 修改 port 即可
```

### 更换 Embedding 模型

编辑 `build_db.py` 和 `server.py` 中的模型名称：

```python
# 推荐的中文模型：
SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')  # 当前，384 维，通用
SentenceTransformer('shibing624/text2vec-base-chinese')        # 中文专用，768 维
```

> ⚠️ 更换模型后需重新运行 `build_db.py` 重建向量索引。

### 后台运行

**Windows:**
```powershell
Start-Process python -ArgumentList "server.py" -WindowStyle Hidden -WorkingDirectory "D:\path\to\h3c-exam-search"
```

**Linux/macOS:**
```bash
nohup python server.py > server.log 2>&1 &
```

### 使用 Docker（可选）

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python parse_pdf.py && python build_db.py
EXPOSE 8765
CMD ["python", "server.py"]
```

## 🔧 题目解析说明

解析器通过正则表达式从 PDF 文本中识别以下结构：

- **题号**：`问题 N` 格式
- **难度**：`★` 数量（1-5 星）
- **选项**：`A.` ~ `F.` 开头的行
- **答案**：`正确答案: XX` 格式
- **解析**：`说明/参考:` 后的内容

当前解析率：782/782 题成功提取，其中 18 题因格式特殊（图片题、填空题等）缺少选项或答案。

## 📄 License

MIT
