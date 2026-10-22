export default function({parentElement,data}){
  const root=parentElement.querySelector('.device-library');let alive=true,manifest,store,device,reader;
  const jobs=globalThis.__plwLibraryJobs??=new Map();
  let job=jobs.get(data.run);
  if(job&&job.base!==data.base){job.controller?.abort();jobs.delete(data.run);job=null;}
  if(!job){job={base:data.base,listeners:new Set(),message:'',running:false};jobs.set(data.run,job);}
  let wasRunning=job.running;
  const tell=message=>{job.message=message;for(const fn of job.listeners)fn();};
  root.innerHTML=`<p>下载到当前设备后，刷新、关闭网页或重启设备仍可复用。电脑与 iPad 各保存一份；更新只补充新增或变化的文件。</p>
    <div class="download-actions"><button class="update-all" disabled>一键更新全部课件</button><button class="stop-download" hidden>停止下载</button><button class="check-library">检查更新</button><button class="keep-library">申请长期保留</button></div>
    <p class="storage-status" role="status"></p><p class="download-progress" role="status" aria-live="polite"></p>
    <p class="download-summary"></p><ul class="download-files"></ul>
    <p class="download-note">课件保存在此浏览器的网站存储中，供 PLW 直接读取。清除本网站数据会删除本机副本；不会删除服务器原件。此功能保存课件，不包含整站断网启动或离线批注同步。</p>`;
  const q=s=>root.querySelector(s),size=v=>(v/1048576).toFixed(1)+' MB';
  function repaint(){
    if(!alive)return;q('.download-progress').textContent=job.message;
    q('.update-all').disabled=!manifest||!store||job.running;q('.check-library').disabled=job.running;
    q('.stop-download').hidden=!job.running;
    if(wasRunning&&!job.running&&manifest&&store)list().catch(e=>tell(e.message));
    wasRunning=job.running;
  }
  job.listeners.add(repaint);
  async function storage(request=false){
    const status=await device.deviceStorageStatus({request});if(!alive)return;
    q('.storage-status').textContent=(status.persistent?'已获持久保存权限':'已保存文件可复用；浏览器尚未批准持久保存，空间紧张时可能回收')+
      (Number.isFinite(status.usage)?' · 本网站已用 '+size(status.usage):'')+
      (Number.isFinite(status.quota)?' / 可用配额 '+size(status.quota):'');
  }
  async function list(){
    const saved=await store.items(data.run);if(!alive)return;
    const lookup=new Map(saved.map(item=>[item.kind+':'+item.id,item]));let ready=0;
    const ul=q('.download-files');ul.replaceChildren();
    for(const item of manifest.files){
      const old=lookup.get(item.kind+':'+item.id),present=old?.digest===item.digest&&old.bytes===item.bytes;
      if(present)ready++;
      const li=document.createElement('li'),label=document.createElement('span');
      label.textContent=(item.course?item.course+' · ':'')+item.filename+' · '+(item.kind==='pdf'?'阅读 PDF':'原始课件')+' · '+size(item.bytes)+' · '+(present?'已保存到此设备':old?'有新版本':'未下载');li.append(label);
      if(present){
        const exportButton=document.createElement('button');exportButton.textContent='另存文件';
        exportButton.onclick=async()=>{
          exportButton.disabled=true;
          try{
            const blob=await device.savedDeviceFile(store,data.run,item);if(!blob)throw Error('本机文件不可用，请更新下载库');
            const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=item.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
          }catch(error){tell(error.message);}finally{if(alive)exportButton.disabled=false;}
        };li.append(exportButton);
      }
      ul.append(li);
    }
    for(const item of manifest.unavailable||[]){const li=document.createElement('li');li.textContent=item.filename+' · '+item.message;ul.append(li);}
    q('.download-summary').textContent=`本机已保存 ${ready} / ${manifest.files.length} 份文件（阅读 PDF 与原件分别计数，相同内容只保存一份）`;
  }
  async function refresh(){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try{
      const response=await fetch(data.manifest,{credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
      if(!response.ok)throw Error(response.status===401?'请重新登录后检查更新':'下载清单读取失败：'+response.status);
      const value=await response.json();if(value.run!==data.run||!Array.isArray(value.files))throw Error('下载清单不属于当前学习库');
      const base=new URL(data.base,location.href).href.replace(/\/$/,'');
      for(const item of value.files)if(!new URL(item.url,location.href).href.startsWith(base+'/download/'))throw Error('课件下载地址不正确');
      manifest=value;await list();repaint();
    }finally{clearTimeout(timer);}
  }
  q('.check-library').onclick=()=>refresh().catch(e=>tell(e.message));
  q('.keep-library').onclick=()=>storage(true).catch(e=>tell(e.message));
  q('.stop-download').onclick=()=>{job.controller?.abort();tell('正在停止，已保存的文件会保留…');};
  q('.update-all').onclick=async()=>{
    if(job.running)return;job.running=true;job.controller=new AbortController();repaint();
    try{
      await storage(true);await refresh();tell('正在检查已下载课件…');
      const result=await device.updateDeviceLibrary({store,manifest,download:reader.downloadCourseware,signal:job.controller.signal,
        onProgress:p=>tell(p.completed?`已处理 ${p.index}/${p.totalFiles} 份`:
          `${p.index+1}/${p.totalFiles} · ${p.item.filename} · ${p.local?'复用本机文件':p.verifying?'正在校验保存':size(p.loaded)+' / '+size(p.total)}`)});
      tell(`${result.stopped?'已停止':'更新完成'}：新保存 ${result.downloaded} 份，复用 ${result.reused} 份，失败 ${result.failed.length} 份。`+
        (result.failed.length?' 再点“一键更新”会保留已完成文件并重试；'+result.failed.slice(0,3).map(v=>v.filename+'：'+v.message).join('；'):''));
      await list();await storage();
    }catch(error){tell('更新未完成：'+error.message+'。已完成文件会保留。');}
    finally{job.running=false;job.controller=null;repaint();}
  };
  (async()=>{
    const base=new URL(data.base,location.href).href.replace(/\/$/,'');
    [device,reader]=await Promise.all([import(base+'/device-library.mjs'),import(base+'/reader-module.mjs')]);
    store=await device.deviceLibrary();await storage();await refresh();
  })().catch(error=>tell('下载库暂不可用：'+error.message));
  return()=>{alive=false;job.listeners.delete(repaint);};
}
