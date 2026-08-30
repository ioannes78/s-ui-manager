import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, get_db, SessionLocal
from .migrations import run_compat_migrations
from .models import (
    Node, CentralUser, UserNodeBinding, TaskJob, TaskTarget,
    ConfigSnapshot, AlertEvent, AuditLog,
)
from .schemas import (
    LoginIn, NodeIn, NodeUpdate, RawSaveIn, NodeActionIn,
    CentralUserIn, CentralUserUpdate, UserSyncIn,
    SnapshotIn, SnapshotRestoreIn, AlertUpdateIn,
)
from .security import (
    create_access_token, current_user, encrypt_token, decrypt_token,
    encrypt_secret, decrypt_secret,
)
from .sui import SUIClient


APP_VERSION = "2.0.1"
SNAPSHOT_OBJECTS = (
    "clients", "inbounds", "outbounds", "tls", "services",
    "endpoints", "config", "settings",
)

run_compat_migrations(engine)
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_: FastAPI):
    monitor_task = None
    if settings.health_monitor_enabled:
        monitor_task = asyncio.create_task(health_monitor_loop())
    try:
        yield
    finally:
        if monitor_task:
            monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await monitor_task


app = FastAPI(title="S-UI Manager API", version=APP_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now() -> datetime:
    return datetime.utcnow()


def safe_json(value: str, fallback):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def sui(node: Node) -> SUIClient:
    return SUIClient(
        node.base_url,
        decrypt_token(node.api_token_enc),
        node.verify_tls,
        settings.node_timeout_seconds,
    )


def audit(db: Session, actor: str, action: str, target: str = "", detail: str = ""):
    db.add(AuditLog(
        actor=actor,
        action=action,
        target=target,
        detail=detail[:10000],
    ))
    db.commit()


def extract_version(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("version", "Version", "suiVersion", "appVersion"):
            if value.get(key):
                return str(value[key])[:50]
        for nested in value.values():
            found = extract_version(nested)
            if found:
                return found
    return ""


def node_view(node: Node):
    return {
        "id": node.id,
        "name": node.name,
        "region": node.region,
        "base_url": node.base_url,
        "verify_tls": node.verify_tls,
        "enabled": node.enabled,
        "group_name": node.group_name,
        "tags": safe_json(node.tags, []),
        "notes": node.notes,
        "sui_version": node.sui_version,
        "last_latency_ms": node.last_latency_ms,
        "last_checked_at": node.last_checked_at,
        "last_ok_at": node.last_ok_at,
        "last_error": node.last_error,
        "online": bool(node.last_ok_at and not node.last_error),
        "created_at": node.created_at,
    }


def binding_view(binding: UserNodeBinding, node: Node|None = None):
    return {
        "id": binding.id,
        "node_id": binding.node_id,
        "node_name": node.name if node else "",
        "sync_status": binding.sync_status,
        "last_error": binding.last_error,
        "last_synced_at": binding.last_synced_at,
    }


def central_user_view(db: Session, central_user: CentralUser):
    bindings = (
        db.query(UserNodeBinding, Node)
        .outerjoin(Node, Node.id == UserNodeBinding.node_id)
        .filter(UserNodeBinding.user_id == central_user.id)
        .all()
    )
    secret = decrypt_secret(central_user.credential_enc)
    hint = f"••••{secret[-4:]}" if len(secret) >= 4 else "••••"
    return {
        "id": central_user.id,
        "username": central_user.username,
        "email": central_user.email,
        "credential_hint": hint,
        "enabled": central_user.enabled,
        "total_gb": central_user.total_gb,
        "used_bytes": central_user.used_bytes,
        "expire_at": central_user.expire_at,
        "limit_ip": central_user.limit_ip,
        "notes": central_user.notes,
        "bindings": [binding_view(binding, node) for binding, node in bindings],
        "created_at": central_user.created_at,
        "updated_at": central_user.updated_at,
    }


def central_user_payload(central_user: CentralUser):
    return {
        "id": central_user.username,
        "email": central_user.email or central_user.username,
        "uuid": decrypt_secret(central_user.credential_enc),
        "enable": central_user.enabled,
        "totalGB": int(central_user.total_gb * 1024 * 1024 * 1024),
        "expiryTime": int(central_user.expire_at.timestamp() * 1000) if central_user.expire_at else 0,
        "limitIp": central_user.limit_ip,
    }


def masked_payload(payload: dict):
    result = dict(payload)
    if result.get("uuid"):
        result["uuid"] = f"••••{str(result['uuid'])[-4:]}"
    return result


def task_view(job: TaskJob):
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "actor": job.actor,
        "target_count": job.target_count,
        "success_count": job.success_count,
        "failure_count": job.failure_count,
        "payload": safe_json(job.payload, {}),
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


def begin_task(db: Session, kind: str, actor: str, nodes: list[Node], payload: dict):
    job = TaskJob(
        kind=kind,
        status="running",
        actor=actor,
        target_count=len(nodes),
        payload=dump_json(payload),
    )
    db.add(job)
    db.flush()
    targets = {}
    for node in nodes:
        target = TaskTarget(
            job_id=job.id,
            node_id=node.id,
            target_name=node.name,
            status="running",
        )
        db.add(target)
        db.flush()
        targets[node.id] = target
    db.commit()
    db.refresh(job)
    return job, targets


def finish_task(db: Session, job: TaskJob, targets: dict[int, TaskTarget], results: list[dict]):
    success_count = 0
    for result in results:
        target = targets.get(result["id"])
        if not target:
            continue
        target.status = "success" if result.get("ok") else "failed"
        target.detail = dump_json(result)
        success_count += int(bool(result.get("ok")))
    job.success_count = success_count
    job.failure_count = job.target_count - success_count
    job.status = "success" if not job.failure_count else ("failed" if not success_count else "partial")
    job.finished_at = now()
    db.commit()


def alert_view(alert: AlertEvent, node: Node|None = None):
    return {
        "id": alert.id,
        "node_id": alert.node_id,
        "node_name": node.name if node else "",
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "status": alert.status,
        "message": alert.message,
        "first_seen_at": alert.first_seen_at,
        "last_seen_at": alert.last_seen_at,
        "resolved_at": alert.resolved_at,
        "acknowledged_at": alert.acknowledged_at,
    }


def upsert_down_alert(db: Session, node: Node, error: str):
    alert = (
        db.query(AlertEvent)
        .filter(
            AlertEvent.node_id == node.id,
            AlertEvent.alert_type == "node_down",
            AlertEvent.status.in_(["open", "acknowledged"]),
        )
        .first()
    )
    if alert:
        alert.last_seen_at = now()
        alert.message = error[:2000]
    else:
        db.add(AlertEvent(
            node_id=node.id,
            alert_type="node_down",
            severity="critical",
            message=error[:2000],
        ))


def resolve_down_alert(db: Session, node_id: int):
    alerts = (
        db.query(AlertEvent)
        .filter(
            AlertEvent.node_id == node_id,
            AlertEvent.alert_type == "node_down",
            AlertEvent.status.in_(["open", "acknowledged"]),
        )
        .all()
    )
    for alert in alerts:
        alert.status = "resolved"
        alert.resolved_at = now()
        alert.last_seen_at = now()


async def probe_node(node: Node):
    started = time.perf_counter()
    try:
        data = await sui(node).status()
        return {
            "id": node.id,
            "ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "version": extract_version(data),
            "data": data,
        }
    except Exception as exc:
        return {
            "id": node.id,
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


def apply_probe_result(db: Session, node: Node, result: dict):
    node.last_checked_at = now()
    node.last_latency_ms = result.get("latency_ms")
    if result.get("ok"):
        node.last_ok_at = now()
        node.last_error = ""
        if result.get("version"):
            node.sui_version = result["version"]
        resolve_down_alert(db, node.id)
    else:
        node.last_error = result.get("error", "Unknown node error")[:10000]
        upsert_down_alert(db, node, node.last_error)


async def health_monitor_loop():
    await asyncio.sleep(3)
    while True:
        db = SessionLocal()
        try:
            nodes = db.query(Node).filter(Node.enabled.is_(True)).all()
            results = await asyncio.gather(*(probe_node(node) for node in nodes))
            by_id = {node.id: node for node in nodes}
            for result in results:
                apply_probe_result(db, by_id[result["id"]], result)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        await asyncio.sleep(max(settings.health_check_interval_seconds, 15))


@app.get("/api/health")
def health():
    return {"ok": True, "name": settings.app_name, "version": APP_VERSION}


@app.get("/api/meta")
def meta(user: str = Depends(current_user)):
    return {
        "name": settings.app_name,
        "version": APP_VERSION,
        "user": user,
        "health_monitor_enabled": settings.health_monitor_enabled,
        "health_check_interval_seconds": settings.health_check_interval_seconds,
        "features": ["nodes", "central_users", "tasks", "snapshots", "alerts", "audit"],
    }


@app.post("/api/login")
def login(body: LoginIn):
    if body.username != settings.admin_username or body.password != settings.admin_password:
        raise HTTPException(401, "Invalid username/password")
    return {"access_token": create_access_token(body.username), "token_type": "bearer"}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), user: str = Depends(current_user)):
    nodes = db.query(Node).order_by(Node.id).all()
    open_alerts = db.query(AlertEvent).filter(AlertEvent.status.in_(["open", "acknowledged"])).count()
    active_users = db.query(CentralUser).filter(CentralUser.enabled.is_(True)).count()
    recent_tasks = db.query(TaskJob).order_by(TaskJob.id.desc()).limit(6).all()
    expiring = db.query(CentralUser).filter(
        CentralUser.enabled.is_(True),
        CentralUser.expire_at.is_not(None),
        CentralUser.expire_at <= datetime.fromtimestamp(time.time() + 7 * 86400),
    ).count()
    return {
        "summary": {
            "nodes": len(nodes),
            "online_nodes": sum(1 for node in nodes if node.last_ok_at and not node.last_error),
            "enabled_users": active_users,
            "expiring_users": expiring,
            "open_alerts": open_alerts,
        },
        "nodes": [node_view(node) for node in nodes],
        "recent_tasks": [task_view(job) for job in recent_tasks],
    }


@app.get("/api/nodes")
def list_nodes(
    query: str = "",
    group_name: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    statement = db.query(Node)
    if query:
        pattern = f"%{query}%"
        statement = statement.filter(or_(Node.name.ilike(pattern), Node.region.ilike(pattern), Node.tags.ilike(pattern)))
    if group_name:
        statement = statement.filter(Node.group_name == group_name)
    return [node_view(node) for node in statement.order_by(Node.group_name, Node.name).all()]


@app.post("/api/nodes")
async def add_node(body: NodeIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    if db.query(Node).filter(Node.name == body.name).first():
        raise HTTPException(409, "Node name already exists")
    node = Node(
        name=body.name,
        region=body.region,
        base_url=body.base_url.rstrip("/"),
        api_token_enc=encrypt_token(body.api_token),
        verify_tls=body.verify_tls,
        enabled=body.enabled,
        group_name=body.group_name,
        tags=dump_json(body.tags),
        notes=body.notes,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    result = await probe_node(node)
    apply_probe_result(db, node, result)
    db.commit()
    audit(db, user, "node.add", node.name, node.base_url)
    return node_view(node)


@app.patch("/api/nodes/{node_id}")
def update_node(node_id: int, body: NodeUpdate, db: Session = Depends(get_db), user: str = Depends(current_user)):
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        duplicate = db.query(Node).filter(Node.name == changes["name"], Node.id != node_id).first()
        if duplicate:
            raise HTTPException(409, "Node name already exists")
    if "api_token" in changes:
        node.api_token_enc = encrypt_token(changes.pop("api_token"))
    if "tags" in changes:
        changes["tags"] = dump_json(changes["tags"])
    for key, value in changes.items():
        setattr(node, key, value.rstrip("/") if key == "base_url" and isinstance(value, str) else value)
    db.commit()
    audit(db, user, "node.update", node.name, dump_json(changes))
    return node_view(node)


@app.delete("/api/nodes/{node_id}")
def delete_node(node_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    name = node.name
    db.query(UserNodeBinding).filter(UserNodeBinding.node_id == node_id).delete()
    db.query(ConfigSnapshot).filter(ConfigSnapshot.node_id == node_id).delete()
    db.delete(node)
    db.commit()
    audit(db, user, "node.delete", name)
    return {"ok": True}


@app.post("/api/nodes/{node_id}/test")
async def test_node(node_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    result = await probe_node(node)
    apply_probe_result(db, node, result)
    db.commit()
    return result


async def remote_node_data(node_id: int, method: str, db: Session):
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    try:
        return await getattr(sui(node), method)()
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/nodes/{node_id}/inbounds")
async def get_inbounds(node_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    return await remote_node_data(node_id, "inbounds", db)


@app.get("/api/nodes/{node_id}/clients")
async def get_clients(node_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    return await remote_node_data(node_id, "clients", db)


@app.get("/api/nodes/{node_id}/status")
async def get_status(node_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    return await remote_node_data(node_id, "status", db)


@app.get("/api/nodes/{node_id}/onlines")
async def get_onlines(node_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    return await remote_node_data(node_id, "onlines", db)


@app.get("/api/nodes/{node_id}/details")
async def node_details(node_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    methods = ("status", "clients", "inbounds", "onlines")
    results = await asyncio.gather(*(getattr(sui(node), method)() for method in methods), return_exceptions=True)
    output = {"node": node_view(node)}
    for method, result in zip(methods, results):
        output[method] = {"error": str(result)} if isinstance(result, Exception) else result
    return output


@app.post("/api/actions/restart-core")
async def restart_core(body: NodeActionIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    nodes = db.query(Node).filter(Node.id.in_(body.node_ids)).all()
    job, targets = begin_task(db, "restart_core", user, nodes, {"node_ids": body.node_ids})

    async def run(node: Node):
        try:
            return {"id": node.id, "name": node.name, "ok": True, "result": await sui(node).restart_core()}
        except Exception as exc:
            return {"id": node.id, "name": node.name, "ok": False, "error": str(exc)}

    results = await asyncio.gather(*(run(node) for node in nodes))
    finish_task(db, job, targets, results)
    audit(db, user, "batch.restart_core", ",".join(node.name for node in nodes), dump_json(results))
    return {"job_id": job.id, "results": results}


@app.post("/api/actions/raw-save")
async def raw_save(body: RawSaveIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    allowed_objects = set(SNAPSHOT_OBJECTS)
    allowed_actions = {"add", "edit", "del", "delete", "update", "save", "bulk", "editBulk"}
    if body.object not in allowed_objects:
        raise HTTPException(400, "Unsupported object")
    if body.action not in allowed_actions:
        raise HTTPException(400, "Unsupported action")
    nodes = db.query(Node).filter(Node.id.in_(body.node_ids)).all()
    job, targets = begin_task(db, "raw_save", user, nodes, {
        "node_ids": body.node_ids,
        "object": body.object,
        "action": body.action,
    })

    async def run(node: Node):
        try:
            result = await sui(node).save(body.object, body.action, body.data, body.initUsers)
            return {"id": node.id, "name": node.name, "ok": True, "result": result}
        except Exception as exc:
            return {"id": node.id, "name": node.name, "ok": False, "error": str(exc)}

    results = await asyncio.gather(*(run(node) for node in nodes))
    finish_task(db, job, targets, results)
    audit(db, user, "batch.raw_save", ",".join(node.name for node in nodes), dump_json({
        "object": body.object,
        "action": body.action,
        "result": results,
    }))
    return {"job_id": job.id, "results": results}


@app.get("/api/users")
def list_central_users(
    query: str = "",
    enabled: bool|None = None,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    statement = db.query(CentralUser)
    if query:
        pattern = f"%{query}%"
        statement = statement.filter(or_(CentralUser.username.ilike(pattern), CentralUser.email.ilike(pattern)))
    if enabled is not None:
        statement = statement.filter(CentralUser.enabled == enabled)
    return [central_user_view(db, item) for item in statement.order_by(CentralUser.id.desc()).all()]


@app.post("/api/users")
def add_central_user(body: CentralUserIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    if db.query(CentralUser).filter(CentralUser.username == body.username).first():
        raise HTTPException(409, "Username already exists")
    credential = body.credential or str(uuid.uuid4())
    item = CentralUser(
        username=body.username,
        email=body.email,
        credential_enc=encrypt_secret(credential),
        enabled=body.enabled,
        total_gb=body.total_gb,
        expire_at=body.expire_at,
        limit_ip=body.limit_ip,
        notes=body.notes,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    audit(db, user, "user.add", item.username)
    result = central_user_view(db, item)
    result["generated_credential"] = credential if body.credential is None else None
    return result


@app.patch("/api/users/{user_id}")
def update_central_user(user_id: int, body: CentralUserUpdate, db: Session = Depends(get_db), user: str = Depends(current_user)):
    item = db.get(CentralUser, user_id)
    if not item:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("username"):
        duplicate = db.query(CentralUser).filter(CentralUser.username == changes["username"], CentralUser.id != user_id).first()
        if duplicate:
            raise HTTPException(409, "Username already exists")
    if "credential" in changes:
        item.credential_enc = encrypt_secret(changes.pop("credential"))
    for key, value in changes.items():
        setattr(item, key, value)
    item.updated_at = now()
    db.commit()
    audit(db, user, "user.update", item.username, dump_json(changes))
    return central_user_view(db, item)


@app.delete("/api/users/{user_id}")
def delete_central_user(user_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    item = db.get(CentralUser, user_id)
    if not item:
        raise HTTPException(404, "User not found")
    username = item.username
    db.query(UserNodeBinding).filter(UserNodeBinding.user_id == user_id).delete()
    db.delete(item)
    db.commit()
    audit(db, user, "user.delete", username)
    return {"ok": True}


@app.post("/api/users/{user_id}/sync")
async def sync_central_user(user_id: int, body: UserSyncIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    item = db.get(CentralUser, user_id)
    if not item:
        raise HTTPException(404, "User not found")
    nodes = db.query(Node).filter(Node.id.in_(body.node_ids), Node.enabled.is_(True)).all()
    payload = central_user_payload(item)
    plan = {
        "user": item.username,
        "action": body.action,
        "nodes": [{"id": node.id, "name": node.name} for node in nodes],
        "payload": masked_payload(payload),
        "compatibility_notice": "S-UI clients fields vary by version; verify with dry-run before execution.",
    }
    if body.dry_run:
        return {"dry_run": True, "plan": plan}

    job, targets = begin_task(db, f"user_{body.action}", user, nodes, {
        "user_id": item.id,
        "username": item.username,
        "node_ids": body.node_ids,
        "action": body.action,
    })

    async def run(node: Node):
        try:
            result = await sui(node).save("clients", body.action, payload)
            return {"id": node.id, "name": node.name, "ok": True, "result": result}
        except Exception as exc:
            return {"id": node.id, "name": node.name, "ok": False, "error": str(exc)}

    results = await asyncio.gather(*(run(node) for node in nodes))
    finish_task(db, job, targets, results)
    for result in results:
        binding = db.query(UserNodeBinding).filter(
            UserNodeBinding.user_id == item.id,
            UserNodeBinding.node_id == result["id"],
        ).first()
        if not binding:
            binding = UserNodeBinding(user_id=item.id, node_id=result["id"])
            db.add(binding)
        binding.sync_status = "synced" if result.get("ok") else "failed"
        binding.last_error = result.get("error", "")
        binding.last_synced_at = now() if result.get("ok") else binding.last_synced_at
    db.commit()
    audit(db, user, f"user.sync.{body.action}", item.username, dump_json(results))
    return {"job_id": job.id, "results": results}


async def capture_snapshot(node: Node):
    async def capture(object_name: str):
        try:
            return object_name, await sui(node).raw_get(object_name)
        except Exception as exc:
            return object_name, {"_capture_error": str(exc)}

    results = await asyncio.gather(*(capture(name) for name in SNAPSHOT_OBJECTS))
    return {name: value for name, value in results}


@app.post("/api/nodes/{node_id}/snapshots")
async def create_snapshot(node_id: int, body: SnapshotIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    payload = await capture_snapshot(node)
    snapshot = ConfigSnapshot(
        node_id=node.id,
        label=body.label,
        payload=dump_json(payload),
        created_by=user,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    audit(db, user, "snapshot.create", node.name, body.label)
    return {"id": snapshot.id, "node_id": node.id, "label": snapshot.label, "created_at": snapshot.created_at}


@app.get("/api/nodes/{node_id}/snapshots")
def list_snapshots(node_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    return [{
        "id": snapshot.id,
        "node_id": snapshot.node_id,
        "label": snapshot.label,
        "created_by": snapshot.created_by,
        "created_at": snapshot.created_at,
    } for snapshot in db.query(ConfigSnapshot).filter(ConfigSnapshot.node_id == node_id).order_by(ConfigSnapshot.id.desc()).all()]


@app.get("/api/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    snapshot = db.get(ConfigSnapshot, snapshot_id)
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    return {
        "id": snapshot.id,
        "node_id": snapshot.node_id,
        "label": snapshot.label,
        "payload": safe_json(snapshot.payload, {}),
        "created_by": snapshot.created_by,
        "created_at": snapshot.created_at,
    }


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    output = {}
    if isinstance(value, dict):
        for key, nested in value.items():
            output.update(flatten(nested, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            output.update(flatten(nested, f"{prefix}[{index}]"))
    else:
        output[prefix] = value
    return output


@app.get("/api/snapshots/{snapshot_id}/diff/{other_id}")
def diff_snapshots(snapshot_id: int, other_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    left = db.get(ConfigSnapshot, snapshot_id)
    right = db.get(ConfigSnapshot, other_id)
    if not left or not right:
        raise HTTPException(404, "Snapshot not found")
    if left.node_id != right.node_id:
        raise HTTPException(400, "Snapshots belong to different nodes")
    before = flatten(safe_json(left.payload, {}))
    after = flatten(safe_json(right.payload, {}))
    changes = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            changes.append({"path": path, "before": before.get(path), "after": after.get(path)})
            if len(changes) >= 1000:
                break
    return {"left_id": snapshot_id, "right_id": other_id, "changes": changes, "truncated": len(changes) >= 1000}


@app.post("/api/snapshots/{snapshot_id}/restore")
async def restore_snapshot(snapshot_id: int, body: SnapshotRestoreIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    snapshot = db.get(ConfigSnapshot, snapshot_id)
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    node = db.get(Node, snapshot.node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    unsupported = set(body.objects) - set(SNAPSHOT_OBJECTS)
    if unsupported:
        raise HTTPException(400, f"Unsupported snapshot objects: {sorted(unsupported)}")
    payload = safe_json(snapshot.payload, {})
    plan = [{"object": name, "available": name in payload and "_capture_error" not in payload.get(name, {})} for name in body.objects]
    if body.dry_run:
        return {"dry_run": True, "node": node.name, "snapshot_id": snapshot.id, "plan": plan}

    job, targets = begin_task(db, "snapshot_restore", user, [node], {
        "snapshot_id": snapshot.id,
        "objects": body.objects,
    })
    errors = []
    responses = {}
    for name in body.objects:
        value = payload.get(name)
        if value is None or (isinstance(value, dict) and value.get("_capture_error")):
            errors.append(f"{name}: unavailable in snapshot")
            continue
        data = value.get("obj", value) if isinstance(value, dict) else value
        try:
            responses[name] = await sui(node).save(name, "save", data)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    result = {"id": node.id, "name": node.name, "ok": not errors, "responses": responses, "errors": errors}
    finish_task(db, job, targets, [result])
    audit(db, user, "snapshot.restore", node.name, dump_json({"snapshot_id": snapshot.id, "result": result}))
    return {"job_id": job.id, "result": result}


@app.get("/api/tasks")
def list_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    status: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    statement = db.query(TaskJob)
    if status:
        statement = statement.filter(TaskJob.status == status)
    return [task_view(job) for job in statement.order_by(TaskJob.id.desc()).limit(limit).all()]


@app.get("/api/tasks/{job_id}")
def get_task(job_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    job = db.get(TaskJob, job_id)
    if not job:
        raise HTTPException(404, "Task not found")
    targets = db.query(TaskTarget).filter(TaskTarget.job_id == job.id).order_by(TaskTarget.id).all()
    result = task_view(job)
    result["targets"] = [{
        "id": target.id,
        "node_id": target.node_id,
        "target_name": target.target_name,
        "status": target.status,
        "detail": safe_json(target.detail, target.detail),
    } for target in targets]
    return result


@app.get("/api/alerts")
def list_alerts(
    status: str = "",
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    statement = db.query(AlertEvent, Node).outerjoin(Node, Node.id == AlertEvent.node_id)
    if status:
        statement = statement.filter(AlertEvent.status == status)
    rows = statement.order_by(AlertEvent.id.desc()).limit(limit).all()
    return [alert_view(alert, node) for alert, node in rows]


@app.patch("/api/alerts/{alert_id}")
def update_alert(alert_id: int, body: AlertUpdateIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    alert = db.get(AlertEvent, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    if body.action == "acknowledge":
        alert.status = "acknowledged"
        alert.acknowledged_at = now()
    elif body.action == "resolve":
        alert.status = "resolved"
        alert.resolved_at = now()
    else:
        alert.status = "open"
        alert.resolved_at = None
    db.commit()
    audit(db, user, f"alert.{body.action}", str(alert.id))
    return alert_view(alert, db.get(Node, alert.node_id) if alert.node_id else None)


@app.get("/api/audit")
def get_audit(
    limit: int = Query(default=100, ge=1, le=500),
    action: str = "",
    query: str = "",
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    statement = db.query(AuditLog)
    if action:
        statement = statement.filter(AuditLog.action == action)
    if query:
        pattern = f"%{query}%"
        statement = statement.filter(or_(AuditLog.target.ilike(pattern), AuditLog.detail.ilike(pattern)))
    rows = statement.order_by(AuditLog.id.desc()).limit(limit).all()
    return [{
        "id": row.id,
        "actor": row.actor,
        "action": row.action,
        "target": row.target,
        "detail": row.detail,
        "created_at": row.created_at,
    } for row in rows]


# Native deployments normally let Nginx serve the frontend. Mounting the
# compiled files when they are available also makes local diagnostics and
# direct backend previews self-contained. API routes above keep precedence.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
