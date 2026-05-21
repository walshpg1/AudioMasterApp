import pytest
from resolve_bridge import connect, import_to_media_pool, BridgeResult


def test_connect_returns_tuple():
    resolve, msg = connect()
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_connect_message_is_descriptive():
    resolve, msg = connect()
    # When Resolve is not running, message must explain why
    if resolve is None:
        assert any(kw in msg.lower() for kw in ["not running", "not found", "error", "connect"])


def test_import_returns_bridge_result_type():
    result = import_to_media_pool("any_path.wav")
    assert isinstance(result, BridgeResult)


def test_import_when_resolve_unavailable_returns_not_connected():
    result = import_to_media_pool("any_path.wav")
    # If Resolve is not running, connected must be False
    if not result.connected:
        assert result.clip_imported is False
        assert result.timeline_created is False
        assert result.error is None or isinstance(result.error, str)


def test_bridge_result_all_fields():
    result = BridgeResult(
        connected=False,
        project_name=None,
        clip_imported=False,
        timeline_created=False,
        message="Resolve is not running",
        error=None,
    )
    assert result.connected is False
    assert result.project_name is None
    assert result.clip_imported is False
    assert result.timeline_created is False
    assert result.message == "Resolve is not running"
    assert result.error is None


def test_bridge_result_with_error():
    result = BridgeResult(
        connected=True,
        project_name="AudioMasterApp",
        clip_imported=False,
        timeline_created=False,
        message="Import failed",
        error="Media pool error",
    )
    assert result.connected is True
    assert result.error == "Media pool error"
