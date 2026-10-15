"""R0 reader probe, separate process and data from the M2 application."""
import argparse
from pathlib import Path
import streamlit as st
from probe_core import run_root,catalog,ProbeStore,Assets

args=argparse.ArgumentParser();args.add_argument('--run',required=True)
root=run_root(args.parse_args().run)
st.set_page_config(page_title='PLW 课件阅读验证',layout='wide')
st.title('课件阅读验证')
st.caption('R0 · 仅合成课件 · 原生 PDF 与 PPT/PPTX 转换结果 · 独立于 M2 数据')

@st.cache_resource
def resources(run):
    root=run_root(run);docs=catalog(root)
    return docs,ProbeStore(root),Assets(root,docs)

docs,store,assets=resources(root.name)
selected=st.selectbox('合成课件',range(len(docs)),format_func=lambda i:docs[i]['name'])
doc=docs[selected]
fail=st.checkbox('模拟保存失败（仅验证）')
st.button('触发页面重跑（仅验证）')
st.session_state.setdefault('reader_error','')
st.session_state.setdefault('reader_ack','')
state=store.read()
render=st.components.v2.component('plw_r0_reader',html='<div class="reader-root"></div>',
    css=(Path(__file__).parent/'reader.css').read_text(encoding='utf-8'),
    js=(Path(__file__).parent/'reader.js').read_text(encoding='utf-8'))
result=render(key='r0_reader',data={'base':assets.url,'run':root.name,'doc':doc['sha256'],
    'pages':doc['pages'],'state':store.document(doc['sha256']),'revision':state['revision'],
    'ack':st.session_state.reader_ack,'error':st.session_state.reader_error},
    on_action_change=lambda:None)
if result.action:
    try:
        store.apply(result.action,{d['sha256']:d for d in docs},fail=fail)
        st.session_state.reader_ack=result.action['id'];st.session_state.reader_error=''
    except (ValueError,OSError,TypeError) as error:
        st.session_state.reader_error=str(error)
    st.rerun()
st.caption(f'已提交操作：{len(state["ops"])} · 此页面为技术探针，课程书架和正式备份接入将在 R1 实现。')
