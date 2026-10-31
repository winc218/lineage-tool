"""Integration tests for all new features"""
import io
import json
import httpx
from openpyxl import Workbook

BASE = "http://127.0.0.1:8090"

def login():
    r = httpx.post(f"{BASE}/api/auth/login",
        data={"username": "admin", "password": "admin123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
    return r.json()["access_token"]

def test_all():
    token = login()
    h = {"Authorization": f"Bearer {token}"}
    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name} - {detail}")

    # Create workspace
    r = httpx.post(f"{BASE}/api/workspaces", json={"name": "IntegrationTest", "description": "test"}, headers=h, timeout=10)
    ws_id = r.json()["id"]
    print(f"\nWorkspace: {ws_id[:8]}...")

    # Create Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    headers_row = ["job_name", "job_type", "source_tables", "target_tables", "sp_name", "field_mappings", "schedule", "description"]
    ws.append(headers_row)
    ws.append(["etl_user_dmt", "ETL", "dbo.t_ods_user", "dbo.t_dmt_user", "sp_user_dmt",
               "[INSERT] dbo.t_ods_user.id -> dbo.t_dmt_user.id", "daily", "user ETL"])
    ws.append(["etl_order_dmt", "ETL", "dbo.t_dmt_user", "dbo.t_dmt_order", "",
               "", "daily", "order ETL"])
    ws.append(["etl_report", "PROCEDURE", "dbo.t_dmt_order", "dbo.t_report", "",
               "", "weekly", "report generation"])
    # Add a cyclic job to test cycle detection
    ws.append(["etl_cycle_test", "ETL", "dbo.t_report", "dbo.t_ods_user", "",
               "", "daily", "cycle test"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    # 1. Template download
    r = httpx.get(f"{BASE}/api/import/template", headers=h, timeout=10)
    check("Template download", r.status_code == 200 and len(r.content) > 1000, f"status={r.status_code} size={len(r.content)}")

    # 2. System fields (non-required job_type, sp_name)
    r = httpx.get(f"{BASE}/api/import/fields", headers=h, timeout=10)
    fields_data = r.json()
    check("Required fields exclude job_type", "job_type" not in fields_data.get("required", []))
    check("Required fields exclude sp_name", "sp_name" not in fields_data.get("required", []))

    # 3. Parse
    buf.seek(0)
    r = httpx.post(f"{BASE}/api/import/parse",
        files={"file": ("test.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=h, timeout=10)
    parse = r.json()
    check("Parse Excel", parse.get("count") == 4, f"count={parse.get('count')}")

    # 4. Validate with auto-mapping
    auto_map = parse.get("auto_mapping", {})
    buf.seek(0)
    r = httpx.post(f"{BASE}/api/import/validate",
        data={"mapping": json.dumps(auto_map)},
        files={"file": ("test.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=h, timeout=10)
    val = r.json()
    check("Validate", val.get("total_valid", 0) >= 3, f"valid={val.get('total_valid')} invalid={val.get('total_invalid')} errors={len(val.get('errors',[]))}")

    # 5. Import
    buf.seek(0)
    r = httpx.post(f"{BASE}/api/import/confirm/{ws_id}",
        data={"mapping": json.dumps(auto_map)},
        files={"file": ("test.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=h, timeout=10)
    imp = r.json()
    check("Import", imp.get("job_count", 0) >= 3, f"jobs={imp.get('job_count')} batch={imp.get('batch_no')}")

    # 6. Lineage graph
    r = httpx.get(f"{BASE}/api/lineage/graph/{ws_id}", headers=h, timeout=30)
    graph = r.json()
    check("Graph nodes", len(graph.get("nodes", [])) >= 3, f"nodes={len(graph.get('nodes',[]))}")
    check("Graph edges", len(graph.get("edges", [])) >= 2, f"edges={len(graph.get('edges',[]))}")
    check("Cycle detection", len(graph.get("cycles", [])) >= 1, f"cycles={len(graph.get('cycles',[]))}")

    # 7. Jobs list with stats
    r = httpx.get(f"{BASE}/api/jobs/list/{ws_id}", headers=h, timeout=10)
    jobs = r.json()
    check("Jobs list", len(jobs) >= 3, f"count={len(jobs)}")
    if jobs:
        check("Job has source_count", "source_count" in jobs[0])
        check("Job has target_count", "target_count" in jobs[0])
        check("Job has field_mapping_count", "field_mapping_count" in jobs[0])

    # 8. Job detail
    if jobs:
        job_id = jobs[0]["id"]
        r = httpx.get(f"{BASE}/api/jobs/detail/{ws_id}/{job_id}", headers=h, timeout=10)
        detail = r.json()
        check("Detail source_tables", len(detail.get("source_tables", [])) > 0)
        check("Detail target_tables", len(detail.get("target_tables", [])) > 0)
        check("Detail upstream/downstream", "upstream" in detail and "downstream" in detail)

    # 9. Import batches
    r = httpx.get(f"{BASE}/api/import/batches/{ws_id}", headers=h, timeout=10)
    batches = r.json()
    check("Import batches", len(batches) >= 1, f"batches={len(batches)}")

    # 10. Re-import (upsert test)
    buf.seek(0)
    r = httpx.post(f"{BASE}/api/import/confirm/{ws_id}",
        data={"mapping": json.dumps(auto_map)},
        files={"file": ("test.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=h, timeout=10)
    imp2 = r.json()
    check("Re-import upsert", imp2.get("job_count", 0) >= 3, f"jobs={imp2.get('job_count')}")

    # Verify graph after re-import
    r = httpx.get(f"{BASE}/api/lineage/graph/{ws_id}", headers=h, timeout=30)
    graph2 = r.json()
    check("Graph after re-import", len(graph2.get("nodes", [])) >= 3 and len(graph2.get("edges", [])) >= 2)

    # 11. Export
    r = httpx.get(f"{BASE}/api/jobs/export/{ws_id}", headers=h, timeout=10)
    check("Export Excel", r.status_code == 200 and len(r.content) > 1000, f"size={len(r.content)}")

    # 12. Admin overview
    r = httpx.get(f"{BASE}/api/workspaces/admin-overview", headers=h, timeout=10)
    overview = r.json()
    # Find our workspace in overview
    our_ws_overview = [o for o in overview if o["workspace_id"] == ws_id]
    check("Admin overview", len(overview) >= 1 and (len(our_ws_overview) > 0 and our_ws_overview[0].get("job_count", 0) >= 1))

    # 13. Admin tables
    r = httpx.get(f"{BASE}/api/admin/tables", headers=h, timeout=10)
    tables = r.json()
    check("Admin tables", len(tables) >= 10, f"tables={len(tables)}")
    if tables:
        r = httpx.get(f"{BASE}/api/admin/tables/{tables[0]}", headers=h, timeout=10)
        td = r.json()
        check("Admin table data", "columns" in td and "rows" in td)

    # 14. Update job
    if jobs:
        job_id = jobs[0]["id"]
        r = httpx.put(f"{BASE}/api/jobs/{ws_id}/{job_id}",
            json={"job_name": jobs[0]["job_name"], "description": "updated description", "sp_name": "test_sp"},
            headers=h, timeout=10)
        check("Update job", r.status_code == 200)
        r = httpx.get(f"{BASE}/api/jobs/detail/{ws_id}/{job_id}", headers=h, timeout=10)
        check("Updated description", r.json().get("description") == "updated description")
        check("Updated sp_name", r.json().get("sp_name") == "test_sp")

    # 15. Batch delete
    if len(jobs) >= 2:
        del_ids = [j["id"] for j in jobs[1:3]]
        r = httpx.post(f"{BASE}/api/jobs/batch-delete/{ws_id}", json=del_ids, headers=h, timeout=10)
        check("Batch delete", r.json().get("deleted", 0) >= 2, f"deleted={r.json().get('deleted')}")
        r = httpx.get(f"{BASE}/api/jobs/list/{ws_id}", headers=h, timeout=10)
        check("Jobs after batch delete", len(r.json()) <= 2, f"remaining={len(r.json())}")

    # Summary
    total = passed + failed
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print(f"{'='*50}")
    return failed == 0

if __name__ == "__main__":
    success = test_all()
    exit(0 if success else 1)
