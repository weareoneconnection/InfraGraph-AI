# 参赛对齐说明

赛道：交通知识资产构建与应用。

## 核心回答

本作品回答的不是“AI怎样回答一个问题”，而是：**如何把交通行业分散、异构、隐性的资料变成结构化、标准化、可计算、可追溯、可持续发布的知识资产。**

## 冠军黄金演示

1. 上传一包工程资料中的 NCR / 合同条款 / HSE 方法书。
2. 系统解析来源、版本、司法辖区、生命周期和领域。
3. 自动生成 Knowledge Assets 和关系。
4. Graph Explorer 展示 `Asset → Inspection → NCR → Corrective Action → Verification`。
5. 提问工程主张，系统只返回实际来源并给出 Claim Verification。
6. 发布 Knowledge Release，生成 manifest SHA-256。

## 可量化评测

- Entity/Type Mapping Accuracy（扩展评测集后）
- Relation Precision/F1（扩展评测集后）
- Recall@5
- Provenance Completeness
- Version Resolution Accuracy
- No-evidence Abstention
