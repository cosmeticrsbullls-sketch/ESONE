// Push only. Do not cache application pages, credentials or business records.
self.addEventListener('push',event=>{
 let data={};try{data=event.data?.json()||{}}catch(_){}
 const url=new URL(data.url||'/notifications',self.location.origin);
 event.waitUntil(self.registration.showNotification(data.title||'ESONE update',{body:data.body||'Open ESONE to view your updates.',icon:'/assets/icon-192.png',badge:'/assets/icon-192.png',tag:data.tag||'esone-update',data:{url:url.origin===self.location.origin?url.href:self.location.origin+'/notifications'}}));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();const url=event.notification.data?.url||self.location.origin+'/notifications';
 event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(async windows=>{
  for(const window of windows){if(new URL(window.url).origin===self.location.origin){await window.navigate(url);return window.focus();}}
  return clients.openWindow(url);
 }));
});
