"""Browser courseware batches. Each file commits independently and can be retried."""
import hashlib
import json
import subprocess
from uuid import UUID, uuid4, uuid5

from . import db, locking, storage
from .materials import MaterialService, MaterialError, UPLOAD_MAX_BYTES
from .workbench import Workbench

MAX_BATCH_FILES = 20
MAX_BATCH_BYTES = 500 * 1024 * 1024


def import_courseware(path, course_id, files, batch_id, progress=None):
    """files is [(client_filename, bytes)]; no client filesystem path is needed."""
    namespace = UUID(batch_id)
    if not files or len(files) > MAX_BATCH_FILES:
        raise ValueError(f'每批请选择 1–{MAX_BATCH_FILES} 份课件。')
    if any(not isinstance(body, bytes) for _, body in files):
        raise ValueError('上传文件内容无效。')
    if sum(len(body) for _, body in files) > MAX_BATCH_BYTES:
        raise ValueError('本批文件超过 500 MB，请分批导入。')
    service = MaterialService(path)
    workbench = Workbench(path)
    results = []
    for index, (name, body) in enumerate(files):
        result = {'filename': name, 'status': 'failed', 'material_id': None,
                  'edition_id': None, 'reused': False, 'message': ''}
        try:
            if not body or len(body) > UPLOAD_MAX_BYTES:
                raise ValueError('请选择非空且不超过 200 MB 的课件。')
            with locking.write_barrier(path):
                with db.transaction(path, write=False) as connection:
                    service._active_course(connection, course_id)
                digest = hashlib.sha256(body).hexdigest()
                rid = str(uuid5(namespace, json.dumps([course_id, name, digest], ensure_ascii=False)))
                # Existing ready copies in the same course are reused. A changed
                # body with the same filename gets a separate record and edition.
                prior = next((r for r in service.list_materials(course_id)
                              if r['storage_mode'] == 'managed_copy' and r['import_state'] == 'ready'
                              and not r['file_deleted_at'] and r['name'] == name
                              and r['baseline_sha256'] == digest), None)
                if prior:
                    # Verify the retained file before advertising an existing copy.
                    target = storage.relative_file(path.parent, prior['managed_relpath'], True)
                    if storage.hash_file(target) != (len(body), digest):
                        raise ValueError('已有同名课件的保存文件校验失败，请在资料管理中检查。')
                    material = prior
                    result['reused'] = True
                else:
                    material = service.import_upload(course_id, name, body, request_id=rid)
                result['material_id'] = material['id']
                result['status'] = 'saved'
                editions = [e for e in workbench.rows('reading_editions') if e['material_id'] == material['id']]
                if editions:
                    edition = max(editions, key=lambda e: e['created_at'])['id']
                else:
                    # A fresh conversion job avoids overwriting artifacts left by
                    # a previous failed converter; the uploaded material is reused.
                    edition = workbench.create_edition(material['id'], str(uuid4()), local_copy_confirmed=True)
                result.update(status='ready', edition_id=edition,
                              message='已在书架，未重复导入' if result['reused'] else '导入完成，可以阅读')
        except (MaterialError, storage.StorageError, db.DatabaseError, locking.LockError, OSError, ValueError, subprocess.SubprocessError) as exc:
            result['message'] = ('课件已保存，阅读准备未完成：' if result['material_id'] else '导入未完成：') + str(exc)
        results.append(result)
        if progress:
            progress(index + 1, len(files), result)
    return results
