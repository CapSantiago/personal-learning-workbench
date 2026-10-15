"""Run interactively on the chosen server; plaintext passwords are never saved."""
import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from plw.private_auth import password_hash


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--cloud-defaults',action='store_true',help='Use the Docker mount paths and current Python')
    args=parser.parse_args()
    target=Path(args.config)
    if not target.is_absolute() or target.exists():raise ValueError('请选择尚不存在的配置绝对路径，不覆盖旧账号。')
    origin=input('网站 HTTPS 地址（不含结尾斜杠）：').strip()
    username=input('登录账号：').strip()
    password=getpass('登录密码（至少12个字符）：')
    if password!=getpass('再次输入密码：'):raise ValueError('两次密码不一致。')
    record=dict(origin=origin,username=username,password_digest=password_hash(password),
        data_root='/var/lib/plw/data' if args.cloud_defaults else input('服务器学习数据目录：').strip(),
        backup_root='/var/lib/plw/backups' if args.cloud_defaults else input('服务器备份目录：').strip(),
        pdf_python=sys.executable if args.cloud_defaults else input('含 pypdf 的 Python 完整路径：').strip(),port=8501)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
    if os.name != 'nt':os.chmod(target,0o600)
    print('登录配置已创建（仅保存加盐校验值）。请运行 launch_private.py --check 验证。')


if __name__=='__main__':main()
