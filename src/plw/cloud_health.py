"""Read-only process/database readiness, with no learning paths or records in output."""
from contextlib import closing
from . import db, storage, workspace, backups


def check():
    initialized = (storage.PRODUCTION_ROOT / 'control/active.json').exists()
    if initialized:
        path = workspace.active_db(storage.PRODUCTION_ROOT)
        with closing(db.connect_snapshot(path)) as connection:
            version = connection.execute('PRAGMA user_version').fetchone()[0]
        if not db.schema_ready(version):
            raise ValueError('Explicit migration required')
        status = backups.recovery_status(storage.PRODUCTION_ROOT)
        if status['phase'] not in ('none', 'complete', 'rolled_back'):
            raise ValueError('Restore requires maintenance')
    return {'ok': True, 'version': db.APP_VERSION, 'initialized': initialized}
