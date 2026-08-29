import asyncio, json
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, engine, get_db
from .models import Node, AuditLog
from .schemas import LoginIn, NodeIn, NodeUpdate, RawSaveIn, NodeActionIn
from .security import create_access_token, current_user, encrypt_token, decrypt_token
from .sui import SUIClient

Base.metadata.create_all(bind=engine)

app = FastAPI(title="S-UI Manager API", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
def health():
    return {"ok": True, "name": settings.app_name, "version": "1.1.0"}

@app.post("/api/login")
def login(body: LoginIn):
    if body.username != settings.admin_username or body.password != settings.admin_password:
        raise HTTPException(401, "Invalid username/password")
    return {"access_token": create_access_token(body.username), "token_type": "bearer"}

def node_view(n: Node):
    return {
        "id": n.id, "name": n.name, "region": n.region, "base_url": n.base_url,
        "verify_tls": n.verify_tls, "enabled": n.enabled,
        "last_ok_at": n.last_ok_at.isoformat() if n.last_ok_at else None,
        "last_error": n.last_error
    }

def sui(n: Node):
    return SUIClient(n.base_url, decrypt_token(n.api_token_enc), n.verify_tls, settings.node_timeout_seconds)

def audit(db: Session, actor: str, action: str, target: str="", detail: str=""):
    db.add(AuditLog(actor=actor, action=action, target=target, detail=detail[:10000]))
    db.commit()

@app.get("/api/nodes")
def list_nodes(db: Session=Depends(get_db), user: str=Depends(current_user)):
    return [node_view(n) for n in db.query(Node).order_by(Node.id).all()]

@app.post("/api/nodes")
async def add_node(body: NodeIn, db: Session=Depends(get_db), user: str=Depends(current_user)):
    if db.query(Node).filter(Node.name == body.name).first():
        raise HTTPException(409, "Node name already exists")
    n = Node(name=body.name, region=body.region, base_url=body.base_url.rstrip("/"),
             api_token_enc=encrypt_token(body.api_token), verify_tls=body.verify_tls, enabled=body.enabled)
    db.add(n); db.commit(); db.refresh(n)
    try:
        await sui(n).status()
        n.last_ok_at = datetime.utcnow(); n.last_error = ""
    except Exception as e:
        n.last_error = str(e)
    db.commit()
    audit(db, user, "node.add", n.name, n.base_url)
    return node_view(n)

@app.patch("/api/nodes/{node_id}")
def update_node(node_id: int, body: NodeUpdate, db: Session=Depends(get_db), user: str=Depends(current_user)):
    n = db.get(Node, node_id)
    if not n: raise HTTPException(404, "Node not found")
    d = body.model_dump(exclude_unset=True)
    if "api_token" in d:
        n.api_token_enc = encrypt_token(d.pop("api_token"))
    for k,v in d.items():
        setattr(n,k,v.rstrip("/") if k=="base_url" and isinstance(v,str) else v)
    db.commit()
    audit(db, user, "node.update", n.name, json.dumps(d, ensure_ascii=False, default=str))
    return node_view(n)

@app.delete("/api/nodes/{node_id}")
def delete_node(node_id: int, db: Session=Depends(get_db), user: str=Depends(current_user)):
    n = db.get(Node, node_id)
    if not n: raise HTTPException(404, "Node not found")
    name=n.name
    db.delete(n); db.commit()
    audit(db, user, "node.delete", name)
    return {"ok": True}

@app.post("/api/nodes/{node_id}/test")
async def test_node(node_id: int, db: Session=Depends(get_db), user: str=Depends(current_user)):
    n = db.get(Node, node_id)
    if not n: raise HTTPException(404, "Node not found")
    try:
        data = await sui(n).status()
        n.last_ok_at = datetime.utcnow(); n.last_error = ""; db.commit()
        return {"ok": True, "data": data}
    except Exception as e:
        n.last_error = str(e); db.commit()
        return {"ok": False, "error": str(e)}

@app.get("/api/nodes/{node_id}/inbounds")
async def get_inbounds(node_id: int, db: Session=Depends(get_db), user: str=Depends(current_user)):
    n=db.get(Node,node_id)
    if not n: raise HTTPException(404,"Node not found")
    return await sui(n).inbounds()

@app.get("/api/nodes/{node_id}/clients")
async def get_clients(node_id: int, db: Session=Depends(get_db), user: str=Depends(current_user)):
    n=db.get(Node,node_id)
    if not n: raise HTTPException(404,"Node not found")
    return await sui(n).clients()

@app.get("/api/nodes/{node_id}/status")
async def get_status(node_id: int, db: Session=Depends(get_db), user: str=Depends(current_user)):
    n=db.get(Node,node_id)
    if not n: raise HTTPException(404,"Node not found")
    return await sui(n).status()

@app.get("/api/nodes/{node_id}/onlines")
async def get_onlines(node_id: int, db: Session=Depends(get_db), user: str=Depends(current_user)):
    n=db.get(Node,node_id)
    if not n: raise HTTPException(404,"Node not found")
    return await sui(n).onlines()

@app.get("/api/dashboard")
async def dashboard(db: Session=Depends(get_db), user: str=Depends(current_user)):
    nodes=db.query(Node).filter(Node.enabled == True).order_by(Node.id).all()
    async def one(n):
        out={"node":node_view(n),"online":False,"status":None,"clients":None,"inbounds":None}
        try:
            st, cl, ib = await asyncio.gather(sui(n).status(), sui(n).clients(), sui(n).inbounds())
            out.update({"online":True,"status":st,"clients":cl,"inbounds":ib})
            n.last_ok_at=datetime.utcnow(); n.last_error=""
        except Exception as e:
            n.last_error=str(e); out["error"]=str(e)
        return out
    res=await asyncio.gather(*(one(n) for n in nodes))
    db.commit()
    return {"nodes":res}

@app.post("/api/actions/restart-core")
async def restart_core(body: NodeActionIn, db: Session=Depends(get_db), user: str=Depends(current_user)):
    nodes=db.query(Node).filter(Node.id.in_(body.node_ids)).all()
    async def run(n):
        try: return {"id":n.id,"name":n.name,"ok":True,"result":await sui(n).restart_core()}
        except Exception as e: return {"id":n.id,"name":n.name,"ok":False,"error":str(e)}
    result=await asyncio.gather(*(run(n) for n in nodes))
    audit(db,user,"batch.restart_core",",".join(n.name for n in nodes),json.dumps(result,ensure_ascii=False,default=str))
    return result

@app.post("/api/actions/raw-save")
async def raw_save(body: RawSaveIn, db: Session=Depends(get_db), user: str=Depends(current_user)):
    allowed_objects={"clients","tls","inbounds","outbounds","services","endpoints","config","settings"}
    allowed_actions={"add","edit","del","delete","update","save","bulk","editBulk"}
    if body.object not in allowed_objects:
        raise HTTPException(400,"Unsupported object")
    if body.action not in allowed_actions:
        raise HTTPException(400,"Unsupported action")
    nodes=db.query(Node).filter(Node.id.in_(body.node_ids)).all()
    async def run(n):
        try:
            r=await sui(n).save(body.object,body.action,body.data,body.initUsers)
            return {"id":n.id,"name":n.name,"ok":True,"result":r}
        except Exception as e:
            return {"id":n.id,"name":n.name,"ok":False,"error":str(e)}
    result=await asyncio.gather(*(run(n) for n in nodes))
    audit(db,user,"batch.raw_save",",".join(n.name for n in nodes),
          json.dumps({"object":body.object,"action":body.action,"result":result},ensure_ascii=False,default=str))
    return result

@app.get("/api/audit")
def get_audit(limit: int=100, db: Session=Depends(get_db), user: str=Depends(current_user)):
    rows=db.query(AuditLog).order_by(AuditLog.id.desc()).limit(min(max(limit,1),500)).all()
    return [{"id":r.id,"actor":r.actor,"action":r.action,"target":r.target,"detail":r.detail,
             "created_at":r.created_at.isoformat()} for r in rows]
