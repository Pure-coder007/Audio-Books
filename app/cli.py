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
        if db.session.scalar(db.select(AdminUser).where(db.func.lower(AdminUser.email) == email)):
            raise click.ClickException('That email is already registered.')
        db.session.add(AdminUser(email=email, password_hash=generate_password_hash(password), role=role))
        db.session.commit()
        click.echo('Staff member created.')

    @app.cli.command('reset-admin-password')
    @click.option('--email', prompt=True)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    def reset_password(email, password):
        from .models import uid, AuditLog
        user = db.session.scalar(db.select(AdminUser).where(db.func.lower(AdminUser.email) == normalize_email(email)))
        if not user or len(password) < 12:
            raise click.ClickException('Staff account must exist; password must have at least 12 characters.')
        user.password_hash = generate_password_hash(password)
        user.session_version = uid()
        db.session.add(AuditLog(admin_id=user.id, action='staff.password_reset', detail='Password reset from server CLI; sessions invalidated'))
        db.session.commit()
        click.echo('Password reset; previous sessions invalidated.')

    @app.cli.command('restore-curated-catalog')
    def restore_curated():
        from .curated_catalog import restore
        restore(app)
        click.echo('Supplied catalogue restored; fictional samples archived.')

    @app.cli.command('seed-demo')
    def seed_demo():
        if app.config['PRODUCTION'] and not app.config['SAMPLE_CATALOG']:
            raise click.ClickException('Set SAMPLE_CATALOG=true to restore sample titles in production.')
        from .seed import seed
        seed(app)
        click.echo('Demo shelf ready. Fictional titles cannot be sold through Stripe.')

    @app.cli.command('deliver-emails')
    def deliver_emails():
        from .services.email_service import configured
        if not configured():
            raise click.ClickException('Configure RESEND_API_KEY and RESEND_FROM_EMAIL, or SMTP, before sending email.')
        click.echo(f'Submitted {deliver_pending()} queued emails to the email provider.')

    @app.cli.command('check-email-config')
    def check_email_config():
        """Check email settings without sending messages or displaying secrets."""
        from .services.email_service import configured
        if not configured():
            raise click.ClickException('Set RESEND_API_KEY and RESEND_FROM_EMAIL (verified domain), or configure SMTP.')
        if not app.config['BASE_URL'].startswith('https://') and app.config['PRODUCTION']:
            raise click.ClickException('Production BASE_URL must be your public HTTPS website URL.')
        click.echo('Email configuration ready: ' + ('Resend' if app.config.get('RESEND_API_KEY') else 'SMTP'))
        click.echo('Sender domain verification and inbox delivery still need a payment test.')

    @app.cli.command('sync-media-to-bunny')
    def sync_media():
        """Upload existing recordings and attachments into private Bunny Storage."""
        from .models import MediaAsset, ProductionEnquiry
        from .services.storage_service import enabled, upload, local_path, StorageError
        if not enabled():
            raise click.ClickException('Configure BUNNY_STORAGE_ZONE and BUNNY_STORAGE_ACCESS_KEY first.')
        keys = set(db.session.scalars(db.select(MediaAsset.storage_key)).all())
        keys.update(db.session.scalars(db.select(ProductionEnquiry.attachment_key).where(ProductionEnquiry.attachment_key.is_not(None))).all())
        uploaded = missing = 0
        for key in sorted(keys):
            if not local_path(key).is_file():
                missing += 1
                continue
            try:
                upload(key)
            except StorageError as error:
                raise click.ClickException(str(error)) from error
            uploaded += 1
            click.echo(f'Uploaded {uploaded} of {len(keys)} files.')
        click.echo(f'Finished: {uploaded} uploaded; {missing} unavailable locally.')
        if missing:
            raise click.ClickException('Some files were unavailable locally. Run from the computer containing the original recordings.')

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
