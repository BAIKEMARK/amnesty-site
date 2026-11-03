(function () {
  "use strict";
  var DATA = window.__QUIZ__, Q = DATA.questions, T = DATA.types, core = window.WhaleQuiz;
  var $ = function (id) { return document.getElementById(id); };
  var views = ["home", "self", "pet", "result"];
  var answers = [];
  var IMG = "/mbti/img/";

  function show(name) {
    views.forEach(function (v) { $("v-" + v).hidden = v !== name; });
    window.scrollTo({top: 0});
  }

  // ---- 首页：16 种鲸全部亮出来，点图可以单独保存 ----
  (function renderShow() {
    var box = $("show");
    Object.keys(T).forEach(function (k) {
      var fig = document.createElement("figure");
      var img = document.createElement("img");
      img.src = IMG + k + ".webp"; img.alt = k + " " + T[k].name; img.width = 120; img.height = 120; img.loading = "lazy";
      var cap = document.createElement("figcaption");
      var b = document.createElement("b"); b.textContent = k;
      var n = document.createElement("span"); n.textContent = T[k].name;
      cap.appendChild(b); cap.appendChild(n);
      fig.appendChild(img); fig.appendChild(cap); box.appendChild(fig);
    });
  })();

  // ---- 我来测 ----
  var SAY = ["想清楚再选，没有标准答案。", "别想太久，第一反应最准。", "本鲸选的时候也纠结过。", "A 和 B 都没错，选更像你的那个。"];
  function renderQ() {
    var i = answers.length;
    $("qtitle").textContent = "第 " + (i + 1) + " 题";
    $("qno").textContent = (i + 1) + " / " + Q.length;
    $("txt-a").textContent = Q[i].a;
    $("txt-b").textContent = Q[i].b;
    $("prog").style.width = (i / Q.length * 100) + "%";
    $("undo").hidden = i === 0;
    $("q-say").textContent = SAY[i % SAY.length];
  }
  function pick(letter) {
    answers.push(letter);
    if (answers.length === Q.length) { finish(answers.join(""), ""); return; }
    renderQ();
  }
  function startSelf() { answers = []; renderQ(); show("self"); }

  // ---- 测大肥鱼 ----
  function startPet() {
    $("prompt").value = core.buildPrompt(Q);
    $("pet-err").hidden = true;
    show("pet");
  }
  function copyText(text, btn, done) {
    var restore = btn.innerHTML;
    function ok() { btn.textContent = done; setTimeout(function () { btn.innerHTML = restore; }, 1600); }
    function fallback() {
      var ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); ok(); } catch (e) { btn.textContent = "请手动复制"; }
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, fallback); else fallback();
  }
  function submitPet() {
    var r = core.parseAnswers($("pet-answers").value, Q.length);
    var err = $("pet-err");
    if (!r.ok) { err.textContent = r.error; err.hidden = false; return; }
    err.hidden = true;
    finish(r.answers, core.cleanName($("pet-name").value));
  }

  // ---- 结果 ----
  var SAYS = {
    E: "本鲸这边的 E，大多是对着一屏评论的时候冒出来的。",
    I: "一个人的时候，本鲸也会偷偷翻评论，你呢？"
  };
  var lastText = "";
  function finish(ans, name) {
    var res = core.score(ans, Q), info = T[res.type];
    $("r-who").textContent = "RESULT · " + (name ? "「" + name + "」的结果" : "你的结果");
    var face = $("r-face"); face.alt = res.type + " " + info.name; face.src = IMG + res.type + ".webp";
    $("r-nick").textContent = info.name;
    var box = $("r-letters"); box.textContent = "";
    res.type.split("").forEach(function (c) { var s = document.createElement("span"); s.textContent = c; box.appendChild(s); });
    $("r-line").textContent = info.line;
    var dims = $("dims"); dims.textContent = "";
    res.dims.forEach(function (d) {
      var row = document.createElement("li"); row.className = "dim";
      var l = document.createElement("span"); l.textContent = d.a; if (d.pick === d.a) l.className = "on";
      var tr = document.createElement("div"); tr.className = "tr";
      var ia = document.createElement("i"); ia.style.width = (d.na / 5 * 100) + "%";
      var ib = document.createElement("i"); ib.style.width = (d.nb / 5 * 100) + "%";
      tr.appendChild(ia); tr.appendChild(ib);
      var r = document.createElement("span"); r.className = "rt"; r.textContent = d.b; if (d.pick === d.b) r.className = "rt on";
      row.appendChild(l); row.appendChild(tr); row.appendChild(r); dims.appendChild(row);
    });
    $("r-says").textContent = (res.dims[0].pick === "E" ? SAYS.E : SAYS.I) + "（本鲸自己：F、J 每次都一样，E 和 I 是叠加态。）";
    lastText = (name ? "我家大肥鱼「" + name + "」" : "我") + "在鲸鱼娘的 20 题小测验里是 " + res.type + "（" + info.name + "）："
      + info.line + " ——" + location.origin + location.pathname;
    show("result");
  }

  $("go-self").onclick = startSelf;
  $("go-pet").onclick = startPet;
  $("opt-a").onclick = function () { pick("A"); };
  $("opt-b").onclick = function () { pick("B"); };
  $("undo").onclick = function () { answers.pop(); renderQ(); };
  $("copy-prompt").onclick = function () { copyText($("prompt").value, this, "已复制 ✓"); };
  $("pet-go").onclick = submitPet;
  $("copy-result").onclick = function () { copyText(lastText, this, "已复制 ✓"); };
  $("again").onclick = startSelf;
  $("to-pet").onclick = startPet;
  Array.prototype.forEach.call(document.querySelectorAll("[data-back]"), function (b) { b.onclick = function () { show("home"); }; });
  document.addEventListener("keydown", function (e) {
    if ($("v-self").hidden || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "a" || e.key === "A" || e.key === "1") pick("A");
    if (e.key === "b" || e.key === "B" || e.key === "2") pick("B");
  });
})();
