/**
 * 一句话扩写剧本 · NSFW
 *
 * 输入一句话创意 + 几个下拉，调 /api/script-expand/generate 产出标准格式剧本。
 * 剧本分块展示（头部 / 角色卡 / 场景卡 / 分场 / 衔接链），每块可单独复制。
 */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  function esc(t) {
    const d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }

  const state = {
    meta: null,
    script: "",
    sections: {},
    stats: null,
  };

  function setStatus(msg, kind) {
    const el = $("se-status");
    if (!el) return;
    el.textContent = msg || "";
    el.className = "skill-status" + (kind ? " " + kind : "");
  }

  function selHtml(id, label, list, hint) {
    const opts = (list || [])
      .map((o) => {
        const v = typeof o === "string" ? o : o.value;
        const l = typeof o === "string" ? o : o.label;
        return `<option value="${esc(v)}">${esc(l)}</option>`;
      })
      .join("");
    return `
      <label class="skill-field">
        <span class="skill-label">${esc(label)}</span>
        <select id="${id}">${opts}</select>
        ${hint ? `<em class="skill-hint">${esc(hint)}</em>` : ""}
      </label>`;
  }

  async function apiPost(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const txt = await res.text();
    let data = {};
    try {
      data = JSON.parse(txt);
    } catch (e) {
      throw new Error(txt.slice(0, 180) || `HTTP ${res.status}`);
    }
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    return data;
  }

  function collect() {
    return {
      idea: $("se-idea")?.value?.trim() || "",
      genre: $("se-genre")?.value || "",
      aspect: $("se-aspect")?.value || "9:16",
      lang: $("se-lang")?.value || "中文",
      characters: $("se-chars")?.value?.trim() || "",
      scene_hint: $("se-scene-hint")?.value?.trim() || "",
      scenes_per_ep: Number($("se-scenes")?.value || 6),
      scene_seconds: Number($("se-scene-s")?.value || 10),
      batch_size: Number($("se-batch")?.value || 2),
    };
  }

  function renderStats(st) {
    const el = $("se-stats");
    if (!el || !st) return;
    const pct = Math.round((st.sex_ratio || 0) * 100);
    el.innerHTML =
      `<span>${st.scenes} 场 · ${st.shots} 镜 · ${st.chars} 字</span>` +
      `<span class="${pct >= 50 ? "ok" : "warn"}">亲密场 ${st.sex_scenes}（${pct}%）</span>`;
  }

  function renderScript(data) {
    state.script = data.script || "";
    state.sections = data.sections || {};
    state.stats = data.stats || null;

    const host = $("se-output");
    if (!host) return;

    if (!state.script) {
      host.innerHTML = '<p class="placeholder-text">没有结果</p>';
      return;
    }

    const s = state.sections;
    const blocks = [
      ["剧本头部", s.title && s.logline ? `${s.title || ""}\n\n${s.logline || ""}\n\n${s.spec || ""}` : ""],
      ["角色卡", s.characters || ""],
      ["场景卡", s.locations || ""],
      ["分场剧本", s.scenes || ""],
      ["场间衔接", [s.chain || "", s.hook || ""].filter(Boolean).join("\n\n")],
    ].filter(([, v]) => v && v.trim());

    host.innerHTML =
      `<div class="se-toolbar">
         <span class="se-toolbar-title"><i class="fa-solid fa-file-lines"></i> 剧本正文</span>
         <span class="se-toolbar-note">各块可单独编辑，编辑后「复制全文」用的是改后的内容</span>
       </div>` +
      blocks
        .map(
          ([name, text], i) => `
        <div class="se-block">
          <div class="se-block-head">
            <span class="se-block-name">${esc(name)}</span>
            <button class="skill-mini-btn" data-se-copy="${esc(text)}">
              <i class="fa-regular fa-copy"></i>
            </button>
          </div>
          <div class="se-block-body" contenteditable="true" spellcheck="false"
               data-se-editable="1">${esc(text)}</div>
        </div>`
        )
        .join("");

    // 块级复制
    host.querySelectorAll("[data-se-copy]").forEach((b) => {
      b.addEventListener("click", () => {
        copyText(b.getAttribute("data-se-copy") || "");
      });
    });

    renderStats(state.stats);

    if (data.warnings && data.warnings.length) {
      setStatus(data.warnings.join("；"), "warn");
    } else {
      setStatus("已生成", "ok");
    }
  }

  /** 收集当前（可能被编辑过的）全文。 */
  function collectScript() {
    const host = $("se-output");
    if (!host) return state.script;
    const bodies = host.querySelectorAll("[data-se-editable]");
    if (!bodies.length) return state.script;
    return Array.from(bodies)
      .map((el) => (el.innerText || el.textContent || "").trim())
      .filter(Boolean)
      .join("\n\n");
  }

  function copyText(text) {
    if (!text) return;
    const done = () => {
      if (typeof window.showToast === "function") window.showToast("已复制", "success");
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else {
      fallbackCopy(text, done);
    }
  }

  function fallbackCopy(text, done) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      done();
    } catch (e) {}
    document.body.removeChild(ta);
  }

  function download() {
    const text = collectScript();
    if (!text) return;
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const title = (state.sections.title || "剧本").replace(/[【】\s]/g, "").slice(0, 20);
    a.download = `${title || "剧本"}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  async function generate() {
    const btn = $("se-generate");
    const payload = collect();
    if (!payload.idea) {
      setStatus("请先写一句话创意", "warn");
      $("se-idea")?.focus();
      return;
    }

    const old = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 扩写中…';
    setStatus("分阶段生成中，约 1-2 分钟…");

    try {
      const r = await apiPost("/api/script-expand/generate", payload);
      renderScript(r);
    } catch (e) {
      setStatus(String(e.message || e).slice(0, 160), "warn");
    } finally {
      btn.disabled = false;
      btn.innerHTML = old;
    }
  }

  async function polish() {
    const text = collectScript();
    if (!text) {
      setStatus("先扩写一版再润色", "warn");
      return;
    }
    const btn = $("se-polish");
    const old = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 润色中…';
    setStatus("按自检清单润色，约 1 分钟…");

    try {
      const r = await apiPost("/api/script-expand/polish", { script: text });
      renderScript(r);
    } catch (e) {
      setStatus(String(e.message || e).slice(0, 160), "warn");
    } finally {
      btn.disabled = false;
      btn.innerHTML = old;
    }
  }

  async function init() {
    const badge = $("se-badge");
    try {
      const res = await fetch("/api/script-expand/meta");
      const meta = await res.json();
      state.meta = meta;

      if (badge) {
        badge.textContent = meta.available ? "skill 就绪" : "skill 未安装";
        badge.className = "skill-badge" + (meta.available ? " ok" : " warn");
      }

      const rule = $("se-rule");
      if (rule && meta.rules) {
        const r = meta.rules;
        rule.textContent =
          `亲密场 ≥50% · 首场 3 秒钩子 · 每场 10s 一镜到底 · ` +
          `角色卡只写声音 · 必出衔接链`;
      }

      // 第一排：类型 / 画幅 / 台词语言
      const row1 = $("se-row1");
      if (row1) {
        row1.innerHTML =
          selHtml("se-genre", "成人向类型", meta.genres || [], "") +
          selHtml("se-aspect", "画幅", meta.aspects || [], "") +
          selHtml("se-lang", "台词语言", meta.langs || [], "");
      }

      // 第二排：角色 / 场景偏好
      const row2 = $("se-row2");
      if (row2) {
        row2.innerHTML = `
          <label class="skill-field">
            <span class="skill-label">主要角色（可选）</span>
            <input type="text" id="se-chars" placeholder="例：林夏（女，29岁）、顾沉（男，32岁）">
          </label>
          <label class="skill-field">
            <span class="skill-label">场景偏好（可选）</span>
            <input type="text" id="se-scene-hint" placeholder="例：酒店套房、浴室、落地窗">
          </label>`;
      }
    } catch (e) {
      if (badge) {
        badge.textContent = "探测失败";
        badge.className = "skill-badge warn";
      }
    }

    $("se-generate")?.addEventListener("click", generate);
    $("se-polish")?.addEventListener("click", polish);
    $("se-copy")?.addEventListener("click", () => copyText(collectScript()));
    $("se-download")?.addEventListener("click", download);

    // Ctrl+Enter 直接扩写
    $("se-idea")?.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        generate();
      }
    });
  }

  window.initScriptExpand = init;
})();
