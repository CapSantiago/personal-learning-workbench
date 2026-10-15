"""Explicit maintenance CLI; real migrations always go through verified restore copies."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--local-preview', action='store_true')
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('status')
    actions.add_parser('init')
    actions.add_parser('backup')
    verify = actions.add_parser('verify')
    verify.add_argument('--archive', required=True)
    restore = actions.add_parser('restore')
    restore.add_argument('--archive', required=True)
    restore.add_argument('--confirm', required=True, help='Current dataset UUID, or EMPTY')
    rollback = actions.add_parser('rollback')
    rollback.add_argument('--confirm', required=True)
    args = parser.parse_args()
    from plw.server_config import load_profile, configure_profile
    profile = load_profile(args.config, preview=args.local_preview)
    configure_profile(profile)
    from plw import storage, workspace, backups, backup_transfer, platform_lock
    root = storage.safe_path(profile['data_root'], directory=True)

    @contextmanager
    def stopped_server():
        lock = storage.safe_path(root / 'control/.server.lock', directory=False)
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open('a+b') as stream:
            platform_lock.acquire(stream)
            try:
                yield
            finally:
                platform_lock.release(stream)

    if args.action == 'status':
        result = workspace.describe(root) if (root / 'control/active.json').exists() else {'initialized': False}
        if 'db_path' in result:
            from contextlib import closing
            from plw import db
            with closing(db.connect_snapshot(result['db_path'])) as connection:
                result['schema_version'] = connection.execute('PRAGMA user_version').fetchone()[0]
    elif args.action == 'init':
        with stopped_server():
            result = workspace.initialize_workspace(root)
    elif args.action == 'backup':
        result = backup_transfer.pack_backup(backups.create_backup(workspace.active_db(root))['path'])
    elif args.action == 'verify':
        result = backup_transfer.unpack_backup(args.archive, storage.BACKUP_ROOT)
    elif args.action == 'restore':
        if not root.exists() and args.confirm != 'EMPTY':
            raise ValueError('首次恢复需要 --confirm EMPTY。')
        with stopped_server():
            report = backup_transfer.unpack_backup(args.archive, storage.BACKUP_ROOT)
            result = backups.restore_backup(root, report['path'], confirmation=args.confirm,
                                           expected_manifest_sha256=report['manifest_sha256'])
    else:
        with stopped_server():
            result = backups.rollback_restore(root, confirmation=args.confirm)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
