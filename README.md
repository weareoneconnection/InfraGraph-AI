# InfraGraph AI

**交通基础设施知识资产工厂与工程知识图谱平台**

InfraGraph AI 是独立的交通知识资产参赛作品。目标不是“再做一个聊天知识库”，而是把分散、隐性、异构的工程资料转成可版本化、可计算、可追溯的知识资产，形成 Ontology + Knowledge Graph + Evidence Graph，并通过检索、Claim Verification 和发布快照为大模型与智能体提供知识底座。

## 一键运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

打开 http://127.0.0.1:8102 。

支持直接上传 TXT/MD/CSV/JSON、带文字层 PDF、DOCX。默认全部离线运行，不需要模型 API。

## 知识生产链

`Ingest → Parse → Extract → Normalize → Entity Resolution → Ontology Mapping → Relation Build → Provenance Validation → Publish`

## 核心工程能力

- Infrastructure Ontology：项目、资产、图纸、规范、工作包、方法书、检验、NCR、合同条款、变更、索赔、风险、许可、整改、核验、进度、成本、传感器、维护等核心类。
- Provenance First：每个 Knowledge Asset 保留 Source Ref、内容哈希、版本、司法辖区、生命周期和领域元数据。
- Knowledge Graph：不仅搜索文件，还建立 Asset → Inspection → NCR → Corrective Action → Verification 等可计算关系。
- Hybrid Retrieval Foundation：当前可运行版本使用 SQLite FTS5 + Graph；生产可替换 pgvector/OpenSearch/Neo4j，而 API 合同不变。
- Claim Verification：对工程主张返回真实检索来源；证据不足时返回 `INSUFFICIENT_EVIDENCE`。
- Knowledge Release：知识资产以 manifest hash 形成可审计版本快照。
- Benchmark：评估 Recall@5 与 Provenance Completeness，而不是只评价“回答像不像人”。

## 边界

当前数据为合成示例，不宣称已经完成企业级知识治理、真实法规法律校核、OCR、图纸语义理解或大规模知识图谱生产。真实落地需要专业人员复核、权限体系、对象存储、OCR/版面模型、向量库、图数据库以及知识发布审批流程。
