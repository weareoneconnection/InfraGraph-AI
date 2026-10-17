"""Transport-infrastructure ontology: entity types, bilingual lexicon, identifier
patterns and relation constraints.

Concept entities resolve across languages through the lexicon: "裂缝" and
"crack" are aliases of one canonical entity ``Defect:crack``. Identified
entities (piers, stations, NCR numbers, standards, clauses) are normalised by
pattern so "P47墩", "Pier P47" and "P47 pier" become ``Asset:P47``. A relation
is accepted only if its subject and object types satisfy the predicate's
domain and range.
"""
from __future__ import annotations

import re

TYPES: dict[str, dict[str, str]] = {
    "Asset": {"zh": "资产/构件", "en": "Asset"},
    "Defect": {"zh": "病害/缺陷", "en": "Defect"},
    "Hazard": {"zh": "危险源", "en": "Hazard"},
    "Measure": {"zh": "措施", "en": "Measure"},
    "Activity": {"zh": "作业活动", "en": "Activity"},
    "Document": {"zh": "文件记录", "en": "Document"},
    "Standard": {"zh": "标准规范", "en": "Standard"},
    "Clause": {"zh": "合同条款", "en": "Contract clause"},
    "Party": {"zh": "参与方", "en": "Party"},
    "Event": {"zh": "合同/安全事件", "en": "Event"},
}

# canonical (English) -> aliases (English and Chinese)
LEXICON: dict[str, dict[str, list[str]]] = {
    "Defect": {
        "crack": ["crack", "cracks", "cracking", "裂缝", "开裂"],
        "honeycombing": ["honeycombing", "honeycomb", "蜂窝", "麻面"],
        "spalling": ["spalling", "剥落", "掉块"],
        "corrosion": ["corrosion", "rust", "锈蚀", "腐蚀"],
        "displacement": ["displacement", "位移", "偏移"],
        "leakage": ["leakage", "seepage", "渗漏", "渗水"],
        "settlement": ["settlement", "沉降"],
        "low concrete strength": ["low strength", "strength below", "强度不足", "强度低于"],
    },
    "Hazard": {
        "unprotected edge": ["unprotected edge", "open edge", "临边", "无防护临边"],
        "fall from height": ["fall from height", "falling from height", "高处坠落", "坠落"],
        "excavation collapse": ["excavation collapse", "trench collapse", "基坑坍塌", "塌方"],
        "struck by load": ["struck by load", "suspended load", "吊物打击", "吊物坠落"],
    },
    "Measure": {
        "edge protection": ["edge protection", "guardrail", "guardrails", "防护栏杆", "临边防护"],
        "fall arrest system": ["fall arrest", "fall-arrest", "safety harness", "安全带", "防坠落"],
        "epoxy injection": ["epoxy injection", "环氧注浆", "注浆修补"],
        "re-inspection": ["re-inspection", "reinspection", "re-inspect", "复检", "复查"],
        "shoring": ["shoring", "支护"],
        "lift plan": ["lift plan", "lifting plan", "吊装方案"],
        "exclusion zone": ["exclusion zone", "警戒区"],
        "core test": ["core test", "coring", "钻芯取样", "钻芯"],
        "permit to work": ["permit to work", "work permit", "作业许可", "作业许可证"],
    },
    "Activity": {
        "work at height": ["work at height", "working at height", "高处作业"],
        "concrete pouring": ["concrete pouring", "concrete pour", "pour", "混凝土浇筑", "浇筑"],
        "formwork removal": ["formwork removal", "striking formwork", "拆模"],
        "lifting operation": ["lifting operation", "lifting", "crane lift", "吊装", "起吊"],
        "excavation": ["excavation", "基坑开挖", "开挖"],
        "bearing inspection": ["bearing inspection", "支座检查"],
    },
    "Party": {
        "engineer": ["the engineer", "engineer's representative", "监理工程师", "监理"],
        "contractor": ["the contractor", "main contractor", "总承包商", "承包商"],
        "subcontractor": ["subcontractor", "sub-contractor", "分包商", "分包"],
        "owner": ["the owner", "the employer", "employer", "业主", "建设单位"],
    },
    "Event": {
        "variation": ["variation", "variation order", "change order", "变更", "变更令"],
        "extension of time": ["extension of time", "eot", "工期延长", "延长工期"],
        "claim": ["claim", "索赔"],
        "incident": ["incident", "accident", "事故", "事件报告"],
    },
}

# Identified entities: (type, regex, normaliser). Normalisers return the canonical id.
def _asset(m: re.Match) -> str:
    return (m.group("id") or "").upper().replace(" ", "")


ID_PATTERNS: list[tuple[str, re.Pattern, callable]] = [
    ("Asset", re.compile(r"(?<![A-Za-z0-9-])(?:pier\s*|墩柱?\s*)?(?P<id>P\d{1,4})(?:\s*(?:墩柱|墩|pier))?(?![A-Za-z0-9])", re.I), _asset),
    ("Asset", re.compile(r"(?<![A-Za-z0-9-])(?:station\s*|车站\s*)?(?P<id>S\d{1,3})(?:\s*车站)?(?![A-Za-z0-9])", re.I), _asset),
    ("Asset", re.compile(r"(?<![A-Za-z0-9])(?P<id>(?:BRG|TUN|ABT|BM)-\d{1,4})(?![A-Za-z0-9])", re.I), _asset),
    ("Document", re.compile(r"(?<![A-Za-z0-9])(?P<id>(?:NCR|RFI|SI|ITP|DWG|MS)-[A-Z0-9-]{2,12})(?![A-Za-z0-9])", re.I), _asset),
    ("Standard", re.compile(r"(?<![A-Za-z])(?P<id>(?:GB/T|GB|JTG/T|JTG|TB|JGJ|BS EN|EN|ISO)\s?[A-Z]?\d{1,5}(?:[./-]\d+)*(?:-\d{4})?)(?![A-Za-z0-9])"),
     lambda m: re.sub(r"\s+", " ", m.group("id").upper()).replace("GB/T", "GB/T ").replace("  ", " ").strip()),
    ("Clause", re.compile(r"(?:sub-?clause|clause)\s*(?P<id>\d{1,2}(?:\.\d{1,2}){0,2})(?!\d|\.\d)", re.I),
     lambda m: "Clause " + m.group("id")),
    ("Clause", re.compile(r"第\s*(?P<id>\d{1,2}(?:\.\d{1,2}){0,2})\s*条"), lambda m: "Clause " + m.group("id")),
]

# predicate -> (allowed subject types, allowed object types, cue words required in the sentence or None)
RELATIONS: dict[str, tuple[set[str], set[str], list[str] | None]] = {
    "HAS_DEFECT": ({"Asset"}, {"Defect"}, None),
    "EXPOSED_TO": ({"Activity", "Asset"}, {"Hazard"}, None),
    "TREATED_BY": ({"Defect", "Hazard"}, {"Measure"},
                   ["require", "requires", "required", "shall", "must", "by", "with", "repair", "repaired", "install",
                    "installed", "须", "必须", "采用", "进行", "设置", "使用", "要求", "修补"]),
    "RECORDED_IN": ({"Defect", "Event", "Hazard"}, {"Document"}, None),
    "ABOUT": ({"Document"}, {"Asset"}, None),
    "GOVERNED_BY": ({"Activity", "Measure", "Defect", "Event"}, {"Standard", "Clause"},
                    ["according to", "in accordance with", "per", "under", "complies with", "comply with", "pursuant to",
                     "按照", "依据", "根据", "符合", "满足", "按", "执行"]),
    "REQUESTED_BY": ({"Event"}, {"Party"}, ["requested by", "submitted by", "raised by", "requests", "request", "提出", "申请"]),
    "PERFORMED_ON": ({"Activity"}, {"Asset"}, None),
    "APPROVED_BY": ({"Measure", "Document", "Event"}, {"Party"}, ["approved by", "approval of", "accepted by", "批准", "审批", "确认"]),
}

PREDICATE_LABEL = {
    "HAS_DEFECT": "存在病害", "EXPOSED_TO": "暴露于", "TREATED_BY": "处置措施", "RECORDED_IN": "记录于", "ABOUT": "涉及",
    "GOVERNED_BY": "依据", "REQUESTED_BY": "提出方", "PERFORMED_ON": "作业对象", "APPROVED_BY": "批准方",
}


# Predicates where one object belongs to one subject: the subject nearest to the
# object within the same clause, else the sentence's first candidate (its topic).
SINGLE_SUBJECT = {"GOVERNED_BY", "APPROVED_BY", "REQUESTED_BY"}


def allowed(predicate: str, subject_type: str, object_type: str) -> bool:
    spec = RELATIONS.get(predicate)
    return bool(spec) and subject_type in spec[0] and object_type in spec[1]


def schema() -> dict:
    return {
        "version": "2.0",
        "types": TYPES,
        "lexicon": LEXICON,
        "relations": {p: {"domain": sorted(d), "range": sorted(r), "cues": c, "label": PREDICATE_LABEL[p]} for p, (d, r, c) in RELATIONS.items()},
    }
