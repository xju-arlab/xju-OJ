# 题目 ZIP 导入格式

管理端“导入 ZIP 题库”以单题 ZIP 为原子格式。批量 ZIP 只是把多个可独立导入的单题 ZIP 放进同一个外层 ZIP；同时保留对旧 QDUOJ 目录包的兼容。

## 单题 ZIP

单题 ZIP 的根目录结构如下：

```text
problem.json
testcase/
  1.in
  1.out
  2.in
  2.out
```

测试数据必须从 `1.in` / `1.out` 开始连续编号。单个单题 ZIP 可以直接上传导入。

## 批量 ZIP

批量 ZIP 的外层只放单题 ZIP，不增加清单文件或额外题目目录：

```text
001-题目标题.zip
002-另一道题.zip
003-第三道题.zip
```

每个内层 ZIP 都必须符合上一节的单题格式并能单独导入。导入器按内层 ZIP 文件名自然排序，整批原子导入；任一道题失败都会整体回滚。

## 旧 QDUOJ 包

旧版数字目录包继续可用，目录不要求从 `1` 连续编号：

```text
1/problem.json
1/testcase/1.in
1/testcase/1.out
2/problem.json
2/testcase/1.in
2/testcase/1.out
```

## `problem.json`

原 QDUOJ 字段继续有效。xju-OJ 另外读取以下可选字段：

- `difficulty`：`Low`、`Mid`、`High`，缺省为 `Mid`；
- `visible`：导入后是否立即可见，缺省为 `false`；
- `languages`：允许提交的语言名称列表，缺省为站点全部语言；
- `tags`：题目标签；
- `time_limit`：毫秒；
- `memory_limit`：MB。

`display_id` 可以省略；即使包内提供，导入时也会忽略。公开题显示 ID 由 OJ 按现有本地公开题数量自动分配，从 `1001` 开始递增。

富文本字段结构如下：

```json
{
  "format": "markdown",
  "value": "Markdown 原文"
}
```

`format` 可取 `markdown` 或 `html`。导入器会把 Markdown 转为 OJ 可展示的安全 HTML。

一个最小的 ACM 题目示例：

```json
{
  "title": "原始题目标题",
  "description": {"format": "markdown", "value": "题目描述"},
  "input_description": {"format": "markdown", "value": "输入描述"},
  "output_description": {"format": "markdown", "value": "输出描述"},
  "data_range": {"format": "markdown", "value": "$1 \\le n \\le 10^5$"},
  "hint": {"format": "markdown", "value": ""},
  "time_limit": 1000,
  "memory_limit": 256,
  "samples": [{"input": "1\n", "output": "1\n", "explanation": "样例解释，可省略"}],
  "template": {},
  "spj": null,
  "rule_type": "ACM",
  "source": "js-problemset /",
  "tags": ["保研真题", "示例大学", "模拟"],
  "difficulty": "Low",
  "visible": false
}
```

`data_range`（数据范围）可省略，旧题包照常导入；值为空时题面不显示该段。
每个样例的 `explanation` 也可省略，它是纯文本（可写 `$...$` 公式），为空时不显示“样例解释”。
导出的 `problem.json` 总会带上这两个字段。

## 安全与回滚

- 单题和批量导入都要求题目管理权限；
- ZIP 拒绝路径穿越、重复文件名、加密成员和超限解压内容；
- 批量 ZIP 只允许包含单题 ZIP；
- 所有题目在一个数据库事务中导入；
- 失败回滚时同步清理本次创建的测试数据目录。
