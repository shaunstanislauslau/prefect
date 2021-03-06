import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pendulum
import pytest

from prefect.client import Client
from prefect.engine.result_handlers import (
    GCSResultHandler,
    JSONResultHandler,
    LocalResultHandler,
    ResultHandler,
)
from prefect.utilities.configuration import set_temporary_config


class TestJSONHandler:
    def test_json_handler_initializes_with_no_args(self):
        handler = JSONResultHandler()

    @pytest.mark.parametrize("res", [42, "stringy", None])
    def test_json_handler_writes(self, res):
        handler = JSONResultHandler()
        blob = handler.write(res)
        assert isinstance(blob, str)

    @pytest.mark.parametrize("res", [42, "stringy", None])
    def test_json_handler_writes_and_reads(self, res):
        handler = JSONResultHandler()
        final = handler.read(handler.write(res))
        assert final == res

    def test_json_handler_raises_normally(self):
        handler = JSONResultHandler()
        with pytest.raises(TypeError):
            handler.write(type(None))


class TestLocalHandler:
    @pytest.fixture(scope="class")
    def tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp

    def test_local_handler_initializes_with_no_args(self):
        handler = LocalResultHandler()

    def test_local_handler_initializes_with_dir(self):
        handler = LocalResultHandler(dir="/.prefect")
        assert handler.dir == "/.prefect"

    @pytest.mark.parametrize("res", [42, "stringy", None, type(None)])
    def test_local_handler_writes_and_writes_to_dir(self, tmp_dir, res):
        handler = LocalResultHandler(dir=tmp_dir)
        fpath = handler.write(res)
        assert isinstance(fpath, str)
        assert os.path.basename(fpath).startswith("prefect")

        with open(fpath, "rb") as f:
            val = f.read()
        assert isinstance(val, bytes)

    @pytest.mark.parametrize("res", [42, "stringy", None, type(None)])
    def test_local_handler_writes_and_reads(self, tmp_dir, res):
        handler = LocalResultHandler(dir=tmp_dir)
        final = handler.read(handler.write(res))
        assert final == res


def test_result_handlers_must_implement_read_and_write_to_work():
    class MyHandler(ResultHandler):
        pass

    with pytest.raises(TypeError) as exc:
        m = MyHandler()

    assert "abstract methods read, write" in str(exc.value)

    class WriteHandler(ResultHandler):
        def write(self, val):
            pass

    with pytest.raises(TypeError) as exc:
        m = WriteHandler()

    assert "abstract methods read" in str(exc.value)

    class ReadHandler(ResultHandler):
        def read(self, val):
            pass

    with pytest.raises(TypeError) as exc:
        m = ReadHandler()

    assert "abstract methods write" in str(exc.value)


@pytest.mark.xfail(raises=ImportError)
class TestGCSResultHandler:
    @pytest.fixture
    def google_client(self, monkeypatch):
        import google.cloud.storage

        client = MagicMock()
        storage = MagicMock(Client=MagicMock(return_value=client))
        with patch.dict("sys.modules", {"google.cloud": MagicMock(storage=storage)}):
            yield client

    def test_gcs_init(self, google_client):
        handler = GCSResultHandler(bucket="bob")
        assert handler.bucket == "bob"
        assert google_client.bucket.call_args[0][0] == "bob"

    def test_gcs_writes_to_blob_prefixed_by_date_suffixed_by_prefect(
        self, google_client
    ):
        bucket = MagicMock()
        google_client.bucket = MagicMock(return_value=bucket)
        handler = GCSResultHandler(bucket="foo")
        handler.write("so-much-data")
        assert bucket.blob.called
        assert bucket.blob.call_args[0][0].startswith(
            pendulum.now("utc").format("Y/M/D")
        )
        assert bucket.blob.call_args[0][0].endswith("prefect_result")

    def test_gcs_writes_binary_string(self, google_client):
        blob = MagicMock()
        google_client.bucket = MagicMock(
            return_value=MagicMock(blob=MagicMock(return_value=blob))
        )
        handler = GCSResultHandler(bucket="foo")
        handler.write(None)
        assert blob.upload_from_string.called
        assert isinstance(blob.upload_from_string.call_args[0][0], str)
