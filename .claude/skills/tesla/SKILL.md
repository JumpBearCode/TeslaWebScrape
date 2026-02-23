---
name: tesla
description: 爬取 Tesla Model Y & Model 3 库存（二手 + 新车），各取前30辆，存盘
---

## 执行流程

### 0. 确认存储方式

问用户数据存到哪里：

- **local** — 仅保存 CSV 到本地 `results/`
- **postgres** — 仅写入 PostgreSQL（Mac Mini 192.168.31.61）
- **both** — CSV + PostgreSQL 都存

默认选 **both**。

### 1. 获取 Cookies

```
acquire_cookies(model="my", condition="used")
```

失败则提示用户稍后重试。

### 2. 搜索二手车（顺序调用）

**先 Model Y，完成后再 Model 3**（不并行，降低被封风险）：

```
search_top_n(model="my", condition="used", zip="30096", range=0, sort="Price", sort_order="asc", top_n=30, year_min=2024, year_max=2026, odometer_max=21000)
```

MY 返回后，再调用：

```
search_top_n(model="m3", condition="used", zip="30096", range=0, sort="Price", sort_order="asc", top_n=30, year_min=2024, year_max=2026, odometer_max=21000)
```

### 3. 搜索新车（顺序调用，无 year/mileage filter）

```
search_top_n(model="my", condition="new", zip="30096", range=0, sort="Price", sort_order="asc", top_n=30)
```

MY 返回后，再调用：

```
search_top_n(model="m3", condition="new", zip="30096", range=0, sort="Price", sort_order="asc", top_n=30)
```

### 4. 错误处理

任一 `search_top_n` 返回 error（403/429），调用 `acquire_cookies` 刷新后重试一次。

`search_top_n` 内部自动翻页 + VIN 去重，每个车型一次调用即可拿到 30 辆。
返回值只有 `{total, returned, raw_file, slim_file}`，不含车辆数据。

### 5. 存储结果

根据步骤 0 用户选择的方式存储：

#### local 或 both → 合并为 CSV

```
merge_results(raw_files=[my_used_raw, m3_used_raw], filename="tesla_used_inventory.csv")
merge_results(raw_files=[my_new_raw, m3_new_raw], filename="tesla_new_inventory.csv")
```

#### postgres 或 both → 写入 PostgreSQL

```
save_to_postgres(raw_files=[my_used_raw, m3_used_raw], condition="used")
save_to_postgres(raw_files=[my_new_raw, m3_new_raw], condition="new")
```

### 6. 清理中间文件

如果选了 local 或 both（即生成了 CSV），删除 `results/` 下本次生成的所有 JSON 文件（raw + slim），只保留最终的 CSV：

```
rm results/topn_*.json
```

如果只选了 postgres，也删除所有 JSON 中间文件（数据已在 DB）。

### 7. 完成

告知用户结果：
- local/both：显示两个 CSV 文件路径
- postgres/both：显示插入的行数
