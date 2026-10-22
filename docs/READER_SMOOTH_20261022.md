# 已下载课件的连续翻页与后台保存

## 定位和已部署传输结果

用户10月22日确认现已能下载。实际结果`native-https-result-20261021-160334-d34458`显示candidate_verified/production_download_verified/final_auth_verified/installation_completed均true。相同8MiB，内核直连409.5KiB/s、候选385.9KiB/s、原网址HTTPS403.4KiB/s，三个SHA完整。独立原生HTTPS已实际上线，严重Serve路径瓶颈已消除。当前HTTPS约直连98.5%，余下首次下载瓶颈不能归咎于阅读器保存，也不能在未读取ECS购买配置时断言套餐限速。约28.2MiB按本次速度需要72秒，首次下载不会因翻页修改变成瞬间完成。没有购买升级、打开公网入口或再切热点。

## 可复现的翻页设计问题

旧reader.js的go()在m.pending时立即return，翻页/缩略图按钮在pending时disabled。每次翻页通过setTriggerValue提交position，ui_workbench.py收到后保存并st.rerun，组件重建。主画布重新分配时先清空，并且每次离开页面cleanup，未保留已渲染大图。因此本机已有完整PDF仍被保存往返和重复绘制拖慢。

## 本次修改

只更新reader.js与reader_runtime.py，不改数据库schema、现有工作台UI、账号、设备下载库、PDF.js legacy资源或native HTTPS服务。

- 新同源JSON保存入口`/plw-reader/{token}/action/{doc}`：外层原有登录保护，入口额外强制精确Origin、application/json、200000字节上限、已注册doc/run和活动数据集；线程池执行原Workbench.reader_action，仍用原请求ID幂等、严格revision和数据集写屏障。保存+返回状态共享写锁，防止返回另一个客户端的更新后版本。跨源/匿名/失效能力被拒绝，无任意路径或客户端指定数据库。
- 新串行后台队列：300ms内未发送的进度只保留最后一页；一个已发操作的ID/body保留到确认，失败手工重试相同ID。翻页和拖动不等待保存；标记/撤销/恢复仍串行，冲突明确提示，不静默覆盖其他设备。新路由成功不触发Streamlit rerun。直接streamlit旧启动模式保留原触发路径。
- 当前页先画到离屏canvas，准备好再一次性替换可见图，避免白屏闪烁；后台预渲染下一页、上一页和后两页中的一页。每文档最多4个大图且32MiB像素预算，按页/旋转/缩放/像素比区分，释放文档时同时清理。大图是有界临时加速；长期下载PDF仍在原有IndexedDB中，不改变文件保留策略。
- 翻页优先取消过时大图预绘制；旧任务不可覆盖新页。文字提取从画面就绪条件移开。退出组件时尽力提交最新进度；小请求使用keepalive。此功能未增加断网批注同步或关闭浏览器前的持久草稿保证，保存失败仍需保留页面并重试。

## 验证

116项Python测试通过，覆盖真实ASGI/Streamlit压缩中间件/PrivateAccess认证、幂等重试不重复标记、跨源/缺Origin/无登录/未知doc/过大体/错误类型/数据集恢复/冲突拒绝，以及既有workbench/访问/下载库回归。35项JS阅读下载/文档复用/后台队列/像素预算通过；另原有13项设备下载库JS回归通过。两份供容器内使用的合成验证器已在本机独立进程通过，Bash语法通过。

真实Edge无头浏览器使用用户课件的独立复制到合成库：第二讲54页和概述35页，固定每次保存延迟3秒。可在未确认时2→3→4→5连续翻页，仅发送页2和5，未调用组件触发器。17页图形保存等待期间切18页，保存图形仍属于17页；人为503后继续19→20并以相同ID重试成功；刷新后页码/标记正确、PDF新增下载0；54→35→54往返不再下载；820px平板尺寸和旋转正常，无pageerror。物理iPad/Safari尚未验收。

首次浏览器报告`.sandbox/reader-smooth-9fedc47d-6bc9-4e4d-9e95-625e960da3d8/report.json`：预绘制命中页画面切换0.3–1ms；首次跳转未预绘制复杂页74/123ms。该数据是本机组件内部绘制时间，不是云端或iPad性能承诺；原生UI自动输入点击总耗时22–224ms。相邻预绘制可能尚未完成，复杂新页仍需本地计算，无法保证任意快速随机跳转每帧都瞬时。

## 部署与范围

以已确认的`plw:0.3.1-device-library-20261021-r2`为唯一旧基线，精确校验旧reader.js/runtime/认证与下载库源码摘要和vendor清单。新镜像`plw:0.3.1-reader-smooth-20261022`只覆盖两文件，离线派生构建、容器内合成路由/保存验证，更新前原有协调备份，原环境快照和失败自动回退。新的native HTTPS入口继续使用原8501后端，完全不修改Serve/证书/代理服务。已下载文件不清除，更新后重新登录即可复用。

本地验证和更新包准备不代表云端已部署。实际部署需用户本机终端一次SSH密码，随后仍需真实电脑/iPad连续翻页验收。不得把“服务已启动”视为实机体验通过。

发布包：`.sandbox/releases/PLW-Reader-Smooth-20261022.zip`，31,915字节，SHA256 `6f679e0c0339e620b9abf310b31652ca67f0965cc8997eb97da4a069ee95a0e1`。单密码入口：`.sandbox/releases/Install-PLW-Reader-Smooth-20261022.ps1`。包内README为发布时快照，本文补充最终包身份和下列最终测试结果。最终实际浏览器报告：`.sandbox/reader-smooth-3c582cc9-129a-4aec-87f4-57a74369b339/report.json`，117项Python（含包身份检查）与48项唯一JS检查均通过。实际Linux镜像构建、云端更新及物理iPad尚未执行。
