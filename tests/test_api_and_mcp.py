import asyncio
import json

from fastapi.testclient import TestClient


def test_api_flow():
    from app.main import app
    with TestClient(app) as client:
        assert client.post("/demo/load").status_code == 200
        r = client.get("/search", params={"q": "S12 吊装方案谁批准"}).json()
        assert r["results"][0]["ref"] == "PLT-LIFT-S12"
        assert client.post("/claims/verify", json={"text": "Edge protection at P47 is optional"}).json()["verdict"] == "CONTRADICTED"
        assert client.get("/entities/Asset:P52").json()["cross_lingual"]
        assert client.get("/graph").json()["edges"]
        files = {"file": ("note.txt", "P90墩发现裂缝，已开具NCR-0101。".encode(), "text/plain")}
        assert client.post("/documents/upload", data={"ref": "UP-1"}, files=files).status_code == 201
        assert client.post("/documents/upload", data={"ref": "UP-2"}, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 415
        assert client.post("/releases", json={"version": "api-1", "actor": "知识管理员 王工"}).status_code in (201, 409)
        assert client.get("/").status_code == 200


def test_mcp_tools(kg):
    from mcp import Client
    from app.mcp_server import EXPOSED, build_server

    async def go():
        async with Client(build_server(kg)) as client:
            assert {t.name for t in (await client.list_tools()).tools} == set(EXPOSED)
            r = json.loads((await client.call_tool("verify_claim", {"text": "P47临边必须设置防护栏杆"})).content[0].text)
            assert r["verdict"] == "SUPPORTED"
            e = json.loads((await client.call_tool("get_entity", {"key": "Asset:P52"})).content[0].text)
            assert e["cross_lingual"]

    asyncio.run(go())
