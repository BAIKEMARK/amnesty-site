// 鲸鱼娘自编 20 题的计分与「粘贴答案」解析。纯函数，页面和 Node 测试共用。
(function (root) {
  "use strict";
  var DIMS = ["EI", "SN", "TF", "JP"];

  // answers：20 个 "A"/"B"，questions：questions.json 里的 questions。
  // 每个维度 5 题，选 A 偏前一个字母；3 票及以上取它（5 题没有平局）。
  function score(answers, questions) {
    var dims = DIMS.map(function (d) {
      var na = 0, nb = 0;
      questions.forEach(function (q, i) {
        if (q.dim !== d) return;
        if (answers[i] === "A") na++; else nb++;
      });
      return {a: d[0], b: d[1], na: na, nb: nb, pick: na > nb ? d[0] : d[1]};
    });
    return {type: dims.map(function (x) { return x.pick; }).join(""), dims: dims};
  }

  // 大肥鱼回传的答案：支持连写 ABBA…、空格/逗号分隔，以及 "1.A 2.B …" 带编号的写法。
  // 只认 A/B 和常见分隔符，其它任何字符都拒绝，粘贴的内容不会被当作别的东西处理。
  function parseAnswers(text, total) {
    total = total || 20;
    var raw = String(text == null ? "" : text).trim();
    if (!raw) return {ok: false, error: "还没有粘贴答案。"};
    if (raw.length > 400) return {ok: false, error: "内容太长了，只需要 " + total + " 个 A/B 字母。"};
    if (/\d/.test(raw)) {
      var re = /(\d{1,2})\s*[.、:：)）\-]?\s*([ABab])(?![A-Za-z])/g, m, got = {}, count = 0;
      while ((m = re.exec(raw))) {
        var n = parseInt(m[1], 10);
        if (n < 1 || n > total || got[n]) return {ok: false, error: "题号 " + n + " 重复或超出范围。"};
        got[n] = m[2].toUpperCase(); count++;
      }
      var rest = raw.replace(re, "").replace(/[\s,，、;；.。:：()（）\-—|/\[\]]/g, "");
      if (rest) return {ok: false, error: "答案里只能有题号和 A/B。"};
      if (count !== total) return {ok: false, error: "识别到 " + count + " 题，需要 " + total + " 题。"};
      var out = "";
      for (var i = 1; i <= total; i++) out += got[i];
      return {ok: true, answers: out};
    }
    var clean = raw.replace(/[\s,，、;；.。:：()（）\-—|/\[\]]/g, "");
    if (!/^[ABab]+$/.test(clean)) return {ok: false, error: "答案里只能有 A 和 B（可以用空格或逗号隔开）。"};
    if (clean.length !== total) return {ok: false, error: "识别到 " + clean.length + " 个字母，需要 " + total + " 个。"};
    return {ok: true, answers: clean.toUpperCase()};
  }

  // 给大肥鱼的提示词：题目、作答要求、只回字母。
  function buildPrompt(questions) {
    var qs = questions.map(function (q, i) { return (i + 1) + ". A. " + q.a + "\n   B. " + q.b; }).join("\n");
    return "请你做一份 20 道二选一的小测验。完全按你自己的真实倾向作答，不用为了好玩而刻意选，也没有标准答案，每题只能选 A 或 B。\n\n"
      + qs + "\n\n只输出 20 个字母，例如 ABBAABBA……，不要解释，不要换行。";
  }

  // 显示名只当纯文本用：去掉控制字符，最多 12 个字符。
  function cleanName(name) {
    return String(name == null ? "" : name).replace(/[\u0000-\u001f\u007f<>]/g, "").trim().slice(0, 12);
  }

  var api = {score: score, parseAnswers: parseAnswers, buildPrompt: buildPrompt, cleanName: cleanName};
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.WhaleQuiz = api;
})(typeof window !== "undefined" ? window : this);
