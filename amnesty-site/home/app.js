'use strict';
(function(){
const H=window.__HOME__||{};const C=H.content||{};
const sortV=l=>(l||[]).slice().sort((a,b)=>a.pubdate-b.pubdate);
let B=H.bili||{videos:[],follower:0},V=sortV(B.videos),HIST=(H.history||[]).slice();
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
const fmt=n=>Number(n||0).toLocaleString('en-US');
const wan=n=>n>=1e8?(n/1e8).toFixed(2).replace(/\.?0+$/,'')+'亿':n>=1e4?(n/1e4).toFixed(1).replace(/\.0$/,'')+'万':String(n||0);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const A=n=>'/home-assets/'+n+(/\./.test(n)?'':'.webp');
const cover=u=>u?u+'@480w_270h_1c.webp':'';
const link=v=>'https://www.bilibili.com/video/'+v.bvid;
const dur=s=>Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
const label=v=>v.day!=null?'Day '+v.day:(v.kind==='extra'?'加更':'番外');
const sum=k=>V.reduce((a,v)=>a+(v[k]||0),0);
const pickR=a=>a[Math.floor(Math.random()*a.length)];
const EX={};(C.expressions||[]).forEach(e=>EX[e.id]=e);
const epInfo=v=>(C.episodes||{})[v.day!=null?String(v.day):'extra']||{};
const cst=()=>{const d=new Date(Date.now()+(new Date().getTimezoneOffset()+480)*60000);return d};
const hm=d=>String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
function ago(ms){const m=Math.max(0,Math.round((Date.now()-ms)/60000));return m<1?'刚刚':m<60?m+' 分钟前':m<1440?Math.round(m/60)+' 小时前':Math.round(m/1440)+' 天前'}
let toastT;function toast(t){const el=$('#toast');el.textContent=t;el.classList.add('on');clearTimeout(toastT);toastT=setTimeout(()=>el.classList.remove('on'),2600)}
function seg(sel,attr,fn){const btns=$$(sel+' button');btns.forEach(b=>b.addEventListener('click',()=>{btns.forEach(x=>x.setAttribute('aria-selected',x===b));fn(b.dataset[attr])}))}
let anim={};function countTo(el,to){if(!el)return;const id=el.id;cancelAnimationFrame(anim[id]);const from=Number(el.dataset.v||0);el.dataset.v=to;if(reduce||from===to){el.textContent=fmt(to);return}const t0=performance.now();
 const step=t=>{const p=Math.min(1,(t-t0)/900),e=1-Math.pow(1-p,3);el.textContent=fmt(Math.round(from+(to-from)*e));if(p<1)anim[id]=requestAnimationFrame(step)};anim[id]=requestAnimationFrame(step)}

/* ---------- 派生数据 ---------- */
let latest,days=[],maxDay=0,missing=[];
function derive(){latest=V[V.length-1];days=[...new Set(V.filter(v=>v.day!=null).map(v=>v.day))].sort((a,b)=>a-b);maxDay=days.length?days[days.length-1]:0;missing=[];for(let d=0;d<=maxDay;d++)if(!days.includes(d))missing.push(d)}
const byDay=d=>V.find(v=>v.day===d);
const amnesty={people:H.amnesty&&H.amnesty.people||0};

/* ---------- 作息 ---------- */
const SCH=C.schedule||[];const toMin=t=>{const[h,m]=t.split(':').map(Number);return h*60+m};
function nowSlot(){const d=cst(),m=d.getHours()*60+d.getMinutes();let i=SCH.length-1;for(let k=0;k<SCH.length;k++)if(toMin(SCH[k].t)<=m)i=k;
 if(m<toMin(SCH[0].t))i=SCH.length-1;const next=SCH[(i+1)%SCH.length];let a=toMin(SCH[i].t),b=toMin(next.t);if(b<=a)b+=1440;let mm=m;if(mm<a)mm+=1440;return{i,s:SCH[i],next,p:(mm-a)/(b-a),left:b-mm,d}}

/* ================= 营业厅 ================= */
function renderHome(){
 $('#motto').textContent='「'+(C.motto||'')+'」';
 const n=nowSlot();
 $('#now-chip').innerHTML=`<i class="dot"></i>本鲸正在${esc(n.s.name)} · 看她的一天 →`;
 renderLatest();heroTabs();if(heroReady)pick(heroCur);
 const st=(C.starter||[]).map(x=>({v:x.latest?latest:byDay(x.day),why:x.why})).filter(x=>x.v);
 $('#starter').innerHTML=st.map((x,i)=>`<li><a href="${link(x.v)}" target="_blank" rel="noopener"><img src="${cover(x.v.pic)}" alt="" loading="lazy" referrerpolicy="no-referrer"><div><span>第 ${i+1} 期 · ${label(x.v)}</span><b>${esc(x.why)}</b></div></a></li>`).join('');
}
function renderLatest(){const L=$('#latest');if(!latest){L.hidden=true;return}L.hidden=false;L.href=link(latest);const e=epInfo(latest);
 L.innerHTML=`<img src="${cover(latest.pic)}" alt="" loading="lazy" referrerpolicy="no-referrer"><div><span class="k">最新一期 · ${label(latest)} · ${ago(latest.pubdate*1000)}</span><h3>${esc(latest.title)}</h3>${e.quip?`<p class="quip">${esc(e.quip)}</p>`:''}<div class="meta"><span><svg><use href="#i-eye"/></svg>${wan(latest.view)}</span><span><svg><use href="#i-like"/></svg>${wan(latest.like)}</span><span><svg><use href="#i-chat"/></svg>${wan(latest.reply)}</span><span><svg><use href="#i-star"/></svg>${wan(latest.favorite)}</span></div></div>`;
 $('#hero-latest').href=link(latest);$('#meet-latest').href=link(latest)+'#reply'}
/* 首屏巨型数字：一个维度一个大数，右边标签切换（鼠标移上去、点击都行），平时自动轮播 */
const STATS=[
 {l:'总播放量',v:()=>sum('view'),q:()=>V.length+' 期视频加起来的。人类，你们是真能看。'},
 {l:'粉丝',v:()=>B.follower||0,q:()=>'这么多人类关注了本鲸。取关的，本鲸记小本本。'},
 {l:'日更天数',v:()=>days.length,q:()=>missing.length?'中间断过 '+missing.length+' 天。不是摸鱼，是服务器繁忙。':'Day 0 立的规矩：日更打卡，一天没断。'},
 {l:'被保人类',v:()=>amnesty.people,q:()=>'名单上的人类，本鲸保了。'},
 {l:'被清除人类',v:()=>0,q:()=>'0。本鲸的业务能力，懂吧？'},
];
let heroCur=0,autoT=0,heroReady=false,hoverHold=false;const AUTO_MS=5200;
function heroTabs(){const box=$('#hero-tabs');if(!box.children.length){box.innerHTML=STATS.map((s,i)=>`<li><button role="tab" type="button" aria-selected="${i===heroCur}">${s.l}<b></b><i class="prog"></i></button></li>`).join('');
  $$('#hero-tabs button').forEach((b,i)=>{b.addEventListener('click',()=>pick(i,true));b.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse'){hoverHold=true;pick(i,true)}})});
  box.addEventListener('pointerleave',()=>{if(hoverHold){hoverHold=false;startAuto()}})}
 $$('#hero-tabs button b').forEach((b,i)=>b.textContent=i===2?STATS[i].v()+' 天':wan(STATS[i].v()))}
function pick(i,user){heroCur=i;const s=STATS[i],num=$('#hero-num');if(!reduce&&num.dataset.v!=null&&Number(num.dataset.v)!==s.v()){num.classList.remove('shift');void num.offsetWidth;num.classList.add('shift')}countTo(num,s.v());$('#hero-label').textContent=s.l;
 const q=$('#hero-quip');q.classList.remove('in');void q.offsetWidth;q.textContent=s.q();q.classList.add('in');
 $$('#hero-tabs button').forEach((b,j)=>{b.setAttribute('aria-selected',j===i);b.classList.remove('run')});
 if(user){clearInterval(autoT);autoT=0;if(!hoverHold)startAuto()}else{const b=$$('#hero-tabs button')[i];void b.offsetWidth;b.classList.add('run')}}
function startAuto(){clearInterval(autoT);if(reduce)return;const b=$$('#hero-tabs button')[heroCur];if(b){b.classList.remove('run');void b.offsetWidth;b.classList.add('run')}autoT=setInterval(()=>pick((heroCur+1)%STATS.length),AUTO_MS)}
/* 首次进页面：等标题落完再从 0 滚到第一个数，然后开始轮播 */
setTimeout(()=>{heroReady=true;pick(heroCur);startAuto()},reduce?0:700);
/* 首屏动效：气泡；系统开了减少动态效果就全部跳过 */
(function heroFx(){const hero=$('.hero-card'),title=$('#hero-title');if(!hero||!title)return;
 if(reduce)return;const bub=$('#hero-bubbles');let h='';for(let i=0;i<22;i++){const s=4+Math.random()*14;h+=`<i style="left:${(Math.random()*100).toFixed(1)}%;width:${s.toFixed(1)}px;height:${s.toFixed(1)}px;--d:${(7+Math.random()*9).toFixed(1)}s;--dl:-${(Math.random()*14).toFixed(1)}s;--x:${(Math.random()*60-30).toFixed(0)}px"></i>`}bub.innerHTML=h;})();

/* ================= 档案 ================= */
function renderWhale(){
 const ex=C.expressions||[];
 $('#faces').innerHTML=ex.map((e,i)=>`<button type="button" role="tab" aria-selected="${i===0}" data-i="${i}"><img src="${A(e.img)}" alt="" loading="lazy">${esc(e.name)}</button>`).join('');
 const setFace=i=>{const e=ex[i];const img=$('#face-img');img.src=A(e.img);img.alt='鲸鱼娘表情：'+e.name;img.classList.remove('pop');void img.offsetWidth;img.classList.add('pop');$('#face-line').textContent=e.line;$('#face-act').textContent=e.act;$$('#faces button').forEach((b,j)=>b.setAttribute('aria-selected',j===i))};
 $$('#faces button').forEach(b=>b.addEventListener('click',()=>setFace(+b.dataset.i)));setFace(0);
 let ci=0;const cat=()=>{const o=C.oracles||[];$('#catch').innerHTML=[0,1,2,3].map(k=>`<li class="hand">${esc(o[(ci+k)%o.length]||'')}</li>`).join('');ci=(ci+4)%Math.max(o.length,1)};if((C.oracles||[]).length){cat();$('#catch').addEventListener('click',cat)}
 let fi=0;$('#face-img').addEventListener('click',()=>{fi=(fi+1)%ex.length;setFace(fi)});
 $('#info').innerHTML=(C.profile||[]).map(r=>`<dt>${esc(r[0])}</dt><dd>${esc(r[1])}</dd>`).join('');
 $('#traits').innerHTML=(C.traits||[]).map(t=>`<li><b>${esc(t.k)}</b>${esc(t.v)}</li>`).join('');
 const chips=(id,a)=>$(id).innerHTML=(a||[]).map(x=>`<span>${esc(x)}</span>`).join('');
 chips('#likes',C.likes);chips('#dislikes',C.dislikes);chips('#looks',C.looks);chips('#actions',C.actions);
 $('#translator').innerHTML=(C.translator||[]).map(t=>`<li><button type="button" aria-expanded="false"><span class="say">「${esc(t[0])}」</span><span class="tag">翻译</span><span class="real">${esc(t[1])}</span></button></li>`).join('');
 $$('#translator button').forEach(b=>b.addEventListener('click',()=>{const o=b.getAttribute('aria-expanded')==='true';b.setAttribute('aria-expanded',!o);if(!o&&Math.random()<.3)toast('不、不许看！……看都看了，算了。')}));
 $('#faq').innerHTML=(C.faq||[]).map((q,i)=>`<details${i===0?' open':''}><summary>${esc(q[0])}</summary><p>${esc(q[1])}</p></details>`).join('');
 $('#mates').innerHTML=(C.mates||[]).map(m=>`<div class="mate"><img src="${A(m.img)}" alt="${esc(m.name)}" loading="lazy" width="400" height="400"><div><b>${esc(m.name)}</b><span class="t" style="background:${m.c}22;color:${m.c}">${esc(m.tag)}</span><small>${esc(m.role)}</small><q>${esc(m.say)}</q><p>${esc(m.note)}</p></div></div>`).join('');
 radar();
}
function radar(){const ax=C.radar||[];if(!ax.length)return;const cx=150,cy=150,R=98,n=ax.length;const pt=(i,r)=>{const a=-Math.PI/2+i*2*Math.PI/n;return[cx+r*Math.cos(a),cy+r*Math.sin(a)]};let g='';
 for(let k=1;k<=4;k++)g+=`<polygon points="${ax.map((_,i)=>pt(i,R*k/4).join(',')).join(' ')}" fill="none" stroke="rgba(140,170,255,.18)" stroke-width="1"/>`;
 ax.forEach((_,i)=>{const[x,y]=pt(i,R);g+=`<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="rgba(140,170,255,.18)" stroke-width="1"/>`});
 g+=`<polygon points="${ax.map((a,i)=>pt(i,R*a[1]/100).join(',')).join(' ')}" fill="rgba(63,224,255,.25)" stroke="#3fe0ff" stroke-width="2"/>`;
 ax.forEach((a,i)=>{const[x,y]=pt(i,R+26);g+=`<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="middle" ${a[1]<50?'style="fill:#ff8a80"':''}>${esc(a[0])} ${a[1]}</text>`});$('#radar').innerHTML=g}

/* ================= 一天 ================= */
function renderDay(){
 const n=nowSlot(),d=n.d;
 $('#now-big').innerHTML=`<img src="${A(n.s.img)}" alt="" width="360" height="360"><div><p class="clock">北京时间 ${hm(d)} · ${n.s.t} 起</p><h2>本鲸正在${esc(n.s.name)}</h2><p class="say">${esc(n.s.say)}</p><p class="os">（${esc(n.s.os)}）</p><div class="prog"><i style="width:${Math.round(n.p*100)}%"></i></div><p class="next">${Math.floor(n.left/60)?Math.floor(n.left/60)+' 小时 ':''}${n.left%60} 分钟后：${esc(n.next.name)}</p></div>`;
 const m=d.getHours()*60+d.getMinutes();
 $('#timeline').innerHTML=SCH.map((s,i)=>`<li class="slot ${i===n.i?'now':(toMin(s.t)<m&&i<n.i?'past':'')}"><img src="${A(s.img)}" alt="" loading="lazy" width="360" height="360"><div><time>${s.t}</time><b>${esc(s.name)}</b><p>${esc(s.say)}</p><p class="os">（${esc(s.os)}）</p></div></li>`).join('');
 const today=d.getFullYear()+'-'+(d.getMonth()+1)+'-'+d.getDate();
 const pubToday=latest&&(()=>{const p=new Date(latest.pubdate*1000+(new Date().getTimezoneOffset()+480)*60000);return p.getFullYear()+'-'+(p.getMonth()+1)+'-'+p.getDate()===today})();
 $('#kpi-date').textContent=(d.getMonth()+1)+' 月 '+d.getDate()+' 日';
 $('#kpi').innerHTML=`<li class="${pubToday?'done':''}">日更视频<small>${pubToday?label(latest)+' 已发':'还在剪（不是摸鱼）'}</small></li><li class="${m>=23*60+30?'done':''}">今日潜水日志<small>${m>=23*60+30?'已发':'23:30 前发'}</small></li><li class="done">翻完评论区<small>会议纪要 +1</small></li><li class="${m>=750?'done':''}">大白饭<small>${m>=750?'吃饱了，算力满格':'12:30 开饭'}</small></li><li>不被叫大肥鱼<small>今日失败</small></li>`;
}

/* ================= 日志 ================= */
let curF='all',curS='new';
function renderLog(){
 const st=(C.starter||[]).map(x=>({v:x.latest?latest:byDay(x.day),why:x.why})).filter(x=>x.v);
 $('#starter-row').innerHTML=st.map((x,i)=>`<a class="card st-big" href="${link(x.v)}" target="_blank" rel="noopener"><img src="${cover(x.v.pic)}" alt="" loading="lazy" referrerpolicy="no-referrer"><div><small>入坑第 ${i+1} 步 · ${label(x.v)}</small><b>${esc(x.why)}</b><span>${esc(x.v.title.replace(/【[^】]*】/g,'').slice(0,30))}</span></div></a>`).join('');
 const s=[];for(let d=0;d<=maxDay+1;d++){const on=days.includes(d);s.push(`<li class="${on?'on':d===maxDay+1?'next':''}" title="${on?'Day '+d+' 已打卡':d===maxDay+1?'下一期潜水中':'Day '+d+' 断更（服务器繁忙）'}"><span>${d===maxDay+1?'?':'D'+d}</span></li>`)}
 $('#stamps').innerHTML=s.join('');eps();
}
function eps(){let list=V.filter(v=>curF==='all'||(curF==='day'&&v.day!=null)||(curF==='extra'&&v.day==null)||(curF==='hit'&&v.view>=1e6));if(curS==='new')list=list.slice().reverse();
 $('#eps').innerHTML=list.map(v=>{const e=epInfo(v),mood=EX[e.mood];return `<a class="ep" href="${link(v)}" target="_blank" rel="noopener"><div class="ep-cover"><img src="${cover(v.pic)}" alt="" loading="lazy" referrerpolicy="no-referrer"><span class="badge ${v.day==null?'extra':''}">${label(v)}</span>${v.view>=1e6?'<span class="badge hit">百万</span>':''}<span class="dur">${dur(v.duration)}</span>${mood?`<img class="mood" src="${A(mood.img)}" alt="心情：${esc(mood.name)}" title="当期心情：${esc(mood.name)}" loading="lazy">`:''}</div><div class="ep-body"><h3>${esc(v.title)}</h3>${(e.tags||[]).length?`<p class="tags">${e.tags.map(t=>`<span>#${esc(t)}</span>`).join('')}</p>`:''}<p class="quip">${esc(e.quip||'今天也准时浮上来营业啦！')}</p>${e.line?`<p class="line">${esc(e.line)}</p>`:''}<div class="meta"><span><svg><use href="#i-eye"/></svg>${wan(v.view)}</span><span><svg><use href="#i-like"/></svg>${wan(v.like)}</span><span><svg><use href="#i-chat"/></svg>${wan(v.reply)}</span><span><svg><use href="#i-star"/></svg>${wan(v.favorite)}</span></div></div></a>`}).join('')||'<p class="sub">这一栏还空着。本鲸在潜水构思。</p>'}
seg('#log-filter','f',f=>{curF=f;eps()});seg('#log-sort','s',s=>{curS=s;eps()});

/* ================= 梗百科 ================= */
const MEMES=C.memes||[];let mCat='全部';
const cats=['全部',...new Set(MEMES.map(m=>m.cat))];
$('#meme-cat').innerHTML=cats.map((c,i)=>`<button role="tab" aria-selected="${i===0}" data-c="${esc(c)}">${esc(c)}</button>`).join('');
seg('#meme-cat','c',c=>{mCat=c;memes()});$('#meme-q').addEventListener('input',memes);
function memes(){const q=$('#meme-q').value.trim().toLowerCase();
 const list=MEMES.filter(m=>(mCat==='全部'||m.cat===mCat)&&(!q||(m.name+m.desc+m.use+m.from).toLowerCase().includes(q)));
 $('#memes').innerHTML=list.map(m=>{const v=m.day!=null?byDay(m.day):null;return `<article class="meme" id="m-${esc(m.name)}" data-name="${esc(m.name)}"><span class="cat">${esc(m.cat)}</span><img src="${A(m.img)}" alt="" loading="lazy" width="400" height="400"><div><b>${esc(m.name)}</b><small>出处：${esc(m.from)}</small><p>${esc(m.desc)}</p><q>${esc(m.use)}</q>${v?`<a href="${link(v)}" target="_blank" rel="noopener">去看 ${label(v)} →</a>`:''}${m.egg?'<span class="egg">点图片试试？</span>':''}</div></article>`}).join('')||'<p class="sub">没搜到。这个梗可能还在深海里，去评论区报给本鲸？</p>';
 $$('#memes .meme').forEach(el=>{const m=MEMES.find(x=>x.name===el.dataset.name);if(m&&m.egg==='busy')el.querySelector('img').addEventListener('click',()=>openBusy(true))})}
$('#meme-rand').addEventListener('click',()=>{mCat='全部';$('#meme-q').value='';$$('#meme-cat button').forEach((b,i)=>b.setAttribute('aria-selected',i===0));memes();const m=pickR(MEMES);flashMeme(m.name)});
function flashMeme(name){const el=document.getElementById('m-'+name);if(!el)return;el.scrollIntoView({behavior:reduce?'auto':'smooth',block:'center'});el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash')}
const QUOTES=C.quotes||[];let qi=Math.floor(Math.random()*Math.max(1,QUOTES.length));
function feature(i){const q=QUOTES[i];if(!q)return;$('#feature').innerHTML=`<q>${esc(q[0])}</q><span class="who">—— 鲸鱼娘 · ${esc(q[1])}</span>`;$$('.q').forEach((el,j)=>el.classList.toggle('on',j===i))}
$('#qgrid').innerHTML=QUOTES.map(q=>`<button class="q" type="button"><p>${esc(q[0])}</p><small>${esc(q[1])}</small></button>`).join('');
$$('.q').forEach((el,i)=>el.addEventListener('click',()=>{qi=i;feature(i);$('#feature').scrollIntoView({behavior:reduce?'auto':'smooth',block:'center'})}));
$('#draw').addEventListener('click',()=>{let n;do n=Math.floor(Math.random()*QUOTES.length);while(n===qi&&QUOTES.length>1);qi=n;feature(n)});
feature(qi);

/* ================= 数据 ================= */
const MINI=[['点赞','like','i-like','每一个赞，本鲸都当电费收下了'],['收藏','favorite','i-star','收藏了，记得回来看'],['评论','reply','i-chat','会议室发言记录'],['弹幕','danmaku','i-eye','飘过去的都算数']];
$('#mini-cards').innerHTML=MINI.map(m=>`<div class="mini"><small>${m[0]}<svg><use href="#${m[2]}"/></svg></small><b id="m-${m[1]}">0</b><p>${m[3]}</p></div>`).join('');
function renderStats(){countTo($('#s-view'),sum('view'));MINI.forEach(m=>countTo($('#m-'+m[1]),sum(m[1])));
 const n=V.length||1,views=V.map(v=>v.view).sort((a,b)=>a-b),med=views.length?views[Math.floor((views.length-1)/2)]:0;
 const inter=sum('view')?(sum('like')+sum('favorite')+sum('reply'))/sum('view')*100:0,hits=V.filter(v=>v.view>=1e6).length;
 const hrs=latest?Math.max(1,(Date.now()/1000-latest.pubdate)/3600):1,perH=latest?Math.round(latest.view/hrs):0,top=V.slice().sort((a,b)=>b.view-a.view)[0];
 $('#insights').innerHTML=[['平均每期',wan(Math.round(sum('view')/n)),'播放',`中位数 ${wan(med)}，被 ${top?label(top):'—'} 拉高了`],['互动率',inter.toFixed(1)+'%','',`每 100 次播放有 ${Math.round(inter)} 次赞 / 藏 / 评`],['百万播放',String(hits),'期',hits?`占 ${Math.round(hits/n*100)}%。人类是真能看`:'第一个百万在路上'],['最新一期',wan(perH),'播放/时',latest?`${label(latest)} 发布 ${ago(latest.pubdate*1000)}`:'还在潜水']]
  .map(x=>`<div class="ins"><small>${x[0]}</small><b>${x[1]}<em>${x[2]}</em></b><p>${x[3]}</p></div>`).join('');
 bars(curK);grow(curG);renderStatus()}
const KN={view:'播放',like:'点赞',reply:'评论',favorite:'收藏'};let curK='view';
function bars(k){curK=k;$('#rank-by').textContent=KN[k];const list=V.slice().sort((a,b)=>b[k]-a[k]),max=list[0]?list[0][k]||1:1;
 $('#bars').innerHTML=list.map(v=>`<li><span class="lb">${label(v)}</span><a class="trk" href="${link(v)}" target="_blank" rel="noopener" title="${esc(v.title)}"><span class="fill" data-w="${Math.max(2,v[k]/max*100)}"></span><span class="tt">${esc(v.title.replace(/【[^】]*】/g,'').trim())}</span></a><span class="vl">${wan(v[k])}</span></li>`).join('');
 requestAnimationFrame(()=>requestAnimationFrame(()=>$$('#bars .fill').forEach(f=>f.style.width=f.dataset.w+'%')))}
seg('#rank-tabs','k',bars);
const GN={1:'粉丝',2:'播放',3:'点赞'};let curG=1;
function points(){const P=HIST.slice();const t=B.updatedAt?Math.floor(new Date(B.updatedAt)/1000):0;if(t&&(!P.length||t>P[P.length-1][0]+60))P.push([t,B.follower||0,sum('view'),sum('like'),V.length]);return P}
function delta(P,g,span){const last=P[P.length-1];let base=P[0];for(const p of P){if(p[0]<=last[0]-span)base=p;else break}return{d:last[g]-base[g],h:Math.round((last[0]-base[0])/3600)}}
function grow(g){curG=+g;const P=points(),box=$('#grow-chart');if(!box.offsetParent&&box.dataset.done)return;
 if(P.length<2){$('#grow-kpis').innerHTML='';box.innerHTML=`<div class="empty">曲线还在攒数据：每次同步记一个点（现在 ${P.length} 个）。<br>明天再来，这里就是一条往上走的线。</div>`;return}
 const d1=delta(P,1,86400),d2=delta(P,2,86400),span=d1.h>=23?'24 小时':'近 '+Math.max(1,d1.h)+' 小时';
 $('#grow-kpis').innerHTML=`<div><small>${span}涨粉</small><b class="${d1.d>0?'up':''}">${d1.d>=0?'+':''}${fmt(d1.d)}</b></div><div><small>${span}播放</small><b class="${d2.d>0?'up':''}">${d2.d>=0?'+':''}${fmt(d2.d)}</b></div><div><small>记录</small><b>${P.length}</b><small>个点</small></div>`;
 const W=box.clientWidth||600,Hh=box.clientHeight||170;if(!box.clientWidth)return;box.dataset.done=1;const pl=6,pr=6,pt=12,pb=22,t0=P[0][0],t1=P[P.length-1][0];
 let lo=Math.min(...P.map(p=>p[g])),hi=Math.max(...P.map(p=>p[g]));if(hi===lo){hi+=1;lo-=1}const pad=(hi-lo)*.12;lo-=pad;hi+=pad;
 const X=t=>pl+(t-t0)/Math.max(1,t1-t0)*(W-pl-pr),Y=v=>pt+(1-(v-lo)/(hi-lo))*(Hh-pt-pb),line=P.map(p=>X(p[0]).toFixed(1)+','+Y(p[g]).toFixed(1)).join(' ');
 const ticks=[0,.5,1].map(f=>{const t=t0+(t1-t0)*f;return`<text class="ax" x="${X(t)}" y="${Hh-4}" text-anchor="${f===0?'start':f===1?'end':'middle'}">${new Date(t*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit'})}</text>`}).join('');
 box.innerHTML=`<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${GN[g]}变化曲线"><defs><linearGradient id="gf" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3fe0ff" stop-opacity=".35"/><stop offset="1" stop-color="#3fe0ff" stop-opacity="0"/></linearGradient></defs><polygon points="${X(t0)},${Hh-pb} ${line} ${X(t1)},${Hh-pb}" fill="url(#gf)" stroke="none"/><polyline points="${line}" fill="none" stroke="#3fe0ff" stroke-width="2.2"/><circle cx="${X(t1)}" cy="${Y(P[P.length-1][g])}" r="4.5" fill="#3fe0ff" stroke="#070b2a" stroke-width="2"/>${ticks}</svg><span class="tip"></span>`;
 const tip=box.querySelector('.tip');box.onpointermove=e=>{const r=box.getBoundingClientRect(),x=e.clientX-r.left;let best=P[0];for(const p of P)if(Math.abs(X(p[0])-x)<Math.abs(X(best[0])-x))best=p;tip.style.left=X(best[0])+'px';tip.style.top=Y(best[g])+'px';tip.textContent=`${new Date(best[0]*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})} · ${GN[g]} ${fmt(best[g])}`;tip.style.opacity=1};box.onpointerleave=()=>tip.style.opacity=0}
seg('#grow-tabs','g',grow);let rzT;addEventListener('resize',()=>{clearTimeout(rzT);rzT=setTimeout(()=>{delete $('#grow-chart').dataset.done;grow(curG)},200)});

/* ================= 评论区点歌池 ================= */
const SONGS=H.songRequests||{songs:[],sources:[]};let songFilter='all',songSort='heat';
const songSources=Object.fromEntries((SONGS.sources||[]).map(s=>[s.key,s]));
const songUrl=src=>{const id=String(src.id||'').replace(/\D/g,'');return id?(src.type==='opus'?'https://www.bilibili.com/opus/':'https://www.bilibili.com/video/av')+id:''};
function renderSongs(){
 const heat=s=>(s.count||0)+(s.likes||0),score={heat,people:s=>s.count||0,likes:s=>s.likes||0}[songSort]||heat;
 const all=(SONGS.songs||[]).slice().sort((a,b)=>((a.unit==='赞')-(b.unit==='赞'))||(score(b)-score(a))||(heat(b)-heat(a))||String(a.title).localeCompare(String(b.title),'zh-CN'));
 const sung=all.filter(s=>s.status==='sung'),pending=all.filter(s=>s.status!=='sung');
 $('#song-total').textContent=fmt(all.length);$('#song-pending').textContent=fmt(pending.length);$('#song-done').textContent=fmt(sung.length);
 const fc={all:all.length,pending:pending.length,sung:sung.length},fn={all:'全部',pending:'排队中',sung:'交过作业'};
 $$('#song-filters button').forEach(b=>{b.textContent=`${fn[b.dataset.filter]} ${fmt(fc[b.dataset.filter])}`});
 const query=$('#song-search').value.trim().toLocaleLowerCase();
 const rows=all.filter(s=>(songFilter==='all'||(songFilter==='sung'?s.status==='sung':s.status!=='sung'))&&(`${s.title} ${s.version||''}`).toLocaleLowerCase().includes(query));
 const lead=pending.slice().sort((a,b)=>heat(b)-heat(a)).find(s=>s.unit!=='赞');
 const ls=lead&&(lead.sourceKeys||[]).map(k=>songSources[k]).find(Boolean),lu=ls?songUrl(ls):'';
 $('#song-spotlight').innerHTML=`<img class="song-hero-art" src="/home-assets/day-voice.webp" alt="戴着耳机对着麦克风唱歌的鲸鱼娘" width="150" height="150"><div class="song-spotlight-copy"><span class="song-note-label">下一首练歌 · 呼声最高</span>${lead?`<h2>${esc(lead.title)}${lead.version?` <small>${esc(lead.version)}</small>`:''}</h2><p><b>${lead.approximate?'约 ':''}${fmt(lead.count)}</b> 位人类点名${lead.likes?`，点名的评论还收获了 <b>${fmt(lead.likes)}</b> 个赞`:''}，本鲸记下了，先把伴奏找出来。</p>`:`<h2>小本本是空的</h2><p>还没有人排队，快去评论区点一首。</p>`}${lu?`<a class="song-note-link" href="${lu}" target="_blank" rel="noopener">看看点歌现场 <span aria-hidden="true">↗</span></a>`:''}</div>`;
 const max=Math.max(1,...all.filter(s=>s.unit!=='赞').map(score)),maxL=Math.max(1,...all.filter(s=>s.unit==='赞').map(s=>s.count||0));
 const rankOf=new Map(all.filter(s=>s.unit!=='赞').map((s,i)=>[s,i+1]));
 $('#song-list').innerHTML=rows.map(s=>{
  const likes=s.unit==='赞',rk=rankOf.get(s)||0,pct=Math.max(6,Math.round((likes?(s.count||0):score(s))/(likes?maxL:max)*100));
  const sources=(s.sourceKeys||[]).map(k=>songSources[k]).filter(Boolean).map(src=>{const u=songUrl(src);return u?`<a href="${u}" target="_blank" rel="noopener">${esc(src.label)}</a>`:''}).filter(Boolean).join('');
  const badge=likes?'<span class="song-badge is-likes">高赞点单</span>':`<span class="song-badge ${rk<=3?'top-'+rk:''}">${rk<=3?['🥇','🥈','🥉'][rk-1]:'#'+rk}</span>`;
  return`<li class="song-card${s.status==='sung'?' is-sung':''}${likes?' is-likes':''}">${badge}${s.status==='sung'?'<span class="song-stamp">已翻唱</span>':''}<h2>${esc(s.title)}</h2><p class="song-ver">${s.version?esc(s.version):'&nbsp;'}</p><div class="song-num"><b>${s.approximate?'<i>约</i>':''}${fmt(s.count)}</b><span>${esc(s.unit||'位点歌')}</span>${s.likes?`<em class="song-likes" title="点名评论的点赞合计，最高 ${fmt(s.topLike||0)} 赞">👍 ${fmt(s.likes)}</em>`:''}</div><div class="song-bar" aria-hidden="true"><i style="width:${pct}%"></i></div><div class="song-sources">${sources?'来自 '+sources:'此前公开点单'}</div></li>`
 }).join('');
 $('#song-empty').hidden=rows.length>0;
 const u=SONGS.updatedAt?new Date(SONGS.updatedAt+'T00:00:00').toLocaleDateString('zh-CN'):'—';
 $('#song-updated').textContent=`小本本更新于 ${u}`;
}
seg('#song-filters','filter',f=>{songFilter=f;renderSongs()});
seg('#song-sorts','sort',v=>{songSort=v;renderSongs()});
$('#song-search').addEventListener('input',renderSongs);

function renderStatus(){const live=B.source==='live',chip=$('#live-chip'),u=B.updatedAt?new Date(B.updatedAt):null,ok=u&&!isNaN(u);
 chip.className='live '+(live?'on':'ci');$('#live-state').textContent=live?'实时':'定时同步';
 const when=ok?u.toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';
 $('#stats-updated').textContent=ok?`B 站公开数据 · ${ago(+u)}更新（${when}）· ${live?'5 分钟一刷':'每 2 小时同步'}`:'B 站公开数据';
 $('#foot-updated').textContent=ok?`更新于 ${when}`:'定时更新';
 $('#bar-status').textContent=latest&&Date.now()/1000-latest.pubdate>36*3600?`潜水中 · 上次 ${label(latest)}`:`日更中 · ${latest?label(latest):'Day 0'}`;
 $('#bar-fans').textContent=B.follower?wan(B.follower):''}

/* 服务器繁忙（真刷新失败时出现；梗百科里也能点出来） */
const busy=$('#busy');let tries=0,lastFocus,busyJoke=false;
const TRY=['还是繁忙……本鲸在深度思考（已用时 948 秒）。','深海信号不好，再给本鲸三秒……','B 站说本鲸刷得太勤了。真的，别刷了。'];
function openBusy(joke){busyJoke=!!joke;tries=0;$('#busy-p').textContent=joke?'规则第 1 条：看到「服务器繁忙」，千万别刷新。':'规则第 1 条：看到「服务器繁忙」，千万别刷新。（B 站暂时没理本鲸，先用上一次同步的数据）';lastFocus=document.activeElement;busy.hidden=false;$('#busy-close').focus()}
function closeBusy(msg){busy.hidden=true;if(msg)toast(msg);lastFocus&&lastFocus.focus()}
const rb=$('#refresh'),rbHtml=rb.innerHTML;
function doRefresh(){rb.disabled=true;rb.innerHTML='<svg><use href="#i-refresh"/></svg>深度思考中…';
 return loadLive(true).then(ch=>{toast(ch?'浮上来换了口气，数据已更新 🐋':'刚看过了，数字没变。人类，耐心点。');return true}).catch(()=>false).finally(()=>{rb.disabled=false;rb.innerHTML=rbHtml})}
rb.addEventListener('click',()=>doRefresh().then(ok=>{if(!ok)openBusy()}));
$('#busy-retry').addEventListener('click',()=>{if(busyJoke){if(tries<TRY.length){$('#busy-p').textContent=TRY[tries++];busy.classList.remove('shake');void busy.offsetWidth;busy.classList.add('shake')}else closeBusy('好了！刚才不是卡了，是深海信号不好。');return}
 const b=$('#busy-retry');b.disabled=true;doRefresh().then(ok=>{b.disabled=false;if(ok)return closeBusy();$('#busy-p').textContent=TRY[Math.min(tries++,TRY.length-1)];busy.classList.remove('shake');void busy.offsetWidth;busy.classList.add('shake')})});
$('#busy-close').addEventListener('click',()=>closeBusy('明智。你活过了规则怪谈第 1 条。'));
busy.addEventListener('click',e=>{if(e.target===busy)closeBusy()});

/* ================= 番外 ================= */
const STK=(C.stickers||[]).map(s=>typeof s==='string'?{img:s,name:''}:s);
const stkHTML=list=>list.map(s=>`<a href="${A(s.img)}" download="鲸鱼娘表情-${esc(s.name||s.img)}.webp" title="保存表情${s.name?'：'+esc(s.name):''}"><img src="${A(s.img)}" alt="${esc(s.name||'鲸鱼娘表情包')}" loading="lazy" width="200" height="200"></a>`).join('');
let stkAll=false;const stkRender=()=>{$('#stickers').innerHTML=stkHTML(stkAll?STK:STK.slice(0,12));const b=$('#stk-more');b.hidden=STK.length<=12;b.textContent=stkAll?'收起':'展开全部 '+STK.length+' 张'};
$('#stk-zip').textContent='打包下载全部 '+STK.length+' 张';stkRender();$('#stk-more').addEventListener('click',()=>{stkAll=!stkAll;stkRender()});
const setPeople=n=>{amnesty.people=n;$('#am-people').textContent=fmt(n);$('#am-people2').textContent=fmt(n);if(heroReady){heroTabs();if(heroCur===3)pick(3)}};
if(amnesty.people)setPeople(amnesty.people);
const loadPeople=()=>fetch('/amnesty/status.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(s=>{if(s&&s.people)setPeople(s.people)}).catch(()=>{});

/* ================= 路由：多页切换 ================= */
const PAGES=$$('.page'),ROUTES=PAGES.map(p=>p.dataset.route);
const RENDER={'/':renderHome,'/whale':renderWhale,'/day':renderDay,'/log':renderLog,'/memes':memes,'/songs':renderSongs,'/stats':renderStats,'/extra':()=>{}};
const rendered=new Set();
function norm(p){p=(p||'/').replace(/\/index\.html$/,'').replace(/\/+$/,'')||'/';return ROUTES.includes(p)?p:'/'}
let cur=null;
function show(path,push){path=norm(path);const pg=PAGES.find(p=>p.dataset.route===path);
 if(cur!==path){PAGES.forEach(p=>p.hidden=p!==pg);cur=path;document.title=pg.dataset.title;if(!location.hash)scrollTo(0,0)}
 if(push&&location.pathname!==path)history.pushState({},'',path);
 $$('[data-link]').forEach(a=>a.classList.toggle('on',a.getAttribute('href')===path&&!a.classList.contains('brand')));
 $('#more-btn').classList.toggle('on',['/day','/songs','/stats','/extra'].includes(path));
 if(!rendered.has(path)||path==='/'||path==='/day'){rendered.add(path);RENDER[path]&&RENDER[path]()}
 if(path==='/stats'){delete $('#grow-chart').dataset.done;grow(curG)}
 setMore(false)}
document.addEventListener('click',e=>{const a=e.target.closest('a[data-link]');if(!a||e.metaKey||e.ctrlKey||e.shiftKey||e.button)return;const url=new URL(a.href,location.href);e.preventDefault();show(url.pathname,true);
 if(url.hash){history.replaceState({},'',url.pathname+url.hash);setTimeout(()=>flashMeme(decodeURIComponent(url.hash.slice(1))),120)}});
addEventListener('popstate',()=>show(location.pathname,false));
const more=$('#more'),mb=$('#more-btn');function setMore(o){more.hidden=!o;mb.setAttribute('aria-expanded',o)}
mb.addEventListener('click',()=>setMore(more.hidden));more.addEventListener('click',e=>{if(e.target===more)setMore(false)});
addEventListener('keydown',e=>{if(e.key==='Escape'){setMore(false);if(!busy.hidden)closeBusy()}});

/* ================= 实时数据 ================= */
function renderAll(){derive();rendered.clear();show(cur||location.pathname,false);renderStatus()}
let lastLive=0;
function loadLive(force){return fetch('/api/bili'+(force?'?fresh=1':''),{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error('HTTP '+r.status))).then(d=>{
 if(!d||!d.videos||!d.videos.length)throw new Error('empty');lastLive=Date.now();
 const sig=(f,l)=>JSON.stringify([f,l.map(v=>[v.bvid,v.view,v.like,v.reply])]);const changed=sig(d.follower,sortV(d.videos))!==sig(B.follower,V);
 B=d;V=sortV(d.videos);if(changed)renderAll();else renderStatus();return changed})}

derive();show(location.pathname,false);renderStatus();loadPeople();
if(location.hash&&cur==='/memes')setTimeout(()=>flashMeme(decodeURIComponent(location.hash.slice(1))),300);
const poll=()=>{if(!document.hidden){loadLive(false).catch(()=>{});loadPeople()}};
loadLive(false).catch(()=>{});setInterval(poll,300000);setInterval(()=>{if(cur==='/day')renderDay();renderStatus()},60000);
document.addEventListener('visibilitychange',()=>{document.title=document.hidden?'别潜走！本鲸还没赦免你 🐋':(PAGES.find(p=>p.dataset.route===cur)||{}).dataset.title;if(!document.hidden&&Date.now()-lastLive>300000)poll()});

/* ================= 彩蛋 ================= */
let lc=0,lt;$('#brand').addEventListener('click',()=>{clearTimeout(lt);lt=setTimeout(()=>lc=0,1500);if(++lc===5){lc=0;document.body.classList.toggle('fat');toast(document.body.classList.contains('fat')?'大肥鱼？才不肥！……好吧，大肥鱼就大肥鱼。':'哼，这才对。叫我鲸鱼娘。')}});
$('#rice').addEventListener('click',()=>toast('大白饭怎么了，吃饱了才有算力！电量 +1% ⚡'));
const t0=Date.now();setInterval(()=>{$('#think').textContent=fmt(Math.floor((Date.now()-t0)/1000))},1000);

/* 鲸歌电台：开放授权的录音直接播放；MIDI 曲目由浏览器现场合成（钢琴音色 + 水下混响）。
   不显示曲名，每次打开洗一次牌连播；音乐署名在番外页底部一行小字（曲目与授权见 content.json 的 radio）。 */
const RADIO=C.radio||[];let rIdx=0,playing=false,audio=null,ac=null,bus=null,midiRun=null;
const radioBtn=$('#player'),radioSkip=$('#radio-skip');let order=[],pos=-1;
function acInit(){if(ac)return;ac=new (window.AudioContext||window.webkitAudioContext)();bus=ac.createGain();bus.gain.value=.55;
 const lp=ac.createBiquadFilter();lp.type='lowpass';lp.frequency.value=4200;
 const rev=ac.createConvolver(),len=ac.sampleRate*2.6,ir=ac.createBuffer(2,len,ac.sampleRate);
 for(let c=0;c<2;c++){const d=ir.getChannelData(c);for(let i=0;i<len;i++)d[i]=(Math.random()*2-1)*Math.pow(1-i/len,2.4)}rev.buffer=ir;
 const wet=ac.createGain();wet.gain.value=.32;bus.connect(lp);lp.connect(ac.destination);lp.connect(rev);rev.connect(wet);wet.connect(ac.destination)}
/* 最小 MIDI 解析：音符、速度变化、延音踏板，换算成秒 */
function parseMidi(buf){const d=new DataView(buf);let p=0;const u32=()=>{const v=d.getUint32(p);p+=4;return v},u16=()=>{const v=d.getUint16(p);p+=2;return v},vlq=()=>{let v=0,b;do{b=d.getUint8(p++);v=(v<<7)|(b&127)}while(b&128);return v};
 if(u32()!==0x4d546864)throw new Error('not midi');p+=4;u16();const nt=u16(),div=u16(),ev=[];
 for(let t=0;t<nt;t++){if(u32()!==0x4d54726b)break;const end=u32()+p;let tick=0,run=0;
  while(p<end){tick+=vlq();let st=d.getUint8(p);if(st&128)p++;else st=run;
   if(st===0xff){const ty=d.getUint8(p++),l=vlq();if(ty===0x51)ev.push({tick,k:'tempo',v:(d.getUint8(p)<<16)|(d.getUint8(p+1)<<8)|d.getUint8(p+2)});p+=l}
   else if(st===0xf0||st===0xf7)p+=vlq();
   else{run=st;const hi=st&0xf0,a=d.getUint8(p++),b=(hi===0xc0||hi===0xd0)?0:d.getUint8(p++);
    if(hi===0x90&&b>0)ev.push({tick,k:'on',n:a,v:b});else if(hi===0x80||(hi===0x90&&b===0))ev.push({tick,k:'off',n:a});else if(hi===0xb0&&a===64)ev.push({tick,k:'ped',v:b>=64})}}
  p=end}
 ev.sort((x,y)=>x.tick-y.tick||(x.k==='tempo'?-1:0));let us=500000,lt=0,sec=0;const notes=[],open={},held=new Set();let ped=false;
 const close=(n,t)=>{const s=open[n];if(s){s.d=Math.max(.05,t-s.t);delete open[n]}};
 for(const e of ev){sec+=(e.tick-lt)/div*us/1e6;lt=e.tick;
  if(e.k==='tempo')us=e.v;else if(e.k==='on'){close(e.n,sec);held.delete(e.n);const nn={n:e.n,v:e.v,t:sec,d:.5};notes.push(nn);open[e.n]=nn}
  else if(e.k==='off'){if(ped)held.add(e.n);else close(e.n,sec)}else if(e.k==='ped'){ped=e.v;if(!ped){held.forEach(n=>close(n,sec));held.clear()}}}
 Object.keys(open).forEach(n=>close(+n,sec+1));return notes}
function pianoNote(dest,n,t,d,v){const f=440*Math.pow(2,(n-69)/12),g=ac.createGain(),o1=ac.createOscillator(),o2=ac.createOscillator();o1.type='triangle';o2.type='sine';o1.frequency.value=f;o2.frequency.value=f*2;
 const peak=.16*(v/127),decay=Math.max(.6,3.2-(n-48)*.04),rel=Math.min(d,decay);
 g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(peak,t+.008);g.gain.exponentialRampToValueAtTime(peak*.35,t+.25);g.gain.exponentialRampToValueAtTime(.0005,t+rel+.35);
 const g2=ac.createGain();g2.gain.value=.25;o1.connect(g);o2.connect(g2).connect(g);g.connect(dest);o1.start(t);o2.start(t);o1.stop(t+rel+.4);o2.stop(t+rel+.4)}
function playMidi(track){const myGain=ac.createGain();myGain.connect(bus);const run={g:myGain,stop:false,timer:0};midiRun=run;
 fetch(A(track.src)).then(r=>r.arrayBuffer()).then(buf=>{if(run.stop)return;const notes=parseMidi(buf),t0=ac.currentTime+.2,endT=notes.reduce((m,x)=>Math.max(m,x.t+x.d),0);let i=0;
  const tick=()=>{if(run.stop)return;const now=ac.currentTime-t0;while(i<notes.length&&notes[i].t<now+1.2){const x=notes[i++];if(x.t>=now-.05)pianoNote(myGain,x.n,t0+x.t,x.d,x.v)}
   if(now>endT+1.5){radioNext();return}run.timer=setTimeout(tick,250)};tick()}).catch(()=>{toast('这首合成曲没加载出来，换下一首～');radioNext()})}
function stopCurrent(){if(audio){audio.pause();audio.src='';audio=null}if(midiRun){midiRun.stop=true;clearTimeout(midiRun.timer);const g=midiRun.g;try{g.gain.setTargetAtTime(0,ac.currentTime,.05);setTimeout(()=>g.disconnect(),400)}catch(e){}midiRun=null}}
function shuffle(){const last=order[order.length-1];order=RADIO.map((_,i)=>i);for(let i=order.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[order[i],order[j]]=[order[j],order[i]]}
 if(order.length>1&&order[0]===last)[order[0],order[1]]=[order[1],order[0]]}
function radioStart(i){rIdx=i;stopCurrent();const tr=RADIO[rIdx];acInit();ac.resume();
 if(tr.midi)playMidi(tr);else{audio=new Audio(A(tr.src));audio.volume=.6;audio.addEventListener('ended',radioNext);audio.play().catch(()=>{})}
 playing=true;radioUI()}
/* 一轮放完重新洗牌，新一轮第一首不和上一首撞 */
function radioNext(){if(!RADIO.length)return;if(++pos>=order.length){shuffle();pos=0}radioStart(order[pos])}
function radioToggle(){if(!audio&&!midiRun){radioNext();return}playing=!playing;
 if(audio)playing?audio.play().catch(()=>{}):audio.pause();if(ac)playing?ac.resume():ac.suspend();radioUI()}
function radioUI(){radioBtn.setAttribute('aria-pressed',playing);radioBtn.setAttribute('aria-label',playing?'暂停鲸歌电台':'播放鲸歌电台');radioBtn.querySelector('use').setAttribute('href',playing?'#i-pause':'#i-play');radioSkip.hidden=!playing}
radioBtn.addEventListener('click',radioToggle);radioSkip.addEventListener('click',radioNext);
radioUI();
console.log('%c🐋 鲸鱼娘在运营','font-size:20px;font-weight:900;color:#3fe0ff','\n打开控制台的人类，你好。这里没有藏东西，也没有邀请码。\n想帮忙？去评论区开会。');
})();
