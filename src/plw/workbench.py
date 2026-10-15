"""Learning and annotation services with durable content operations and CAS writes."""
from contextlib import closing
from datetime import datetime, UTC, date
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from uuid import uuid4, UUID

from . import db, storage, locking
from .materials import MaterialService


def now():
    return datetime.now(UTC).isoformat()


def uid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('ID 格式无效。')
    return value


def title(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 500:
        raise ValueError('标题应为 1–500 个字符。')
    return value.strip()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def request(c, request_id, payload, result_id=None):
    uid(request_id)
    raw = encoded(payload)
    old = c.execute('SELECT * FROM workbench_requests WHERE id=?', (request_id,)).fetchone()
    if old:
        if old['payload'] != raw:
            raise ValueError('请求内容已改变；请重新载入表单后保存。')
        return old['result_id']
    if result_id is not None:
        c.execute('INSERT INTO workbench_requests VALUES(?,?,?,?)', (request_id, raw, result_id, now()))
    return None


def require_course(c, course_id):
    MaterialService._active_course(c, uid(course_id))


def _validate_links(c, kind, identity, course_id, materials):
    if kind not in ('task', 'note', 'chapter'):
        raise ValueError('关联类型无效。')
    existing = {r[0] for r in c.execute(
        f'SELECT material_id FROM {kind}_materials WHERE {kind}_id=?', (identity,))}
    for material in set(materials):
        row = c.execute('SELECT course_id,deleted_at,import_state FROM materials WHERE id=?', (uid(material),)).fetchone()
        if (not row or row['course_id'] != course_id or row['import_state'] != 'ready'
                or (row['deleted_at'] and material not in existing)):
            raise ValueError('资料必须属于同一课程且已就绪。')


def links(c, kind, identity, course_id, materials):
    # Removing courseware from the shelf must not prevent editing its existing
    # tasks, notes or chapters, nor allow a new association with hidden material.
    _validate_links(c, kind, identity, course_id, materials)
    c.execute(f'DELETE FROM {kind}_materials WHERE {kind}_id=?', (identity,))
    c.executemany(f'INSERT INTO {kind}_materials VALUES(?,?)', [(identity, m) for m in set(materials)])


class Workbench:
    def __init__(self, path):
        self.path = Path(path)
        self.root = self.path.parent

    def rows(self, table, course_id=None):
        if table not in ('tasks', 'chapters', 'knowledge_points', 'notes', 'reading_editions', 'annotations', 'content_operations'):
            raise ValueError('未知实体。')
        with db.transaction(self.path, write=False) as c:
            clause = ' WHERE course_id=?' if course_id else ''
            return [dict(r) for r in c.execute(f'SELECT * FROM {table}' + clause, (course_id,) if course_id else ())]

    def associations(self, kind, identity):
        if kind not in ('task', 'note', 'chapter'):
            raise ValueError('未知关联。')
        with db.transaction(self.path, write=False) as c:
            return [r[0] for r in c.execute(f'SELECT material_id FROM {kind}_materials WHERE {kind}_id=?', (identity,))]

    def save_task(self, course_id, values, materials, request_id, *, identity=None, revision=None):
        identity = uid(identity or request_id)
        v = dict(values)
        v['title'] = title(v['title'])
        allowed = {'title','task_type','due_kind','due_date','due_at_utc','due_timezone','planned_date','priority','status','estimated_minutes','actual_minutes','remarks'}
        if set(v) != allowed:
            raise ValueError('任务字段不完整。')
        for key in ('due_date', 'planned_date'):
            if v[key]:
                date.fromisoformat(v[key])
        if v['due_at_utc']:
            moment = datetime.fromisoformat(v['due_at_utc'])
            if moment.utcoffset() is None or moment.utcoffset().total_seconds() != 0:
                raise ValueError('精确截止时间须转换为 UTC。')
        for key in ('estimated_minutes','actual_minutes'):
            if v[key] is not None and (type(v[key]) is not int or v[key] < 0):
                raise ValueError('耗时必须是非负整数分钟。')
        payload = [course_id, dict(v), sorted(materials), identity, revision]
        with db.transaction(self.path) as c:
            if request(c, request_id, payload):
                return identity
            require_course(c, course_id)
            stamp = now()
            v['completed_at'] = stamp if v['status'] == 'done' else None
            if revision is not None and v['status'] == 'done':
                previous = c.execute('SELECT status,completed_at FROM tasks WHERE id=? AND course_id=?', (identity,course_id)).fetchone()
                if previous and previous['status'] == 'done':
                    v['completed_at'] = previous['completed_at']
            if revision is None:
                fields = {'id':identity,'course_id':course_id,**v,'created_at':stamp,'updated_at':stamp}
                c.execute('INSERT INTO tasks ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')', tuple(fields.values()))
            else:
                result = c.execute('UPDATE tasks SET '+','.join(k+'=?' for k in v)+',updated_at=?,revision=revision+1 WHERE id=? AND course_id=? AND revision=?', (*v.values(),stamp,identity,course_id,revision))
                if result.rowcount != 1:
                    raise ValueError('任务已在其他页面修改，请刷新后重试。')
            links(c, 'task', identity, course_id, materials)
            request(c, request_id, payload, identity)
        return identity

    def set_task_completed(self, identity, completed, expected_revision, request_id):
        """Move between pending and completed without rewriting task content or links."""
        identity = uid(identity)
        if type(completed) is not bool or type(expected_revision) is not int or expected_revision < 1:
            raise ValueError('任务操作参数无效。')
        payload = ['task_completion',identity,completed,expected_revision]
        with db.transaction(self.path) as c:
            if request(c,request_id,payload):
                return identity
            row = c.execute('SELECT * FROM tasks WHERE id=?',(identity,)).fetchone()
            if not row or row['revision'] != expected_revision:
                raise ValueError('任务已在其他页面修改，请刷新后重试。')
            require_course(c,row['course_id'])
            allowed = ('todo','doing') if completed else ('done',)
            if row['status'] not in allowed:
                raise ValueError('任务状态已改变，请刷新后重试。')
            stamp = now()
            c.execute('UPDATE tasks SET status=?,completed_at=?,updated_at=?,revision=revision+1 WHERE id=? AND revision=?',
                      ('done' if completed else 'todo',stamp if completed else None,stamp,identity,expected_revision))
            request(c,request_id,payload,identity)
        return identity

    def save_chapter(self, course_id, name, materials, request_id, *, identity=None, revision=None, position=0):
        identity = uid(identity or request_id)
        payload = [course_id,title(name),sorted(materials),identity,revision,position]
        with db.transaction(self.path) as c:
            if request(c,request_id,payload): return identity
            require_course(c,course_id)
            if revision is None:
                c.execute('INSERT INTO chapters(id,course_id,title,position,created_at,updated_at) VALUES(?,?,?,?,?,?)', (identity,course_id,title(name),position,now(),now()))
            elif c.execute('UPDATE chapters SET title=?,position=?,updated_at=?,revision=revision+1 WHERE id=? AND course_id=? AND revision=?', (title(name),position,now(),identity,course_id,revision)).rowcount != 1:
                raise ValueError('章节已更新，请重新载入。')
            links(c,'chapter',identity,course_id,materials)
            request(c,request_id,payload,identity)
        return identity

    def save_knowledge(self, course_id, chapter_id, name, state, remarks, request_id, *, identity=None, revision=None):
        identity=uid(identity or request_id)
        payload=[course_id,chapter_id,title(name),state,remarks,identity,revision]
        with db.transaction(self.path) as c:
            if request(c,request_id,payload): return identity
            require_course(c,course_id)
            if revision is None:
                c.execute('INSERT INTO knowledge_points(id,course_id,chapter_id,title,learning_state,remarks,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)', (identity,course_id,chapter_id,title(name),state,remarks,now(),now()))
            elif c.execute('UPDATE knowledge_points SET chapter_id=?,title=?,learning_state=?,remarks=?,updated_at=?,revision=revision+1 WHERE id=? AND course_id=? AND revision=?', (chapter_id,title(name),state,remarks,now(),identity,course_id,revision)).rowcount != 1:
                raise ValueError('知识点已更新，请重新载入。')
            request(c,request_id,payload,identity)
        return identity

    def note_body(self, identity, revision_id=None):
        with db.transaction(self.path,write=False) as c:
            row=c.execute('SELECT r.* FROM note_revisions r JOIN notes n ON n.id=r.note_id WHERE n.id=? AND r.id=coalesce(?,n.current_revision_id)',(identity,revision_id)).fetchone()
            if not row: raise ValueError('笔记版本不存在。')
            p=storage.relative_file(self.root,row['body_relpath'],must_exist=True)
            if storage.hash_file(p)!=(row['size_bytes'],row['sha256']): raise ValueError('笔记校验失败，未显示可能损坏的正文。')
            return p.read_text(encoding='utf-8')

    def _stage(self, request_id):
        root=locking.workspace_for(self.path) or self.root.parent
        p=storage.safe_path(root/'jobs'/uid(request_id),directory=True)
        p.mkdir(parents=True,exist_ok=True)
        return p

    def _content(self, kind, request_id, payload, staged, target):
        size,digest=storage.hash_file(staged)
        payload={**payload,'sha256':digest,'size_bytes':size,'stage':str(staged),'target':target}
        with db.transaction(self.path) as c:
            old=c.execute('SELECT * FROM content_operations WHERE id=?',(request_id,)).fetchone()
            if old:
                if old['payload_json']!=encoded(payload): raise ValueError('文件请求内容不同，请使用新的请求。')
            else:
                c.execute('INSERT INTO content_operations VALUES(?,?,?,?,?,?,NULL)',(request_id,kind,'planned',target,encoded(payload),now()))
        self._finish_content(request_id)

    def _finish_content(self, operation_id):
        with locking.write_barrier(self.path):
            with db.transaction(self.path,write=False) as c:
                op=dict(c.execute('SELECT * FROM content_operations WHERE id=?',(operation_id,)).fetchone())
            if op['state']=='committed': return
            p=json.loads(op['payload_json'])
            target=storage.relative_file(self.root,p['target'])
            # All semantic checks precede publication. Retry rechecks optimistic versions.
            with db.transaction(self.path,write=False) as c:
                require_course(c,p['course_id'])
                if op['kind']=='note':
                    existing=c.execute('SELECT version FROM notes WHERE id=?',(p['id'],)).fetchone()
                    if (existing['version'] if existing else None)!=p['version']:
                        raise ValueError('笔记版本已改变；待保存内容保留在暂存区。')
            if not target.exists():
                # Publish a complete verified file atomically; failed copies stay
                # outside the dataset, so retries never overwrite a partial body.
                staged=storage.safe_path(Path(p['stage']),must_exist=True,directory=False)
                temporary=staged.with_name('publish-'+str(uuid4())+staged.suffix)
                storage.copy_verified(staged,temporary,expected_sha256=p['sha256'])
                target.parent.mkdir(parents=True,exist_ok=True)
                storage.safe_path(target,directory=False)
                os.rename(temporary,target)  # Windows refuses an existing destination.
            if storage.hash_file(target)!=(p['size_bytes'],p['sha256']):
                raise ValueError('待提交文件校验不一致，已保留现场。')
            with db.transaction(self.path) as c:
                if op['kind']=='edition':
                    c.execute('INSERT INTO reading_editions VALUES(?,?,?,?,?,?,?,?,?)',(p['id'],p['material_id'],p['source_sha256'],p['target'],p['sha256'],p['size_bytes'],p['pages'],p['converter'],now()))
                    c.executemany('INSERT INTO edition_pages VALUES(?,?)',[(p['id'],i) for i in range(1,p['pages']+1)])
                    c.execute('INSERT INTO reading_progress VALUES(?,1,0,?)',(p['id'],now()))
                else:
                    version=(p['version'] or 0)+1
                    if p['version'] is None:
                        c.execute('INSERT INTO notes(id,course_id,chapter_id,title,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(p['id'],p['course_id'],p['chapter_id'],p['title'],1,now(),now()))
                    c.execute('INSERT INTO note_revisions(id,note_id,revision_no,body_relpath,sha256,size_bytes,created_at) VALUES(?,?,?,?,?,?,?)',(operation_id,p['id'],version,p['target'],p['sha256'],p['size_bytes'],now()))
                    c.execute('UPDATE notes SET title=?,chapter_id=?,current_revision_id=?,version=?,updated_at=? WHERE id=?',(p['title'],p['chapter_id'],operation_id,version,now(),p['id']))
                    links(c,'note',p['id'],p['course_id'],p['materials'])
                c.execute("UPDATE content_operations SET state='committed',error=NULL WHERE id=?",(operation_id,))

    def recover_content(self):
        results=[]
        for op in self.rows('content_operations'):
            if op['state']=='committed': continue
            try:
                self._finish_content(op['id']);results.append(op['id']+': 已完成')
            except (OSError,ValueError,db.DatabaseError) as e:
                results.append(op['id']+': '+str(e))
        return results

    def cancel_content(self, identity):
        """Cancel only unpublished content. Never remove a published or partial file."""
        with db.transaction(self.path) as c:
            op=c.execute('SELECT * FROM content_operations WHERE id=?',(uid(identity),)).fetchone()
            if not op or storage.relative_file(self.root,op['target_relpath']).exists():
                raise ValueError('已有目标文件，须核对后提交，不能取消。')
            c.execute("UPDATE content_operations SET state='committed',error='cancelled_before_publication' WHERE id=?",(identity,))

    def save_note(self,course_id,name,body,chapter_id,materials,request_id,*,identity=None,version=None):
        uid(request_id);identity=uid(identity or request_id)
        if not isinstance(body,str) or len(body.encode('utf-8'))>2_000_000: raise ValueError('笔记最多 2 MB。')
        with locking.write_barrier(self.path):
            with db.transaction(self.path,write=False) as c:
                require_course(c,course_id)
                if chapter_id and not c.execute('SELECT 1 FROM chapters WHERE id=? AND course_id=?',(chapter_id,course_id)).fetchone(): raise ValueError('章节不属于本课程。')
                _validate_links(c,'note',identity,course_id,materials)
            staged=self._stage(request_id)/'note.md'
            content=body.encode('utf-8')
            if staged.exists():
                if staged.read_bytes()!=content: raise ValueError('请求正文改变，请重新载入后另存。')
            else:
                with staged.open('xb') as f: f.write(content);f.flush();os.fsync(f.fileno())
            self._content('note',request_id,{'id':identity,'course_id':course_id,'title':title(name),'chapter_id':chapter_id,'materials':sorted(materials),'version':version},staged,f'notes/{identity}/{request_id}.md')
        return identity

    def create_edition(self,material_id,request_id,*,local_copy_confirmed=False,exported_pdf=None,uploaded_pdf=None):
        from .reader_runtime import inspect_pdf, convert_ppt
        uid(request_id)
        if uploaded_pdf is not None and (not isinstance(uploaded_pdf,bytes) or not uploaded_pdf or len(uploaded_pdf)>200*1024*1024):
            raise ValueError('请选择非空且不超过 200 MB 的 PDF。')
        if exported_pdf and uploaded_pdf is not None:raise ValueError('只能选择一种 PDF 来源。')
        with locking.write_barrier(self.path):
            with db.transaction(self.path,write=False) as c:
                old=c.execute('SELECT payload_json FROM content_operations WHERE id=?',(request_id,)).fetchone()
                if old:
                    p=json.loads(old[0])
                    if p.get('material_id')!=material_id: raise ValueError('请求所属资料不同。')
                    if uploaded_pdf is not None and p.get('sha256')!=hashlib.sha256(uploaded_pdf).hexdigest():raise ValueError('请求 PDF 内容已改变。')
                    self._finish_content(request_id);return request_id
            row=MaterialService(self.path).get_material(material_id)
            if row['deleted_at'] or row['import_state']!='ready': raise ValueError('资料尚未就绪或已隐藏。')
            if not local_copy_confirmed: raise ValueError('请确认保存独立的本地阅读副本。')
            source=(storage.relative_file(self.root,row['managed_relpath'],must_exist=True) if row['storage_mode']=='managed_copy' else storage.check_source(row['reference_path'],True,db_path=self.path))
            size,digest=storage.hash_file(source)
            stage=self._stage(request_id)
            target=stage/'reading.pdf'
            converter='PDF snapshot'
            if uploaded_pdf is not None:
                with target.open('xb') as f:f.write(uploaded_pdf);f.flush();os.fsync(f.fileno())
                converter='uploaded PDF; slide mapping unverified'
            elif exported_pdf:
                manual=storage.check_source(exported_pdf,True,db_path=self.path)
                if manual.suffix.lower()!='.pdf': raise ValueError('请提供 PDF 文件。')
                storage.copy_verified(manual,target)
                converter='user-exported PDF; slide mapping unverified'
            elif source.suffix.lower()=='.pdf':
                storage.copy_verified(source,target,expected_sha256=digest)
            elif source.suffix.lower() in ('.ppt','.pptx'):
                if os.environ.get('PLW_PRIVATE_SITE')=='1':
                    raise ValueError('网站已保存 PPT 原件；请上传从 PowerPoint 导出的 PDF 阅读版。')
                isolated=stage/('input'+source.suffix.lower())
                storage.copy_verified(source,isolated,expected_sha256=digest)
                convert_ppt(isolated,target)
                converter='Microsoft PowerPoint static PDF; includes hidden slides'
            else: raise ValueError('阅读器支持 PDF、PPT 和 PPTX。')
            meta=inspect_pdf(target)
            if storage.hash_file(source)!=(size,digest): raise ValueError('转换期间来源发生变化，请重新生成。')
            self._content('edition',request_id,{'id':request_id,'course_id':row['course_id'],'material_id':material_id,'source_sha256':digest,'pages':meta['pages'],'converter':converter},target,f'reading/{request_id}.pdf')
        return request_id

    def edition_state(self,identity):
        with db.transaction(self.path,write=False) as c:
            progress=c.execute('SELECT * FROM reading_progress WHERE edition_id=?',(identity,)).fetchone()
            if not progress: raise ValueError('阅读版本不存在。')
            marks=[{'id':r['id'],'page':r['page'],'type':r['kind'],'points':json.loads(r['geometry_json'])} for r in c.execute("SELECT * FROM annotations WHERE edition_id=? AND deleted_at IS NULL AND kind IN ('ink','rectangle','highlight')",(identity,))]
            return {'page':progress['page'],'revision':progress['revision'],'marks':marks}

    def reader_action(self,action):
        if not isinstance(action,dict) or len(encoded(action))>200_000: raise ValueError('标记数据过大。')
        edition=uid(action['doc']);rid=uid(action['id'])
        if action['run']!=self.root.name: raise ValueError('数据集已切换，请刷新。')
        if type(action['page']) is not int: raise ValueError('页码无效。')
        if type(action['base_revision']) is not int or action['base_revision']<0: raise ValueError('版本号无效。')
        with db.transaction(self.path) as c:
            if request(c,rid,action): return
            progress=c.execute('SELECT * FROM reading_progress WHERE edition_id=?',(edition,)).fetchone()
            if not progress or action['base_revision']!=progress['revision']: raise ValueError('阅读数据已在其他页面更新，请重新载入。')
            if not c.execute('SELECT 1 FROM edition_pages WHERE edition_id=? AND page=?',(edition,action['page'])).fetchone(): raise ValueError('页码超出范围。')
            if action['kind']=='mark':
                pts=action['points']
                if action['type'] not in ('ink','rectangle','highlight') or not isinstance(pts,list) or not 2<=len(pts)<=4096: raise ValueError('图形标记无效。')
                for p in pts:
                    if not isinstance(p,list) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in p): raise ValueError('标记坐标无效。')
                c.execute('INSERT INTO annotations(id,edition_id,page,kind,geometry_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(rid,edition,action['page'],action['type'],encoded(pts),now(),now()))
            elif action['kind'] in ('undo','redo'):
                deleted=action['kind']=='redo'
                row=c.execute('SELECT id FROM annotations WHERE edition_id=? AND kind IN (\'ink\',\'rectangle\',\'highlight\') AND deleted_at IS '+('NOT NULL' if deleted else 'NULL')+' ORDER BY updated_at DESC LIMIT 1',(edition,)).fetchone()
                if row: c.execute('UPDATE annotations SET deleted_at=?,updated_at=?,revision=revision+1 WHERE id=?',(None if deleted else now(),now(),row[0]))
            elif action['kind']!='position': raise ValueError('未知阅读操作。')
            c.execute('UPDATE reading_progress SET page=?,revision=revision+1,updated_at=? WHERE edition_id=?',(action['page'],now(),edition))
            request(c,rid,action,rid)

    def save_annotation(self,edition,page,kind,body,request_id,*,identity=None,revision=None,resolved=False,deleted=False):
        if kind not in ('bookmark','comment','important','question'): raise ValueError('未知标记类型。')
        if len(body)>20000: raise ValueError('批注过长。')
        identity=uid(identity or request_id)
        payload=[edition,page,kind,body,identity,revision,resolved,deleted]
        with db.transaction(self.path) as c:
            if request(c,request_id,payload): return identity
            if revision is None:
                c.execute('INSERT INTO annotations(id,edition_id,page,kind,body,resolved,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(identity,edition,page,kind,body,int(resolved),now(),now()))
            elif c.execute('UPDATE annotations SET body=?,resolved=?,deleted_at=?,updated_at=?,revision=revision+1 WHERE id=? AND edition_id=? AND revision=?',(body,int(resolved),now() if deleted else None,now(),identity,edition,revision)).rowcount!=1:
                raise ValueError('批注已修改，请重新载入。')
            request(c,request_id,payload,identity)
        return identity
