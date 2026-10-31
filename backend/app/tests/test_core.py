"""核心功能测试：认证、工作空间、Excel 导入、血缘解析、SP 比对"""
import os
import io
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """每个测试模块共享一个 client，启动时建表"""
    # 确保测试用独立数据库
    os.environ["DATA_DIR"] = "./test_data"
    os.environ["DB_MODE"] = "sqlite"
    # 清理旧测试库
    db_path = "./test_data/lineage.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_token(client):
    """获取管理员 token"""
    res = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def workspace_id(client, headers):
    """创建测试工作空间"""
    res = client.post("/api/workspaces", json={"name": "测试空间", "description": "测试"}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["id"]


class TestAuth:
    """认证测试"""

    def test_login_success(self, client):
        res = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
        assert res.status_code == 200
        assert "access_token" in res.json()

    def test_login_wrong_password(self, client):
        res = client.post("/api/auth/login", data={"username": "admin", "password": "wrong"})
        assert res.status_code == 401

    def test_me(self, client, headers):
        res = client.get("/api/auth/me", headers=headers)
        assert res.status_code == 200
        assert res.json()["username"] == "admin"


class TestWorkspace:
    """工作空间测试"""

    def test_list_workspaces(self, client, headers, workspace_id):
        res = client.get("/api/workspaces", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) >= 1
        assert any(w["id"] == workspace_id for w in res.json())

    def test_list_members(self, client, headers, workspace_id):
        res = client.get(f"/api/workspaces/{workspace_id}/members", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) >= 1
        assert res.json()[0]["role"] == "OWNER"


class TestExcelImport:
    """Excel 导入测试"""

    def _make_excel(self) -> bytes:
        """生成测试 Excel"""
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["作业名", "源表", "目标表", "类型"])
        ws.append(["job_a", "dbo.t_src_1", "dbo.t_tgt_1", "ETL"])
        ws.append(["job_b", "dbo.t_tgt_1", "dbo.t_tgt_2", "ETL"])  # 依赖 job_a
        ws.append(["job_c", "dbo.t_tgt_2", "dbo.t_tgt_3", "ETL"])  # 依赖 job_b
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def test_parse_excel(self, client, headers):
        excel = self._make_excel()
        res = client.post(
            "/api/import/parse",
            files={"file": ("test.xlsx", excel, "application/vnd.ms-excel")},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["count"] == 3
        assert "作业名" in data["headers"]

    def test_validate_excel(self, client, headers):
        excel = self._make_excel()
        mapping = {"作业名": "job_name", "源表": "source_tables", "目标表": "target_tables", "类型": "job_type"}
        res = client.post(
            "/api/import/validate",
            data={"mapping": json.dumps(mapping)},
            files={"file": ("test.xlsx", excel, "application/vnd.ms-excel")},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["valid"] is True
        assert data["total_valid"] == 3

    def test_confirm_import(self, client, headers, workspace_id):
        excel = self._make_excel()
        mapping = {"作业名": "job_name", "源表": "source_tables", "目标表": "target_tables", "类型": "job_type"}
        res = client.post(
            f"/api/import/confirm/{workspace_id}",
            data={"mapping": json.dumps(mapping)},
            files={"file": ("test.xlsx", excel, "application/vnd.ms-excel")},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["job_count"] == 3


class TestLineage:
    """血缘分析测试"""

    def test_graph_has_3_nodes(self, client, headers, workspace_id):
        res = client.get(f"/api/lineage/graph/{workspace_id}", headers=headers)
        assert res.status_code == 200, res.text
        data = res.json()
        assert len(data["nodes"]) == 3
        # job_a -> job_b -> job_c，应有 2 条边
        assert len(data["edges"]) == 2

    def test_no_cycles(self, client, headers, workspace_id):
        res = client.get(f"/api/lineage/cycles/{workspace_id}", headers=headers)
        assert res.status_code == 200
        assert len(res.json()["cycles"]) == 0

    def test_impact_analysis(self, client, headers, workspace_id):
        # 获取 job_a 的 id
        res = client.get(f"/api/jobs/list/{workspace_id}", params={"keyword": "job_a"}, headers=headers)
        job_a_id = res.json()[0]["id"]
        # 影响分析：job_a 的下游应包含 job_b 和 job_c
        res = client.get(f"/api/lineage/impact/{workspace_id}/{job_a_id}", headers=headers)
        assert res.status_code == 200
        downstream = res.json()["downstream"]
        names = {d["job_name"] for d in downstream}
        assert names == {"job_b", "job_c"}

    def test_trace_analysis(self, client, headers, workspace_id):
        res = client.get(f"/api/jobs/list/{workspace_id}", params={"keyword": "job_c"}, headers=headers)
        job_c_id = res.json()[0]["id"]
        res = client.get(f"/api/lineage/trace/{workspace_id}/{job_c_id}", headers=headers)
        upstream = res.json()["upstream"]
        names = {u["job_name"] for u in upstream}
        assert names == {"job_a", "job_b"}


class TestJobManagement:
    """作业管理测试"""

    def test_list_jobs(self, client, headers, workspace_id):
        res = client.get(f"/api/jobs/list/{workspace_id}", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) == 3

    def test_job_detail(self, client, headers, workspace_id):
        res = client.get(f"/api/jobs/list/{workspace_id}", params={"keyword": "job_a"}, headers=headers)
        job_id = res.json()[0]["id"]
        res = client.get(f"/api/jobs/detail/{workspace_id}/{job_id}", headers=headers)
        assert res.status_code == 200
        detail = res.json()
        assert detail["job_name"] == "job_a"
        assert len(detail["source_tables"]) == 1
        assert len(detail["target_tables"]) == 1
        assert detail["source_tables"][0]["table_name"] == "dbo.t_src_1"

    def test_update_job(self, client, headers, workspace_id):
        res = client.get(f"/api/jobs/list/{workspace_id}", params={"keyword": "job_a"}, headers=headers)
        job_id = res.json()[0]["id"]
        res = client.put(
            f"/api/jobs/{workspace_id}/{job_id}",
            json={"description": "更新描述", "sp_name": "test_sp_update"},
            headers=headers,
        )
        assert res.status_code == 200
        # 验证更新
        res = client.get(f"/api/jobs/detail/{workspace_id}/{job_id}", headers=headers)
        assert res.json()["description"] == "更新描述"
        assert res.json()["sp_name"] == "test_sp_update"


class TestSpReconciliation:
    """SP 血缘比对测试（不依赖外部，直接构造 SP 定义）"""

    def test_reconcile_logic(self):
        """直接测试比对算法"""
        from app.services.sp_service import reconcile_lineage
        diffs = reconcile_lineage(
            excel_sources=["dbo.t_src_1", "dbo.t_src_2"],
            excel_targets=["dbo.t_tgt_1"],
            sp_sources=["dbo.t_src_1", "dbo.t_src_3"],
            sp_targets=["dbo.t_tgt_1", "dbo.t_tgt_2"],
        )
        diff_types = {d["diff_type"] for d in diffs}
        assert "source_missing" in diff_types  # SP 多了 t_src_3
        assert "source_extra" in diff_types    # Excel 多了 t_src_2
        assert "target_missing" in diff_types  # SP 多了 t_tgt_2

    def test_sp_overview(self, client, headers, workspace_id):
        res = client.get(f"/api/sp/overview/{workspace_id}", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total_jobs"] == 3
