# 真实列名与数据覆盖（Task 1 固化，勿凭记忆）

来源：`Gaokao-Compass-11M`（Hugging Face）· 经由 **`hf-mirror.com`** 镜像下载（`huggingface.co` 本机不可达）
路径形如 `data/<年份>/guangdong/<表名>.csv`，已下载到 `data/raw/<年份>-<表名>.csv`
下载日期：2026-10-11 · 范围：广东 · 2021–2025

---

## 一、真实列名（逐字抄）

### `score-range.csv` —— 一分一段表
```
province, year, category, batch, control_score, score, score_range,
segment_count, cumulative_count, rank_range
```
- **`category`** 取值：`物理类` / `历史类`（**不是** `物理` / `历史`）
- **`batch`** 取值：`本科批` / `专科批`（**不是** `本科普通批`）
- **累计人数列名是 `cumulative_count`**（不是 `cumulative`）
- `rank_range` 例：分数 695 → `1-31` ⇒ **`cumulative_count` 是该分数段的末位**

### `school-admission.csv` —— 院校专业组投档线
```
province, year, category, batch, university_code, university_name, major_group,
subject_req, min_score, min_rank, control_score, score_diff, admit_count,
school_province, school_nature, is_985, is_211
```
- **专业组列名是 `major_group`**（不是 `group_code`）

### `major-admission.csv` —— 专业录取分（含专业组）
```
province, [province.1,] year, category, batch, university_code, university_name,
major_group, major_code, major_name, major_note, subject_req,
min_score, min_rank, max_score, avg_score, admit_count,
school_province, school_nature, is_985, is_211
```
> ⚠️ `province.1` 只在部分年份出现（2021/2024 有，2022/2025 没有）—— 读的时候要**按列名取，不能按位置取**。

### `enrollment-plan.csv` —— 招生计划（含选科要求）
```
province, year, batch, category, university_code, university_name, major_group,
major_code, major_name, major_note, subject_req, plan_count, duration, tuition
```
- `subject_req` 例：`首选物理，再选化学`

---

## 二、🔴 数据覆盖（**本科批**）—— 这是关键发现

| 年份 | 一分一段表 | 投档线 `school-admission` | 专业录取分 `major-admission` |
|---|---|---|---|
| **2021** | ❌ **`category` 与 `batch` 全空**（1164 行无法区分科类） | ✅ 2553 行 | ✅ 15345 行 · 专业组 ✅ · **但 `min_rank` 全空** |
| **2022** | ✅ 480 行（物理类/历史类齐） | ✅ 2601 行 | ✅ 16142 行 · 专业组 ✅ · `min_rank` ✅ |
| **2023** | ✅ 500 行 | ❌ **本科批 0 行**（只有专科批） | ❌ **文件不存在**（内容为 `Entry not found`） |
| **2024** | ✅ 492 行 | ❌ **本科批 0 行**（只有专科批） | ❌ **本科批 0 行**（只有专科批 2866） |
| **2025** | ✅ 471 行 | ✅ 1100 行 | ✅ 7561 行 · 专业组 ✅ · `min_rank` ✅ |

### 结论：**能用的是哪些**

| 检查 | 依赖的数据 | 可用年份 |
|---|---|---|
| **位次换算**（分 → 位次） | 一分一段表 | **2022 / 2023 / 2024 / 2025** |
| **投档线核对**（声称值 vs 真实值） | 录取数据（专业组粒度 + 位次） | **2022 / 2025** |
| **分档逻辑**（冲稳保是否自洽） | 录取数据的 `min_rank` | **2022 / 2025** |
| **选科/计划** | `enrollment-plan` 的 `subject_req` / `plan_count` | 2021/2022/2025 有 `subject_req`；**2024 `plan_count` 全空** |

> **⚠️ 与 spec §6「广东 · 2021–2025」不符：投档线相关检查实际只有 2022 和 2025 两年。**
> 这是**数据集自身的缺口**（2023 整张专业录取分表缺失、2023/2024 投档线无本科批），不是下载出错。

### 其它要注意的

- 🔴 **`subject_req` 有两种格式，按年份不同**：
  - **2022 / 2024**：`首选物理，再选化学` / `首选物理，再选不限`
  - **2025**：`不限` / `化学` / `地理` / `化学和生物` —— **丢了"首选X"前缀**
  - 还有**或**语义：`化学/生物(2选1)`
  - ⚠️ 只认第一种的解析器碰上 2025 会**一律判为"满足"→ 检查静默失效、永远报不出问题**。
    （本项目已修：`checks/subject_plan.py` 两种都解析，并有回归测试 `test_2025_format_is_...`）
- `enrollment-plan` 的 `major_group` **只有 2025 非空**（2021/2022/2024 全空）
  → **检查④（选科）实际只在 2025 可用**（它必须按专业组查）。
- 2021 的 `major-admission` 有 `major_group` 但 **`min_rank` 全空** → 无法做位次层面的比对。

---

## 三、未验证 / 待定

- 广东省教育考试院 `eea.gd.gov.cn` 的 PDF 能否补上 2023/2024 的本科批投档线（**未验证**）
- 是否换用别的数据集（如阳光高考系）补洞（**未验证**）
