import logging
import re

class RedactAccessTokens(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        message = re.sub(r'(/library/access/)[^\s?\"]+', r'\1[redacted]', message)
        message = re.sub(r'([?&]token=)[^\s&\"]+', r'\1[redacted]', message)
        record.msg, record.args = message, ()
        return True

def configure_token_redaction():
    for name in ['werkzeug', 'gunicorn.access']:
        logger = logging.getLogger(name)
        if not any(isinstance(item, RedactAccessTokens) for item in logger.filters):
            logger.addFilter(RedactAccessTokens())
