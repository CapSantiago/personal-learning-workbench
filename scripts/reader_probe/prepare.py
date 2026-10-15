"""Create isolated synthetic PDF fixtures; never open a user-selected document."""
from pathlib import Path
import hashlib
import json
import shutil
import uuid
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter
import pypdfium2

PROJECT = Path(__file__).resolve().parents[2]
RUNTIME = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies'

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    root = PROJECT / '.sandbox' / 'r0' / str(uuid.uuid4())
    root.mkdir(parents=True, exist_ok=False)
    for name in ['sources', 'converted', 'evidence', 'build']:
        (root/name).mkdir()
    guards = [PROJECT/'.sandbox/m1/plw.sqlite3']
    control = PROJECT/'.sandbox/m2/control'
    guards += [p for p in control.glob('*.json') if p.is_file()]
    guards += [p for p in (PROJECT/'.sandbox/m2/datasets').rglob('*') if p.is_file() and p.name != '.write.lock']
    (root/'before.json').write_text(json.dumps({str(p):digest(p) for p in guards if p.exists()},indent=2),encoding='utf-8')
    vendor = RUNTIME/'node/node_modules/pdfjs-dist'
    target = root/'vendor'
    target.mkdir()
    for folder in ['build','cmaps','standard_fonts','wasm']:
        if (vendor/folder).exists():
            shutil.copytree(vendor/folder,target/folder)
    for name in ['LICENSE','package.json']:
        shutil.copyfile(vendor/name,target/name)
    (root/'vendor-manifest.json').write_text(json.dumps({
        'source':str(vendor), 'version':json.loads((vendor/'package.json').read_text())['version'],
        'license':'Apache-2.0','files':{str(p.relative_to(target)):digest(p) for p in target.rglob('*') if p.is_file()}
    },indent=2),encoding='utf-8')
    pdfmetrics.registerFont(TTFont('Chinese',r'C:\Windows\Fonts\simhei.ttf'))
    files=[]
    def fixture(name,pages,mixed=False):
        path=root/'sources'/name
        c=canvas.Canvas(str(path),pagesize=(960,540),pageCompression=1)
        c.setTitle('PLW 合成课件')
        for i in range(pages):
            w,h = ((600,800) if mixed and i==1 else (960,540))
            c.setPageSize((w,h))
            c.setFillColorRGB(.96,.97,.98);c.rect(0,0,w,h,fill=1,stroke=0)
            c.setFillColorRGB(.08,.14,.2);c.setFont('Chinese',28)
            c.drawString(45,h-65,'控制原理 / 合成 PDF 课件')
            c.setFont('Chinese',18)
            for j,line in enumerate(['闭环控制：输出反馈到输入端','状态方程：dx/dt = A x(t) + B u(t)','矩阵 A = [ 0  1 ; -2  -3 ]','中文 空格路径 / native PDF / 页面 %d'%(i+1)]):
                c.drawString(45,h-115-j*36,line)
            c.drawString(45,h-285,'传递函数 G(s) =')
            c.drawCentredString(285,h-270,'1')
            c.line(225,h-280,345,h-280)
            c.setFont('Helvetica',18)
            c.drawCentredString(285,h-304,'s² + 3s + 2')
            c.setStrokeColorRGB(.1,.3,.6)
            for x in [45,170,320,465]:c.line(x,60,x,175)
            for y in [60,100,140,175]:c.line(45,y,465,y)
            c.setFont('Chinese',15)
            for x,t in [(55,'参数'),(185,'数值'),(335,'单位')]:c.drawString(x,151,t)
            c.drawString(55,115,'采样周期');c.drawString(185,115,'0.01');c.drawString(335,115,'s')
            c.drawString(55,75,'角速度');c.drawString(185,75,'2.0');c.drawString(335,75,'rad/s')
            c.showPage()
        c.save()
        files.append({'id':path.stem,'name':name,'path':str(path.relative_to(root)), 'kind':'pdf','pages':pages,'sha256':digest(path)})
        return path
    sample=fixture('原生 PDF 中文课件.pdf',3,True)
    writer=PdfWriter()
    reader=PdfReader(sample)
    for i,p in enumerate(reader.pages):
        if i==2:
            p.rotate(90)
            p.cropbox.lower_left=(20,20)
            p.cropbox.upper_right=(940,520)
        writer.add_page(p)
    rotated=root/'sources/旋转 裁剪.pdf'
    with rotated.open('xb') as stream:writer.write(stream)
    files.append({'id':'cropped','name':rotated.name,'path':str(rotated.relative_to(root)),'kind':'pdf','pages':3,'sha256':digest(rotated)})
    for count in [30,100,300]:fixture(f'性能 {count}页.pdf',count)
    image=root/'build/scanned-page.png'
    document=pypdfium2.PdfDocument(sample)
    document[0].render(scale=1.5).to_pil().save(image)
    scanned=root/'sources/图片型 PDF.pdf'
    c=canvas.Canvas(str(scanned),pagesize=(960,540));c.drawImage(str(image),0,0,960,540);c.showPage();c.save()
    files.append({'id':'scanned','name':scanned.name,'path':str(scanned.relative_to(root)),'kind':'pdf','pages':1,'sha256':digest(scanned)})
    (root/'sources/损坏.pdf').write_bytes(b'%PDF-1.7\ninvalid synthetic input')
    (root/'fixtures.json').write_text(json.dumps({'run_id':root.name,'files':files},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'root':str(root),'files':len(files)},ensure_ascii=False))

if __name__=='__main__': main()
