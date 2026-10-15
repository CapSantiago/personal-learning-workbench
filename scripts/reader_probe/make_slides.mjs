// Synthetic fixtures only. Absolute runtime import avoids modifying dependencies.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [root,modules,skill,python]=process.argv.slice(2);
process.env.RUNTIME_NODE_MODULES=modules;
const {Presentation,PresentationFile}=await import(pathToFileURL(path.join(modules,'@oai/artifact-tool/dist/artifact_tool.mjs')));
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')));
for(const [name,width,height] of [['宽屏 合成课件',1280,720],['标准 合成课件',960,720]]){
  const p=Presentation.create({slideSize:{width,height}});
  const lines=[
    ['控制原理与机器人','合成 PPTX 阅读验证','闭环控制与反馈 / Control systems','中文、空格路径、数字 0123456789'],
    ['状态空间与传递函数','ẋ(t) = A x(t) + B u(t)','A = [ 0  1 ; −2  −3 ]','G(s) = 1 / (s² + 3s + 2)','∫ f(t) dt     θ = π / 2'],
    ['参数与曲线','采样周期：0.01 s','角速度：2.0 rad/s','关节位置：0.0 / 0.5 / 1.0 rad'],
    ['隐藏页样本','本页在转换验证时设为隐藏','预期阅读 PDF 仍包含此页','静态导出不包含全部动画中间步骤']
  ];
  for(const [index,content] of lines.entries()){
    const slide=p.slides.add();slide.background.fill='#F5F7FA';
    for(const [j,text] of content.entries()){
      const box=slide.shapes.add({geometry:'textbox',position:{left:64,top:55+j*96,width:width-128,height:80},fill:'none',line:{fill:'none',width:0}});
      box.text=text;box.text.style={fontFamily:'SimHei',fontSize:j===0?40:28,color:'#14283E'};
    }
    if(index===2)slide.charts.add('line',{position:{left:width-440,top:350,width:350,height:280},categories:['0','1','2','3'],series:[{name:'位置',values:[0,.5,.8,1],fill:'#2869AD'}],hasLegend:false});
  }
  const candidate=path.join(root,'build',name+'.pptx');
  await(await PresentationFile.exportPptx(p)).save(candidate);
  await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:path.join(root,'sources',name+'.pptx'),pythonExecutable:python,
    integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
    layoutArgs:['--expected-slide-size-emu',`${width*9525},${height*9525}`],explicitTotalSlideCount:4,
    materializeLiteralChartWorkbooks:true,verifyArtifactToolImport:true,receiptPath:path.join(root,'build',name+'.validation.json')});
}
console.log('Created synthetic 16:9 and 4:3 PPTX fixtures.');
