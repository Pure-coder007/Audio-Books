from pathlib import Path
from uuid import uuid4
import json
from flask import current_app
from ..models import ProductionEnquiry

ENQUIRY_TYPES = {'general':'General enquiry','author':'Author / publisher project','children':'Children’s content','partnership':'Partnership','creative':'Creative professional','innovation':'Innovation / investment','accessibility':'Accessibility'}

def project_details(form):
    fields={'company':150,'author':150,'genre':80,'word_count':12,'publication_status':30,'publisher':150,'preferred_style':60}
    details={key:form.get(key,'').strip()[:limit] for key,limit in fields.items()}
    if details['word_count'] and (not details['word_count'].isdigit() or not 1 <= int(details['word_count']) <= 10000000):
        raise ValueError('Enter a word count between 1 and 10,000,000.')
    if details['publication_status'] not in {'','published','unpublished'}:
        raise ValueError('Choose a valid publication status.')
    if details['preferred_style'] not in {'','Classic narration','Enhanced','Dramatised','Not sure yet'}:
        raise ValueError('Choose a valid production style.')
    return json.dumps({key:value for key,value in details.items() if value},ensure_ascii=False)

def save_manuscript(upload):
    if not upload or not upload.filename:return None
    name=Path(upload.filename).name[:180]
    suffix=Path(name).suffix.lower()
    if suffix not in {'.pdf','.txt','.docx'}:raise ValueError('Upload a PDF, TXT or DOCX manuscript.')
    content=upload.stream.read(10*1024*1024+1)
    if not content or len(content)>10*1024*1024:raise ValueError('Manuscripts must be non-empty and no larger than 10 MB.')
    if suffix=='.pdf' and not content.startswith(b'%PDF-'):raise ValueError('The uploaded file is not a valid PDF.')
    if suffix=='.txt':
        try:content.decode('utf-8')
        except UnicodeDecodeError:raise ValueError('TXT files must use UTF-8 encoding.')
        if b'\x00' in content:raise ValueError('Upload a plain text manuscript.')
    if suffix=='.docx':
        import io,zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names=archive.namelist()
                if 'word/document.xml' not in names or '[Content_Types].xml' not in names or any('vbaProject' in n for n in names) or sum(i.file_size for i in archive.infolist())>50*1024*1024:
                    raise ValueError('Upload a valid DOCX without macros, no larger than 50 MB when expanded.')
        except zipfile.BadZipFile:raise ValueError('The uploaded file is not a valid DOCX.')
    key='manuscript-'+uuid4().hex+suffix
    root=Path(current_app.config['MEDIA_ROOT']);root.mkdir(parents=True,exist_ok=True)
    (root/key).write_bytes(content)
    from .storage_service import upload as upload_remote
    upload_remote(key)
    return key,name
