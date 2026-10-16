"""Create an allowlisted code-only ZIP. Credentials and learning data are excluded."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

PROJECT=Path(__file__).resolve().parents[1]
FILES=['app.py','README.md','pyproject.toml','requirements.lock.txt','requirements-server.lock.txt',
    '.streamlit/config.toml','deploy/Caddyfile','docs/DEPLOY_PRIVATE.md','docs/BACKUP_RESTORE.md',
    'scripts/launch.py','scripts/launch_private.py','scripts/setup_private.py','scripts/pdf_metadata.py',
    'scripts/convert_courseware.ps1','scripts/export_courseware_video.ps1','scripts/ocr_helper.cs','scripts/ocr_worker.py']
FILES += ['Dockerfile','compose.yaml','.env.example','.dockerignore',
    'scripts/cloud_data.py','scripts/healthcheck.py','scripts/cloud_compose.sh','scripts/update_cloud.sh',
    'scripts/offline_smoke.py','scripts/verify_offline_bundle.py','scripts/install_offline.sh','scripts/extract_tailscale.py',
    'docs/CLOUD_DEPLOYMENT.md','docs/CLOUD_DATA_BACKUP.md','docs/UPDATE_WORKFLOW.md',
    'docs/CLOUD_TEST_REPORT.md','docs/PROJECT_STATUS.md']
FILES += ['docs/ALIYUN_OFFLINE_DEPLOYMENT.md']
FILES += ['scripts/verify_loaded_image.py','scripts/resume_offline_prepare.py']


def package(target):
    target=Path(target)
    if not target.is_absolute() or '..' in target.parts or not target.is_relative_to(PROJECT/'.sandbox/releases'):
        raise ValueError('发布包只写入项目 .sandbox/releases 子目录。')
    if any(p.is_symlink() or p.is_junction() for p in (target,*target.parents)):raise ValueError('发布路径不能包含链接。')
    files=[PROJECT/name for name in FILES]
    for directory in ('src','assets/pdfjs'):
        files.extend(p for p in (PROJECT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'))
    records=[]
    for file in sorted(files):
        if any(p.is_symlink() or p.is_junction() for p in (file,*file.parents)) or file.stat().st_nlink!=1:raise ValueError('发布文件含链接。')
        data=file.read_bytes()
        records.append((file.relative_to(PROJECT).as_posix(),data))
    manifest={'format':1,'target':'Windows local / Linux Docker preparation (runtime acceptance pending) / one process','data_included':False,'credentials_included':False,
        'files':[{'path':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in records]}
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in records:archive.writestr(name,data)
        archive.writestr('release-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for record in manifest['files']:assert hashlib.sha256(archive.read(record['path'])).hexdigest()==record['sha256']
    return {'path':str(target),'files':len(records),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'data_included':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    print(json.dumps(package(parser.parse_args().output),ensure_ascii=False))
