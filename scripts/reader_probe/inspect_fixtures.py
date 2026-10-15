"""Render synthetic PDFs and verify protected hashes; avoid stdlib module names."""
import argparse
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader
import pypdfium2
from probe_core import run_root

parser=argparse.ArgumentParser();parser.add_argument('--run',required=True)
root=run_root(parser.parse_args().run)
documents=[]
for path in list((root/'converted').glob('*.pdf'))+[root/'sources/原生 PDF 中文课件.pdf',root/'sources/图片型 PDF.pdf']:
    pdf=PdfReader(path);renderer=pypdfium2.PdfDocument(path)
    entries=[]
    for i,page in enumerate(pdf.pages):
        renderer[i].render(scale=1.3).to_pil().save(root/'evidence'/f'{path.stem}-page-{i+1}.png')
        entries.append({'page':i+1,'text':page.extract_text()[:160],'width':float(page.mediabox.width),'height':float(page.mediabox.height)})
    if path.parent.name=='converted':assert len(entries)==4,'Hidden page missing'
    documents.append({'name':path.name,'pages':entries})
before=json.loads((root/'before.json').read_text(encoding='utf-8'))
changed=[p for p,h in before.items() if not Path(p).exists() or hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
report={'documents':documents,'protected_files_checked':len(before),'changed':changed}
(root/'evidence/pdf-inspection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert not changed,'M1/M2 data changed during isolated R0 probe'
print(json.dumps({'rendered_documents':len(documents),'protected_files_checked':len(before),'changed':changed},ensure_ascii=False))
