import {parentPort,workerData} from 'node:worker_threads';
delete Map.prototype.getOrInsertComputed;delete Uint8Array.prototype.toHex;delete Promise.withResolvers;
const listeners=new Map();
const port={postMessage:(data,transfer)=>parentPort.postMessage(data,transfer),addEventListener(type,fn){const listener=data=>fn({data});listeners.set(fn,listener);parentPort.on(type,listener);},removeEventListener(type,fn){parentPort.off(type,listeners.get(fn));listeners.delete(fn);}};
const {WorkerMessageHandler}=await import(workerData.url);
WorkerMessageHandler.initializeFromPort(port);
parentPort.postMessage({compatReady:true,map:typeof Map.prototype.getOrInsertComputed,hex:typeof Uint8Array.prototype.toHex,promise:typeof Promise.withResolvers});
