import io
from app.extensions import db
from app.models import ProductionEnquiry, NewsletterSubscriber, AnalyticsEvent


def test_business_pages_navigation_and_innovation(client):
    for slug in ['about','services','immersive-audio','children','originals','innovation','contact','privacy','terms','cookies','copyright','accessibility']:
        response=client.get('/'+slug)
        assert response.status_code == 200, slug
        assert ('/'+slug).encode() in client.get('/sitemap.xml').data
    home=client.get('/').data
    assert b'Stories are meant' in home
    assert b'nav-discover' in home
    assert b'Create an account' not in home
    innovation=client.get('/innovation').data
    assert b'StoryDNA Engine' in innovation
    assert b'Now live' in innovation
    assert b'not implemented' not in innovation and b'under development' not in innovation
    nav=home.decode().split('<nav',1)[1].split('</nav>',1)[0]
    assert 'class="nav-innovation' in nav and 'href="/innovation"' not in nav.split('nav-discover-menu',1)[1]
    assert 'storydna-home' in home.decode() and 'proposed' not in home.decode()


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
    # Page views are written once the server closes the response, as gunicorn does after sending it.
    client.get('/innovation').close()
    with app.app_context():
        assert db.session.scalar(db.select(NewsletterSubscriber)).first_name=='Ada'
        assert db.session.scalar(db.select(AnalyticsEvent).where(AnalyticsEvent.kind=='page_view:/innovation'))


def test_legal_documents_are_complete_and_linked_from_every_footer(client):
    privacy = client.get('/privacy').data.decode()
    assert 'Privacy Policy' in privacy and 'MyAudioShelf Ltd' in privacy and '27 October 2026' in privacy
    assert 'Data Protection Act 2018' in privacy and 'A.ct' not in privacy
    assert 'We do not sell personal information to third parties.' in privacy
    assert privacy.count('class="legal-section"') == 14 and 'href="/cookies"' in privacy
    terms = client.get('/terms').data.decode()
    assert terms.count('class="legal-section"') == 19 and 'England and Wales' in terms
    assert 'Consumer Rights Act 2015' in terms and 'Artificial Intelligence and Synthetic Narration' in terms
    for page in [privacy, terms, client.get('/cookies').data.decode(), client.get('/copyright').data.decode()]:
        assert 'contact@myaudioshelf.com' in page and '22 Laxton Close, Corby' in page
    for path in ['/', '/books', '/contact', '/privacy']:
        footer = client.get(path).data.decode().split('<footer', 1)[1]
        assert '© 2026 MyAudioShelf Ltd. All Rights Reserved.' in footer
        for link in ['/privacy', '/terms', '/cookies', '/copyright', '/accessibility']:
            assert f'href="{link}"' in footer


def test_audiobook_recording_notice_only_on_books_recorded_by_myaudioshelf(client, app):
    from app.models import Audiobook, Author
    with app.app_context():
        book = db.session.get(Audiobook, app.config['TEST_BOOK_ID'])
        other = book.author.name
        book.author = Author(name='David Mozie', slug='david-mozie')
        db.session.commit()
        slug = book.slug
    page = client.get(f'/books/{slug}').data.decode()
    assert '© ' in page and 'David Mozie. All Rights Reserved.' in page and '℗' in page and 'Produced by MyAudioShelf Ltd.' in page
    with app.app_context():
        book = db.session.get(Audiobook, app.config['TEST_BOOK_ID'])
        book.author = Author(name=other + ' Two', slug='another-author')
        db.session.commit()
    assert '℗' not in client.get(f'/books/{slug}').data.decode()


def test_footer_links_to_verified_social_profiles(client):
    for path in ['/', '/books', '/featured', '/contact', '/admin/login']:
        page = client.get(path).data.decode()
        footer = page.split('<footer', 1)[1]
        for url in ['https://www.facebook.com/profile.php?id=61590071573615', 'https://www.instagram.com/myaudioshelf.official/',
                'https://x.com/Myaudioshelf', 'https://www.tiktok.com/@david_mozie']:
            assert f'href="{url}"' in footer
        assert footer.count('rel="noopener noreferrer me"') == 4
    assert '"sameAs"' in client.get('/').data.decode()
