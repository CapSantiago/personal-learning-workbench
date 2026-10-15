"""Build self-contained synthetic PDFs for reader navigation acceptance."""
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from plw import storage, workspace
from plw.materials import MaterialService
from plw.services import LearningService
from plw.workbench import Workbench


def pdf_bytes(specs):
    """Minimal deterministic PDF; no package or external fixture is needed."""
    objects = [b'', b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    page_ids = []
    for number, (width, height, rotation, crop) in enumerate(specs, 1):
        page_id, stream_id = len(objects) + 1, len(objects) + 2
        page_ids.append(page_id)
        content = (f'q 0.95 0.97 0.99 rg 0 0 {width} {height} re f '
                   f'0.15 0.4 0.5 RG 4 w 45 45 {width-90} {height-90} re S '
                   f'0.12 0.25 0.3 rg BT /F1 24 Tf 70 {height-100} Td (SYNTHETIC PAGE {number}) Tj '
                   f'0 -40 Td /F1 16 Tf ({width} x {height} points; rotate {rotation}) Tj ET '
                   f'0.2 0.5 0.7 rg 90 90 160 70 re f Q\n').encode('ascii')
        crop_entry = f' /CropBox [{" ".join(map(str,crop))}]' if crop else ''
        objects.append((f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}]'
                        f'{crop_entry} /Rotate {rotation} /Resources << /Font << /F1 3 0 R >> >>'
                        f' /Contents {stream_id} 0 R >>').encode('ascii'))
        objects.append(f'<< /Length {len(content)} >>\nstream\n'.encode('ascii') + content + b'endstream')
    objects[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
    objects[1] = (f'<< /Type /Pages /Count {len(page_ids)} /Kids [' + ' '.join(f'{i} 0 R' for i in page_ids) + '] >>').encode('ascii')
    data = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'); offsets = [0]
    for identity, obj in enumerate(objects, 1):
        offsets.append(len(data)); data.extend(f'{identity} 0 obj\n'.encode('ascii') + obj + b'\nendobj\n')
    xref = len(data)
    data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode('ascii'))
    for offset in offsets[1:]: data.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode('ascii'))
    return bytes(data)


def main():
    root = storage.ROOTS[1] / ('reader-navigation-' + str(uuid4()))
    workspace.initialize_workspace(root)
    database = workspace.active_db(root); service = LearningService(database)
    semester = service.create_semester('阅读导航 · 合成验收', request_id=str(uuid4()))
    course = service.create_course(semester['id'], '阅读导航 · 合成课件', request_id=str(uuid4()))
    sources = root / 'sources'; sources.mkdir()
    specs = [(960,540,0,None), (600,800,0,None), (800,600,90,[40,35,760,565]),
             (960,540,0,None), (600,800,270,None)]
    documents = {}
    for key, name, pages in [('mixed','01 横竖旋转测试.pdf',specs),
                             ('long','02 三百页测试.pdf',[(960,540,0,None)] * 300)]:
        source = sources / name; source.write_bytes(pdf_bytes(pages))
        material = MaterialService(database).import_file(course['id'],str(source),'managed_copy',request_id=str(uuid4()))
        edition = Workbench(database).create_edition(material['id'],str(uuid4()),local_copy_confirmed=True)
        documents[key] = {'name':name,'material':material['id'],'edition':edition,'pages':len(pages),
                          'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    evidence = root / 'evidence'; evidence.mkdir()
    setup = {'root':str(root),'database':str(database),'course':{'id':course['id'],'name':course['name']},'documents':documents}
    (evidence/'setup.json').write_text(json.dumps(setup,ensure_ascii=False,indent=2),encoding='utf-8')
    (storage.PROJECT_ROOT/'.sandbox/reader-navigation-run.txt').write_text(str(root),encoding='utf-8')
    print(root)

if __name__ == '__main__': main()
