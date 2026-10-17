from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,File,Form,HTTPException,UploadFile,Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .db import init_db
from .models import TextIngest,ClaimIn,ReleaseIn
from .parser import parse_bytes
from . import service

@asynccontextmanager
async def lifespan(app:FastAPI):init_db();yield
app=FastAPI(title='InfraGraph AI',version='1.0.0',description='Transport infrastructure knowledge asset factory and engineering knowledge graph',lifespan=lifespan)
STATIC=Path(__file__).parent/'static';app.mount('/static',StaticFiles(directory=STATIC),name='static')
@app.get('/',include_in_schema=False)
def home():return FileResponse(STATIC/'index.html')
@app.get('/health')
def health():return {'status':'ok','product':'InfraGraph AI','version':'1.0.0','architecture':'ingest-extract-normalize-link-validate-publish'}
@app.post('/documents/text',status_code=201)
def ingest_text(p:TextIngest):
    try:return service.ingest_text(**p.model_dump())
    except ValueError as e:raise HTTPException(422,str(e))
@app.post('/documents/upload',status_code=201)
async def upload(file:UploadFile=File(...),source_ref:str=Form(...),authority:str=Form(''),jurisdiction:str=Form(''),lifecycle_stage:str=Form(''),domain:str=Form(''),version:str=Form('1.0')):
    b=await file.read(20*1024*1024+1)
    if len(b)>20*1024*1024:raise HTTPException(413,'file too large')
    try:text=parse_bytes(file.filename or 'upload.txt',b);return service.ingest_text(title=file.filename or source_ref,source_ref=source_ref,content=text,authority=authority,jurisdiction=jurisdiction,lifecycle_stage=lifecycle_stage,domain=domain,version=version)
    except ValueError as e:raise HTTPException(422,str(e))
@app.get('/documents')
def docs():return service.list_documents()
@app.get('/documents/{source_ref}')
def doc(source_ref:str):
    try:return service.get_document(source_ref)
    except KeyError:raise HTTPException(404,'source not found')
@app.get('/search')
def search(q:str=Query(min_length=2),limit:int=Query(10,ge=1,le=50),jurisdiction:str|None=None,asset_type:str|None=None):return {'query':q,'results':service.search(q,limit,jurisdiction,asset_type)}
@app.get('/graph')
def graph(source_ref:str|None=None,limit:int=Query(250,ge=1,le=1000)):return service.graph(source_ref,limit)
@app.post('/claims/verify')
def verify(p:ClaimIn):return service.verify_claim(p.text,p.jurisdiction)
@app.post('/releases',status_code=201)
def release(p:ReleaseIn):
    try:return service.create_release(p.version)
    except Exception as e:
        if 'UNIQUE' in str(e).upper():raise HTTPException(409,'release version exists')
        raise
@app.get('/metrics')
def metrics():return service.metrics()
