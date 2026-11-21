/**
 * 二次元厚涂御姐（anime-thickpaint-oneesan-prompts）
 *
 * 七大独立词池，全部做成下拉：
 *   年龄 / 气质 / 发型 / 服装类别 / 服装 / 性感动词 / 姿态 / 场景 / 光线 / 丝袜概率
 * 加上通用的人种/身材/气质，共 14 个控件。
 */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const API = "/api/anime-oneesan";

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
    const el = $("ao-status");
    if (!el) return;
    el.textContent = text || "";
    el.className = "skill-status" + (kind ? ` ${kind}` : "");
  }

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      if (typeof showToast === "function") showToast("已复制", "success");
    } catch (_) {
      if (typeof showToast === "function") showToast("复制失败", "error");
    }
  }

  function selHtml(id, label, items, placeholder) {
    const opts = (items || [])
      .map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`)
      .join("");
    return `
      <label class="skill-field">
        <span class="skill-label">${esc(label)}</span>
        <select id="${id}">
          <option value="">${esc(placeholder || "随机")}</option>
          ${opts}
        </select>
      </label>`;
  }

  function renderCards(items) {
    const host = $("ao-output");
    if (!host) return;
    if (!items || !items.length) {
      host.innerHTML = '<p class="placeholder-text">没有结果</p>';
      return;
    }
    host.innerHTML = items
      .map((it, i) => {
        const p = it.prompt || "";
        const el = it.elements || {};
        const tags = [];
        if (el.category) tags.push(el.category);
        if (el.stockings) tags.push("丝袜");
        const tagHtml = tags.map((t) => `<span class="skill-tag">${esc(t)}</span>`).join("");
        return `
        <div class="skill-card">
          <div class="skill-card-head">
            <span class="skill-card-idx">#${it.index || i + 1}</span>
            ${tagHtml}
            <button class="skill-mini-btn primary" data-render="${esc(p)}">
              <i class="fa-solid fa-bolt"></i> 生成图片
            </button>
            <button class="skill-mini-btn" data-copy="${esc(p)}">
              <i class="fa-regular fa-copy"></i>
            </button>
          </div>
          ${window.PromptEdit.html(p)}
          ${
            el && Object.keys(el).length
              ? `<details class="skill-elements"><summary>元素拆解</summary><pre>${esc(
                  JSON.stringify(el, null, 1)
                )}</pre></details>`
              : ""
          }
        </div>`;
      })
      .join("");

    // 批量出图
    if (items.length > 1) {
      window.BatchDraw?.attach(
        host,
        () => window.BatchDraw.promptsFromCards(host),
        { person: "厚涂御姐", theme: "厚涂御姐" }
      );
    }
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
        tone: "厚涂御姐",
        scene: "",
        person: "厚涂御姐",
        theme: "厚涂御姐",
      };
      try {
        const bound = localStorage.getItem("guoman_active_card");
        if (bound) payload.card_id = bound;
      } catch (_) {}
      const r = await fetch("/api/guoman/direct", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const txt = await r.text();
      if (!r.ok) {
        let d = txt;
        try { d = JSON.parse(txt).detail || txt; } catch (_) {}
        throw new Error(String(d).slice(0, 200));
      }
      const data = JSON.parse(txt);
      if (data.card_id) {
        try { localStorage.setItem("guoman_active_card", data.card_id); } catch (_) {}
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
  let meta = null;

  async function initAnimeOneesan() {
    if (inited) return;
    const view = $("view-anime-oneesan");
    if (!view) return;
    inited = true;

    window.PromptEdit?.bind(view);
    view.addEventListener("click", (e) => {
      const c = e.target.closest("[data-copy]");
      if (c) { copy(c.getAttribute("data-copy") || ""); return; }
      const r = e.target.closest("[data-render]");
      if (r) renderPrompt(r.getAttribute("data-render"), r);
    });

    try {
      meta = await apiGet("/meta");
      const badge = $("ao-badge");
      if (badge) {
        badge.textContent = meta.available ? "skill 就绪" : "skill 未安装";
        badge.className = "skill-badge" + (meta.available ? " ok" : " warn");
      }
      const rule = $("ao-rule");
      if (rule) {
        const n = (meta.pools?.stats?.outfits || 0);
        rule.textContent =
          `必含「${meta.required}」 · 禁词 ${(meta.banned || []).length} 个 · 服装 ${n} 条`;
      }

      const pools = meta.pools || {};

      // 风格下拉（二次元厚涂 / 国漫3D / 3A游戏CG / 国风厚涂）
      const styleRow = $("ao-style-row");
      if (styleRow) {
        const styles = meta.styles || [];
        const opts = styles
          .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
          .join("");
        styleRow.innerHTML = `
          <label class="skill-field">
            <span class="skill-label">风格</span>
            <select id="ao-style">${opts}</select>
            <em class="skill-hint" id="ao-style-hint"></em>
          </label>`;
        const styleSel = $("ao-style");
        const styleHint = $("ao-style-hint");
        const updateStyleHint = () => {
          const cur = styles.find((s) => s.value === (styleSel ? styleSel.value : ""));
          if (styleHint && cur) styleHint.textContent = cur.desc || "";
        };
        styleSel?.addEventListener("change", updateStyleHint);
        updateStyleHint();
      }

      // 第一排：年龄 / 气质 / 发型
      const row1 = $("ao-row1");
      if (row1) {
        row1.innerHTML =
          selHtml("ao-age", "年龄", pools.ages) +
          selHtml("ao-temper", "气质", pools.tempers) +
          selHtml("ao-hair", "发型", pools.hairs);
      }

      // 第二排：服装类别 / 服装 / 丝袜概率
      const row2 = $("ao-row2");
      if (row2) {
        const cats = meta.outfit_categories || [];
        const main = cats.filter((c) => c.group === "主线");
        const cult = cats.filter((c) => c.group === "修仙扩展");
        const optgroups =
          `<optgroup label="主线（五类均衡）">${main
            .map((c) => `<option value="${esc(c.value)}">${esc(c.label)}</option>`)
            .join("")}</optgroup>` +
          (cult.length
            ? `<optgroup label="修仙扩展">${cult
                .map((c) => `<option value="${esc(c.value)}">${esc(c.label)}</option>`)
                .join("")}</optgroup>`
            : "");

        row2.innerHTML =
          `
          <label class="skill-field">
            <span class="skill-label">服装类别</span>
            <select id="ao-category">
              <option value="">随机（五类轮换）</option>
              ${optgroups}
            </select>
          </label>
          <label class="skill-field">
            <span class="skill-label">服装</span>
            <select id="ao-outfit">
              <option value="">随机</option>
            </select>
          </label>` +
          selHtml("ao-stockings", "丝袜概率", (meta.stockings_levels || []).map((s) => ({
            value: String(s.value),
            label: s.label,
          })), "40%（默认）");

        // 类别切换 → 重填服装
        const catSel = $("ao-category");
        const outfitSel = $("ao-outfit");
        const refill = () => {
          if (!outfitSel) return;
          const cat = catSel ? catSel.value : "";
          let list = [];
          if (cat && pools.outfits && pools.outfits[cat]) {
            list = pools.outfits[cat];
          } else {
            list = Object.values(pools.outfits || {}).flat();
          }
          outfitSel.innerHTML =
            '<option value="">随机</option>' +
            list.map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("");
        };
        catSel?.addEventListener("change", refill);
        refill();
        // 默认丝袜 40%
        const st = $("ao-stockings");
        if (st) st.value = "0.4";
      }

      // 第三排：性感动词 / 姿态
      const row3 = $("ao-row3");
      if (row3) {
        row3.innerHTML =
          selHtml("ao-sexy", "性感动词", pools.sexy) +
          selHtml("ao-pose", "姿态", pools.poses);
      }

      // 第四排：场景 / 光线 / 机位构图
      const row4 = $("ao-row4");
      if (row4) {
        row4.innerHTML =
          selHtml("ao-scene", "场景", pools.scenes) +
          selHtml("ao-light", "光线", pools.lights) +
          selHtml("ao-shot", "机位构图", meta.shots);
      }

      // 第五排：人种 / 身材 / 表情气质
      const row5 = $("ao-row5");
      if (row5) {
        const groups = meta.ethnicity_groups || {};
        const ethOpts = Object.keys(groups)
          .map((g) => {
            const inner = (groups[g] || [])
              .map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`)
              .join("");
            return inner ? `<optgroup label="${esc(g)}">${inner}</optgroup>` : "";
          })
          .join("");
        row5.innerHTML =
          `
          <label class="skill-field">
            <span class="skill-label">人种</span>
            <select id="ao-ethnicity">
              <option value="">不限（东亚）</option>
              ${ethOpts}
            </select>
          </label>` +
          selHtml("ao-body", "身材", meta.bodies) +
          selHtml("ao-vibe", "表情气质", meta.vibes);
      }

      // 修仙开关
      const cultCb = $("ao-cultivation");
      if (cultCb && !(meta.cultivation_categories || []).length) {
        cultCb.disabled = true;
        cultCb.closest("label").title = "该 skill 未提供修仙扩展池";
      }
    } catch (e) {
      setStatus(String(e.message), "error");
    }

    // 生成一条
    $("ao-generate")?.addEventListener("click", async () => {
      const btn = $("ao-generate");
      const orig = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 生成中…';
      setStatus("生成中…");
      try {
        // 不传 seed —— 后端每次自动换新种子，保证点一次就换一批
        const payload = {
          style: $("ao-style")?.value || "",
          age: $("ao-age")?.value || "",
          temper: $("ao-temper")?.value || "",
          hair: $("ao-hair")?.value || "",
          category: $("ao-category")?.value || "",
          outfit: $("ao-outfit")?.value || "",
          stockings: $("ao-stockings")?.value ?? "0.4",
          sexy: $("ao-sexy")?.value || "",
          pose: $("ao-pose")?.value || "",
          scene: $("ao-scene")?.value || "",
          shot: $("ao-shot")?.value || "",
          light: $("ao-light")?.value || "",
          body: $("ao-body")?.value || "",
          vibe: $("ao-vibe")?.value || "",
          ethnicity: $("ao-ethnicity")?.value || "",
          include_cultivation: Boolean($("ao-cultivation")?.checked),
          seed: "random",
        };

        const _an = Math.max(1, Number($("ao-count")?.value || 1));
        if (_an > 1) {
          const batchPayload = { ...payload, n: _an };
          delete batchPayload.category;
          const catB = $("ao-category")?.value || "";
          batchPayload.categories = catB ? [catB] : [];
          const rb = await apiPost("/batch", batchPayload);
          renderCards(rb.items || []);
          setStatus(`已生成 ${rb.count} 条`, "ok");
          return;
        }
        const r = await apiPost("/generate", payload);
        renderCards([{ index: 1, prompt: r.prompt, elements: r.elements }]);
        setStatus("已生成", "ok");
      } catch (e) {
        setStatus(String(e.message), "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    });

    // 批量
  }

  window.initAnimeOneesan = initAnimeOneesan;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAnimeOneesan);
  } else {
    initAnimeOneesan();
  }
})();
