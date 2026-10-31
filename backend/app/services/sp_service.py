"""存储过程解析与比对服务"""
import os
import glob
import json
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy.orm import Session

from app.models.sp import SpSource, SpDefinition, SpParseResult, LineageDiff
from app.models.job import Job, JobSource, JobTarget, TableMeta
from app.services.lineage_service import rebuild_dependencies


def pull_sp_from_git(repo_url: str, branch: str, token: str, sp_dir: str, local_path: str,
                     protocol: str = "https", username: str = "", ssh_key: str = "") -> list[dict]:
    """从 Git 拉取存储过程文件，支持 HTTPS 和 SSH 两种协议"""
    import git
    import tempfile

    clone_kwargs = {"branch": branch}

    if protocol == "ssh":
        # SSH 协议：需要设置 SSH key
        if ssh_key:
            ssh_cmd = _setup_ssh_key(ssh_key)
            clone_kwargs["env"] = {"GIT_SSH_COMMAND": ssh_cmd}

    if os.path.exists(local_path):
        repo = git.Repo(local_path)
        if protocol == "ssh" and ssh_key:
            with repo.git.custom_environment(GIT_SSH_COMMAND=ssh_cmd):
                repo.remotes.origin.pull()
        else:
            repo.remotes.origin.pull()
    else:
        if protocol == "ssh":
            repo = git.Repo.clone_from(repo_url, local_path, **clone_kwargs)
        else:
            url = repo_url
            if token:
                if username:
                    url = repo_url.replace("https://", f"https://{username}:{token}@")
                else:
                    url = repo_url.replace("https://", f"https://{token}@")
            repo = git.Repo.clone_from(url, local_path, branch=branch)

    sp_files = glob.glob(os.path.join(local_path, sp_dir, "*.sql"))
    result = []
    for f in sp_files:
        sp_name = os.path.splitext(os.path.basename(f))[0]
        with open(f, encoding="utf-8") as fh:
            sp_text = fh.read()
        result.append({"sp_name": sp_name, "sp_text": sp_text, "file_path": f})
    return result


def _setup_ssh_key(ssh_key: str) -> str:
    """设置 SSH key 到临时文件并返回 GIT_SSH_COMMAND"""
    import stat
    import tempfile
    ssh_dir = os.path.join(tempfile.gettempdir(), "lineage_ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    key_path = os.path.join(ssh_dir, "id_rsa")
    with open(key_path, "w") as f:
        f.write(ssh_key.strip() + "\n")
    os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
    return f"ssh -i {key_path} -o StrictHostKeyChecking=no"


def pull_sp_from_db(engine, schema: str = "dbo") -> list[dict]:
    """从数据库查询存储过程定义"""
    from sqlalchemy import text
    if engine.dialect.name == "mssql":
        sql = text("""
            SELECT o.name AS sp_name, m.definition AS sp_text
            FROM sys.sql_modules m
            JOIN sys.objects o ON m.object_id = o.object_id
            WHERE o.type = 'P' AND SCHEMA_NAME(o.schema_id) = :schema
        """)
    else:
        sql = text("""
            SELECT routine_name AS sp_name, routine_definition AS sp_text
            FROM information_schema.routines
            WHERE routine_type = 'PROCEDURE' AND routine_schema = :schema
        """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"schema": schema}).fetchall()
    return [{"sp_name": r[0], "sp_text": r[1] or "", "file_path": ""} for r in rows]


def save_sp_definitions(db: Session, workspace_id: str, sp_source_id: str, sp_list: list[dict]):
    """保存拉取的 SP 定义到数据库（upsert）"""
    now = datetime.now(timezone.utc)
    for item in sp_list:
        existing = (
            db.query(SpDefinition)
            .filter_by(workspace_id=workspace_id, sp_source_id=sp_source_id, sp_name=item["sp_name"])
            .first()
        )
        if existing:
            existing.sp_text = item["sp_text"]
            existing.file_path = item.get("file_path", "")
            existing.parse_status = "pending"
            existing.updated_at = now
        else:
            db.add(SpDefinition(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                sp_source_id=sp_source_id,
                sp_name=item["sp_name"],
                sp_text=item["sp_text"],
                file_path=item.get("file_path", ""),
                match_status="unmatched",
                parse_status="pending",
            ))
    # 更新同步时间
    source = db.query(SpSource).filter_by(id=sp_source_id).first()
    if source:
        source.last_sync_at = now
    db.commit()


def match_sp_to_jobs(db: Session, workspace_id: str, sp_source_id: str) -> dict:
    """自动匹配 SP 与作业"""
    sp_defs = db.query(SpDefinition).filter_by(workspace_id=workspace_id, sp_source_id=sp_source_id).all()
    jobs = db.query(Job).filter_by(workspace_id=workspace_id).all()
    job_by_name = {j.job_name.lower(): j for j in jobs}
    job_by_sp = {j.sp_name.lower(): j for j in jobs if j.sp_name}

    matched = 0
    fuzzy = 0
    unmatched = 0
    for sp_def in sp_defs:
        sp_name_lower = sp_def.sp_name.lower()
        # 1. 精确匹配作业 sp_name
        if sp_name_lower in job_by_sp:
            sp_def.matched_job_id = job_by_sp[sp_name_lower].id
            sp_def.match_status = "auto_matched"
            matched += 1
            continue
        # 2. 精确匹配作业名
        if sp_name_lower in job_by_name:
            sp_def.matched_job_id = job_by_name[sp_name_lower].id
            sp_def.match_status = "auto_matched"
            matched += 1
            continue
        # 3. 模糊匹配
        cleaned = sp_name_lower
        for prefix in ("sp_", "proc_", "p_"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        best_job = None
        best_ratio = 0.0
        for j in jobs:
            ratio = SequenceMatcher(None, cleaned, j.job_name.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_job = j
        if best_job and best_ratio >= 0.8:
            sp_def.matched_job_id = best_job.id
            sp_def.match_status = "fuzzy_matched"
            fuzzy += 1
        else:
            sp_def.match_status = "unmatched"
            unmatched += 1
    db.commit()
    return {"matched": matched, "fuzzy": fuzzy, "unmatched": unmatched}


def parse_sp_sql(sp_text: str, dialect: str = "mysql") -> dict:
    """用 sqllineage 解析 SP SQL，返回表级和字段级血缘"""
    try:
        from sqllineage.runner import LineageRunner
        r = LineageRunner(sp_text, dialect=dialect)
        source_tables = sorted({t.raw for t in r.source_tables()})
        target_tables = sorted({t.raw for t in r.target_tables()})
        try:
            column_lineage = r.get_column_lineage()
        except Exception:
            column_lineage = []

        # 尝试获取带表名的列血缘（增强字段级血缘）
        enhanced_column_lineage = _enhance_column_lineage(column_lineage, source_tables, target_tables)

        return {
            "source_tables": source_tables,
            "target_tables": target_tables,
            "column_lineage": enhanced_column_lineage,
            "status": "success",
            "error": "",
        }
    except Exception as e:
        return {"status": "failed", "error": str(e), "source_tables": [], "target_tables": [], "column_lineage": []}


def _enhance_column_lineage(column_lineage: list, source_tables: list[str], target_tables: list[str]) -> list:
    """
    增强列血缘：尝试为每个字段对关联表名。
    sqllineage 的 get_column_lineage() 返回 [[src_col, tgt_col], ...] 不含表名。
    我们尝试用 source_columns()/target_columns() 获取带表名的列信息。
    """
    if not column_lineage:
        return []

    enhanced = []
    default_src = source_tables[0] if source_tables else ""
    default_tgt = target_tables[0] if target_tables else ""

    for pair in column_lineage:
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            src_col = str(pair[0])
            tgt_col = str(pair[1])
        elif isinstance(pair, dict):
            src_col = str(pair.get("source") or pair.get("source_field") or "")
            tgt_col = str(pair.get("target") or pair.get("target_field") or "")
        else:
            continue

        # 解析可能包含的表名前缀（如 "dbo.t1.col1"）
        src_table, src_field = _split_table_col(src_col)
        tgt_table, tgt_field = _split_table_col(tgt_col)

        if not src_table:
            src_table = default_src
        if not tgt_table:
            tgt_table = default_tgt

        enhanced.append({
            "source_table": src_table,
            "source_field": src_field,
            "target_table": tgt_table,
            "target_field": tgt_field,
        })

    return enhanced


def _split_table_col(col: str) -> tuple[str, str]:
    """从 'dbo.t1.col1' 或 't1.col1' 或 'col1' 中拆分出表名和字段名"""
    col = col.strip()
    if "." in col:
        parts = col.rsplit(".", 1)
        return parts[0].strip(), parts[1].strip()
    return "", col


def parse_all_sp(db: Session, workspace_id: str, sp_source_id: str, dialect: str = "mysql") -> dict:
    """批量解析 SP，保存结果"""
    sp_defs = db.query(SpDefinition).filter_by(
        workspace_id=workspace_id, sp_source_id=sp_source_id
    ).all()
    success = 0
    failed = 0
    now = datetime.now(timezone.utc)
    for sp_def in sp_defs:
        result = parse_sp_sql(sp_def.sp_text, dialect=dialect)
        sp_def.parse_status = result["status"]
        sp_def.parse_error = result["error"]
        if result["status"] == "success":
            success += 1
            # 删除旧结果
            db.query(SpParseResult).filter_by(sp_def_id=sp_def.id).delete()
            db.add(SpParseResult(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                sp_def_id=sp_def.id,
                source_tables=json.dumps(result["source_tables"], ensure_ascii=False),
                target_tables=json.dumps(result["target_tables"], ensure_ascii=False),
                column_lineage=json.dumps(result["column_lineage"], ensure_ascii=False),
                parsed_at=now,
            ))
        else:
            failed += 1
    db.commit()
    return {"success": success, "failed": failed}


def reconcile_lineage(
    excel_sources: list[str], excel_targets: list[str],
    sp_sources: list[str], sp_targets: list[str],
    excel_field_mappings: list[dict] | None = None,
    sp_column_lineage: list | None = None,
) -> list[dict]:
    """比对 Excel 血缘与 SP 血缘，返回差异列表（含表级与字段级 mismatch）"""
    diffs = []
    es, et = set(excel_sources), set(excel_targets)
    ss, st = set(sp_sources), set(sp_targets)

    for t in ss - es:
        diffs.append({"diff_type": "source_missing", "excel_value": "", "sp_value": t, "action": "add"})
    for t in es - ss:
        diffs.append({"diff_type": "source_extra", "excel_value": t, "sp_value": "", "action": "remove"})
    for t in st - et:
        diffs.append({"diff_type": "target_missing", "excel_value": "", "sp_value": t, "action": "add"})
    for t in et - st:
        diffs.append({"diff_type": "target_extra", "excel_value": t, "sp_value": "", "action": "remove"})

    # 字段级 mismatch 比对（F-29）
    if excel_field_mappings and sp_column_lineage:
        # Excel 字段映射: [{"source_field":..., "target_field":...}]
        # SP 列血缘: [[src_col, tgt_col], ...] 或 [{"source":..., "target":...}]
        excel_pairs = set()
        for m in excel_field_mappings:
            s = m.get("source_field", "")
            t = m.get("target_field", "")
            if s and t:
                excel_pairs.add((s.lower(), t.lower()))

        sp_pairs = set()
        for cl in sp_column_lineage:
            if isinstance(cl, (list, tuple)) and len(cl) >= 2:
                sp_pairs.add((str(cl[0]).lower(), str(cl[1]).lower()))
            elif isinstance(cl, dict):
                s = cl.get("source") or cl.get("source_field") or ""
                t = cl.get("target") or cl.get("target_field") or ""
                if s and t:
                    sp_pairs.add((s.lower(), t.lower()))

        # Excel 有但 SP 没有 → mismatch（Excel 登记的字段映射在 SP 中未找到）
        for s, t in excel_pairs - sp_pairs:
            diffs.append({
                "diff_type": "mismatch",
                "excel_value": f"{s}→{t}",
                "sp_value": "",
                "action": "remove",
            })
        # SP 有但 Excel 没有 → mismatch（SP 解析出字段映射但 Excel 未登记）
        for s, t in sp_pairs - excel_pairs:
            diffs.append({
                "diff_type": "mismatch",
                "excel_value": "",
                "sp_value": f"{s}→{t}",
                "action": "add",
            })

    return diffs


def run_reconciliation(db: Session, workspace_id: str, sp_source_id: str) -> dict:
    """对所有已匹配且解析成功的 SP，执行血缘比对，生成差异"""
    sp_defs = db.query(SpDefinition).filter_by(
        workspace_id=workspace_id, sp_source_id=sp_source_id,
        match_status="auto_matched", parse_status="success",
    ).all()

    # 批量预加载所需数据，避免 N+1
    all_job_ids = {sp_def.matched_job_id for sp_def in sp_defs if sp_def.matched_job_id}
    all_sp_def_ids = {sp_def.id for sp_def in sp_defs}

    # 批量加载 JobSource/JobTarget/FieldMapping/SpParseResult
    from app.models.job import FieldMapping
    all_js = db.query(JobSource).filter(JobSource.workspace_id == workspace_id).all() if all_job_ids else []
    all_jt = db.query(JobTarget).filter(JobTarget.workspace_id == workspace_id).all() if all_job_ids else []
    all_fm = db.query(FieldMapping).filter(FieldMapping.workspace_id == workspace_id).all() if all_job_ids else []
    all_pr = db.query(SpParseResult).filter(SpParseResult.sp_def_id.in_(all_sp_def_ids)).all() if all_sp_def_ids else []

    # 表 ID -> 表名
    all_table_ids = {r.table_id for r in all_js + all_jt}
    table_map = {}
    if all_table_ids:
        tables = db.query(TableMeta).filter(TableMeta.id.in_(all_table_ids)).all()
        table_map = {t.id: t.table_name for t in tables}

    # 按作业分组
    js_by_job = {}
    for r in all_js:
        js_by_job.setdefault(r.job_id, []).append(r)
    jt_by_job = {}
    for r in all_jt:
        jt_by_job.setdefault(r.job_id, []).append(r)
    fm_by_job = {}
    for r in all_fm:
        fm_by_job.setdefault(r.job_id, []).append(r)
    pr_by_spdef = {r.sp_def_id: r for r in all_pr}

    # 清理旧的 pending 差异
    try:
        db.query(LineageDiff).filter_by(workspace_id=workspace_id, status="pending").delete()

        total_diffs = 0
        for sp_def in sp_defs:
            if not sp_def.matched_job_id:
                continue
            job_id = sp_def.matched_job_id

            excel_sources = [table_map.get(r.table_id, "") for r in js_by_job.get(job_id, []) if r.table_id in table_map]
            excel_targets = [table_map.get(r.table_id, "") for r in jt_by_job.get(job_id, []) if r.table_id in table_map]

            parse_result = pr_by_spdef.get(sp_def.id)
            if not parse_result:
                continue
            sp_sources = json.loads(parse_result.source_tables or "[]")
            sp_targets = json.loads(parse_result.target_tables or "[]")
            sp_column_lineage = json.loads(parse_result.column_lineage or "[]")

            # Excel 字段映射
            excel_field_mappings = [
                {"source_field": m.source_field, "target_field": m.target_field}
                for m in fm_by_job.get(job_id, [])
            ]

            diffs = reconcile_lineage(
                excel_sources, excel_targets, sp_sources, sp_targets,
                excel_field_mappings=excel_field_mappings,
                sp_column_lineage=sp_column_lineage,
            )
            for d in diffs:
                db.add(LineageDiff(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    job_id=job_id,
                    sp_def_id=sp_def.id,
                    diff_type=d["diff_type"],
                    excel_value=d["excel_value"],
                    sp_value=d["sp_value"],
                    status="pending",
                    action=d["action"],
            ))
            total_diffs += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"total_diffs": total_diffs}


def apply_patch(db: Session, workspace_id: str, diff_ids: list[str]) -> dict:
    """采纳差异修订（含表级与字段级 mismatch）"""
    from app.models.job import FieldMapping
    accepted = 0
    try:
        for did in diff_ids:
            diff = db.query(LineageDiff).filter_by(id=did, workspace_id=workspace_id).first()
            if not diff or diff.status != "pending":
                continue
            job_id = diff.job_id

            if diff.diff_type == "mismatch":
                # 字段级差异：excel_value/sp_value 格式为 "src→tgt"
                _apply_mismatch(db, workspace_id, job_id, diff)
            else:
                # 表级差异
                table_name = diff.sp_value or diff.excel_value
                t = db.query(TableMeta).filter_by(workspace_id=workspace_id, table_name=table_name).first()
                if not t:
                    t = TableMeta(
                        id=str(uuid.uuid4()),
                        workspace_id=workspace_id,
                        table_name=table_name,
                    )
                    db.add(t)
                    db.flush()

                if diff.diff_type in ("source_missing", "source_extra"):
                    if diff.action == "add":
                        exist = db.query(JobSource).filter_by(
                            workspace_id=workspace_id, job_id=job_id, table_id=t.id
                        ).first()
                        if not exist:
                            db.add(JobSource(
                                id=str(uuid.uuid4()),
                                workspace_id=workspace_id,
                                job_id=job_id,
                                table_id=t.id,
                            ))
                    else:
                        db.query(JobSource).filter_by(
                            workspace_id=workspace_id, job_id=job_id, table_id=t.id
                        ).delete()
                elif diff.diff_type in ("target_missing", "target_extra"):
                    if diff.action == "add":
                        exist = db.query(JobTarget).filter_by(
                            workspace_id=workspace_id, job_id=job_id, table_id=t.id
                        ).first()
                        if not exist:
                            db.add(JobTarget(
                                id=str(uuid.uuid4()),
                                workspace_id=workspace_id,
                                job_id=job_id,
                                table_id=t.id,
                            ))
                    else:
                        db.query(JobTarget).filter_by(
                            workspace_id=workspace_id, job_id=job_id, table_id=t.id
                        ).delete()

            diff.status = "accepted"
            diff.resolved_at = datetime.now(timezone.utc)
            accepted += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    # 重建受影响的依赖
    rebuild_dependencies(db, workspace_id)
    return {"accepted": accepted}


def _apply_mismatch(db: Session, workspace_id: str, job_id: str, diff: LineageDiff):
    """处理字段级 mismatch 差异"""
    from app.models.job import FieldMapping
    if diff.action == "add":
        # SP 解析出但 Excel 未登记 → 补充字段映射
        # sp_value 格式 "src→tgt" 或 "src_table.src_field→tgt_table.tgt_field"
        parts = diff.sp_value.split("→")
        if len(parts) == 2:
            src_part = parts[0].strip()
            tgt_part = parts[1].strip()
            src_table, src_field = _split_table_col(src_part)
            tgt_table, tgt_field = _split_table_col(tgt_part)

            # 尝试精确匹配表
            src_t = None
            tgt_t = None
            if src_table:
                t = db.query(TableMeta).filter_by(workspace_id=workspace_id, table_name=src_table).first()
                if t:
                    src_t = db.query(JobSource).filter_by(
                        workspace_id=workspace_id, job_id=job_id, table_id=t.id
                    ).first()
            if tgt_table:
                t = db.query(TableMeta).filter_by(workspace_id=workspace_id, table_name=tgt_table).first()
                if t:
                    tgt_t = db.query(JobTarget).filter_by(
                        workspace_id=workspace_id, job_id=job_id, table_id=t.id
                    ).first()
            # 回退到第一个源表/目标表
            if not src_t:
                src_t = db.query(JobSource).filter_by(workspace_id=workspace_id, job_id=job_id).first()
            if not tgt_t:
                tgt_t = db.query(JobTarget).filter_by(workspace_id=workspace_id, job_id=job_id).first()

            if src_t and tgt_t:
                db.add(FieldMapping(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    job_id=job_id,
                    source_table_id=src_t.table_id,
                    target_table_id=tgt_t.table_id,
                    source_field=src_field,
                    target_field=tgt_field,
                    source="sp",
                ))
    elif diff.action == "remove":
        # Excel 有但 SP 没有 → 删除该字段映射
        parts = diff.excel_value.split("→")
        if len(parts) == 2:
            src_field, tgt_field = parts[0].strip(), parts[1].strip()
            # 去掉可能的表名前缀
            if "." in src_field:
                src_field = src_field.rsplit(".", 1)[-1]
            if "." in tgt_field:
                tgt_field = tgt_field.rsplit(".", 1)[-1]
            db.query(FieldMapping).filter(
                FieldMapping.workspace_id == workspace_id,
                FieldMapping.job_id == job_id,
                FieldMapping.source_field == src_field,
                FieldMapping.target_field == tgt_field,
            ).delete()


def supplement_field_lineage(db: Session, workspace_id: str, sp_source_id: str) -> dict:
    """
    从 SP 解析结果自动补充字段级血缘到 FieldMapping 表。
    当作业已有 Excel 导入的 FieldMapping 时，只补充缺失的；无 FieldMapping 时全部补充。
    """
    from app.models.job import FieldMapping

    sp_defs = db.query(SpDefinition).filter_by(
        workspace_id=workspace_id, sp_source_id=sp_source_id,
        match_status="auto_matched", parse_status="success",
    ).all()

    added = 0
    skipped = 0

    for sp_def in sp_defs:
        if not sp_def.matched_job_id:
            continue
        job_id = sp_def.matched_job_id

        parse_result = db.query(SpParseResult).filter_by(sp_def_id=sp_def.id).first()
        if not parse_result:
            continue

        column_lineage = json.loads(parse_result.column_lineage or "[]")
        if not column_lineage:
            continue

        # 获取该作业已有的字段映射（source=excel 或 source=sp）
        existing_mappings = db.query(FieldMapping).filter_by(
            workspace_id=workspace_id, job_id=job_id
        ).all()
        existing_pairs = set()
        for m in existing_mappings:
            existing_pairs.add((m.source_field.lower(), m.target_field.lower()))

        # 获取作业的源表和目标表
        job_sources = db.query(JobSource).filter_by(
            workspace_id=workspace_id, job_id=job_id
        ).all()
        job_targets = db.query(JobTarget).filter_by(
            workspace_id=workspace_id, job_id=job_id
        ).all()
        src_tables_by_name = {}
        for js in job_sources:
            t = db.query(TableMeta).filter_by(id=js.table_id).first()
            if t:
                src_tables_by_name[t.table_name.lower()] = js.table_id
        tgt_tables_by_name = {}
        for jt in job_targets:
            t = db.query(TableMeta).filter_by(id=jt.table_id).first()
            if t:
                tgt_tables_by_name[t.table_name.lower()] = jt.table_id

        default_src_id = job_sources[0].table_id if job_sources else None
        default_tgt_id = job_targets[0].table_id if job_targets else None

        for cl in column_lineage:
            if isinstance(cl, dict):
                src_table = cl.get("source_table", "")
                src_field = cl.get("source_field", "")
                tgt_table = cl.get("target_table", "")
                tgt_field = cl.get("target_field", "")
            elif isinstance(cl, (list, tuple)) and len(cl) >= 2:
                src_field = str(cl[0])
                tgt_field = str(cl[1])
                src_table = ""
                tgt_table = ""
            else:
                continue

            if not src_field and not tgt_field:
                continue

            # 去掉可能的表名前缀
            if "." in src_field:
                src_table, src_field = _split_table_col(src_field)
            if "." in tgt_field:
                tgt_table, tgt_field = _split_table_col(tgt_field)

            pair = (src_field.lower(), tgt_field.lower())
            if pair in existing_pairs:
                skipped += 1
                continue

            # 匹配源表和目标表 ID
            src_table_id = src_tables_by_name.get(src_table.lower(), default_src_id) if src_table else default_src_id
            tgt_table_id = tgt_tables_by_name.get(tgt_table.lower(), default_tgt_id) if tgt_table else default_tgt_id

            db.add(FieldMapping(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                job_id=job_id,
                source_table_id=src_table_id,
                target_table_id=tgt_table_id,
                source_field=src_field,
                target_field=tgt_field,
                source="sp",
            ))
            existing_pairs.add(pair)
            added += 1

    db.commit()
    return {"added": added, "skipped": skipped}
