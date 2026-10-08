from pathlib import Path
from unittest.mock import MagicMock
import pytest
import requests
from app.services.storage_service import path_for, upload, validate_config, StorageError

def configure(app):
    app.config.update(BUNNY_STORAGE_ZONE='private-books', BUNNY_STORAGE_ACCESS_KEY='storage-password', BUNNY_STORAGE_ENDPOINT='https://uk.storage.bunnycdn.com')

def response(status=200, chunks=(b'recording',)):
    value=MagicMock();value.__enter__.return_value=value;value.status_code=status;value.iter_content.return_value=iter(chunks)
    return value

def test_private_download_is_cached_without_exposing_key(app,monkeypatch):
    configure(app);calls=[]
    def get(url,**kwargs):calls.append((url,kwargs));return response()
    monkeypatch.setattr(requests,'get',get)
    with app.app_context():
        assert path_for('chapter.mp3').read_bytes()==b'recording'
        assert path_for('chapter.mp3').read_bytes()==b'recording'
    assert len(calls)==1
    assert calls[0][0]=='https://uk.storage.bunnycdn.com/private-books/chapter.mp3'
    assert calls[0][1]['headers']['AccessKey']=='storage-password'
    assert calls[0][1]['allow_redirects'] is False

def test_interrupted_download_does_not_leave_partial_audio(app,monkeypatch):
    configure(app)
    value=response()
    def interrupted(**kwargs):
        yield b'partial'
        raise requests.ConnectionError('network')
    value.iter_content.side_effect=interrupted
    monkeypatch.setattr(requests,'get',lambda *a,**kw:value)
    with app.app_context(),pytest.raises(StorageError):path_for('chapter.mp3')
    assert not (Path(app.config['MEDIA_ROOT'])/'chapter.mp3').exists()
    assert not list(Path(app.config['MEDIA_ROOT']).glob('.download-*'))

def test_missing_remote_file_remains_missing(app,monkeypatch):
    configure(app);monkeypatch.setattr(requests,'get',lambda *a,**kw:response(404))
    with app.app_context():assert not path_for('missing.mp3').exists()

def test_failed_upload_is_reported(app,monkeypatch):
    configure(app);monkeypatch.setattr(requests,'put',lambda *a,**kw:response(401))
    with app.app_context(),pytest.raises(StorageError):upload('private.wav')

def test_storage_rejects_path_escape_and_untrusted_endpoints(app):
    with app.app_context(),pytest.raises(ValueError):path_for('../secret')
    for endpoint in ['http://storage.bunnycdn.com','https://evil.example','https://storage.bunnycdn.com.evil.example','https://user@storage.bunnycdn.com']:
        with pytest.raises(RuntimeError):validate_config({'BUNNY_STORAGE_ENDPOINT':endpoint})
    with pytest.raises(RuntimeError):validate_config({'BUNNY_STORAGE_ZONE':'books'})

def test_availability_check_does_not_download_body(app,monkeypatch):
    from app.services.storage_service import exists
    configure(app);value=response();monkeypatch.setattr(requests,'get',lambda *a,**kw:value)
    with app.app_context():assert exists('remote-chapter.mp3')
    value.iter_content.assert_not_called()

def test_private_download_rejects_unpaid_access_before_storage_lookup(client,app,monkeypatch):
    configure(app);get=MagicMock();monkeypatch.setattr(requests,'get',get)
    assert client.get('/library/download/'+app.config['TEST_BOOK_ID']).status_code==403
    get.assert_not_called()
