from io import BytesIO
from pathlib import Path
import uuid
from zipfile import ZipFile,BadZipFile
from django.core.files.base import ContentFile
from rest_framework.exceptions import ValidationError
from PIL import Image,ImageOps,UnidentifiedImageError

def image_file(uploaded):
    if not uploaded or uploaded.size>5*1024*1024:raise ValidationError('Choose an image up to 5 MB.')
    try:
        with Image.open(uploaded) as image:
            if image.format not in ['JPEG','PNG','WEBP'] or image.width*image.height>20000000:raise ValidationError('Use JPG, PNG or WebP, up to 20 megapixels.')
            image=ImageOps.exif_transpose(image);image.thumbnail((1800,1800))
            output=BytesIO();image.convert('RGB').save(output,'JPEG',quality=88)
            return ContentFile(output.getvalue(),name=uuid.uuid4().hex+'.jpg')
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):raise ValidationError('This image could not be read.')

def submission_file(uploaded):
    if not uploaded or uploaded.size>10*1024*1024:raise ValidationError('Choose a file up to 10 MB.')
    name=Path(uploaded.name.replace('\\','/')).name[:180]
    ext=Path(name).suffix.lower()
    if ext in ['.jpg','.jpeg','.png','.webp']:
        file=image_file(uploaded)
        return file,name,'image',file.size
    header=uploaded.read(12);uploaded.seek(0)
    if ext=='.pdf':valid=header.startswith(b'%PDF-')
    elif ext=='.txt':
        try:uploaded.read().decode('utf-8');valid=True
        except UnicodeDecodeError:valid=False
        uploaded.seek(0)
    elif ext=='.docx':
        try:
            with ZipFile(uploaded) as archive:
                valid='word/document.xml' in archive.namelist() and sum(info.file_size for info in archive.infolist())<=50*1024*1024
        except (BadZipFile,OSError):valid=False
        uploaded.seek(0)
    else:valid=False
    if not valid:raise ValidationError('Use a valid PDF, DOCX, TXT, JPG, PNG or WebP file.')
    content=ContentFile(uploaded.read(),name=uuid.uuid4().hex+ext)
    return content,name,'document',content.size
