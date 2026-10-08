"""Initialize Render's runtime database before any web workers start."""
import os
import subprocess
import sys


def on_starting(server):
    if os.environ.get('RENDER', '').lower() == 'true':
        server.log.info('Applying database migrations before starting workers.')
        subprocess.run([sys.executable, '-m', 'flask', '--app', 'wsgi', 'db', 'upgrade'], check=True)

        server.log.info('Restoring supplied catalogue and retiring fictional samples.')
        subprocess.run([sys.executable, '-m', 'flask', '--app', 'wsgi', 'restore-curated-catalog'], check=True)
