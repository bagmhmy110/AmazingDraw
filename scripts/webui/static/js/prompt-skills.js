/**
 * 三个独立 prompt skill 的前端（各自独立，不合并）。
 *
 *   guoman-portrait  → 国漫 / 东方女性人像（四条风格线）
 *   moss-architect   → MOSS-Image 提示词架构师（Caption / Layout）
 *   nsfw-templates   → NSFW 模板词库（14 模块组装）
 */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  function esc(t) {
    const d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }

  async function apiGet(url) {
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
    return r.json();
  }

  async function apiPost(url, body) {
    const r = await fetch(url, {
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

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      if (typeof showToast === "function") showToast("已复制", "success");
    } catch (_) {
      if (typeof showToast === "function") showToast("复制失败", "error");
    }
  }

  function setStatus(id, text, kind) {
    const el = $(id);
    if (!el) return;
    el.textContent = text || "";
    el.className = "skill-status" + (kind ? ` ${kind}` : "");
  }

  // ── 通用：人种 / 年龄 / 身材 / 气质 下拉 ────────────────────────────

  /** 渲染人种下拉（按分组）。 */
  function ethnicitySelectHtml(id, groups) {
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
        <select id="${id}">
          <option value="">不限（亚洲人）</option>
          ${opts}
        </select>
      </label>`;
  }

  /** 渲染年龄下拉。 */
  function ageSelectHtml(id, ages) {
    const opts = (ages || [])
      .map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`)
      .join("");
    return `
      <label class="skill-field">
        <span class="skill-label">年龄</span>
        <select id="${id}">${opts}</select>
      </label>`;
  }

  /** 渲染简单下拉（body / vibe 这类）。 */
  function simpleSelectHtml(id, label, items) {
    const opts = (items || [])
      .map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`)
      .join("");
    return `
      <label class="skill-field">
        <span class="skill-label">${esc(label)}</span>
        <select id="${id}">${opts}</select>
      </label>`;
  }

  /** 收集通用人种/年龄字段。 */
  function collectPersona(prefix) {
    const out = {};
    const eth = $(`${prefix}-ethnicity`)?.value?.trim();
    if (eth) out.ethnicity = eth;
    const age = $(`${prefix}-age`)?.value?.trim();
    if (age) out.age = age;
    const body = $(`${prefix}-body`)?.value?.trim();
    if (body) out.body = body;
    const vibe = $(`${prefix}-vibe`)?.value?.trim();
    if (vibe) out.vibe = vibe;
    return out;
  }

  /** 往容器里填充人种/年龄/身材/气质四个下拉。 */
  function fillPersona(hostId, prefix, meta) {
    const host = $(hostId);
    if (!host) return;
    host.innerHTML =
      ethnicitySelectHtml(`${prefix}-ethnicity`, meta.ethnicity_groups) +
      ageSelectHtml(`${prefix}-age`, meta.ages) +
      simpleSelectHtml(`${prefix}-body`, "身材", meta.bodies) +
      simpleSelectHtml(`${prefix}-vibe`, "气质", meta.vibes);
  }

  // 通用：把生成结果渲染成卡片（带复制 + 可选出图按钮）
  function renderCards(hostId, items, opts) {
    const host = $(hostId);
    if (!host) return;
    opts = opts || {};
    if (!items || !items.length) {
      host.innerHTML = '<p class="placeholder-text">没有结果</p>';
      return;
    }
    host.innerHTML = items
      .map((it, i) => {
        const p = it.prompt || "";
        const tags = [];
        if (it.line_label) tags.push(it.line_label);
        if (it.category) tags.push(it.category);
        if (it.tone) tags.push(it.tone);
        if (it.scene) tags.push(it.scene);
        const tagHtml = tags.map((t) => `<span class="skill-tag">${esc(t)}</span>`).join("");
        return `
        <div class="skill-card">
          <div class="skill-card-head">
            <span class="skill-card-idx">#${it.index || i + 1}</span>
            ${tagHtml}
            <button class="skill-mini-btn primary" data-render="${esc(p)}" data-tone="${esc(it.tone || opts.tone || "")}" data-scene="${esc(it.scene || opts.scene || "")}">
              <i class="fa-solid fa-bolt"></i> 生成图片
            </button>
            <button class="skill-mini-btn" data-copy="${esc(p)}">
              <i class="fa-regular fa-copy"></i>
            </button>
          </div>
          ${window.PromptEdit.html(p)}
          ${
            it.elements
              ? `<details class="skill-elements"><summary>元素拆解</summary><pre>${esc(
                  typeof it.elements === "string" ? it.elements : JSON.stringify(it.elements, null, 1)
                )}</pre></details>`
              : ""
          }
        </div>`;
      })
      .join("");

    // 批量出图：一键把这一批提示词全部投进队列
    if (items.length > 1) {
      window.BatchDraw?.attach(
        host,
        () => window.BatchDraw.promptsFromCards(host),
        {
          person: opts.person || opts.personName || "",
          tone: opts.tone || "",
          theme: opts.theme || "",
        }
      );
    }
  }

  // 通用：出图（走主引擎的直投，复用卡片绑定）
  // person = 来源 skill 名，决定卡片显示名与文件名前缀
  // theme  = 风格名，参与文件名 <person>-<scene>-<theme>.png
  async function renderPrompt(prompt, tone, scene, btnEl, person, theme) {
    if (!prompt) return;
    const orig = btnEl ? btnEl.innerHTML : "";
    if (btnEl) {
      btnEl.disabled = true;
      btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }
    try {
      const payload = {
        prompt,
        tone: tone || "国漫立绘",
        scene: scene || "",
        person: person || "国漫立绘",
      };
      if (theme) payload.theme = theme;
      try {
        const bound = localStorage.getItem("guoman_active_card");
        if (bound) payload.card_id = bound;
      } catch (_) {}
      const r = await apiPost("/api/guoman/direct", payload);
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

  // 通用事件委托
  function bindCardActions(viewId, person, theme) {
    const view = $(viewId);
    if (!view) return;
    view.addEventListener("click", (e) => {
      const c = e.target.closest("[data-copy]");
      if (c) { copy(c.getAttribute("data-copy") || ""); return; }
      const r = e.target.closest("[data-render]");
      if (r) {
        renderPrompt(
          r.getAttribute("data-render"),
          r.getAttribute("data-tone"),
          r.getAttribute("data-scene"),
          r,
          person,
          theme
        );
      }
    });
  }

  // ══════════════════════════════════════════════════════════════════
  // 1. 国漫 / 东方女性人像
  // ══════════════════════════════════════════════════════════════════

  let gpInited = false;

  async function initGuomanPortrait() {
    if (gpInited) return;
    const view = $("view-guoman-portrait");
    if (!view) return;
    gpInited = true;

    bindCardActions("view-guoman-portrait", "国漫人像", "人像");
    window.PromptEdit?.bind($("view-guoman-portrait"));

    try {
      const meta = await apiGet("/api/guoman-portrait/meta");
      const badge = $("gp-badge");
      if (badge) {
        badge.textContent = meta.available ? "skill 就绪" : "skill 未安装";
        badge.className = "skill-badge" + (meta.available ? " ok" : " warn");
      }
      const lineSel = $("gp-line");
      if (lineSel && meta.lines) {
        // 基础线（B/C/A/D）与画风线分两组显示，别把 id 露出来当标题
        const base = meta.lines.filter((l) => !l._style);
        const styled = meta.lines.filter((l) => l._style);
        const opt = (l) => `<option value="${esc(l.id)}">${esc(l.label)}</option>`;
        lineSel.innerHTML =
          `<optgroup label="基础线">${base.map(opt).join("")}</optgroup>` +
          (styled.length ? `<optgroup label="画风线">${styled.map(opt).join("")}</optgroup>` : "");
      }
      const legSel = $("gp-leg");
      if (legSel && meta.leg_levels) {
        legSel.innerHTML = meta.leg_levels
          .map((l) => `<option value="${esc(l.value)}">${esc(l.label)}</option>`)
          .join("");
        legSel.value = "mild";
      }
      const lineHint = $("gp-line-hint");
      const updateHint = () => {
        const cur = (meta.lines || []).find((l) => l.id === (lineSel ? lineSel.value : "B"));
        if (lineHint && cur) lineHint.textContent = `${cur.desc} · ${cur.words}`;
      };
      lineSel?.addEventListener("change", updateHint);
      updateHint();
      // 人种 / 年龄 / 身材 / 气质
      fillPersona("gp-persona", "gp", meta);
      // 本 skill 专属：人物类型 / 发型 / 性感级别
      const pools = meta.pools || {};
      const look = $("gp-look");
      if (look) {
        look.innerHTML =
          simpleSelectHtml("gp-temper", "人物类型", pools.tempers) +
          simpleSelectHtml("gp-hair", "发型", pools.hairs) +
          simpleSelectHtml("gp-sexy", "性感级别", pools.sexy);
      }
      // 第三排：场景 / 光线 / 姿势 / 机位构图
      const setting = $("gp-setting");
      if (setting) {
        setting.innerHTML =
          simpleSelectHtml("gp-scene", "场景", pools.scenes) +
          simpleSelectHtml("gp-light", "光线", pools.lights) +
          simpleSelectHtml("gp-pose", "姿势", pools.poses) +
          simpleSelectHtml("gp-shot", "机位构图", meta.shots);
      }
      // 第四排：服装类别 / 服装
      const outfitRow = $("gp-outfit-row");
      if (outfitRow) {
        const outfits = pools.outfits || {};
        const cats = pools.outfit_categories || [];
        outfitRow.innerHTML = `
          <label class="skill-field">
            <span class="skill-label">服装类别</span>
            <select id="gp-outfit-cat">
              ${(cats || []).map((c) => `<option value="${esc(c.value)}">${esc(c.label)}</option>`).join("")}
            </select>
          </label>
          <label class="skill-field">
            <span class="skill-label">服装</span>
            <select id="gp-outfit">
              <option value="">不限（按风格自选）</option>
            </select>
          </label>`;

        // 类别切换时重填服装下拉
        const catSel = $("gp-outfit-cat");
        const outfitSel = $("gp-outfit");
        const refill = () => {
          if (!outfitSel) return;
          const cat = catSel ? catSel.value : "";
          const list = cat && outfits[cat] ? outfits[cat] : Object.values(outfits).flat();
          outfitSel.innerHTML =
            '<option value="">不限（按风格自选）</option>' +
            (list || [])
              .map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`)
              .join("");
        };
        catSel?.addEventListener("change", refill);
        refill();
      }
    } catch (e) {
      setStatus("gp-status", String(e.message), "error");
    }

    $("gp-generate")?.addEventListener("click", async () => {
      const btn = $("gp-generate");
      const orig = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 生成中…';
      setStatus("gp-status", "生成中…");
      try {
        const _n = Math.max(1, Number($("gp-count")?.value || 1));
        if (_n > 1) {
          const r = await apiPost("/api/guoman-portrait/batch", {
            n: _n,
            seed: "random",
            line: $("gp-line")?.value || "B",
            leg: $("gp-leg")?.value || "mild",
            temper: $("gp-temper")?.value || "",
            hair: $("gp-hair")?.value || "",
            sexy: $("gp-sexy")?.value || "",
            scene: $("gp-scene")?.value || "",
            light: $("gp-light")?.value || "",
            pose: $("gp-pose")?.value || "",
            shot: $("gp-shot")?.value || "",
            outfit_cat: $("gp-outfit-cat")?.value || "",
            outfit: $("gp-outfit")?.value || "",
            ...collectPersona("gp"),
            extra_style: $("gp-style")?.value || "",
          });
          renderCards("gp-output", r.items || [], { person: "国漫人像", theme: "人像" });
          setStatus("gp-status", `已生成 ${r.count} 条`, "ok");
          return;
        }
        const r = await apiPost("/api/guoman-portrait/generate", {
          line: $("gp-line")?.value || "B",
          theme: $("gp-theme")?.value?.trim() || "",
          leg: $("gp-leg")?.value || "mild",
          extra: $("gp-extra")?.value?.trim() || "",
          temper: $("gp-temper")?.value || "",
          hair: $("gp-hair")?.value || "",
          sexy: $("gp-sexy")?.value || "",
          scene: $("gp-scene")?.value || "",
          light: $("gp-light")?.value || "",
          pose: $("gp-pose")?.value || "",
          shot: $("gp-shot")?.value || "",
          outfit: $("gp-outfit")?.value || "",
          ...collectPersona("gp"),
        });
        renderCards("gp-output", [{ index: 1, prompt: r.prompt, line_label: r.line_label }]);
        setStatus("gp-status", "已生成", "ok");
      } catch (e) {
        setStatus("gp-status", String(e.message), "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    });

  }

  // ══════════════════════════════════════════════════════════════════
  // 2. MOSS-Image 架构师
  // ══════════════════════════════════════════════════════════════════

  let maInited = false;

  async function initMossArchitect() {
    if (maInited) return;
    const view = $("view-moss-architect");
    if (!view) return;
    maInited = true;

    bindCardActions("view-moss-architect", "MOSS", "散文");
    window.PromptEdit?.bind($("view-moss-architect"));

    try {
      const meta = await apiGet("/api/moss-architect/meta");
      const badge = $("ma-badge");
      if (badge) {
        badge.textContent = meta.available ? "skill 就绪" : "skill 未安装";
        badge.className = "skill-badge" + (meta.available ? " ok" : " warn");
      }
      const modeSel = $("ma-mode");
      if (modeSel && meta.modes) {
        modeSel.innerHTML = meta.modes
          .map((m) => `<option value="${esc(m.value)}">${esc(m.label)}</option>`)
          .join("");
      }
      const subSel = $("ma-subject");
      if (subSel && meta.subjects) {
        subSel.innerHTML =
          '<option value="">不限</option>' +
          meta.subjects.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
      }
      const hint = $("ma-constraint");
      if (hint && meta.hard_constraint) hint.textContent = meta.hard_constraint;

      // 新增下拉：画风 / 场景 / 光线 / 机位 / 画幅
      const more = $("ma-more");
      if (more) {
        const styles = meta.extra_styles || [];
        const styleOpts = styles
          .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
          .join("");
        more.innerHTML =
          `<label class="skill-field">
             <span class="skill-label">画风</span>
             <select id="ma-style">
               <option value="">不限（用原风格）</option>
               ${styleOpts}
             </select>
           </label>` +
          simpleSelectHtml("ma-scene", "场景", meta.scenes) +
          simpleSelectHtml("ma-light", "光线", meta.lights) +
          simpleSelectHtml("ma-shot", "机位构图", meta.shots) +
          simpleSelectHtml("ma-aspect", "画幅", meta.aspects);
      }
      // 人种 / 年龄 / 身材 / 气质
      fillPersona("ma-persona", "ma", meta);
    } catch (e) {
      setStatus("ma-status", String(e.message), "error");
    }

    $("ma-generate")?.addEventListener("click", async () => {
      const idea = $("ma-idea")?.value?.trim();
      if (!idea) { setStatus("ma-status", "请填写想法", "warn"); return; }
      const btn = $("ma-generate");
      const orig = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 生成中…';
      setStatus("ma-status", "生成中…");
      try {
        const _mn = Math.max(1, Number($("ma-count")?.value || 1));
        if (_mn > 1) {
          const r = await apiPost("/api/moss-architect/batch", {
            idea,
            n: _mn,
            mode: $("ma-mode")?.value || "caption",
            subject: $("ma-subject")?.value || "",
            extra: $("ma-extra")?.value?.trim() || "",
            scene: $("ma-scene")?.value || "",
            light: $("ma-light")?.value || "",
            shot: $("ma-shot")?.value || "",
            aspect: $("ma-aspect")?.value || "",
            extra_style: $("ma-style")?.value || "",
            ...collectPersona("ma"),
          });
          renderCards("ma-output", r.items || [], { tone: "散文", person: "MOSS", theme: "散文" });
          setStatus("ma-status", `已生成 ${r.count} 条`, "ok");
          return;
        }
        const r = await apiPost("/api/moss-architect/generate", {
          idea,
          mode: $("ma-mode")?.value || "caption",
          subject: $("ma-subject")?.value || "",
          extra: $("ma-extra")?.value?.trim() || "",
          scene: $("ma-scene")?.value || "",
          light: $("ma-light")?.value || "",
          shot: $("ma-shot")?.value || "",
          aspect: $("ma-aspect")?.value || "",
          extra_style: $("ma-style")?.value || "",
          ...collectPersona("ma"),
        });
        const host = $("ma-output");
        if (host) {
          const isLayout = r.mode === "layout";
          host.innerHTML = `
            <div class="skill-card">
              <div class="skill-card-head">
                <span class="skill-card-idx">${isLayout ? "Layout" : "Caption"}</span>
                ${isLayout && r.valid_json === false ? '<span class="skill-tag warn">JSON 未通过校验</span>' : ""}
                <button class="skill-mini-btn primary" data-render="${esc(isLayout ? (r.layout?.caption || r.prompt) : r.prompt)}" data-tone="${esc(r.mode === "layout" ? "排版" : "散文")}" data-scene="${esc($("ma-scene")?.value || "")}">
                  <i class="fa-solid fa-bolt"></i> 生成图片
                </button>
                <button class="skill-mini-btn" data-copy="${esc(r.prompt)}">
                  <i class="fa-regular fa-copy"></i>
                </button>
              </div>
              ${window.PromptEdit.html(r.prompt)}
            </div>`;
        }
        setStatus("ma-status", "已生成", "ok");
      } catch (e) {
        setStatus("ma-status", String(e.message), "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    });

  }

  // ══════════════════════════════════════════════════════════════════
  // 3. NSFW 模板词库
  // ══════════════════════════════════════════════════════════════════

  let ntInited = false;
  let ntModules = [];

  async function initNsfwTemplates() {
    if (ntInited) return;
    const view = $("view-nsfw-templates");
    if (!view) return;
    ntInited = true;

    bindCardActions("view-nsfw-templates", "NSFW模板", "模板");
    window.PromptEdit?.bind($("view-nsfw-templates"));

    try {
      const meta = await apiGet("/api/nsfw-templates/meta");
      ntModules = meta.modules || [];
      const badge = $("nt-badge");
      if (badge) {
        badge.textContent = meta.available ? "skill 就绪" : "skill 未安装";
        badge.className = "skill-badge" + (meta.available ? " ok" : " warn");
      }
      const b = $("nt-boundary");
      if (b && meta.boundary) b.textContent = meta.boundary;

      // 人种 / 年龄 / 身材 / 气质 + 画风
      fillPersona("nt-persona", "nt", meta);
      const ntPersona = $("nt-persona");
      if (ntPersona) {
        const styles = meta.extra_styles || [];
        if (styles.length) {
          const styleOpts = styles
            .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
            .join("");
          ntPersona.insertAdjacentHTML(
            "beforeend",
            `<label class="skill-field">
               <span class="skill-label">画风</span>
               <select id="nt-style">
                 <option value="">不限（用原风格）</option>
                 ${styleOpts}
               </select>
             </label>`
          );
        }
        // 机位构图（复用 MOSS 那套）
        const shotOpts = (meta.shots || [])
          .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
          .join("");
        if (shotOpts) {
          ntPersona.insertAdjacentHTML(
            "beforeend",
            `<label class="skill-field">
               <span class="skill-label">机位构图</span>
               <select id="nt-shot">${shotOpts}</select>
             </label>`
          );
        }
      }

      // 必读槽 → 下拉（按小节分组，词条来自词库缓存）
      const termsMap = meta.terms || {};
      const reqHost = $("nt-required");
      if (reqHost) {
        reqHost.innerHTML = (meta.required_slots || [])
          .map((slot) => {
            const m = ntModules.find((x) => x.slot === slot) || {};
            const info = termsMap[slot] || {};
            const sections = info.sections || {};
            const total = info.total || 0;

            // 每个小节一个 <optgroup>
            const groups = Object.keys(sections)
              .map((sec) => {
                const opts = (sections[sec] || [])
                  .map((t) => `<option value="${esc(t)}">${esc(t)}</option>`)
                  .join("");
                return opts ? `<optgroup label="${esc(sec)}">${opts}</optgroup>` : "";
              })
              .join("");

            return `
              <label class="skill-field">
                <span class="skill-label">${esc(slot)}<em>模块 ${esc(m.id || "")} · ${total} 条</em></span>
                <select data-nt-slot="${esc(slot)}">
                  <option value="">（不填 · 由模型自选）</option>
                  ${groups}
                </select>
              </label>`;
          })
          .join("");
      }
      // 选读槽 → 勾选框 + 可选词条下拉（勾了才生效）
      const optHost = $("nt-optional");
      if (optHost) {
        optHost.innerHTML = (meta.optional_slots || [])
          .map((slot) => {
            const m = ntModules.find((x) => x.slot === slot) || {};
            const info = termsMap[slot] || {};
            const sections = info.sections || {};
            const total = info.total || 0;

            const groups = Object.keys(sections)
              .map((sec) => {
                const opts = (sections[sec] || [])
                  .map((t) => `<option value="${esc(t)}">${esc(t)}</option>`)
                  .join("");
                return opts ? `<optgroup label="${esc(sec)}">${opts}</optgroup>` : "";
              })
              .join("");

            return `
              <div class="skill-opt-slot">
                <label class="skill-check">
                  <input type="checkbox" value="${esc(slot)}" data-nt-opt>
                  <span>${esc(slot)}<em>${esc(m.desc || "")} · ${total} 条</em></span>
                </label>
                <select data-nt-opt-term="${esc(slot)}" disabled>
                  <option value="">（不指定 · 由模型自选）</option>
                  ${groups}
                </select>
              </div>`;
          })
          .join("");

        // 勾选后才启用下拉
        optHost.querySelectorAll("[data-nt-opt]").forEach((cb) => {
          cb.addEventListener("change", () => {
            const sel = optHost.querySelector(`[data-nt-opt-term="${cb.value}"]`);
            if (sel) {
              sel.disabled = !cb.checked;
              if (!cb.checked) sel.value = "";
            }
          });
        });
      }
      // 模块浏览下拉
      const modSel = $("nt-module");
      if (modSel) {
        modSel.innerHTML = ntModules
          .map((m) => `<option value="${esc(m.id)}">${esc(m.id)} · ${esc(m.slot)}</option>`)
          .join("");
      }
    } catch (e) {
      setStatus("nt-status", String(e.message), "error");
    }

    // 浏览模块内容
    $("nt-load-module")?.addEventListener("click", async () => {
      const id = $("nt-module")?.value || "01";
      setStatus("nt-status", "读取中…");
      try {
        const r = await apiGet(`/api/nsfw-templates/module?module=${encodeURIComponent(id)}&max_chars=20000`);
        const host = $("nt-module-view");
        if (host) {
          host.innerHTML = `
            <div class="skill-card">
              <div class="skill-card-head">
                <span class="skill-card-idx">${esc(r.module)} · ${esc(r.slot)}</span>
                <span class="skill-tag">${r.length} 字</span>
              </div>
              <pre class="skill-module-pre">${esc(r.text)}</pre>
            </div>`;
        }
        setStatus("nt-status", "已载入", "ok");
      } catch (e) {
        setStatus("nt-status", String(e.message), "error");
      }
    });

    // 组装
    $("nt-assemble")?.addEventListener("click", async () => {
      const slots = {};
      document.querySelectorAll("[data-nt-slot]").forEach((el) => {
        const v = (el.value || "").trim();
        if (v) slots[el.getAttribute("data-nt-slot")] = v;
      });
      // 选读槽：勾选 + 选中的具体词条
      const optional = [];
      document.querySelectorAll("[data-nt-opt]:checked").forEach((cb) => {
        const slot = cb.value;
        const sel = document.querySelector(`[data-nt-opt-term="${slot}"]`);
        const term = sel ? (sel.value || "").trim() : "";
        optional.push(slot);
        if (term) slots[slot] = term;
      });

      const theme = $("nt-theme")?.value?.trim() || "";
      if (!Object.keys(slots).length && !theme) {
        setStatus("nt-status", "请至少选一个槽位词条或填主题", "warn");
        return;
      }
      const btn = $("nt-assemble");
      const orig = btn.innerHTML;
      // 模式：fast = 纯代码拼装（0.01s），llm = 走大模型润色（4-6s）
      const mode = $("nt-mode")?.value || "fast";
      btn.disabled = true;
      btn.innerHTML =
        mode === "fast"
          ? '<i class="fa-solid fa-bolt"></i> 拼装中…'
          : '<i class="fa-solid fa-spinner fa-spin"></i> 组装中…';
      setStatus("nt-status", mode === "fast" ? "极速拼装中…" : "组装中…");
      try {
        const r = await apiPost("/api/nsfw-templates/assemble", {
          theme,
          slots,
          optional,
          count: Number($("nt-count")?.value || 1),
          mode,
          ...collectPersona("nt"),
          extra_style: $("nt-style")?.value || "",
          shot: $("nt-shot")?.value || "",
        });
        renderCards("nt-output", r.items || [], { tone: "模板", person: "NSFW模板", theme: "模板" });
        const label = r.mode === "fast" ? "极速拼装" : "LLM 组装";
        setStatus("nt-status", `${label} ${r.count} 条`, "ok");
      } catch (e) {
        setStatus("nt-status", String(e.message), "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    });

    // 自由扩写
    $("nt-expand")?.addEventListener("click", async () => {
      const idea = $("nt-idea")?.value?.trim();
      if (!idea) { setStatus("nt-status", "请填写想法", "warn"); return; }
      const btn = $("nt-expand");
      const orig = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 扩写中…';
      setStatus("nt-status", "扩写中…");
      try {
        const r = await apiPost("/api/nsfw-templates/expand", { idea });
        renderCards("nt-output", [{ index: 1, prompt: r.prompt }], { tone: "模板" });
        setStatus("nt-status", "已生成", "ok");
      } catch (e) {
        setStatus("nt-status", String(e.message), "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    });
  }

  // ── 导出 ──────────────────────────────────────────────────────────

  window.initGuomanPortrait = initGuomanPortrait;
  window.initMossArchitect = initMossArchitect;
  window.initNsfwTemplates = initNsfwTemplates;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initGuomanPortrait();
      initMossArchitect();
      initNsfwTemplates();
    });
  } else {
    initGuomanPortrait();
    initMossArchitect();
    initNsfwTemplates();
  }
})();
