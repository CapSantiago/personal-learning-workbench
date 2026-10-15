"""Read local PDF structure only. No network, files written, OCR or scripts."""
import json
import sys
from pypdf import PdfReader

pdf=PdfReader(sys.argv[1],strict=False)
if pdf.is_encrypted:
    raise ValueError('加密 PDF 需要先解锁。')
count=len(pdf.pages)
if not 1 <= count <= 10000:
    raise ValueError('仅支持 1–10000 页的 PDF。')
print(json.dumps({'pages':count}))
