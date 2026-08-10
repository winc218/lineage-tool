"""血缘解析服务 - 基于 networkx 构建有向图，计算作业依赖、环路、影响/溯源"""
from collections import defaultdict
import networkx as nx
from sqlalchemy.orm import Session

from app.models.job import Job, JobSource, JobTarget, JobDependency, TableMeta


def build_graph(db: Session, workspace_id: str) -> nx.DiGraph:
    """构建工作空间的有向依赖图（批量加载避免 N+1）"""
    g = nx.DiGraph()
    jobs = db.query(Job).filter_by(workspace_id=workspace_id).all()
    for j in jobs:
        g.add_node(j.id, job_name=j.job_name, job_type=j.job_type, sp_name=j.sp_name)

    # 批量加载所有源/目标关系与表元数据，避免 N+1
    all_targets = db.query(JobTarget).filter_by(workspace_id=workspace_id).all()
    all_sources = db.query(JobSource).filter_by(workspace_id=workspace_id).all()
    table_ids = {jt.table_id for jt in all_targets} | {js.table_id for js in all_sources}
    table_map = {}
    if table_ids:
        tables = db.query(TableMeta).filter(TableMeta.id.in_(table_ids)).all()
        table_map = {t.id: t for t in tables}

    # 表名 -> 生产者作业列表
    table_name_to_producers: dict[str, list[str]] = defaultdict(list)
    for jt in all_targets:
        t = table_map.get(jt.table_id)
        if t:
            table_name_to_producers[t.table_name].append(jt.job_id)

    for js in all_sources:
        t = table_map.get(js.table_id)
        if not t:
            continue
        for producer in table_name_to_producers.get(t.table_name, []):
            if producer != js.job_id:
                g.add_edge(producer, js.job_id, via_table=t.table_name)
    return g


def rebuild_dependencies(db: Session, workspace_id: str):
    """重新计算并持久化 job_dependency 表（先构建内存集合，再事务内 delete+insert）"""
    import uuid
    g = build_graph(db, workspace_id)
    # 收集 via_table_name -> table_id 映射
    via_names = {data.get("via_table", "") for _, _, data in g.edges(data=True) if data.get("via_table")}
    table_map = {}
    if via_names:
        tables = db.query(TableMeta).filter(
            TableMeta.workspace_id == workspace_id,
            TableMeta.table_name.in_(via_names),
        ).all()
        table_map = {t.table_name: t.id for t in tables}

    # 先在内存构建新边集合，再事务内原子替换
    new_deps = []
    for u, v, data in g.edges(data=True):
        via_name = data.get("via_table", "")
        new_deps.append(JobDependency(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            upstream_job_id=u,
            downstream_job_id=v,
            via_table_id=table_map.get(via_name, ""),
            via_table_name=via_name,
            source="excel",
        ))

    try:
        db.query(JobDependency).filter_by(workspace_id=workspace_id).delete()
        for dep in new_deps:
            db.add(dep)
        db.commit()
    except Exception:
        db.rollback()
        raise


def detect_cycles(db: Session, workspace_id: str) -> list[list[dict]]:
    """检测环路，返回每个环的作业信息列表"""
    g = build_graph(db, workspace_id)
    return _cycles_from_graph(g, db, workspace_id)


def _cycles_from_graph(g: nx.DiGraph, db: Session, workspace_id: str) -> list[list[dict]]:
    """从已构建的图提取环路（避免重复构建）"""
    jobs = {j.id: j for j in db.query(Job).filter_by(workspace_id=workspace_id).all()}
    cycles = []
    for cycle_ids in nx.simple_cycles(g):
        cycles.append([
            {"job_id": jid, "job_name": jobs[jid].job_name if jid in jobs else jid}
            for jid in cycle_ids
        ])
    return cycles


def impact_analysis(db: Session, workspace_id: str, job_id: str) -> list[dict]:
    """影响分析：下游所有作业"""
    g = build_graph(db, workspace_id)
    if job_id not in g:
        return []
    jobs = {j.id: j for j in db.query(Job).filter_by(workspace_id=workspace_id).all()}
    descendants = nx.descendants(g, job_id)
    return [
        {"job_id": jid, "job_name": jobs[jid].job_name}
        for jid in descendants if jid in jobs
    ]


def root_cause_analysis(db: Session, workspace_id: str, job_id: str) -> list[dict]:
    """溯源分析：上游所有作业"""
    g = build_graph(db, workspace_id)
    if job_id not in g:
        return []
    jobs = {j.id: j for j in db.query(Job).filter_by(workspace_id=workspace_id).all()}
    ancestors = nx.ancestors(g, job_id)
    return [
        {"job_id": jid, "job_name": jobs[jid].job_name}
        for jid in ancestors if jid in jobs
    ]


def graph_data(db: Session, workspace_id: str) -> dict:
    """返回前端 G6 所需的 nodes/edges 结构（复用已构建图，避免重复）"""
    g = build_graph(db, workspace_id)
    jobs = {j.id: j for j in db.query(Job).filter_by(workspace_id=workspace_id).all()}
    nodes = []
    for nid in g.nodes():
        j = jobs.get(nid)
        nodes.append({
            "id": nid,
            "label": j.job_name if j else nid,
            "job_type": j.job_type if j else "",
            "sp_name": j.sp_name if j else "",
            "degree": g.degree(nid),
        })
    edges = []
    for u, v, data in g.edges(data=True):
        edges.append({"source": u, "target": v, "via_table": data.get("via_table", "")})
    # 复用 g 提取环路，避免重复 build_graph
    cycles = _cycles_from_graph(g, db, workspace_id)
    return {"nodes": nodes, "edges": edges, "cycles": cycles}
