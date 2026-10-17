// 셸(HTML/CSS)만 캐시, signals.json은 항상 네트워크
self.addEventListener('install',e=>{self.skipWaiting()});
self.addEventListener('fetch',e=>{
  if(e.request.url.includes('signals.json')) return;
  e.respondWith(caches.open('ss-v1').then(async c=>{
    const r=await c.match(e.request);
    const f=fetch(e.request).then(n=>{c.put(e.request,n.clone());return n}).catch(()=>r);
    return r||f;
  }));
});
