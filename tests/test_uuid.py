from uuid import UUID
from app.extensions import db
from app.models import Audiobook, AdminUser, LegacyUuidMap

def test_entity_ids_are_uuids(app):
    with app.app_context():
        for model in [Audiobook,AdminUser]:
            assert UUID(db.session.scalar(db.select(model)).id).version==4

def test_legacy_cart_and_book_route_preserve_access(client,app):
    with app.app_context():
        db.session.add(LegacyUuidMap(table_name='audiobook',legacy_id=1,uuid=app.config['TEST_BOOK_ID']));db.session.commit()
    with client.session_transaction() as session:session['cart']=[1]
    assert client.get('/cart').status_code==200
    with client.session_transaction() as session:assert session['cart']==[app.config['TEST_BOOK_ID']]
    assert client.post('/cart/add/1',headers={'Accept':'application/json'}).status_code==200

def test_legacy_staff_session_survives_migration(client,app):
    with app.app_context():
        db.session.add(LegacyUuidMap(table_name='admin_user',legacy_id=1,uuid=app.config['TEST_ADMIN_ID']));db.session.commit()
    with client.session_transaction() as session:
        session['admin_id']=1;session['admin_version']=app.config['TEST_ADMIN_VERSION']
    assert client.get('/admin/').status_code==200

def test_staff_email_matching_ignores_case(client,app):
    with app.app_context():
        user=db.session.get(AdminUser,app.config['TEST_ADMIN_ID']);user.email='Owner@Example.com';db.session.commit()
    result=client.post('/admin/login',data={'email':'  OWNER@example.com  ','password':'test-password-long'})
    assert result.status_code==302 and result.location.endswith('/admin/')
    assert client.get('/admin/').status_code==200
