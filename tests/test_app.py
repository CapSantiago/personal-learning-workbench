"""UI reruns operate on an isolated synthetic sandbox, never real study data."""
from pathlib import Path
from uuid import uuid4

from streamlit.testing.v1 import AppTest

from plw_probe import core

PROJECT = Path(__file__).resolve().parents[1]

def test_initial_render_has_no_data_writes(monkeypatch):
    isolated = PROJECT / ".sandbox" / "test-runs" / str(uuid4())
    # Read-side UI rendering must not create a DB or copy a source.
    monkeypatch.setattr(core, "list_imports", lambda root: [])
    monkeypatch.setattr(core, "initialize", lambda root: (_ for _ in ()).throw(AssertionError("unexpected write")))
    monkeypatch.setattr(core, "create_demo_sources", lambda root: (_ for _ in ()).throw(AssertionError("unexpected write")))
    monkeypatch.setattr(core, "probe_import", lambda *args: (_ for _ in ()).throw(AssertionError("unexpected write")))
    app = AppTest.from_file(str(PROJECT / "app_m0.py"), default_timeout=20).run()
    assert not app.exception
    app.run()
    assert not app.exception
    assert not isolated.exists()
    assert app.metric[0].value == "0"

def test_explicit_submit_and_rerun_do_not_repeat_service_call(monkeypatch):
    calls = []
    rows = []
    monkeypatch.setattr(core, "list_imports", lambda root: list(rows))
    def submit(root, source, mode, operation_id):
        calls.append(operation_id)
        row = {"id": "synthetic", "storage_mode": mode}
        if not rows:
            rows.append(row)
        return row
    monkeypatch.setattr(core, "probe_import", submit)
    app = AppTest.from_file(str(PROJECT / "app_m0.py"), default_timeout=20).run()
    next(button for button in app.button if button.label == "提交验证").click().run()
    assert not app.exception
    assert len(calls) == 1
    app.run()
    assert len(calls) == 1
    assert app.metric[0].value == "1"

def test_submission_error_preserves_form(monkeypatch):
    monkeypatch.setattr(core, "list_imports", lambda root: [])
    def fail(*args):
        raise OSError("synthetic copy failure")
    monkeypatch.setattr(core, "probe_import", fail)
    app = AppTest.from_file(str(PROJECT / "app_m0.py"), default_timeout=20).run()
    source_before = app.text_input(key="source_path").value
    next(button for button in app.button if button.label == "提交验证").click().run()
    assert not app.exception
    assert app.error
    assert "synthetic copy failure" in app.error[0].value
    assert app.text_input(key="source_path").value == source_before
    assert app.metric[0].value == "0"
