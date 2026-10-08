"""Private Bunny Storage, with a local cache for Flask range responses and ZIPs."""
from pathlib import Path
from urllib.parse import urlsplit, quote
import os
import tempfile
import requests
from flask import current_app

class StorageError(ValueError):
    pass

def validate_config(config):
    zone = config.get('BUNNY_STORAGE_ZONE', '')
    key = config.get('BUNNY_STORAGE_ACCESS_KEY', '')
    if bool(zone) != bool(key):
        raise RuntimeError('Configure both BUNNY_STORAGE_ZONE and BUNNY_STORAGE_ACCESS_KEY.')
    endpoint = urlsplit(config.get('BUNNY_STORAGE_ENDPOINT') or 'https://storage.bunnycdn.com')
    if endpoint.scheme != 'https' or not endpoint.hostname or not (endpoint.hostname == 'storage.bunnycdn.com' or endpoint.hostname.endswith('.storage.bunnycdn.com')) or endpoint.port or endpoint.username or endpoint.password or endpoint.path not in ('', '/') or endpoint.query or endpoint.fragment:
        raise RuntimeError('Use the HTTPS Bunny Storage endpoint shown in your storage zone.')
    if zone and ('/' in zone or zone in {'.', '..'}):
        raise RuntimeError('BUNNY_STORAGE_ZONE must be a storage zone name.')

def enabled():
    return bool(current_app.config.get('BUNNY_STORAGE_ZONE'))

def local_path(key):
    base = Path(current_app.config['MEDIA_ROOT']).resolve()
    path = (base / key).resolve()
    if not path.is_relative_to(base) or path == base:
        raise ValueError('Invalid media path.')
    return path

def remote_url(key):
    local_path(key)
    config = current_app.config
    return config['BUNNY_STORAGE_ENDPOINT'].rstrip('/') + '/' + quote(config['BUNNY_STORAGE_ZONE'], safe='') + '/' + quote(key, safe='/')

def upload(key):
    if not enabled():
        return
    for attempt in range(3):
        try:
            # Reopen on each attempt so a interrupted upload starts from byte zero.
            with local_path(key).open('rb') as source:
                with requests.put(remote_url(key), data=source, headers={'AccessKey': current_app.config['BUNNY_STORAGE_ACCESS_KEY'], 'Content-Type': 'application/octet-stream'}, timeout=(20, 180), allow_redirects=False) as response:
                    if response.status_code in (200, 201):
                        return
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < 2:
                            continue
                    raise StorageError('Media storage upload failed. Check your Bunny storage credentials and endpoint.')
        except requests.RequestException as error:
            if attempt == 2:
                raise StorageError('Media storage is unavailable. Please try again.') from error
        except OSError as error:
            raise StorageError('The local media file could not be read.') from error

def path_for(key):
    path = local_path(key)
    if path.is_file() or not enabled():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with requests.get(remote_url(key), headers={'AccessKey': current_app.config['BUNNY_STORAGE_ACCESS_KEY']}, stream=True, timeout=(10, 180), allow_redirects=False) as response:
            if response.status_code == 404:
                return path
            if response.status_code != 200:
                raise StorageError('Media storage is unavailable. Please try again.')
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.download-', delete=False) as target:
                temporary = target.name
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    target.write(chunk)
            os.replace(temporary, path)
            temporary = None
    except (requests.RequestException, OSError) as error:
        raise StorageError('Media storage is unavailable. Please try again.') from error
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return path

def exists(key):
    """Check availability without fetching the recording before checkout."""
    if local_path(key).is_file():
        return True
    if not enabled():
        return False
    try:
        with requests.get(remote_url(key), headers={'AccessKey': current_app.config['BUNNY_STORAGE_ACCESS_KEY']}, stream=True, timeout=(10, 30), allow_redirects=False) as response:
            if response.status_code == 404:
                return False
            if response.status_code != 200:
                raise StorageError('Media storage is unavailable. Please try again.')
            return True
    except requests.RequestException as error:
        raise StorageError('Media storage is unavailable. Please try again.') from error
