from pydantic import BaseModel,Field
class TextIngest(BaseModel):
    title:str=Field(min_length=2,max_length=300)
    source_ref:str=Field(min_length=2,max_length=120)
    content:str=Field(min_length=20,max_length=200000)
    authority:str=''
    jurisdiction:str=''
    lifecycle_stage:str=''
    domain:str=''
    version:str='1.0'
class ClaimIn(BaseModel):
    text:str=Field(min_length=3,max_length=4000)
    jurisdiction:str|None=None
class ReleaseIn(BaseModel):
    version:str=Field(min_length=1,max_length=40)
