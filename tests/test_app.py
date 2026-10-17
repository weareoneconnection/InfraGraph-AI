import os,tempfile
os.environ['INFRAGRAPH_DB']=tempfile.mktemp(suffix='.db')
from fastapi.testclient import TestClient
from app.main import app

def test_ingest_graph_and_claim():
    with TestClient(app) as c:
        p={'title':'NCR','source_ref':'QA-1','content':'P52 pier crack NCR. Inspection and corrective action shall be verified before closure.','authority':'Synthetic','jurisdiction':'CN','lifecycle_stage':'construction','domain':'quality','version':'1.0'}
        r=c.post('/documents/text',json=p);assert r.status_code==201
        g=c.get('/graph').json();assert g['nodes'] and g['edges']
        v=c.post('/claims/verify',json={'text':'P52 crack corrective action'}).json();assert 'QA-1' in v['evidence_refs']

def test_release_hash():
    with TestClient(app) as c:
        c.post('/documents/text',json={'title':'HSE','source_ref':'HSE-1','content':'Work at height hazard and permit inspection evidence shall be retained.','version':'1.0'})
        r=c.post('/releases',json={'version':'1.0.0'});assert r.status_code==201 and len(r.json()['manifest_hash'])==64
