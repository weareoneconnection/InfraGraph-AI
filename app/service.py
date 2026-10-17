from __future__ import annotations
import hashlib,json,re,uuid
from datetime import datetime,timezone
from .db import tx,connect
from .extract import extract_assets, build_relations, norm

NOW=lambda:datetime.now(timezone.utc).isoformat()
def rid(p):return f"{p}-{uuid.uuid4().hex[:10].upper()}"
def j(v):return json.dumps(v,ensure_ascii=False,sort_keys=True)

def ingest_text(*,title,source_ref,content,authority='',jurisdiction='',lifecycle_stage='',domain='',version='1.0'):
    content=' '.join(content.split()) if len(content)<200000 else content[:200000]
    if len(content.strip())<20: raise ValueError('document has insufficient extractable text')
    h=hashlib.sha256(content.encode()).hexdigest(); doc_id=rid('DOC')
    assets=extract_assets(content,source_ref)
    rels=build_relations(assets,source_ref)
    with tx() as c:
        old=c.execute('SELECT id FROM documents WHERE source_ref=?',(source_ref,)).fetchone()
        if old:
            # version replacement: retire previous assets and relations but preserve document lineage
            c.execute("UPDATE assets SET status='SUPERSEDED' WHERE source_ref=?",(source_ref,))
            c.execute('DELETE FROM relations WHERE source_ref=?',(source_ref,))
            c.execute('DELETE FROM knowledge_fts WHERE source_ref=?',(source_ref,))
            c.execute('UPDATE documents SET title=?,authority=?,jurisdiction=?,lifecycle_stage=?,domain=?,version=?,content_hash=?,content=?,status=?,created_at=? WHERE source_ref=?',
                (title,authority,jurisdiction,lifecycle_stage,domain,version,h,content,'CURRENT',NOW(),source_ref))
            doc_id=old['id']
        else:
            c.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(doc_id,title,source_ref,authority,jurisdiction,lifecycle_stage,domain,version,h,content,'CURRENT',NOW()))
        for a in assets:
            props={**a['properties'],'document_id':doc_id,'source_hash':h,'authority':authority,'jurisdiction':jurisdiction,'lifecycle_stage':lifecycle_stage,'domain':domain,'version':version}
            complete=int(bool(source_ref and h and version))
            c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?)',(a['id'],a['asset_type'],a['canonical_name'],norm(a['canonical_name']),j(props),source_ref,a['confidence'],complete,'PUBLISHED',NOW()))
            body=f"{a['canonical_name']} {a['asset_type']} {content[:3000]}"
            c.execute('INSERT INTO knowledge_fts(asset_id,canonical_name,asset_type,source_ref,body) VALUES(?,?,?,?,?)',(a['id'],a['canonical_name'],a['asset_type'],source_ref,body))
        for r in rels:
            c.execute('INSERT OR IGNORE INTO relations VALUES(?,?,?,?,?,?,?)',(r['id'],r['subject_id'],r['predicate'],r['object_id'],r['source_ref'],r['confidence'],NOW()))
    return get_document(source_ref)

def get_document(source_ref):
    with connect() as c:
        d=c.execute('SELECT * FROM documents WHERE source_ref=?',(source_ref,)).fetchone()
        if not d: raise KeyError(source_ref)
        out=dict(d)
        out['assets']=[dict(r) for r in c.execute("SELECT id,asset_type,canonical_name,source_ref,confidence,provenance_complete,status FROM assets WHERE source_ref=? AND status='PUBLISHED'",(source_ref,))]
        ids=[x['id'] for x in out['assets']]
        if ids:
            q=','.join('?'*len(ids)); out['relations']=[dict(r) for r in c.execute(f'SELECT * FROM relations WHERE subject_id IN ({q}) OR object_id IN ({q})',ids+ids)]
        else: out['relations']=[]
        return out

def list_documents():
    with connect() as c:return [dict(r) for r in c.execute('SELECT id,title,source_ref,authority,jurisdiction,lifecycle_stage,domain,version,content_hash,status,created_at FROM documents ORDER BY created_at DESC')]

def search(query:str,limit:int=10,jurisdiction:str|None=None,asset_type:str|None=None):
    terms=[x for x in re.findall(r'[A-Za-z0-9_\-\u4e00-\u9fff]+',query) if len(x)>1]
    match=' OR '.join(f'"{t}"' for t in terms[:12]) or '"__none__"'
    sql="SELECT f.asset_id,bm25(knowledge_fts) score,a.asset_type,a.canonical_name,a.source_ref,a.confidence,a.properties,d.jurisdiction,d.version,d.content_hash FROM knowledge_fts f JOIN assets a ON a.id=f.asset_id JOIN documents d ON d.source_ref=a.source_ref WHERE knowledge_fts MATCH ? AND a.status='PUBLISHED'"
    args=[match]
    if jurisdiction: sql+=' AND (d.jurisdiction=? OR d.jurisdiction=\'\')'; args.append(jurisdiction)
    if asset_type: sql+=' AND a.asset_type=?'; args.append(asset_type)
    sql+=' ORDER BY score LIMIT ?'; args.append(limit)
    try:
        with connect() as c: rows=[dict(r) for r in c.execute(sql,args)]
    except Exception:
        rows=[]
    for r in rows:
        r['properties']=json.loads(r['properties']); r['relevance']=round(max(0.0,1.0/(1.0+abs(r.pop('score')))),4)
    return rows

def graph(source_ref:str|None=None,limit:int=250):
    with connect() as c:
        if source_ref:
            nodes=[dict(r) for r in c.execute("SELECT id,asset_type,canonical_name,source_ref,confidence,status FROM assets WHERE source_ref=? AND status='PUBLISHED' LIMIT ?",(source_ref,limit))]
        else:
            nodes=[dict(r) for r in c.execute("SELECT id,asset_type,canonical_name,source_ref,confidence,status FROM assets WHERE status='PUBLISHED' LIMIT ?",(limit,))]
        ids=[n['id'] for n in nodes]
        if not ids:return {'nodes':[],'edges':[]}
        q=','.join('?'*len(ids)); edges=[dict(r) for r in c.execute(f'SELECT id,subject_id,predicate,object_id,source_ref,confidence FROM relations WHERE subject_id IN ({q}) AND object_id IN ({q})',ids+ids)]
        return {'nodes':nodes,'edges':edges}

def verify_claim(text:str,jurisdiction:str|None=None):
    hits=search(text,5,jurisdiction)
    refs=[]
    for h in hits:
        if h['source_ref'] not in refs:refs.append(h['source_ref'])
    status='SUPPORTED' if hits and hits[0]['relevance']>=0.3 else 'INSUFFICIENT_EVIDENCE'
    cid=rid('CLM')
    with tx() as c:c.execute('INSERT INTO claims VALUES(?,?,?,?,?)',(cid,text,status,j(refs),NOW()))
    return {'claim_id':cid,'text':text,'status':status,'evidence_refs':refs,'hits':hits}

def create_release(version:str):
    with tx() as c:
        assets=c.execute("SELECT id,asset_type,canonical_name,source_ref,properties FROM assets WHERE status='PUBLISHED' ORDER BY id").fetchall()
        rels=c.execute('SELECT subject_id,predicate,object_id,source_ref FROM relations ORDER BY id').fetchall()
        manifest={'assets':[dict(x) for x in assets],'relations':[dict(x) for x in rels]}
        h=hashlib.sha256(j(manifest).encode()).hexdigest(); rid_=rid('REL')
        c.execute('INSERT INTO releases VALUES(?,?,?,?,?,?,?)',(rid_,version,h,len(assets),len(rels),'PUBLISHED',NOW()))
    return {'id':rid_,'version':version,'manifest_hash':h,'asset_count':len(assets),'relation_count':len(rels),'status':'PUBLISHED'}

def metrics():
    with connect() as c:
        return {
            'documents':c.execute('SELECT COUNT(*) n FROM documents').fetchone()['n'],
            'published_assets':c.execute("SELECT COUNT(*) n FROM assets WHERE status='PUBLISHED'").fetchone()['n'],
            'relations':c.execute('SELECT COUNT(*) n FROM relations').fetchone()['n'],
            'provenance_complete':c.execute("SELECT COUNT(*) n FROM assets WHERE status='PUBLISHED' AND provenance_complete=1").fetchone()['n'],
            'classes':{r['asset_type']:r['n'] for r in c.execute("SELECT asset_type,COUNT(*) n FROM assets WHERE status='PUBLISHED' GROUP BY asset_type")},
        }
