"""Languages for audiobooks and for reading the site.

BOOK_LANGUAGES are the languages an audiobook can be recorded in: (English name, own name).
SITE_LANGUAGE_GROUPS are the languages the site itself can be shown in, translated by Google
Translate in the visitor's browser: (Google language code, English name, own name).
"""
import re

BOOK_LANGUAGES = [
    ('English', 'English'), ('French', 'Français'), ('Spanish', 'Español'), ('Portuguese', 'Português'), ('German', 'Deutsch'),
    ('Italian', 'Italiano'), ('Dutch', 'Nederlands'), ('Arabic', 'العربية'), ('Chinese (Mandarin)', '中文'), ('Japanese', '日本語'),
    ('Korean', '한국어'), ('Hindi', 'हिन्दी'), ('Bengali', 'বাংলা'), ('Urdu', 'اردو'), ('Punjabi', 'ਪੰਜਾਬੀ'), ('Gujarati', 'ગુજરાતી'),
    ('Tamil', 'தமிழ்'), ('Telugu', 'తెలుగు'), ('Marathi', 'मराठी'), ('Russian', 'Русский'), ('Ukrainian', 'Українська'),
    ('Polish', 'Polski'), ('Czech', 'Čeština'), ('Hungarian', 'Magyar'), ('Romanian', 'Română'), ('Greek', 'Ελληνικά'),
    ('Turkish', 'Türkçe'), ('Persian', 'فارسی'), ('Hebrew', 'עברית'), ('Swedish', 'Svenska'), ('Norwegian', 'Norsk'),
    ('Danish', 'Dansk'), ('Finnish', 'Suomi'), ('Indonesian', 'Bahasa Indonesia'), ('Malay', 'Bahasa Melayu'), ('Filipino', 'Filipino'),
    ('Vietnamese', 'Tiếng Việt'), ('Thai', 'ไทย'),
]

BOOK_LANGUAGE_NAMES = {name for name, _ in BOOK_LANGUAGES}

# Google Translate codes, checked against Google's website translator. Languages it cannot translate a page into are left out.
SITE_LANGUAGE_GROUPS = [
    ('World languages', [
        ('ar', 'Arabic', 'العربية'), ('zh-CN', 'Chinese', '中文'), ('fr', 'French', 'Français'), ('es', 'Spanish', 'Español'),
        ('pt', 'Portuguese', 'Português'), ('de', 'German', 'Deutsch'), ('it', 'Italian', 'Italiano'), ('nl', 'Dutch', 'Nederlands'),
        ('ru', 'Russian', 'Русский'), ('ja', 'Japanese', '日本語'), ('ko', 'Korean', '한국어'), ('hi', 'Hindi', 'हिन्दी'),
        ('bn', 'Bengali', 'বাংলা'), ('ur', 'Urdu', 'اردو'), ('pa', 'Punjabi', 'ਪੰਜਾਬੀ'), ('gu', 'Gujarati', 'ગુજરાતી'),
        ('ta', 'Tamil', 'தமிழ்'), ('te', 'Telugu', 'తెలుగు'), ('mr', 'Marathi', 'मराठी'), ('tr', 'Turkish', 'Türkçe'),
        ('fa', 'Persian', 'فارسی'), ('iw', 'Hebrew', 'עברית'), ('el', 'Greek', 'Ελληνικά'), ('pl', 'Polish', 'Polski'),
        ('uk', 'Ukrainian', 'Українська'), ('cs', 'Czech', 'Čeština'), ('ro', 'Romanian', 'Română'), ('hu', 'Hungarian', 'Magyar'),
        ('sv', 'Swedish', 'Svenska'), ('no', 'Norwegian', 'Norsk'), ('da', 'Danish', 'Dansk'), ('fi', 'Finnish', 'Suomi'),
        ('id', 'Indonesian', 'Bahasa Indonesia'), ('ms', 'Malay', 'Bahasa Melayu'), ('tl', 'Filipino', 'Filipino'),
        ('vi', 'Vietnamese', 'Tiếng Việt'), ('th', 'Thai', 'ไทย'),
    ]),
]
SITE_LANGUAGE_CODES = {code for _, choices in SITE_LANGUAGE_GROUPS for code, _, _ in choices}
SITE_LANGUAGE_BY_CODE = {code: (code, english, own) for _, choices in SITE_LANGUAGE_GROUPS for code, english, own in choices}


def chosen_site_language(cookie):
    """The visitor's chosen site language from Google Translate's cookie, e.g. '/en/yo'; None for English or anything unexpected."""
    match = re.fullmatch(r'/(?:auto|en)/([A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?)', cookie or '')
    return SITE_LANGUAGE_BY_CODE.get(match.group(1)) if match else None
