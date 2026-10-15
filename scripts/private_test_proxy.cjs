// Loopback-only HTTPS fixture. Not a production proxy or a system certificate install.
const fs=require('node:fs'),path=require('node:path'),https=require('node:https'),http=require('node:http'),net=require('node:net'),assert=require('node:assert/strict');
const root=path.resolve(process.argv[2]),rel=path.relative(path.join(__dirname,'../.sandbox/test-runs'),root);
assert.ok(rel&&!rel.startsWith('..')&&!path.isAbsolute(rel));
const server=https.createServer({key:fs.readFileSync(path.join(root,'test-key.pem')),cert:fs.readFileSync(path.join(root,'test-cert.pem'))},(req,res)=>{
 const upstream=http.request({hostname:'127.0.0.1',port:8505,path:req.url,method:req.method,headers:{...req.headers,host:'127.0.0.1:8506','x-forwarded-proto':'https'}},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res);});
 upstream.on('error',()=>{res.writeHead(502);res.end();});req.pipe(upstream);
});
server.on('upgrade',(req,socket,head)=>{
 const upstream=net.connect(8505,'127.0.0.1',()=>{
  const headers={...req.headers,host:'127.0.0.1:8506','x-forwarded-proto':'https'};
  upstream.write(req.method+' '+req.url+' HTTP/1.1\r\n'+Object.entries(headers).map(([k,v])=>k+': '+v).join('\r\n')+'\r\n\r\n');
  if(head.length)upstream.write(head);socket.pipe(upstream);upstream.pipe(socket);
 });
 upstream.on('error',()=>socket.destroy());socket.on('error',()=>upstream.destroy());
});
server.listen(8506,'127.0.0.1',()=>console.log('Synthetic HTTPS proxy on 127.0.0.1:8506'));
