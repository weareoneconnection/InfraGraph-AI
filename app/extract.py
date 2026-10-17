from __future__ import annotations
import hashlib,re,uuid
from .ontology import CLASSES, RELATION_RULES

def eid(prefix='KA'):return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"

def norm(s:str)->str:
    return re.sub(r'\s+',' ',re.sub(r'[^\w\-\u4e00-\u9fff ]+',' ',s.lower())).strip()

def extract_assets(text:str,source_ref:str)->list[dict]:
    low=text.lower(); out=[]
    # project/asset identifiers such as P47, ST12, BRG-03, TUN-01
    ids=set(re.findall(r'\b(?:P\d{1,4}|ST\d{1,3}|BRG[- ]?\d{1,3}|TUN[- ]?\d{1,3}|WP[- ]?[A-Z0-9]+)\b',text,re.I))
    for x in sorted(ids):
        out.append({'id':eid(),'asset_type':'Asset','canonical_name':x.upper().replace(' ', '-'),'properties':{'identifier':x},'confidence':0.98})
    for klass,terms in CLASSES.items():
        hits=[t for t in terms if t.lower() in low]
        if not hits: continue
        # create one knowledge asset per class occurrence cluster to keep demo graph concise
        snippet=' '.join(text.split())[:240]
        name=f"{klass}: {hits[0]}"
        out.append({'id':eid(),'asset_type':klass,'canonical_name':name,'properties':{'matched_terms':hits[:6],'snippet':snippet},'confidence':0.90})
    # deterministic dedupe within document
    uniq={}
    for a in out: uniq[(a['asset_type'],norm(a['canonical_name']))]=a
    return list(uniq.values())

def build_relations(assets:list[dict],source_ref:str)->list[dict]:
    by={}
    for a in assets:by.setdefault(a['asset_type'],[]).append(a)
    rels=[]
    for s,p,o in RELATION_RULES:
        if by.get(s) and by.get(o):
            for sa in by[s][:2]:
                for oa in by[o][:2]:
                    rels.append({'id':eid('REL'),'subject_id':sa['id'],'predicate':p,'object_id':oa['id'],'source_ref':source_ref,'confidence':0.86})
    # link all typed knowledge back to an explicit Asset identifier when present
    if by.get('Asset'):
        root=by['Asset'][0]
        for a in assets:
            if a['id']!=root['id'] and a['asset_type'] in {'NCR','Inspection','Variation','Claim','Hazard','MaintenanceTask'}:
                rels.append({'id':eid('REL'),'subject_id':a['id'],'predicate':'ABOUT','object_id':root['id'],'source_ref':source_ref,'confidence':0.88})
    return rels
