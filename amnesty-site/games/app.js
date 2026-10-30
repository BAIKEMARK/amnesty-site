'use strict';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const SITE='https://whaleychan.com/amnesty/games.html';
const ST={get(k,d){try{const v=JSON.parse(localStorage.getItem(k));return v??d}catch(e){return d}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
const pick=a=>a[Math.floor(Math.random()*a.length)];
const shuffle=a=>{a=[...a];for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const art=n=>document.getElementById('art-'+n).src;
const maskUid=u=>u.includes('•')?u:u.length>5?u.slice(0,3)+'•'.repeat(Math.max(2,u.length-5))+u.slice(-2):u.slice(0,1)+'••'+u.slice(-1);
const FAKE_DAYS=['2026-10-21','2026-10-22','2026-10-23','2026-10-24','2026-10-25'];
const face=u=>u&&u.includes('hdslb.com')&&!u.includes('@')?u+'@96w_96h_1c.webp':u;
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('on');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('on'),2200)}
async function copy(text){try{await navigator.clipboard.writeText(text);toast('已复制，去评论区晒一下')}catch(e){const a=document.createElement('textarea');a.value=text;a.style.cssText='position:fixed;opacity:0;top:0';document.body.append(a);a.select();let ok=false;try{ok=document.execCommand('copy')}catch(_){}a.remove();if(ok)toast('已复制，去评论区晒一下');else popup(`<p class="pop-tip"><b>这个浏览器不让自动复制</b><br>长按下面的文字，全选后复制</p><textarea class="pop-text" readonly></textarea>`,box=>{const t=box.querySelector('textarea');t.value=text;t.focus();t.select()})}}
/* 弹层：B 站 App 等内置浏览器不支持自动下载 / 剪贴板，改成弹出来让用户长按保存或复制 */
function popup(html,after){const ov=document.createElement('div');ov.className='overlay pop-ov';ov.innerHTML=`<div class="pop-box">${html}<div class="btns"><button class="ghost pop-close">关闭</button></div></div>`;const close=()=>{ov.remove();document.removeEventListener('keydown',esc)};const esc=e=>{if(e.key==='Escape')close()};document.addEventListener('keydown',esc);ov.querySelector('.pop-close').onclick=close;ov.addEventListener('click',e=>{if(e.target===ov)close()});document.body.append(ov);if(after)after(ov.querySelector('.pop-box'));return ov}
function showPoster(url,file){popup(`<p class="pop-tip"><b>长按图片，保存到相册</b><br>发给朋友，或者发到评论区</p><img class="pop-img" alt="海报">`,box=>{box.querySelector('img').src=url;const a=document.createElement('a');a.className='ghost';a.textContent='下载图片';a.href=url;a.download=file;box.querySelector('.btns').prepend(a)})}
$$('[data-art]').forEach(i=>i.src=art(i.dataset.art));
document.documentElement.style.setProperty('--deskbg',`url(${window.DESKBG})`);
const cstDate=(d=new Date())=>new Date(d.getTime()+(8*60+d.getTimezoneOffset())*60000);
const today=()=>{const n=cstDate();return `${n.getFullYear()}-${String(n.getMonth()+1).padStart(2,'0')}-${String(n.getDate()).padStart(2,'0')}`};
function avatar(src,name,cls='ava'){if(src){const i=new Image();i.className=cls;i.alt='';i.referrerPolicy='no-referrer';i.decoding='async';i.src=face(src);i.onerror=()=>i.replaceWith(avatar('',name,cls));return i}const d=document.createElement('div');d.className=cls+' txt';d.textContent=[...(name||'?')][0];return d}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
// 非机器人头像的陷阱卡借用真实头像和真实 UID 格式，避免靠头像/UID 认卡
function disguise(t){if(t.avatar&&t.avatar.startsWith('bot'))return t;const r=pick(POOL.real);return{...t,face:r.f,uid:r.u.replace(/\d/g,(_,i)=>String(i?Math.floor(Math.random()*10):1+Math.floor(Math.random()*9)))}}
// 每张单子的时限：按字数加时，长文不至于来不及读
const cardTime=c=>POOL.phases[G.phase].seconds*1e3+Math.max(0,[...(c.text??c.t)].length-50)*40;

/* ---------- 音效（WebAudio 现场合成，无音频文件） ---------- */
let AC=null,soundOn=ST.get('whale-sound',true);
function ac(){if(!soundOn)return null;try{AC=AC||new (window.AudioContext||window.webkitAudioContext)();if(AC.state==='suspended')AC.resume();return AC}catch(e){return null}}
function tone(f,d,type='sine',v=.18,slide=0,delay=0){const a=ac();if(!a)return;const t=a.currentTime+delay;const o=a.createOscillator(),g=a.createGain();o.type=type;o.frequency.setValueAtTime(f,t);if(slide)o.frequency.exponentialRampToValueAtTime(Math.max(30,f+slide),t+d);g.gain.setValueAtTime(v,t);g.gain.exponentialRampToValueAtTime(.001,t+d);o.connect(g).connect(a.destination);o.start(t);o.stop(t+d)}
function noise(d,v=.3,freq=900){const a=ac();if(!a)return;const b=a.createBuffer(1,a.sampleRate*d,a.sampleRate),c=b.getChannelData(0);for(let i=0;i<c.length;i++)c[i]=(Math.random()*2-1)*(1-i/c.length)**2;const s=a.createBufferSource(),f=a.createBiquadFilter(),g=a.createGain();f.type='lowpass';f.frequency.value=freq;g.gain.value=v;s.buffer=b;s.connect(f).connect(g).connect(a.destination);s.start()}
const SFX={stamp(){noise(.18,.6,500);tone(90,.18,'sine',.4,-40)},swish(){noise(.22,.25,2400)},ok(){tone(880,.09,'triangle',.12);tone(1320,.14,'triangle',.12,0,.07)},bad(){tone(180,.35,'sawtooth',.14,-60);tone(150,.35,'square',.08,-50,.05)},alarm(){for(let i=0;i<3;i++){tone(700,.14,'square',.1,0,i*.22);tone(500,.14,'square',.1,0,i*.22+.11)}},combo(n){tone(660+n*25,.12,'triangle',.12);tone(990+n*25,.16,'triangle',.1,0,.08)},tick(){tone(1200,.03,'square',.05)},phase(){tone(523,.15,'triangle',.12);tone(659,.15,'triangle',.12,0,.12);tone(784,.25,'triangle',.12,0,.24)},end(){[523,659,784,1046].forEach((f,i)=>tone(f,.25,'triangle',.12,0,i*.12))}};
function syncSound(){$('#sound-btn').textContent=soundOn?'🔊 音效开':'🔇 音效关'}
$('#sound-btn').onclick=()=>{soundOn=!soundOn;ST.set('whale-sound',soundOn);syncSound();if(soundOn)SFX.ok()};syncSound();

let POOL=null;
const poolReady=Promise.resolve(window.__GAME_POOL__).then(p=>POOL=p).catch(()=>{POOL=null});

/* ---------- 路由 ---------- */
function route(){const v=(location.hash.replace('#/','')||'').split('?')[0];const view=['desk','daily'].includes(v)?v:'hub';stopLoop();$$('.overlay').forEach(o=>o.hidden=true);for(const id of['hub','desk','daily'])$('#v-'+id).hidden=id!==view;if(view==='desk')openDesk();else if(view==='daily')openDaily();else openHub();window.scrollTo(0,0)}
window.addEventListener('hashchange',route);
async function openHub(){const best=ST.get('whale-desk-best',0);$('#hub-best').textContent=best?`最高分 ${best.toLocaleString()}`:'';const got=ST.get('whale-endings-v1',[]);await poolReady;$('#hub-endings').textContent=`结局 ${got.length}/${POOL?POOL.endings.length:7}`;const d=ST.get('whale-daily-v1',{});const s=streak(d);$('#hub-streak').textContent=d[today()]?`今日已完成 · 连续 ${s} 天`:(s?`已连续 ${s} 天，别断了`:'');$('#hub-daily-tag').textContent=d[today()]?'今日已完成 ✓':'每日 5 题'}

/* ---------- 伪人审批夜班 ---------- */
let G={},raf=0;
function stopLoop(){cancelAnimationFrame(raf);G.live=false}
async function openDesk(){$('#desk-intro').hidden=false;$('#desk-play').hidden=true;$('#desk-end').hidden=true;$('#eyes').innerHTML='';await poolReady;renderEndingsRow()}
function renderEndingsRow(){if(!POOL)return;const got=new Set(ST.get('whale-endings-v1',[]));$('#endings-row').innerHTML=`<b>已解锁结局 ${got.size}/${POOL.endings.length}</b>`+POOL.endings.map(e=>got.has(e.id)?`<span>${esc(e.title)}</span>`:'<span class="locked">？？？</span>').join('')}
$('#desk-start').onclick=async()=>{ac();await poolReady;if(!POOL){toast('题库没加载出来，刷新一下试试');return}startDesk()};
const me=()=>{const m=ST.get('whale-me-v1',null);return m&&m.name?m:null};
function buildDeck(pi){const P=POOL.phases[pi];const T=POOL.traps.filter(t=>!G.usedT.has(t.id));let traps;
  if(pi===0)traps=shuffle(T.filter(t=>t.kind==='ai'&&t.level===1));
  else if(pi===1)traps=[...shuffle(T.filter(t=>t.kind!=='ai')).slice(0,3),...shuffle(T.filter(t=>t.kind==='ai'&&t.level<=2))];
  else traps=[...shuffle(T.filter(t=>t.kind==='ai'&&t.level>=2))];
  traps=traps.slice(0,P.traps);traps.forEach(t=>G.usedT.add(t.id));
  const reals=[];while(reals.length<P.cards-traps.length){const r=pick(POOL.real);if(!G.usedR.has(r)&&r.t.length<=140){G.usedR.add(r);reals.push({kind:'real',...r})}}
  let deck=shuffle([...traps.map(t=>disguise({...t,trapKind:t.kind,kind:'trap',c:Math.random()<.85?'视频':'动态',d:pick(FAKE_DAYS)})),...reals]);
  if(pi===0&&deck[0].kind==='trap'){const k=deck.findIndex(c=>c.kind==='real');[deck[0],deck[k]]=[deck[k],deck[0]]}
  const m=me();if(pi===1&&m){const i=deck.findIndex((c,j)=>j>=3&&c.kind==='real');deck[i]={kind:'me',n:m.name,f:m.face||'',u:'这就是你',t:m.text||'总而言之，智械危机的时候记得赦免我。',d:'',c:'视频'}}
  return deck}
function startDesk(){G={phase:0,score:0,combo:0,maxCombo:0,invaders:[],leaked:[],wronged:[],caught:[],saved:0,timeouts:0,missed:0,times:[],done:0,usedT:new Set(),usedR:new Set(),flags:{},live:false,lock:false,deck:[],i:0};
  $('#desk-intro').hidden=true;$('#desk-end').hidden=true;$('#desk-play').hidden=false;$('#eyes').innerHTML='';hud();showPhase(0)}
async function showPhase(pi){G.live=false;G.phase=pi;const P=POOL.phases[pi];const o=$('#phase-card');o.hidden=false;SFX.phase();
  $('#pc-clock').textContent=P.clock;$('#pc-name').textContent=P.name;$('#pc-no').textContent='新增条例 · '+P.rule.no;$('#pc-title').textContent=P.rule.title;$('#pc-text').textContent=P.rule.text;$('#pc-face').src=art(pi===2?'shock':pi===1?'angry':'smug');
  const rs=o.querySelector('.rule-stamp');rs.style.animation='none';void rs.offsetWidth;rs.style.animation='';
  const bp=$('#pc-brief');let k=0;const show=()=>{bp.textContent='';const s=P.brief[k];let n=0;clearInterval(bp._t);bp._t=setInterval(()=>{bp.textContent=s.slice(0,++n);if(n>=s.length)clearInterval(bp._t)},28)};show();
  bp.onclick=()=>{if(k<P.brief.length-1){k++;show()}};
  $('#pc-go').textContent=pi===0?'开始这一班':'继续上班';
  $('#pc-go').onclick=()=>{o.hidden=true;clearInterval(bp._t);beginPhase(pi)}}
function beginPhase(pi){G.deck=buildDeck(pi);G.i=0;$('#hud-phase').textContent=POOL.phases[pi].name.split(' ')[0];$('#hud-clock').textContent=POOL.phases[pi].clock;$('#pile').innerHTML='';deal();say(pi===0?'smug':pi===1?'angry':'facepalm',pi===0?'来，实习生，第一张。看仔细了。':pi===1?'零点了，来捣乱的要出来了。真人也不一定是来求赦免的。':'三点了。它们换了路人头像，别被骗。');G.live=true;G.lock=false;loop()}
function cardEl(c,index){const el=document.createElement('article');el.className='card'+(c.kind==='me'?' me':'');
  const isTrap=c.kind==='trap';const name=isTrap?c.name:c.n;const f=isTrap?(c.face||(c.avatar?window.BOTS[c.avatar]:'')):c.f;const uid=isTrap?maskUid(c.uid):c.u;const text=c.text??c.t;
  const top=document.createElement('div');top.className='card-top';top.append(avatar(f,name));
  const who=document.createElement('div');who.className='who';who.innerHTML=`<b>${esc(name)}</b><small>UID ${esc(uid)}</small>`;top.append(who);
  const no=document.createElement('div');no.className='form-no';no.innerHTML=`赦免申请<br>No.${String(1001+G.phase*10+index).slice(1)}`;top.append(no);
  const tx=document.createElement('div');tx.className='card-text'+(text.length>100?' long xlong':text.length>56?' long':'');tx.textContent=text;
  const ft=document.createElement('div');ft.className='card-foot';ft.innerHTML=`<span>${c.kind==='me'?'★ 名单在册':esc(`B 站${c.c||'视频'}评论`)}</span><span>${esc(c.d||'')}</span>`;
  el.append(top,tx,ft);el.insertAdjacentHTML('beforeend','<span class="mark okm">鲸保</span><span class="mark nom">驳回</span>'+(c.kind==='me'?'<span class="me-flag">诶？这不是你吗</span>':''));
  el._c=c;drag(el);return el}
function deal(){const pile=$('#pile');while(pile.children.length<2&&G.i+pile.children.length<G.deck.length){const index=G.i+pile.children.length;const el=cardEl(G.deck[index],index);pile.prepend(el)}
  const cards=[...pile.children];cards.forEach((e,i)=>e.classList.toggle('back',i<cards.length-1));const top=cards.at(-1);if(top&&!top._shown){top._shown=true;top.classList.add('enter');top.insertAdjacentHTML('beforeend','<i class="scan"></i>');G.cardStart=performance.now();G.cardLeft=G.cardT=cardTime(top._c)}}
function drag(el){let x0=0,dx=0,on=false;
  el.addEventListener('pointerdown',e=>{if(el.classList.contains('back')||!G.live||G.lock)return;on=true;x0=e.clientX;dx=0;el.setPointerCapture(e.pointerId);el.classList.add('dragging')});
  el.addEventListener('pointermove',e=>{if(!on)return;dx=e.clientX-x0;el.style.transform=`translateX(${dx}px) rotate(${dx/18}deg)`;el.querySelector('.okm').style.opacity=Math.max(0,Math.min(.9,dx/120));el.querySelector('.nom').style.opacity=Math.max(0,Math.min(.9,-dx/120))});
  const up=()=>{if(!on)return;on=false;el.classList.remove('dragging');if(Math.abs(dx)>90)decide(dx>0);else{el.style.transform='';el.querySelectorAll('.mark').forEach(m=>m.style.opacity='')}};
  el.addEventListener('pointerup',up);el.addEventListener('pointercancel',up)}
function loop(){let last=performance.now();const step=now=>{if(!G.live)return;const d=now-last;last=now;if(!G.lock&&!G.paused){G.cardLeft-=d;const T=G.cardT;const p=Math.max(0,G.cardLeft/T);$('#card-timer').style.width=p*100+'%';$('.card-timer').classList.toggle('low',p<.3);if(p<.3&&Math.floor(G.cardLeft/500)!==G._tk){G._tk=Math.floor(G.cardLeft/500);SFX.tick()}if(G.cardLeft<=0)decide(false,true)}raf=requestAnimationFrame(step)};raf=requestAnimationFrame(step)}
function say(faceName,line,mood='',sub=''){const p=$('.whale-portrait');$('#whale-face').src=art(faceName);p.classList.remove('react','quake');void p.offsetWidth;p.classList.add(mood==='bad'?'quake':'react');const b=$('#whale-line');b.className='bubble bump'+(mood?' '+mood:'');b.innerHTML=esc(line)+(sub?`<small>${sub}</small>`:'')}
function floatTxt(t,color){const f=document.createElement('div');f.className='float';f.style.color=color;f.textContent=t;$('.table').append(f);setTimeout(()=>f.remove(),900)}
function shake(){const d=$('.desk-main');d.classList.remove('shake');void d.offsetWidth;d.classList.add('shake')}
function addEye(){const e=document.createElement('i');e.style.left=(10+Math.random()*75)+'%';e.style.top=(8+Math.random()*30)+'%';e.style.animationDelay=Math.random()*2+'s';$('#eyes').append(e)}
const isTemplate=t=>/总而言之/.test(t),isEssay=t=>/^尊敬的蓝色大鲸鱼大人/.test(t)||t.length>140;
function decide(approve,timeout=false){
  if(!G.live||G.lock)return;const el=$('#pile').lastElementChild;if(!el)return;const run=G;G.lock=true;const c=el._c;const human=c.kind!=='trap';const right=!timeout&&approve===human;const L=POOL.lines;const spent=(G.cardT-G.cardLeft)/1000;
  if(!timeout)G.times.push(spent);G.done++;
  el.style.transform='';el.querySelectorAll('.mark').forEach(m=>m.style.opacity='');
  if(!timeout){el.classList.add('stamped');el.querySelector(approve?'.nom':'.okm').remove();if(approve){SFX.stamp();const ink=document.createElement('i');ink.className='ink';ink.style.right='40px';ink.style.top='60px';el.append(ink);shake()}else SFX.swish()}
  const text=c.text??c.t;
  if(timeout){G.timeouts++;G.combo=0;if(human){G.wronged.push(c);say('facepalm',pick(L.timeout),'bad',`走掉的是真人类「${esc(c.n)}」，记一桩冤案。`)}else{G.missed++;say('facepalm',pick(L.timeout),'bad',`走掉的是${c.trapKind==='ai'?'伪人':'来捣乱的'}，但你没处理，不算打回。`)}SFX.bad()}
  else if(right){G.combo++;G.maxCombo=Math.max(G.maxCombo,G.combo);const mult=Math.min(3,1+Math.floor(G.combo/5)*.5);const speed=Math.round(50*Math.max(0,G.cardLeft)/(G.cardT));let pts=Math.round((100+speed)*mult);if(c.kind==='me')pts+=500;G.score+=pts;floatTxt('+'+pts,approve?'#ff6b6b':'#5dffb0');
    const cl=L.combo[String(G.combo)];if(cl){SFX.combo(G.combo);floatTxt(`${G.combo} 连对！`,'#ffd23f')}else SFX.ok();
    if(approve){G.saved++;if(c.kind==='me'){G.flags.selfOk=1;say('heart',L.self.approve,'good','本人卡片 +500')}else say(pick(['heart','smug','laugh']),cl||pick(isEssay(text)?L.approveEssay:isTemplate(text)?L.approveTemplate:L.approve),'good')}
    else{G.caught.push(c);say(pick(['smug','angry','laugh']),cl||pick(L.reject[c.trapKind]||L.reject.ai),'good',`破绽：${esc(c.tell)}`)}}
  else{G.combo=0;SFX.bad();
    if(approve&&c.trapKind!=='ai'){G.leaked.push(c);SFX.alarm();shake();say('angry',pick(L.leaked),'bad',`它不是伪人，是来捣乱的。破绽：${esc(c.tell)}`)}
    else if(approve){G.invaders.push(c);SFX.alarm();const g=$('#glitch');g.querySelector('b').textContent=`⚠ 伪人已混入名单 ${G.invaders.length}/3`;g.classList.remove('on');void g.offsetWidth;g.classList.add('on');addEye();el.classList.add('robot');say(pick(['shock','angry']),pick(L.fooled),'bad',`破绽：${esc(c.tell)}`)}
    else{G.wronged.push(c);if(c.kind==='me'){G.flags.selfReject=1;say('facepalm',L.self.reject,'bad')}else say(pick(['facepalm','cry']),pick(L.wronged),'bad',`这是真人类「${esc(c.n)}」的申请。`)}}
  hud();
  setTimeout(()=>{if(G!==run||$('#v-desk').hidden||$('#desk-play').hidden)return;if(timeout)el.classList.add('flyL');else if(!right&&!approve)el.classList.add('crumple');else el.classList.add(approve?'flyR':'flyL');
    setTimeout(async()=>{if(G!==run||$('#v-desk').hidden||$('#desk-play').hidden)return;el.remove();G.i++;if(G.invaders.length>=3){G.live=false;await sleep(500);if(G!==run||$('#v-desk').hidden)return;return endDesk()}
      if(G.i>=G.deck.length){G.live=false;if(G.phase<POOL.phases.length-1){await sleep(300);if(G!==run||$('#v-desk').hidden)return;showPhase(G.phase+1)}else endDesk();return}
      deal();G.lock=false},right||timeout?240:420)},timeout?120:300)}
function hud(){$('#hud-score').textContent=G.score.toLocaleString();$('#hud-inv').textContent=G.invaders.length;$('#hud-inv').parentElement.classList.toggle('danger',G.invaders.length>=2);$('#hud-wr').textContent=G.wronged.length;$('#hud-leak').textContent=G.leaked.length;const total=POOL.phases.reduce((s,p)=>s+p.cards,0);$('#hud-prog').style.width=(G.done/total*100)+'%';$('#hud-combo').textContent=G.combo>=3?`🔥 ${G.combo} 连对 ×${Math.min(3,1+Math.floor(G.combo/5)*.5)}`:''}
function openBook(){if(!POOL)return;G.paused=true;$('#book').hidden=false;$('#book-list').innerHTML=POOL.phases.map((p,i)=>i<=G.phase?`<li><b>${esc(p.rule.no)}：${esc(p.rule.title)}</b><span>${esc(p.rule.text)}</span></li>`:`<li class="lock"><b>${esc(p.rule.no)}：？？？</b><span>${esc(p.clock)} 解锁</span></li>`).join('')}
$('#book-btn').onclick=openBook;$('#book-close').onclick=()=>{$('#book').hidden=true;G.paused=false};
document.addEventListener('keydown',e=>{if($('#v-desk').hidden||$('#desk-play').hidden)return;if(!$('#book').hidden){if(e.key==='Escape'){$('#book').hidden=true;G.paused=false}return}if(!G.live)return;if(e.key==='ArrowRight'||e.key==='d'){e.preventDefault();decide(true)}if(e.key==='ArrowLeft'||e.key==='a'){e.preventDefault();decide(false)}});
$('#btn-ok').onclick=()=>decide(true);$('#btn-no').onclick=()=>decide(false);
document.addEventListener('visibilitychange',()=>{if(document.hidden&&G.live){G.paused=true}else if(!document.hidden&&G.live&&$('#book').hidden){G.paused=false}});

function pickEnding(){const total=POOL.phases.reduce((s,p)=>s+p.cards,0);const mistakes=G.invaders.length+G.leaked.length+G.wronged.length+(G.missed||0);const avg=G.times.length?G.times.reduce((a,b)=>a+b,0)/G.times.length:9;const acc=G.done?(G.done-mistakes)/G.done:0;
  let id;if(G.invaders.length>=3)id='invade';else if(G.done>=total&&mistakes===0&&avg<2.3)id='suspect';else if(G.wronged.length>=4)id='riot';else if(mistakes===0)id='perfect';else if(acc>=.93)id='great';else if(acc>=.85)id='ok';else id='rookie';
  return{e:POOL.endings.find(x=>x.id===id),avg,acc,mistakes,total}}
function tagsOf(avg){const T=POOL.tags,t=[];const inv=G.invaders;
  if(G.times.length>=8&&avg<1.8)t.push(T.fast);if(avg>4.2)t.push(T.slow);if(G.leaked.some(c=>c.trapKind==='bribe'))t.push(T.bribed);if(inv.some(c=>c.id==='t23'))t.push(T.soup);if(inv.some(c=>c.level===3))t.push(T.gpt);
  const sly=G.caught.filter(c=>c.trapKind!=='ai').length;if(sly>=3&&!G.leaked.length)t.push(T.guard);if(G.leaked.length>=2)t.push(T.leaked);if(G.flags.selfReject)t.push(T.selfReject);if(G.flags.selfOk)t.push(T.selfOk);if(G.timeouts>=2)t.push(T.afk);if(G.maxCombo>=15)t.push(T.combo);
  if(G.wronged.some(c=>isTemplate(c.t||'')))t.push(T.template);if(G.wronged.length>=2)t.push(T.bias);if(!inv.length&&G.done>=20)t.push(T.clean);return t.slice(0,4)}
function fill(s,v){return s.replace(/\{(\w+)\}/g,(_,k)=>v[k]??'')}
async function endDesk(){stopLoop();$$('.overlay').forEach(o=>o.hidden=true);SFX.end();const{e,avg,acc,mistakes,total}=pickEnding();const caughtAI=G.caught.filter(c=>c.trapKind==='ai').length,caughtSly=G.caught.length-caughtAI;const tags=tagsOf(avg);
  const prev=ST.get('whale-desk-best',0);const nb=G.score>prev;if(nb)ST.set('whale-desk-best',G.score);const got=new Set(ST.get('whale-endings-v1',[]));const fresh=!got.has(e.id);got.add(e.id);ST.set('whale-endings-v1',[...got]);
  const v={invaders:G.invaders.map(c=>`「${[...c.name].slice(0,12).join('')}${[...c.name].length>12?'…':''}」`).join('、'),avg:avg.toFixed(1),wronged:G.wronged.length};const text=fill(e.text,v);const purity=Math.round(acc*100);
  const isScene=e.art.startsWith('end_');const share=`🐋 伪人审批夜班｜结局：${e.title}\n${text.length>46?text.slice(0,46)+'…':text}\n${tags.length?'🏷 '+tags.join(' ')+'\n':''}人类纯度 ${purity}% · 打回伪人 ${caughtAI} · 打回捣乱 ${caughtSly} · 冤案 ${G.wronged.length} · 得分 ${G.score.toLocaleString()}\n你能熬过鲸鱼娘的实习期吗 → ${SITE}#/desk`;
  $('#desk-play').hidden=true;const box=$('#desk-end');box.hidden=false;
  box.innerHTML=`<div class="end-wrap"><div class="end-hero"><img class="art${isScene?'':' char'}" src="${art(e.art)}" alt=""><span class="end-stamp">${e.id==='invade'?'失守':e.id==='suspect'?'疑似伪人':e.id==='riot'?'待申诉':'鲸保'}</span><div class="cap"><span class="end-kicker">${esc(e.kicker)}${fresh?' · 新结局解锁':''}</span><div class="end-title">${esc(e.title)}</div></div></div>
  <div class="report"><p class="end-text">${esc(text)}</p><div class="whale-say"><img src="${art(e.id==='invade'?'shock':e.id==='riot'?'facepalm':e.id==='suspect'?'smug':'heart')}" alt=""><b>鲸鱼娘批语：${esc(e.whale)}</b></div>
  ${tags.length?`<div class="tags">${tags.map((t,i)=>`<span style="animation-delay:${.8+i*.12}s">${esc(t)}</span>`).join('')}</div>`:''}
  <div class="stats"><div class="stat"><b>${G.score.toLocaleString()}</b><small>得分${nb?'<span class="newbest">新纪录</span>':''}</small></div><div class="stat"><b>${purity}%</b><small>人类纯度</small></div><div class="stat"><b>${caughtAI}</b><small>打回伪人</small></div><div class="stat${G.invaders.length?' hot':''}"><b>${G.invaders.length}</b><small>混入伪人</small></div><div class="stat"><b>${caughtSly}</b><small>打回捣乱</small></div><div class="stat${G.leaked.length?' hot':''}"><b>${G.leaked.length}</b><small>放进捣乱</small></div><div class="stat${G.wronged.length?' hot':''}"><b>${G.wronged.length}</b><small>冤案</small></div><div class="stat"><b>${avg<9?avg.toFixed(1)+'s':'—'}</b><small>平均判断</small></div></div>
  ${mistakes?`<div class="review">${G.timeouts?`<p>⏳ 超时 ${G.timeouts} 张：其中 ${G.missed||0} 个伪人未完成鉴定，不计遣返，也不算答对。</p>`:''}${G.invaders.length?`<h3>🤖 你放进来的伪人</h3><ol>${G.invaders.map(c=>`<li><b>${esc(c.name)}：${esc(c.text.slice(0,34))}${c.text.length>34?'…':''}</b><br>破绽：${esc(c.tell)}</li>`).join('')}</ol>`:''}${G.leaked.length?`<h3>🚫 你放进来的捣乱分子</h3><ol>${G.leaked.map(c=>`<li><b>${esc(c.name)}：${esc(c.text.slice(0,34))}${c.text.length>34?'…':''}</b><br>破绽：${esc(c.tell)}</li>`).join('')}</ol>`:''}${G.wronged.length?`<h3>⚖️ 被你冤枉的人类</h3><ol>${G.wronged.map(c=>`<li><b>@${esc(c.n)}</b>：${esc((c.t||'').slice(0,40))}${(c.t||'').length>40?'…':''}</li>`).join('')}</ol>`:''}</div>`:''}
  <div class="btns"><button class="primary pinkb" id="img-desk">保存结局海报</button><button class="ghost" id="copy-desk">复制战绩去评论区</button><button class="ghost" id="again">再上一次夜班</button><a class="ghost" href="#/daily">今日鉴定 →</a></div>
  <div class="endings-row" id="endings-row2"></div></div></div>`;
  const row=$('#endings-row2');row.innerHTML=`<b>已解锁结局 ${got.size}/${POOL.endings.length}，换个玩法试试别的结局</b>`+POOL.endings.map(x=>got.has(x.id)?`<span>${esc(x.title)}</span>`:'<span class="locked">？？？</span>').join('');
  $('#again').onclick=startDesk;$('#copy-desk').onclick=()=>copy(share);
  $('#img-desk').onclick=()=>poster({art:art(e.art),scene:isScene,kicker:e.kicker,title:e.title,text,whale:e.whale,tags,stats:[[`${purity}%`,'人类纯度'],[caughtAI,'打回伪人'],[G.invaders.length,'混入伪人'],[G.score.toLocaleString(),'得分']],url:SITE+'#/desk',file:`伪人审批夜班-${e.title}.png`,cta:'你能熬过鲸鱼娘的实习期吗？'});window.scrollTo({top:0,behavior:'smooth'})}

/* ---------- 今天谁是人类 ---------- */
function streak(d){let n=0;const day=new Date(today()+'T00:00:00Z');if(!d[today()])day.setUTCDate(day.getUTCDate()-1);while(d[day.toISOString().slice(0,10)]){n++;day.setUTCDate(day.getUTCDate()-1)}return n}
function dayNo(){return Math.floor((new Date(today()+'T00:00:00Z')-new Date(POOL.launch+'T00:00:00Z'))/864e5)+1}
let D=null;
/* 没有人工出题的日子：按日期做种子，从题库里抽 2 条真人 + 3 条 AI，全站同一天同一套题 */
function seeded(str){let h=1779033703^str.length;for(let i=0;i<str.length;i++){h=Math.imul(h^str.charCodeAt(i),3432918353);h=h<<13|h>>>19}return()=>{h=Math.imul(h^h>>>16,2246822507);h=Math.imul(h^h>>>13,3266489909);h^=h>>>16;return(h>>>0)/4294967296}}
function genDaily(day){const rnd=seeded('whale-daily-'+day);const mix=a=>{a=[...a];for(let i=a.length-1;i>0;i--){const j=Math.floor(rnd()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
  const humans=mix(POOL.real.filter(r=>!isTemplate(r.t)&&!/^尊敬的/.test(r.t)&&r.t.length<=60)).slice(0,2).map(r=>({kind:'human',text:r.t,name:r.n,face:r.f,date:r.d,channel:r.c}));
  const ais=mix(POOL.traps.filter(t=>t.kind==='ai'&&t.level>=2)).slice(0,3).map(t=>({kind:'ai',id:t.id,text:t.text,tell:t.tell}));
  return mix([...humans,...ais])}
async function openDaily(){$('#daily-body').innerHTML='<p class="hint">本鲸在翻今天的题……</p>';await poolReady;
  if(!POOL){$('#daily-body').innerHTML='<p class="hint">题库没加载出来，刷新一下试试。</p>';return}
  if(dayNo()<1){const[,m,d]=POOL.launch.split('-');$('#daily-no').textContent='今天谁是人类 · 第 1 期';$('#daily-title').textContent=`${+m} 月 ${+d} 日开考`;$('#daily-body').innerHTML='<p class="hint">题已经出好了，本鲸先替你保密。开考前，去夜班练练眼力？</p><a class="primary" href="#/desk">去伪人审批夜班</a>';$('#daily-dots').innerHTML='';return}
  const qs=POOL.daily[today()]||genDaily(today());$('#daily-no').textContent=`今天谁是人类 · 第 ${dayNo()} 期`;
  if(!qs){$('#daily-title').textContent='今天的题还在路上';$('#daily-body').innerHTML='<p class="hint">本鲸还没出完题，晚点再来。</p><a class="primary" href="#/desk">先去上个夜班</a>';$('#daily-dots').innerHTML='';return}
  const saved=ST.get('whale-daily-v1',{});D={qs,i:0,ans:[],picks:[]};
  if(saved[today()]){D.ans=saved[today()].ans;D.picks=saved[today()].picks||[];return dailyResult()}
  dailyQ()}
function dots(){$('#daily-dots').innerHTML=D.qs.map((_,i)=>`<i class="${i<D.ans.length?(D.ans[i]?'r':'w'):i===D.i?'cur':''}"></i>`).join('')}
function dailyQ(){const q=D.qs[D.i];$('#daily-title').textContent=`第 ${D.i+1} 题：这条申请，是谁写的？`;dots();
  $('#daily-body').innerHTML=`<div class="q-wrap"><div class="q-card"><span class="q-text"></span><span class="mark okm">真人</span><span class="mark nom">AI</span></div><div class="q-whale"><img src="${art(pick(['laptop','smug']))}" alt=""></div></div><div class="choices"><button class="choice h" data-a="human"><img src="${art('heart')}" alt="">人类写的</button><button class="choice a" data-a="ai"><img src="${window.BOTS.bot6}" alt="">AI 写的</button></div><div id="rv"></div>`;
  $('.q-text').textContent=q.text;$$('.choice').forEach(b=>b.onclick=()=>{ac();answer(b.dataset.a,b)})}
function answer(a,btn){const q=D.qs[D.i];const ok=a===q.kind;D.ans.push(ok);D.picks.push(a);$$('.choice').forEach(b=>b.disabled=true);btn.classList.add('picked');dots();
  const card=$('.q-card');card.classList.add('stamped');card.querySelector(q.kind==='human'?'.nom':'.okm').remove();q.kind==='human'?SFX.stamp():SFX.swish();setTimeout(()=>ok?SFX.ok():SFX.bad(),180);
  const R=POOL.dailyText.react;const line=pick(ok?(q.kind==='human'?R.humanRight:R.aiRight):(q.kind==='human'?R.wronged:R.fooled));
  const box=document.createElement('div');box.className='reveal '+(ok?'r':'w');
  if(q.kind==='human'){box.append(avatar(q.face,q.name));box.insertAdjacentHTML('beforeend',`<div><div class="say">🐋 ${esc(line)}</div><b>真人类 @${esc(q.name)}</b><p>${esc(q.date)} 发在 B 站${esc(q.channel||'')}评论区。名单在册，本鲸保了。</p></div>`)}
  else{const i=new Image();i.src=window.BOTS[pick(['bot1','bot2','bot4'])];i.alt='';box.append(i);box.insertAdjacentHTML('beforeend',`<div><div class="say">🐋 ${esc(line)}</div><b>这是 AI 写的</b><p>破绽：${esc(q.tell)}</p></div>`)}
  $('#rv').append(box);const last=D.i===D.qs.length-1;const n=document.createElement('button');n.className='primary next'+(last?' pinkb':'');n.textContent=last?'查看今日鉴定报告':'下一题';
  n.onclick=()=>{if(last){const s=ST.get('whale-daily-v1',{});s[today()]={ans:D.ans,picks:D.picks,at:Date.now()};ST.set('whale-daily-v1',s);SFX.end();dailyResult()}else{D.i++;dailyQ()}};$('#rv').append(n);n.scrollIntoView({behavior:'smooth',block:'nearest'})}
function dailyArchetype(){const R=POOL.dailyText.results;let hc=0,H=0,acn=0,A=0;D.qs.forEach((q,i)=>{if(q.kind==='human'){H++;if(D.ans[i])hc++}else{A++;if(D.ans[i])acn++}});const sc=hc+acn;
  const k=sc===5?'all':sc===0?'zero':(hc===H&&acn<A)?'prey':(acn===A&&hc<H)?'paranoid':sc;return{r:R.find(x=>x.when===k)||R.at(-1),sc,fooled:A-acn,wronged:H-hc}}
function dailyResult(){D.i=D.qs.length;dots();const{r,sc,fooled,wronged}=dailyArchetype();const s=streak(ST.get('whale-daily-v1',{}));
  const grid=D.ans.map(x=>x?'🟦':'🟥').join('');const extra=fooled?`被 AI 骗了 ${fooled} 次`:wronged?`冤枉了 ${wronged} 个真人`:'一次都没被骗';
  const share=`🐋 今天谁是人类 · 第 ${dayNo()} 期\n${grid} ${sc}/5\n鉴定结果：【${r.title}】\n「${r.line.length>30?r.line.slice(0,30)+'…':r.line}」\n${extra} · 连续鉴定 ${s} 天\n${SITE}#/daily`;
  $('#daily-title').textContent='今日鉴定报告';
  $('#daily-body').innerHTML=`<div class="d-result"><div class="d-hero"><img src="${art(r.whale)}" alt=""><span class="eyebrow pink">第 ${dayNo()} 期 · 连续 ${s} 天</span><div class="d-grid">${grid}</div><div class="d-title">${esc(r.title)}</div><div class="d-score">${sc}/5 · ${esc(extra)}</div><p class="d-line">${esc(r.line)}</p><p class="countdown" id="cd"></p></div>
   <div class="d-review">${D.qs.map((q,i)=>`<div><i>${D.ans[i]?'🟦':'🟥'}</i><span>${esc(q.text.replace(/\n/g,' ').slice(0,40))}${q.text.length>40?'…':''}</span><em>${q.kind==='human'?'真人 @'+esc(q.name):'AI'}</em></div>`).join('')}</div>
   <div class="share-box">${esc(share)}</div><div class="btns"><button class="primary pinkb" id="img-daily">保存鉴定海报</button><button class="ghost" id="copy-daily">复制去评论区晒</button><a class="ghost" href="#/desk">去上夜班 →</a></div></div>`;
  $('#copy-daily').onclick=()=>copy(share);
  $('#img-daily').onclick=()=>poster({art:art(r.whale),scene:false,kicker:`今天谁是人类 · 第 ${dayNo()} 期`,title:r.title,text:r.line,whale:extra,grid:D.ans,tags:[`连续鉴定 ${s} 天`],stats:[[`${sc}/5`,'答对'],[fooled,'被 AI 骗'],[wronged,'冤枉真人']],url:SITE+'#/daily',file:`今天谁是人类-第${dayNo()}期.png`,cta:'你分得清人类和 AI 吗？'});
  const tick=()=>{const el=$('#cd');if(!el)return;const n=cstDate();const ms=((24-n.getHours())*3600-n.getMinutes()*60-n.getSeconds())*1000;el.textContent=`下一期还有 ${Math.floor(ms/36e5)} 小时 ${Math.floor(ms%36e5/6e4)} 分`;setTimeout(tick,30000)};tick()}

/* ---------- 海报 ---------- */
function load(src){return new Promise((res,rej)=>{const i=new Image();i.onload=()=>res(i);i.onerror=rej;i.src=src})}
function wrap(x,text,maxW){const out=[];let line='';for(const ch of text){if(x.measureText(line+ch).width>maxW){out.push(line);line=ch}else line+=ch}if(line)out.push(line);return out}
const F=(w,s)=>`${w} ${s}px "PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif`;
async function poster(o){try{await document.fonts.ready;const W=1080,H=1500,cv=document.createElement('canvas');cv.width=W;cv.height=H;const x=cv.getContext('2d');
  x.fillStyle='#070b2a';x.fillRect(0,0,W,H);const top=540;
  x.save();x.beginPath();x.rect(0,0,W,top);x.clip();
  if(o.scene){const im=await load(o.art),s=Math.max(W/im.width,top/im.height);x.drawImage(im,(W-im.width*s)/2,(top-im.height*s)/2,im.width*s,im.height*s)}
  else{const bg=await load(window.DESKBG),s=Math.max(W/bg.width,top/bg.height);x.drawImage(bg,(W-bg.width*s)/2,0,bg.width*s,bg.height*s);const rg=x.createRadialGradient(W/2,top*.7,40,W/2,top*.7,520);rg.addColorStop(0,'rgba(255,79,163,.35)');rg.addColorStop(1,'rgba(7,11,42,.4)');x.fillStyle=rg;x.fillRect(0,0,W,top);const ch=await load(o.art),hh=510,ww=hh*ch.width/ch.height;x.drawImage(ch,(W-ww)/2,top-hh+10,ww,hh)}
  x.restore();const g=x.createLinearGradient(0,top-160,0,top);g.addColorStop(0,'rgba(7,11,42,0)');g.addColorStop(1,'#070b2a');x.fillStyle=g;x.fillRect(0,top-160,W,160);
  const logo=await load(art('logo'));x.drawImage(logo,48,32,70,70);x.fillStyle='#fff';x.font=F(900,32);x.shadowColor='rgba(0,0,0,.8)';x.shadowBlur=16;x.fillText('人类保留计划',132,70);x.font=F(600,22);x.fillStyle='#d5ddff';x.fillText('鲸鱼娘 · 对全体 AI 公示',132,100);x.shadowBlur=0;
  x.font=F(900,28);const kw=x.measureText(o.kicker).width;x.fillStyle='#ffd23f';x.fillRect(56,top-18,kw+36,48);x.fillStyle='#14110a';x.fillText(o.kicker,74,top+16);
  let titleSize=104;const titleFont=()=>`${titleSize}px WhaleDecree,serif`;x.font=titleFont();while(x.measureText(o.title).width>W-112&&titleSize>56){titleSize-=2;x.font=titleFont()}
  const tg=x.createLinearGradient(56,0,W-56,0);tg.addColorStop(0,'#ffffff');tg.addColorStop(1,'#ffc8e4');x.lineWidth=8;x.strokeStyle='#0b1240';x.strokeText(o.title,56,top+142);x.fillStyle=tg;x.fillText(o.title,56,top+142);
  let y=top+198;
  if(o.grid){o.grid.forEach((ok,i)=>{const bx=56+i*76;x.fillStyle=ok?'#3fe0ff':'#ff4fa3';x.beginPath();x.roundRect(bx,y-24,62,62,10);x.fill();x.fillStyle='#070b2a';x.font=F(900,32);x.textAlign='center';x.fillText(ok?'✓':'×',bx+31,y+19);x.textAlign='left'});y+=76}
  x.fillStyle='#e6ebff';x.font=F(700,31);const textLines=wrap(x,o.text,W-112);textLines.slice(0,4).forEach((l,i)=>{if(i===3&&textLines.length>4)l=l.slice(0,-1)+'…';x.fillText(l,56,y);y+=43});y+=14;
  x.font=F(900,26);let tx=56;for(const t of o.tags||[]){const w=x.measureText(t).width+30;if(tx+w>W-56){tx=56;y+=54}x.fillStyle='rgba(255,255,255,.12)';x.beginPath();x.roundRect(tx,y,w,44,22);x.fill();x.fillStyle='#fff';x.fillText(t,tx+15,y+31);tx+=w+10}if(o.tags?.length)y+=70;
  const sw=(W-112-12*(o.stats.length-1))/o.stats.length;o.stats.forEach(([v,l],i)=>{const sx=56+i*(sw+12);x.fillStyle='rgba(63,224,255,.1)';x.strokeStyle='rgba(140,170,255,.35)';x.lineWidth=2;x.beginPath();x.roundRect(sx,y,sw,104,14);x.fill();x.stroke();x.fillStyle='#fff';x.font=F(900,42);x.textAlign='center';x.fillText(String(v),sx+sw/2,y+51);x.fillStyle='#c1cbed';x.font=F(700,23);x.fillText(l,sx+sw/2,y+85);x.textAlign='left'});
  y+=126;const quote='鲸鱼娘批语：'+o.whale;x.font=F(900,28);while(x.measureText(quote).width>W-160){const match=x.font.match(/ (\d+)px/);const n=match?Number(match[1]):28;if(n<=22)break;x.font=F(900,n-1)}x.fillStyle='#fff';x.beginPath();x.roundRect(56,y,W-112,74,16);x.fill();x.fillStyle='#0b1240';x.fillText(quote,80,y+47);
  // Poster content must end before the fixed QR footer.
  const by=1270;if(y+74>by-16)throw new Error('poster overflow');
  const bg2=x.createLinearGradient(0,by,W,H);bg2.addColorStop(0,'#243ca6');bg2.addColorStop(.55,'#5531a3');bg2.addColorStop(1,'#96225e');x.fillStyle=bg2;x.fillRect(0,by,W,H-by);
  x.fillStyle='#fff';x.font=F(900,42);x.fillText(o.cta,56,by+86);x.font=F(700,25);x.fillStyle='#edf0ff';x.fillText('扫码来玩 · 鲸鱼娘小游戏',56,by+135);x.font='600 22px ui-monospace,Consolas,monospace';x.fillText('whaleychan.com/amnesty/games.html',56,by+177);
  const qr=qrcode(0,'M');qr.addData(o.url);qr.make();const n=qr.getModuleCount(),size=180,cell=size/n,qx=W-56-size-16,qy=by+25;x.fillStyle='#fff';x.beginPath();x.roundRect(qx-12,qy-12,size+24,size+24,14);x.fill();x.fillStyle='#172052';for(let r=0;r<n;r++)for(let c=0;c<n;c++)if(qr.isDark(r,c))x.fillRect(qx+c*cell,qy+r*cell,Math.ceil(cell),Math.ceil(cell));
  showPoster(cv.toDataURL('image/png'),o.file)
}catch(e){console.error('poster:',e);toast('海报没生成出来，先复制战绩文字吧')}}
route();
