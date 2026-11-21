/**
 * 21 岁成人写实摄影提示词（adult-photorealistic-prompt-style-21）
 *
 * 四类语料风格：情趣时尚 / 都市纪实 / 汉服舞台 / 瑜伽体操。
 * 特点：内置确定性年龄规范化（18/19/20/女孩 → 21 岁成年女性），
 *      生成后自动过一遍规范化，也可单独粘贴文本做规范化。
 */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const API = "/api/adult-photo21";

  function esc(t) {
    const d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }

  async function apiGet(path) {
    const r = await fetch(API + path, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
    return r.json();
  }

  async function apiPost(path, body) {
    const r = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const txt = await r.text();
    if (!r.ok) {
      let d = txt;
      try { d = JSON.parse(txt).detail || txt; } catch (_) {}
      throw new Error(String(d).slice(0, 300));
    }
    return JSON.parse(txt);
  }

  function setStatus(text, kind) {
    const el = $("ap-status");
    if (!el) return;
    el.textContent = text || "";
    el.className = "skill-status" + (kind ? ` ${kind}` : "");
  }

  // ── 人种 / 年龄 / 身材 / 气质 下拉 ──────────────────────────────────

  function ethnicityHtml(groups) {
    const gs = groups || {};
    const opts = Object.keys(gs)
      .map((g) => {
        const inner = (gs[g] || [])
          .map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`)
          .join("");
        return inner ? `<optgroup label="${esc(g)}">${inner}</optgroup>` : "";
      })
      .join("");
    return `
      <label class="skill-field">
        <span class="skill-label">人种</span>
        <select id="ap-ethnicity">
          <option value="">不限（中国女性）</option>
          ${opts}
        </select>
      </label>`;
  }

  function simpleHtml(id, label, items) {
    const opts = (items || [])
      .map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`)
      .join("");
    return `
      <label class="skill-field">
        <span class="skill-label">${esc(label)}</span>
        <select id="${id}">${opts}</select>
      </label>`;
  }

  function fillPersona(meta) {
    const host = $("ap-persona");
    if (!host) return;
    host.innerHTML =
      ethnicityHtml(meta.ethnicity_groups) +
      simpleHtml("ap-age", "年龄", meta.ages) +
      simpleHtml("ap-body", "身材", meta.bodies) +
      simpleHtml("ap-vibe", "气质", meta.vibes);
  }

  function collectPersona() {
    const out = {};
    const eth = $("ap-ethnicity")?.value?.trim();
    if (eth) out.ethnicity = eth;
    const age = $("ap-age")?.value?.trim();
    if (age) out.age = age;
    const body = $("ap-body")?.value?.trim();
    if (body) out.body = body;
    const vibe = $("ap-vibe")?.value?.trim();
    if (vibe) out.vibe = vibe;
    return out;
  }

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      if (typeof showToast === "function") showToast("已复制", "success");
    } catch (_) {
      if (typeof showToast === "function") showToast("复制失败", "error");
    }
  }

  function renderCards(items) {
    const host = $("ap-output");
    if (!host) return;
    if (!items || !items.length) {
      host.innerHTML = '<p class="placeholder-text">没有结果</p>';
      return;
    }
    host.innerHTML = items
      .map((it, i) => {
        const p = it.prompt || "";
        const normTag = it.normalized
          ? '<span class="skill-tag">已规范化年龄</span>'
          : "";
        const residTag = it.residual
          ? '<span class="skill-tag warn">仍有低龄词</span>'
          : "";
        return `
        <div class="skill-card">
          <div class="skill-card-head">
            <span class="skill-card-idx">#${it.index || i + 1}</span>
            ${normTag}${residTag}
            <button class="skill-mini-btn primary" data-render="${esc(p)}">
              <i class="fa-solid fa-bolt"></i> 生成图片
            </button>
            <button class="skill-mini-btn" data-copy="${esc(p)}">
              <i class="fa-regular fa-copy"></i>
            </button>
          </div>
          ${window.PromptEdit.html(p)}
        </div>`;
      })
      .join("");

    // 批量出图
    if (items.length > 1) {
      window.BatchDraw?.attach(
        host,
        () => window.BatchDraw.promptsFromCards(host),
        { person: "写实摄影", theme: "写实摄影" }
      );
    }
  }

  /**
   * 出图投递：走主引擎的 /api/guoman/direct。
   * 注意不能用 apiPost() —— 它会自动拼上本 skill 的 API 前缀，
   * 结果变成 /api/adult-photo21/api/guoman/direct → 405 Method Not Allowed。
   */
  async function postDirect(payload) {
    const r = await fetch("/api/guoman/direct", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const txt = await r.text();
    if (!r.ok) {
      let d = txt;
      try { d = JSON.parse(txt).detail || txt; } catch (_) {}
      throw new Error(String(d).slice(0, 300));
    }
    return JSON.parse(txt);
  }

  async function renderPrompt(prompt, btnEl) {
    if (!prompt) return;
    const orig = btnEl ? btnEl.innerHTML : "";
    if (btnEl) {
      btnEl.disabled = true;
      btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }
    try {
      const payload = {
        prompt,
        tone: "写实摄影",
        scene: "",
        person: "写实摄影",
        theme: "写实",
      };
      try {
        const bound = localStorage.getItem("guoman_active_card");
        if (bound) payload.card_id = bound;
      } catch (_) {}
      const r = await postDirect(payload);
      if (r.card_id) {
        try { localStorage.setItem("guoman_active_card", r.card_id); } catch (_) {}
      }
      if (btnEl) btnEl.innerHTML = '<i class="fa-solid fa-check"></i> 已投递';
      if (typeof showToast === "function") showToast("已提交出图队列", "success");
      if (typeof refreshCards === "function") setTimeout(() => refreshCards().catch(() => {}), 1500);
    } catch (e) {
      if (btnEl) btnEl.innerHTML = orig;
      if (typeof showToast === "function") showToast("投递失败：" + String(e.message).slice(0, 60), "error");
    } finally {
      if (btnEl) btnEl.disabled = false;
    }
  }

  let inited = false;

  async function initAdultPhoto21() {
    if (inited) return;
    const view = $("view-adult-photo21");
    if (!view) return;
    inited = true;

    window.PromptEdit?.bind(view);
    // 卡片按钮委托
    view.addEventListener("click", (e) => {
      const c = e.target.closest("[data-copy]");
      if (c) { copy(c.getAttribute("data-copy") || ""); return; }
      const r = e.target.closest("[data-render]");
      if (r) renderPrompt(r.getAttribute("data-render"), r);
    });

    try {
      const meta = await apiGet("/meta");
      const badge = $("ap-badge");
      if (badge) {
        badge.textContent = meta.available ? "skill 就绪" : "skill 未安装";
        badge.className = "skill-badge" + (meta.available ? " ok" : " warn");
      }
      const rule = $("ap-age-rule");
      if (rule && meta.age_rule) rule.textContent = meta.age_rule;

      const styleSel = $("ap-style");
      if (styleSel && meta.styles) {
        styleSel.innerHTML = meta.styles
          .map((s) => `<option value="${esc(s.id)}">${esc(s.label)}</option>`)
          .join("");
      }
      const shotSel = $("ap-shot");
      if (shotSel && meta.shots) {
        shotSel.innerHTML = meta.shots
          .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
          .join("");
      }
      const lightSel = $("ap-light");
      if (lightSel && meta.lights) {
        lightSel.innerHTML = meta.lights
          .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
          .join("");
      }
      const poseSel = $("ap-pose");
      if (poseSel && meta.poses) {
        poseSel.innerHTML = meta.poses
          .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
          .join("");
      }
      // 风格提示
      const hint = $("ap-style-hint");
      const updateHint = () => {
        const cur = (meta.styles || []).find((s) => s.id === (styleSel ? styleSel.value : ""));
        if (hint && cur) hint.textContent = `${cur.desc} · ${cur.hint}`;
      };
      styleSel?.addEventListener("change", updateHint);
      updateHint();
      // 人种 / 年龄 / 身材 / 气质
      fillPersona(meta);
    } catch (e) {
      setStatus(String(e.message), "error");
    }

    // 生成
    $("ap-generate")?.addEventListener("click", async () => {
      const btn = $("ap-generate");
      const orig = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 生成中…';
      setStatus("生成中…");
      try {
        const r = await apiPost("/generate", {
          style: $("ap-style")?.value || "editorial",
          subject: $("ap-subject")?.value?.trim() || "",
          pose: $("ap-pose")?.value || "",
          shot: $("ap-shot")?.value || "",
          light: $("ap-light")?.value || "",
          extra: $("ap-extra")?.value?.trim() || "",
          count: Number($("ap-count")?.value || 1),
          ...collectPersona(),
        });
        renderCards(r.items || []);
        setStatus(`已生成 ${r.count} 条`, "ok");
      } catch (e) {
        setStatus(String(e.message), "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    });

    // 改写
    $("ap-rewrite")?.addEventListener("click", async () => {
      const text = $("ap-rewrite-input")?.value?.trim();
      if (!text) { setStatus("请贴入要改写的提示词", "warn"); return; }
      const btn = $("ap-rewrite");
      const orig = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 改写中…';
      setStatus("改写中…");
      try {
        const r = await apiPost("/rewrite", { text });
        renderCards([{ index: 1, prompt: r.rewritten, residual: r.residual }]);
        setStatus("已改写", "ok");
      } catch (e) {
        setStatus(String(e.message), "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    });

    // 纯规范化（不走 LLM）
    $("ap-normalize")?.addEventListener("click", async () => {
      const text = $("ap-rewrite-input")?.value?.trim();
      if (!text) { setStatus("请贴入要规范化的文本", "warn"); return; }
      setStatus("规范化中…");
      try {
        const r = await apiPost("/normalize", { text });
        renderCards([{
          index: 1,
          prompt: r.normalized,
          normalized: r.changed,
          residual: r.residual,
        }]);
        setStatus(r.changed ? "已规范化" : "无需改动", "ok");
      } catch (e) {
        setStatus(String(e.message), "error");
      }
    });
  }

  window.initAdultPhoto21 = initAdultPhoto21;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAdultPhoto21);
  } else {
    initAdultPhoto21();
  }
})();
