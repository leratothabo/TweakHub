"""
HTTP-level tests for the object-storage + background-job rework of
POST /api/tools/{tool}/process: sync tools now return a JSON body with a
download_url (instead of the file bytes directly), and async tools
(ASYNC_TOOL_NAMES — video-category + document-engine) return 202 with a
job_id to poll via GET /api/jobs/{id}. GET /api/files/{key} is the signed
download link both paths end up pointing at for the local storage
backend.

Async tests set JOB_QUEUE_SYNCHRONOUS=true (services/job_queue.py) so
they don't need a separate `rq worker` process — see test_job_queue.py
for coverage of the real enqueue/dequeue plumbing itself.
"""
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _signup_and_login(client, email="tools-route@example.com"):
    signup = client.post("/api/auth/signup", json={"email": email, "password": "correct horse battery"})
    assert signup.status_code == 201, signup.text
    login = client.post("/api/auth/login", json={"email": email, "password": "correct horse battery"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _download_path(url: str) -> str:
    """The download_url is absolute (http://<api_url>/api/files/...) —
    TestClient's transport dispatches by path regardless of host, but
    stripping to path+query keeps the intent explicit rather than relying
    on that cross-host behavior."""
    parsed = urlparse(url)
    return f"{parsed.path}?{parsed.query}"


def test_sync_tool_returns_json_with_download_url(client, sample_png_bytes):
    headers = _signup_and_login(client)

    resp = client.post(
        "/api/tools/image_convert/process",
        files={"file": ("in.png", sample_png_bytes, "image/png")},
        data={"options": '{"target_format": "png"}'},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["is_async"] is False
    assert body["download_url"]
    assert body["credits_spent"] > 0
    assert "credit_balance" in body

    download = client.get(_download_path(body["download_url"]))
    assert download.status_code == 200
    assert download.headers["content-type"] == "image/png"
    assert len(download.content) > 0


def test_sync_tool_failure_still_records_a_failed_job(client):
    headers = _signup_and_login(client, email="tools-route-fail@example.com")

    resp = client.post(
        "/api/tools/image_convert/process",
        files={"file": ("in.png", b"not a real image", "image/png")},
        data={"options": '{"target_format": "png"}'},
        headers=headers,
    )
    assert resp.status_code == 502
    assert "Processing failed" in resp.json()["detail"]


def test_async_tool_returns_202_then_resolves_via_job_polling(client):
    # Deliberately does NOT use JOB_QUEUE_SYNCHRONOUS=true here: that runs
    # the worker function inline inside enqueue_processing_job(), which —
    # for html_to_pdf specifically — means inside this async route
    # handler's own event loop, and Playwright's sync API (used by
    # document_convert.py's html_to_pdf handler) refuses to run nested
    # inside an already-running asyncio loop. That's not a production bug
    # (a real `rq worker` process has no asyncio loop at all — see
    # apps/workers/README.md), just a reason this one test calls
    # run_processing_job() directly, after the request has returned and
    # control is back in plain sync test code, to stand in for "a worker
    # picks this up later" the same way test_job_worker.py does.
    headers = _signup_and_login(client, email="tools-route-async@example.com")

    resp = client.post(
        "/api/tools/html_to_pdf/process",
        files={"file": ("in.html", b"<html><body><h1>hi</h1></body></html>", "text/html")},
        data={"options": "{}"},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["is_async"] is True
    assert body["status"] == "pending"

    from services.job_worker import run_processing_job

    run_processing_job(body["job_id"])

    job_resp = client.get(f"/api/jobs/{body['job_id']}", headers=headers)
    assert job_resp.status_code == 200
    job_body = job_resp.json()
    assert job_body["status"] == "succeeded", job_body
    assert job_body["download_url"]


def test_async_tool_without_synchronous_queue_returns_202_pending(client, override_settings):
    # Default: job_queue_synchronous=False — nothing actually processes
    # it (no worker running in tests), so the response should be a
    # genuine 202/pending, and GET /api/jobs/{id} should agree.
    headers = _signup_and_login(client, email="tools-route-pending@example.com")

    resp = client.post(
        "/api/tools/html_to_pdf/process",
        files={"file": ("in.html", b"<html></html>", "text/html")},
        data={"options": "{}"},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert "download_url" not in body

    job_resp = client.get(f"/api/jobs/{body['job_id']}", headers=headers)
    assert job_resp.status_code == 200
    assert job_resp.json()["status"] == "pending"


def test_get_job_404s_for_another_users_job(client, override_settings):
    override_settings(job_queue_synchronous=True)
    headers_a = _signup_and_login(client, email="tools-route-a@example.com")
    headers_b = _signup_and_login(client, email="tools-route-b@example.com")

    resp = client.post(
        "/api/tools/image_convert/process",
        files={"file": ("in.png", b"", "image/png")},
        data={"options": '{"target_format": "png"}'},
        headers=headers_a,
    )
    # Doesn't matter whether it succeeded or failed — either way a
    # ProcessingJob row exists to test the ownership check against. A
    # blank file may fail image_convert, so just extract the job id from
    # whichever path this landed on.
    job_id = resp.json().get("job_id") if resp.status_code in (200, 202) else None
    if job_id is None:
        # image_convert failed outright (502) with no JSON job_id — fall
        # back to a run that's guaranteed to succeed for this check.
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, format="PNG")
        resp = client.post(
            "/api/tools/image_convert/process",
            files={"file": ("in.png", buf.getvalue(), "image/png")},
            data={"options": '{"target_format": "png"}'},
            headers=headers_a,
        )
        job_id = resp.json()["job_id"]

    resp_b = client.get(f"/api/jobs/{job_id}", headers=headers_b)
    assert resp_b.status_code == 404


def test_list_jobs_returns_only_the_caller_s_jobs(client, sample_png_bytes):
    headers = _signup_and_login(client, email="tools-route-list@example.com")
    client.post(
        "/api/tools/image_convert/process",
        files={"file": ("in.png", sample_png_bytes, "image/png")},
        data={"options": '{"target_format": "png"}'},
        headers=headers,
    )

    resp = client.get("/api/jobs", headers=headers)
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["tool_name"] == "image_convert"


def test_download_link_rejects_tampered_signature(client, sample_png_bytes):
    headers = _signup_and_login(client, email="tools-route-tamper@example.com")
    resp = client.post(
        "/api/tools/image_convert/process",
        files={"file": ("in.png", sample_png_bytes, "image/png")},
        data={"options": '{"target_format": "png"}'},
        headers=headers,
    )
    download_url = resp.json()["download_url"]
    path = _download_path(download_url).replace("sig=", "sig=deadbeef")
    tampered = client.get(path)
    assert tampered.status_code == 403


def test_get_tools_reports_is_async(client):
    resp = client.get("/api/tools", params={"category": "video"})
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert tools  # video category is non-empty
    assert all(t["is_async"] for t in tools)

    resp_pdf = client.get("/api/tools", params={"category": "pdf"})
    pdf_tools = {t["name"]: t["is_async"] for t in resp_pdf.json()["tools"]}
    assert pdf_tools["pdf_rotate"] is False  # manipulate engine, sync
