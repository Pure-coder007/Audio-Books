import io, pytest
from pathlib import Path
from werkzeug.datastructures import FileStorage
from app.extensions import db
from app.models import Audiobook
from app.services.media_service import store_upload

SAMPLES = Path(__file__).parent / 'fixtures'

@pytest.mark.parametrize('name', ['sample-mpeg.mpeg', 'sample-mp2.mp2', 'sample-m4b.m4b'])
def test_mpeg_and_audiobook_formats_upload(app, name):
    with app.app_context():
        book = db.session.get(Audiobook, app.config['TEST_BOOK_ID'])
        asset = store_upload(FileStorage(stream=io.BytesIO((SAMPLES / name).read_bytes()), filename=name), book, 'trailer')
        assert asset.duration_seconds > 0

def test_editor_file_picker_lists_mpeg(admin_client):
    assert b'.mpeg' in admin_client.get('/admin/books/new').data
