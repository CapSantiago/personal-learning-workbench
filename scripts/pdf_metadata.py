"""Read local PDF structure only. No network, files written, OCR or scripts."""
import json
import sys
from pypdf import PdfReader

pdf=PdfReader(sys.argv[1],strict=False)
if pdf.is_encrypted and not pdf.decrypt(''):
    raise ValueError('PDF 需要打开密码，请先用已知密码在 PDF 软件中解锁后重新导入。')
count=len(pdf.pages)
if not 1 <= count <= 10000:
    raise ValueError('仅支持 1–10000 页的 PDF。')
print(json.dumps({'pages':count}))
