from __future__ import annotations
import json,os,tempfile
from pathlib import Path
os.environ['INFRAGRAPH_DB']=tempfile.mktemp(suffix='.db')
from app.db import init_db
from app.service import ingest_text,search,verify_claim,metrics
init_db();rows=[json.loads(x) for x in (Path(__file__).parent.parent/'data/demo_docs.jsonl').read_text().splitlines() if x.strip()]
for r in rows:ingest_text(**r)
cases=[('concrete crack corrective action','QA-NCR-001'),('variation cost schedule','COM-VAR-001'),('work at height permit','HSE-WAH-001'),('maintenance sensor telemetry','OM-SENSOR-001')]
res=[]
for q,ref in cases:
    hits=search(q,5);res.append({'query':q,'expected':ref,'found':[h['source_ref'] for h in hits],'recall':ref in [h['source_ref'] for h in hits]})
m=metrics();prov=(m['provenance_complete']/m['published_assets']) if m['published_assets'] else 0
metrics_={'recall_at_5':sum(x['recall'] for x in res)/len(res),'provenance_completeness':prov}
passed=metrics_['recall_at_5']>=0.75 and metrics_['provenance_completeness']==1
print(json.dumps({'suite':'INFRAGRAPH_KNOWLEDGE','status':'PASSED' if passed else 'FAILED','metrics':metrics_,'cases':res},ensure_ascii=False,indent=2));raise SystemExit(0 if passed else 1)
