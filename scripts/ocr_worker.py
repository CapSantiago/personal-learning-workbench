"""Render one verified PDF page/image for local Windows OCR, with bounded pixels."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from plw import storage

MAX_SIDE = 4000
MAX_PIXELS = 16_000_000


def run(mode, source, job, helper, page=None):
    from PIL import Image, ImageOps
    job = storage.safe_path(Path(job), must_exist=True, directory=True)
    if job.parent.name != 'jobs' or job.parent.parent.name != 'ocr':
        raise ValueError('OCR 工作目录无效。')
    source = storage.safe_path(Path(source), must_exist=True, directory=False)
    helper = storage.safe_path(Path(helper), root=job, must_exist=True, directory=False)
    rendered = storage.safe_path(job / 'rendered.png', directory=False)
    if rendered.exists():
        raise ValueError('识别工作目录已使用，请重试。')
    if mode == 'pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(source) as document:
            if type(page) is not int or not 1 <= page <= len(document):
                raise ValueError('识别页码超出范围。')
            pdf_page = document[page - 1]
            try:
                width, height = pdf_page.get_size()
                if not all(math.isfinite(v) and v > 0 for v in (width, height)):
                    raise ValueError('PDF 页面尺寸无效。')
                scale = min(2.0, MAX_SIDE / width, MAX_SIDE / height,
                            math.sqrt(MAX_PIXELS / (width * height)))
                bitmap = pdf_page.render(scale=scale)
                try:
                    bitmap.to_pil().save(rendered, format='PNG')
                finally:
                    bitmap.close()
            finally:
                pdf_page.close()
    else:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(source) as original:
                if original.format not in ('PNG', 'JPEG'):
                    raise ValueError('仅支持 PNG 和 JPG 图片内容。')
                if original.width * original.height > MAX_PIXELS:
                    raise ValueError('图片最多 1600 万像素，请缩小后重试。')
                image = ImageOps.exif_transpose(original)
                image.thumbnail((MAX_SIDE, MAX_SIDE))
                if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    rgba = image.convert('RGBA')
                    normalized = Image.new('RGB', rgba.size, 'white')
                    normalized.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    normalized = image.convert('RGB')
                normalized.save(rendered, format='PNG')
    storage.safe_path(rendered, must_exist=True, directory=False)
    result = subprocess.run([str(helper), str(rendered)], capture_output=True, text=True,
                            encoding='utf-8-sig', timeout=45,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError(result.stderr.strip()[-500:] or 'Windows OCR 未完成。')
    payload = json.loads(result.stdout)
    if not isinstance(payload.get('text'), str) or len(payload['text']) > 100_000:
        raise ValueError('识别文字过多或结果无效，请分区域识别。')
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('pdf', 'image'))
    parser.add_argument('source')
    parser.add_argument('job')
    parser.add_argument('helper')
    parser.add_argument('--page', type=int)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.mode, args.source, args.job, args.helper, args.page), ensure_ascii=False))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
