"""Initialize Render's runtime database before any web workers start."""
import os
import subprocess
import sys


def on_starting(server):
    if os.environ.get('RENDER', '').lower() == 'true':
        server.log.info('Applying database migrations before starting workers.')
        subprocess.run([sys.executable, '-m', 'flask', '--app', 'wsgi', 'db', 'upgrade'], check=True)

        if os.environ.get('SAMPLE_CATALOG', 'true').lower() == 'true':
            server.log.info('Restoring sample catalogue without overwriting existing titles.')
            subprocess.run([sys.executable, '-m', 'flask', '--app', 'wsgi', 'seed-demo'], check=True)
