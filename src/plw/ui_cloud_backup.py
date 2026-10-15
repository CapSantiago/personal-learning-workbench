"""Small browser backup UI; restores stay behind an explicit preview and confirmation."""
import streamlit as st

from . import backups, backup_transfer


def panel(root, path):
    st.header('数据与备份')
    st.caption('完整备份包括数据库、课件、阅读 PDF、标记、笔记和任务。请定期下载到 Windows 保存。')
    if path and st.button('生成完整备份包', type='primary'):
        with st.spinner('生成一致性备份、打包并校验…'):
            report = backup_transfer.pack_backup(backups.create_backup(path)['path'])
            st.session_state['cloud_backup'] = dict(report, download=backup_transfer.register_download(report))
    report = st.session_state.get('cloud_backup')
    if report:
        st.success('备份包已生成并校验。')
        st.link_button('下载完整备份包', report['download'])
        st.code(report['archive_sha256'], language=None)
        st.caption(f"ZIP SHA-256 · {report['archive_size'] / 1024**2:.1f} MiB；外部引用原件未包含：{len(report['external'])} 份。")
    st.info('恢复和首次迁移通过服务器维护命令完成：先验证备份，再恢复到新数据集，确认后切换。操作见 CLOUD_DATA_BACKUP.md。')
    status = backups.recovery_status(root)
    if status['phase'] not in ('none', 'complete', 'rolled_back'):
        st.warning('存在未完成的恢复操作，请通过维护命令核对或回滚后继续。')
