"""Model paths with scripted models: what is accepted and what is rejected."""


class Scripted:
    def __init__(self, answer=None, claim=None):
        self.answer, self.claim = answer, claim

    def complete_json(self, system, user, schema):
        assert "<data>" in user
        if schema["title"] == "grounded_answer":
            return self.answer
        if schema["title"] == "claim_check":
            return self.claim
        return None


def test_grounded_answer_is_accepted_with_valid_citations(kg):
    kg.model = Scripted(answer={"answer": "P52墩柱裂缝须采用环氧注浆修补 [P1]。", "citations": ["P1"]})
    r = kg.ask("P52 裂缝怎么修补")
    assert r["method"] == "model" and r["citations"] == ["P1"]


def test_answer_with_invented_number_or_no_citation_falls_back(kg):
    kg.model = Scripted(answer={"answer": "裂缝须在 3 天内修补 [P1]。", "citations": ["P1"]})
    assert kg.ask("P52 裂缝怎么修补")["method"] == "extractive"
    kg.model = Scripted(answer={"answer": "裂缝须修补。", "citations": []})
    assert kg.ask("P52 裂缝怎么修补")["method"] == "extractive"


def test_model_can_resolve_an_insufficient_claim_only_with_a_verbatim_quote(kg):
    claim = "TUN-01 tunnel ventilation fans require monthly maintenance"
    kg.model = Scripted(claim={"verdict": "SUPPORTED", "passage": "P1", "quote": "this text is not in the passage", "reason": "x"})
    assert kg.verify_claim(claim)["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_model_never_overturns_a_rules_contradiction(kg):
    kg.model = Scripted(claim={"verdict": "SUPPORTED", "passage": "P1", "quote": "裂缝", "reason": "x"})
    r = kg.verify_claim("P52裂缝无需修补，NCR-0042可直接关闭")
    assert r["verdict"] == "CONTRADICTED" and r["needs_review"] is True


def test_model_paraphrase_support_is_adopted_with_quote(kg):
    claim = "P52 的开裂要用环氧树脂灌浆处理"
    base = kg.verify_claim(claim)["verdict"]
    passages = kg.search(claim, top_k=8)
    idx = next(i for i, p in enumerate(passages[:5]) if "环氧注浆" in p["text"])
    kg.model = Scripted(claim={"verdict": "SUPPORTED", "passage": f"P{idx + 1}", "quote": "环氧注浆修补", "reason": "same repair"})
    r = kg.verify_claim(claim)
    assert r["verdict"] == "SUPPORTED" and (base == "SUPPORTED" or r["method"] == "model")
