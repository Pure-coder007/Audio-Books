import click
from pathlib import Path
from werkzeug.security import generate_password_hash
from .extensions import db
from .models import AdminUser, EmailDelivery, MagicLink, now
from .services.access_service import normalize_email
from .services.email_service import deliver_pending

def register_commands(app):
    @app.cli.command('init-db')
    def init_db():
        """Initialize a development database; production uses flask db upgrade."""
        db.create_all()
        click.echo('Database initialized.')

    @app.cli.command('create-admin')
    @click.option('--email', prompt=True)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option('--role', type=click.Choice(['owner', 'editor', 'support']), default='owner')
    def create_admin(email, password, role):
        email = normalize_email(email)
        if len(password) < 12:
            raise click.ClickException('Use a password of at least 12 characters.')
        if db.session.scalar(db.select(AdminUser).where(AdminUser.email == email)):
            raise click.ClickException('That email is already registered.')
        db.session.add(AdminUser(email=email, password_hash=generate_password_hash(password), role=role))
        db.session.commit()
        click.echo('Staff member created.')

    @app.cli.command('reset-admin-password')
    @click.option('--email', prompt=True)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    def reset_password(email, password):
        from .models import uid, AuditLog
        user = db.session.scalar(db.select(AdminUser).where(AdminUser.email == normalize_email(email)))
        if not user or len(password) < 12:
            raise click.ClickException('Staff account must exist; password must have at least 12 characters.')
        user.password_hash = generate_password_hash(password)
        user.session_version = uid()
        db.session.add(AuditLog(admin_id=user.id, action='staff.password_reset', detail='Password reset from server CLI; sessions invalidated'))
        db.session.commit()
        click.echo('Password reset; previous sessions invalidated.')

    @app.cli.command('seed-demo')
    def seed_demo():
        if app.config['PRODUCTION'] and not app.config['SAMPLE_CATALOG']:
            raise click.ClickException('Set SAMPLE_CATALOG=true to restore sample titles in production.')
        from .seed import seed
        seed(app)
        click.echo('Demo shelf ready. Fictional titles cannot be sold through Stripe.')

    @app.cli.command('deliver-emails')
    def deliver_emails():
        if not app.config['MAIL_HOST']:
            raise click.ClickException('Configure MAIL_HOST before sending email.')
        # Reissue links near expiry before delivery, e.g. after an SMTP outage.
        from .services.access_service import issue_magic_link
        from datetime import timedelta
        queued = db.session.scalars(db.select(EmailDelivery).where(EmailDelivery.status == 'queued')).all()
        for email in queued:
            if email.created_at < now() - timedelta(minutes=5):
                link = issue_magic_link(email.recipient)
                email.body = f'Open your MyAudioShelf purchases using this single-use link within 15 minutes:\n\n{link}\n\nIf it expires, request a new link from My Purchases.'
                email.created_at = now()
        db.session.commit()
        click.echo(f'Delivered {deliver_pending()} queued emails.')

    @app.cli.command('cleanup-access')
    def cleanup_access():
        result = db.session.execute(db.delete(MagicLink).where(MagicLink.expires_at < now()))
        db.session.commit()
        click.echo(f'Removed {result.rowcount} expired links.')

    @app.cli.command('cleanup-media')
    def cleanup_media():
        """Remove old unreferenced files after interrupted/replaced uploads (24h grace)."""
        import time
        from .models import MediaAsset
        retained = set(db.session.scalars(db.select(MediaAsset.storage_key)).all())
        from .models import ProductionEnquiry
        retained.update(db.session.scalars(db.select(ProductionEnquiry.attachment_key).where(ProductionEnquiry.attachment_key.is_not(None))).all())
        removed = 0
        for path in Path(app.config['MEDIA_ROOT']).glob('*'):
            if path.is_file() and path.name not in retained and path.stat().st_mtime < time.time() - 86400:
                path.unlink()
                removed += 1
        click.echo(f'Removed {removed} unreferenced media files.')
