from app.extract import extract, resolve
from app.ontology import allowed


def triples(text):
    return {(r.subject, r.predicate, r.object) for r in extract(text).relations}


def test_chinese_and_english_produce_the_same_graph():
    zh = triples("P52墩柱拆模后发现裂缝，已开具NCR-0042。裂缝须采用环氧注浆修补，并按照GB 50204-2015进行复检。")
    en = triples("A crack was found on Pier P52 after formwork removal and recorded in NCR-0042. "
                 "The crack shall be repaired by epoxy injection, and re-inspection is carried out in accordance with GB 50204-2015.")
    assert ("Asset:P52", "HAS_DEFECT", "Defect:crack") in zh & en
    assert ("Defect:crack", "TREATED_BY", "Measure:epoxy injection") in zh & en
    assert ("Measure:re-inspection", "GOVERNED_BY", "Standard:GB 50204-2015") in zh & en


def test_identifiers_normalise():
    assert resolve("Asset", "Pier P47") == "P47" and resolve("Asset", "P47墩") == "P47"
    assert resolve("Defect", "裂缝") == "crack"
    keys = {m.key for m in extract("The variation is valued under Sub-Clause 13.3. 依据第8.4条通知。按照JTG H11-2004评定。").mentions}
    assert {"Clause:Clause 13.3", "Clause:Clause 8.4", "Standard:JTG H11-2004"} <= keys


def test_step_numbers_are_not_clauses():
    assert not [m for m in extract("第3步：检查P47墩临边防护。").mentions if m.type == "Clause"]


def test_governed_by_attaches_to_the_nearest_subject_in_the_clause():
    t = triples("裂缝须采用环氧注浆修补，并按照GB 50204-2015进行复检。")
    assert ("Measure:re-inspection", "GOVERNED_BY", "Standard:GB 50204-2015") in t
    assert ("Measure:epoxy injection", "GOVERNED_BY", "Standard:GB 50204-2015") not in t


def test_ambiguous_cooccurrence_goes_to_review():
    rels = extract("巡检发现P70和P71墩存在裂缝和剥落。").relations
    assert rels and all(r.confidence < 0.7 for r in rels)


def test_relations_respect_the_ontology():
    assert allowed("HAS_DEFECT", "Asset", "Defect") and not allowed("HAS_DEFECT", "Defect", "Asset")


def test_every_relation_quotes_its_sentence():
    text = "P47墩盖梁施工属于高处作业，作业面存在临边。\n临边必须设置防护栏杆。"
    for r in extract(text).relations:
        assert text[r.start:r.end] == r.quote


class Hostile:
    def complete_json(self, system, user, schema):
        return {"entities": [{"type": "Asset", "name": "P99", "quote": "P99 pier collapsed"},
                             {"type": "Defect", "name": "crack", "quote": "裂缝"}],
                "relations": [{"subject_type": "Defect", "subject": "crack", "predicate": "HAS_DEFECT", "object_type": "Asset", "object": "P52"},
                              {"subject_type": "Asset", "subject": "P99", "predicate": "HAS_DEFECT", "object_type": "Defect", "object": "crack"}]}


def test_model_items_must_quote_the_sentence_and_fit_the_ontology():
    result = extract("P52墩柱发现裂缝。", model=Hostile())
    keys = {m.key for m in result.mentions}
    assert "Asset:P99" not in keys  # quote not in the sentence
    assert ("Defect:crack", "HAS_DEFECT", "Asset:P52") not in {(r.subject, r.predicate, r.object) for r in result.relations}
