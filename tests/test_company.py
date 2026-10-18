import io
from app.extensions import db
from app.models import ProductionEnquiry, NewsletterSubscriber, AnalyticsEvent


def test_business_pages_navigation_and_innovation(client):
    for slug in ['about','services','immersive-audio','children','originals','innovation','contact','privacy','terms','accessibility']:
        response=client.get('/'+slug)
        assert response.status_code == 200, slug
        assert ('/'+slug).encode() in client.get('/sitemap.xml').data
    home=client.get('/').data
    assert b'Stories are meant' in home
    assert b'nav-discover' in home
    assert b'Create an account' not in home
    innovation=client.get('/innovation').data
    assert b'StoryDNA Engine' in innovation
    assert b'not implemented' in innovation


def test_project_upload_and_private_staff_access(client,admin_client,app):
    response=client.post('/production',data={'name':'Author','email':'writer@example.com','title':'New story','message':'A new production','consent':'on','word_count':'35000','preferred_style':'Dramatised','company':'Publisher','manuscript':(io.BytesIO(b'A private manuscript.'),'story.txt')})
    assert response.status_code == 302
    with app.app_context():
        enquiry=db.session.scalar(db.select(ProductionEnquiry))
        enquiry_id=enquiry.id
        assert enquiry.details['word_count']=='35000'
        assert enquiry.attachment_key.startswith('manuscript-')
    # Staff route must require authentication for a separate visitor.
    anonymous=app.test_client()
    assert anonymous.get(f'/admin/enquiries/{enquiry_id}/manuscript').status_code == 302
    response=admin_client.get(f'/admin/enquiries/{enquiry_id}/manuscript')
    assert response.status_code == 200
    assert response.data == b'A private manuscript.'
    assert 'attachment' in response.headers['Content-Disposition']
    assert b'35000' in admin_client.get('/admin/enquiries').data


def test_invalid_manuscript_and_contact_consent(client,app):
    response=client.post('/production',data={'name':'Author','email':'writer@example.com','title':'New story','message':'Test','consent':'on','manuscript':(io.BytesIO(b'not a pdf'),'fake.pdf')})
    assert b'not a valid PDF' in response.data
    assert client.post('/contact',data={'name':'Partner','email':'p@example.com','message':'Partnership','enquiry_type':'partnership'}).status_code == 200
    with app.app_context():assert db.session.scalar(db.select(ProductionEnquiry)) is None
    assert client.post('/contact',data={'name':'Partner','email':'p@example.com','message':'Partnership','enquiry_type':'partnership','consent':'on'}).status_code==302
    with app.app_context():assert db.session.scalar(db.select(ProductionEnquiry)).enquiry_type=='partnership'


def test_newsletter_name_and_aggregate_engagement(client,app):
    client.post('/newsletter',data={'first_name':'Ada','email':'a@example.com','consent':'on'})
    assert client.post('/engagement',json={'kind':'audio_complete'}).status_code==200
    assert client.post('/engagement',json={'kind':'invented'}).status_code==400
    client.get('/innovation')
    with app.app_context():
        assert db.session.scalar(db.select(NewsletterSubscriber)).first_name=='Ada'
        assert db.session.scalar(db.select(AnalyticsEvent).where(AnalyticsEvent.kind=='page_view:/innovation'))


def test_footer_links_to_verified_social_profiles(client):
    for path in ['/', '/books', '/featured', '/contact', '/admin/login']:
        page = client.get(path).data.decode()
        footer = page.split('<footer', 1)[1]
        for url in ['https://www.facebook.com/profile.php?id=61590071573615', 'https://www.instagram.com/myaudioshelf.official/',
                'https://x.com/Myaudioshelf', 'https://www.tiktok.com/@david_mozie']:
            assert f'href="{url}"' in footer
        assert footer.count('rel="noopener noreferrer me"') == 4
    assert '"sameAs"' in client.get('/').data.decode()
