/**
 * 国漫 · 服装装配与仙侠立绘（guoman-costume-xianxia-prompts skill 的 WebUI 前端）
 *
 * 线 C（立绘成稿）/ 线 D（服装装配）/ 批量生产，三条线共用一套参数面板。
 */

(function () {
  "use strict";

  const API = "/api/guoman";
  const STICKY_CARD_KEY = "guoman_active_card";
  const state = {
    meta: null,
    mode: "portrait",
    busy: false,
    results: [],       // 当前输出区内容
    // 当前国漫会话绑定的卡片 id：出图复用它，避免每点一次就新建一张卡
    cardId: null,
  };

  /** 读取上次绑定的卡片（跨刷新保留）。 */
  function loadStickyCard() {
    try {
      state.cardId = localStorage.getItem(STICKY_CARD_KEY) || null;
    } catch (_) {
      state.cardId = null;
    }
  }

  /** 绑定/解绑卡片。 */
  function setStickyCard(cardId) {
    state.cardId = cardId || null;
    try {
      if (cardId) localStorage.setItem(STICKY_CARD_KEY, cardId);
      else localStorage.removeItem(STICKY_CARD_KEY);
    } catch (_) {}
    renderCardBadge();
  }

  /** 在参数区顶部显示「当前绑定卡片」，带「新建」按钮。 */
  function renderCardBadge() {
    const host = $("guoman-card-badge");
    if (!host) return;
    const cid = state.cardId;
    if (!cid) {
      host.innerHTML = `<span class="guoman-badge-hint">出图时会新建一张卡片</span>`;
      host.classList.remove("has-card");
      return;
    }
    const short = cid.length > 24 ? cid.slice(0, 12) + "…" + cid.slice(-6) : cid;
    host.innerHTML = `
      <span class="guoman-badge-label"><i class="fa-solid fa-link"></i> 出图写入</span>
      <code class="guoman-badge-id" title="${esc(cid)}">${esc(short)}</code>
      <button type="button" class="guoman-mini-btn" id="guoman-card-unbind" title="解绑，下次出图新建卡片">
        <i class="fa-solid fa-link-slash"></i> 解绑
      </button>
    `;
    host.classList.add("has-card");
    $("guoman-card-unbind")?.addEventListener("click", () => {
      setStickyCard(null);
      setStatus("已解绑，下次出图会新建卡片", "warn");
    });
  }

  const $ = (id) => document.getElementById(id);

  // ── 工具 ──────────────────────────────────────────────────────────────

  function setStatus(text, kind) {
    const el = $("guoman-status");
    if (!el) return;
    el.textContent = text || "";
    el.className = "guoman-status" + (kind ? ` ${kind}` : "");
  }

  async function apiGet(path) {
    const res = await fetch(API + path, { headers: { Accept: "application/json" } });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`${res.status} ${body.slice(0, 200)}`);
    }
    return res.json();
  }

  async function apiPost(path, payload) {
    const res = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      let detail = body;
      try {
        const parsed = JSON.parse(body);
        detail = parsed.detail || body;
      } catch (_) {}
      throw new Error(`${res.status} ${String(detail).slice(0, 300)}`);
    }
    return res.json();
  }

  function esc(text) {
    const d = document.createElement("div");
    d.textContent = text == null ? "" : String(text);
    return d.innerHTML;
  }

  // ── 元数据加载 ────────────────────────────────────────────────────────

  async function loadMeta() {
    const badge = $("guoman-skill-badge");
    try {
      const meta = await apiGet("/meta");
      state.meta = meta;
      if (badge) {
        badge.textContent = meta.available ? "skill 就绪" : "skill 未安装";
        badge.className = "guoman-skill-badge" + (meta.available ? " ok" : " warn");
      }
      if (!meta.available) {
        setStatus("未找到 guoman skill，请安装到 ~/.dsh/skills/", "warn");
        return;
      }
      window.PromptEdit?.bind($("view-guoman"));
      fillToneOptions(meta);
      fillSceneOptions(meta);
      fillExposureOptions(meta);
      fillShotOptions(meta);
      updateToneHint();
      fillPoseOptions();
      await loadSlotOptions();
    } catch (err) {
      if (badge) {
        badge.textContent = "探测失败";
        badge.className = "guoman-skill-badge warn";
      }
      setStatus(String(err.message || err), "error");
    }
  }

  function fillToneOptions(meta) {
    const sel = $("guoman-tone");
    if (!sel) return;
    const tones = meta.tones || [];
    sel.innerHTML =
      '<option value="__random__">🎲 随机</option>' +
      tones.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
  }

  function fillSceneOptions(meta) {
    const sel = $("guoman-scene");
    if (!sel) return;
    const scenes = meta.scenes || [];
    sel.innerHTML =
      '<option value="__random__">🎲 随机</option>' +
      scenes.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
  }

  function updateToneHint() {
    const hint = $("guoman-tone-hint");
    const sel = $("guoman-tone");
    if (!hint || !sel || !state.meta) return;
    const val = sel.value;
    if (val === "__random__") {
      const tones = state.meta.tones || [];
      hint.textContent = `从 ${tones.length} 个调性里随机：${tones.join(" / ")}`;
      return;
    }
    const desc = (state.meta.tone_desc || {})[val] || "";
    hint.textContent = desc;
  }

  /** 裸露档位下拉。 */
  function fillExposureOptions(meta) {
    const sel = $("guoman-exposure");
    if (!sel) return;
    const list = meta.exposures || [];
    const prev = sel.value || "none";
    sel.innerHTML = list
      .map((e) => `<option value="${esc(e.value)}">${esc(e.label)}</option>`)
      .join("");
    sel.value = list.some((e) => e.value === prev) ? prev : "none";
    updateExposureHint();
  }

  /** 机位构图（复用 MOSS 那套） */
  function fillShotOptions(meta) {
    const sel = $("guoman-shot");
    if (!sel) return;
    const list = meta.shots || [];
    const prev = sel.value || "";
    sel.innerHTML = list
      .map((s) => `<option value="${esc(s.value)}">${esc(s.label)}</option>`)
      .join("");
    sel.value = list.some((s) => s.value === prev) ? prev : "";
  }

  function updateExposureHint() {
    const hint = $("guoman-exposure-hint");
    const sel = $("guoman-exposure");
    if (!hint || !sel || !state.meta) return;
    const item = (state.meta.exposures || []).find((e) => e.value === sel.value);
    hint.textContent = item ? item.desc : "";
  }

  /** 姿势下拉：跟随当前调性，带「随机」与「动作/构图」标记。 */
  function fillPoseOptions() {
    const sel = $("guoman-pose");
    if (!sel || !state.meta) return;
    const tone = $("guoman-tone")?.value || "仙侠";
    const allPoses = state.meta.poses || {};

    // 调性为「随机」时，把所有调性的姿势合并去重（否则查不到池子只剩 1 条）
    let pool = [];
    if (tone === "__random__" || !allPoses[tone]) {
      const seen = new Set();
      for (const list of Object.values(allPoses)) {
        for (const p of list || []) {
          if (!seen.has(p)) { seen.add(p); pool.push(p); }
        }
      }
    } else {
      pool = allPoses[tone] || [];
    }

    const prev = sel.value;
    const opts = ['<option value="">🎲 随机</option>'];
    for (const p of pool) {
      // 动作姿态带具体动词，构图姿态是「以…姿态…画面」
      const isAction = !/^以.*占据画面|^以.*立于画面|^以.*压近画面|^以.*贯穿画面/.test(p);
      const tag = isAction ? "动作" : "构图";
      opts.push(`<option value="${esc(p)}">[${tag}] ${esc(p)}</option>`);
    }
    sel.innerHTML = opts.join("");
    sel.value = pool.includes(prev) ? prev : "";
  }

  async function loadSlotOptions() {
    const toneSel = $("guoman-tone");
    let tone = toneSel?.value || "仙侠";
    // 随机调性时，用第一个调性的词库填充下拉（仅作候选，实际生成仍随机）
    if (tone === "__random__") {
      tone = (state.meta?.tones || ["仙侠"])[0];
    }
    try {
      const data = await apiGet(`/combos?tone=${encodeURIComponent(tone)}`);
      const slots = data.slots || {};
      const map = {
        color: "配色",
        fabric: "材质",
        pattern: "纹样",
        sleeve: "袖型",
        skirt: "裙装结构",
        waist: "腰部",
        shoulder: "肩部",
      };
      for (const [key, slotName] of Object.entries(map)) {
        const sel = document.querySelector(`[data-slot="${key}"]`);
        if (!sel) continue;
        const opts = slots[slotName] || [];
        sel.innerHTML =
          '<option value="">随机</option>' +
          opts.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
      }
    } catch (_) {
      // 词库拉取失败不阻断生成（脚本侧仍会随机）
    }
  }

  // ── 模式切换 ──────────────────────────────────────────────────────────



  // ── 生成 ──────────────────────────────────────────────────────────────

  /** 收集已锁定的服装槽位（留「随机」的不带上）。 */
  function collectSlots() {
    const slots = {};
    document.querySelectorAll("[data-slot]").forEach((sel) => {
      const v = sel.value;
      if (v) slots[sel.getAttribute("data-slot")] = v;
    });
    return slots;
  }

  /** 更新折叠标题上的「已锁 N 槽」角标。 */
  function updateSlotCount() {
    const el = $("guoman-slot-count");
    if (!el) return;
    const n = Object.keys(collectSlots()).length;
    el.textContent = n ? `已锁 ${n} 槽` : "";
    el.classList.toggle("active", n > 0);
  }

  function collectPortraitPayload() {
    const payload = {
      tone: $("guoman-tone")?.value || "仙侠",
      scene: $("guoman-scene")?.value || "",
      leg: $("guoman-leg")?.value || "mild",
      pick: true,
    };
    const pose = $("guoman-pose")?.value?.trim();
    if (pose) payload.pose = pose;
    const exposure = $("guoman-exposure")?.value?.trim();
    if (exposure && exposure !== "none") payload.exposure = exposure;
    const shot = $("guoman-shot")?.value?.trim();
    if (shot) payload.shot = shot;
    // 服装槽位并入立绘：锁定后该槽不再随机
    const slots = collectSlots();
    if (Object.keys(slots).length) payload.slots = slots;
    // 不传种子 —— 后端每次自动换新
    return payload;
  }

  function collectBatchPayload() {
    const n = Number($("guoman-batch-n")?.value || 20);
    const payload = {
      n,
      tones: $("guoman-batch-tones")?.value?.trim() || "仙侠,宫廷,战斗,暗黑,新中式",
      scenes: $("guoman-batch-scenes")?.value?.trim() || "庭院,云海,樱林,废墟,暗室,亭台,雪山,夜市,宫殿,竹林",
      leg: $("guoman-leg")?.value === "bold" ? "bold" : "mild",
      seed: "random",
    };
    // 裸露范围与姿势在批量模式同样生效
    const exposure = $("guoman-exposure")?.value?.trim();
    if (exposure) payload.exposure = exposure;
    const shotB = $("guoman-shot")?.value?.trim();
    if (shotB) payload.shot = shotB;
    const pose = $("guoman-pose")?.value?.trim();
    if (pose) payload.pose = pose;
    // 锁定的服装槽位在批量里同样生效
    const slotsB = collectSlots();
    if (Object.keys(slotsB).length) payload.slots = slotsB;
    return payload;
  }

  function renderSingle(result, kind) {
    const out = $("guoman-output");
    if (!out) return;
    const prompt = result.prompt || "";
    const breakdown = result.breakdown || "";
    const label = "立绘提示词";
    // 记住这条提示词实际用的调性/场景，投递时带上，避免用当前下拉框的值
    const usedTone = result.tone || "";
    const usedScene = result.scene || "";
    state.results = [{ prompt, breakdown, kind, tone: usedTone, scene: usedScene }];

    out.innerHTML = `
      <div class="guoman-card">
        <div class="guoman-card-head">
          <span class="guoman-card-title"><i class="fa-solid fa-quote-left"></i> ${esc(label)}</span>
          <span class="guoman-card-meta">${prompt.length} 字</span>
          <button class="guoman-mini-btn primary" data-render="${esc(prompt)}" data-tone="${esc(usedTone)}" data-scene="${esc(usedScene)}">
            <i class="fa-solid fa-bolt"></i> 生成图片
          </button>
          <button class="guoman-mini-btn" data-copy="${esc(prompt)}">
            <i class="fa-regular fa-copy"></i> 复制
          </button>
        </div>
        ${window.PromptEdit.html(prompt)}
      </div>
      ${
        breakdown
          ? `<details class="guoman-breakdown">
               <summary><i class="fa-solid fa-list-check"></i> 选中元素拆解</summary>
               <pre>${esc(breakdown)}</pre>
             </details>`
          : ""
      }
    `;
  }

  function renderBatch(result) {
    const out = $("guoman-output");
    if (!out) return;
    const items = result.items || [];
    state.results = items.map((it) => ({ prompt: it.prompt, kind: "batch" }));

    out.innerHTML = `
      <div class="guoman-card">
        <div class="guoman-card-head">
          <span class="guoman-card-title"><i class="fa-solid fa-layer-group"></i> 批量结果 · ${items.length} 条</span>
          <button class="guoman-mini-btn" id="guoman-copy-all">
            <i class="fa-regular fa-copy"></i> 复制全部
          </button>
        </div>
        <ol class="guoman-batch-list">
          ${items
            .map(
              (it) => `
            <li class="guoman-batch-item">
              <div class="guoman-batch-head">
                <span class="guoman-batch-idx">#${it.index}</span>
                ${it.tone ? `<span class="guoman-tag">${esc(it.tone)}</span>` : ""}
                ${it.scene ? `<span class="guoman-tag ghost">${esc(it.scene)}</span>` : ""}
                <button class="guoman-mini-btn primary" data-render="${esc(it.prompt)}" data-tone="${esc(it.tone || "")}" data-scene="${esc(it.scene || "")}">
                  <i class="fa-solid fa-bolt"></i> 生成图片
                </button>
                <button class="guoman-mini-btn" data-copy="${esc(it.prompt)}"><i class="fa-regular fa-copy"></i></button>
              </div>
              ${window.PromptEdit.html(it.prompt, "compact")}
            </li>`
            )
            .join("")}
        </ol>
      </div>
    `;

    $("guoman-copy-all")?.addEventListener("click", () => {
      copyText(items.map((it) => it.prompt).join("\n\n"));
    });

    // 批量出图：一键把整批提示词投进队列
    if (items.length > 1) {
      window.BatchDraw?.attach(
        out,
        () => window.BatchDraw.promptsFromCards(out),
        { person: "国漫立绘", theme: "立绘" }
      );
    }
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      if (typeof showToast === "function") showToast("已复制", "success");
      setStatus("已复制到剪贴板", "ok");
    } catch (_) {
      if (typeof showToast === "function") showToast("复制失败", "error");
    }
  }

  /**
   * 从提示词正文反推场景 / 调性。
   * 提示词里已经写死了真实场景（如「场景落在青石铺地的道观前庭」），
   * 比当前下拉框的值可靠 —— 下拉框可能已被用户改动过。
   */
  function inferFromPrompt(text) {
    const out = { tone: "", scene: "" };
    const toneMatch = /^一位东方(.+?)风格的/.exec(text);
    if (toneMatch) out.tone = toneMatch[1];
    // 两种句式：「场景落在X，」「背景为X，」
    const sceneMatch = /(?:场景落在|背景为)([^，。]+)/.exec(text);
    if (sceneMatch) {
      let s = sceneMatch[1].trim();
      // 去掉形容词前缀（如梦似幻的 / 香火未绝的 …），取最后一个「的」之后
      const idx = s.lastIndexOf("的");
      if (idx > 0 && idx < s.length - 1) s = s.slice(idx + 1);
      out.scene = s;
    }
    return out;
  }

  /** 把某条现成提示词直接投递出图（卡片 / 批量行上的「生成图片」按钮）。 */
  async function doRenderPrompt(prompt, tone, scene, btnEl) {
    const text = (prompt || "").trim();
    if (!text) {
      setStatus("提示词为空", "warn");
      return;
    }
    if (state.busy) return;
    state.busy = true;

    // 优先级：按钮携带的元数据 > 从正文反推 > 当前下拉框
    const inferred = inferFromPrompt(text);
    const finalTone = (tone && tone.trim()) || inferred.tone || $("guoman-tone")?.value || "仙侠";
    let finalScene = (scene && scene.trim()) || inferred.scene || $("guoman-scene")?.value || "";
    if (finalScene === "__random__") finalScene = inferred.scene || "";

    const original = btnEl ? btnEl.innerHTML : "";
    if (btnEl) {
      btnEl.disabled = true;
      btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }
    setStatus("投递中…");

    try {
      const payload = {
        prompt: text,
        tone: finalTone,
        scene: finalScene,
      };
      // 复用当前绑定的卡片，避免列表里多出一条
      if (state.cardId) payload.card_id = state.cardId;

      const r = await apiPost("/direct", payload);
      if (r.card_id) setStickyCard(r.card_id);
      setStatus(`已投递 · job ${String(r.job_id || "").slice(0, 12)}`, "ok");
      if (typeof showToast === "function") showToast("已提交到出图队列", "success");
      if (btnEl) {
        btnEl.innerHTML = '<i class="fa-solid fa-check"></i> 已投递';
      }
      if (typeof refreshCards === "function") {
        setTimeout(() => refreshCards().catch(() => {}), 1500);
      }
      // 出图后刷新一次卡片列表（约 30s 后）
      setTimeout(() => {
        if (typeof refreshCards === "function") refreshCards().catch(() => {});
      }, 35000);
    } catch (err) {
      setStatus(String(err.message || err), "error");
      if (typeof showToast === "function") showToast("投递失败：" + String(err.message || err).slice(0, 80), "error");
      if (btnEl) btnEl.innerHTML = original;
    } finally {
      state.busy = false;
      if (btnEl) btnEl.disabled = false;
    }
  }

  /** 生成：条数 = 1 走单次，> 1 走批量（共用同一组槽位选项）。 */
  async function doGenerate() {
    if (state.busy) return;
    const n = Math.max(1, Number($("guoman-count")?.value || 1));
    state.busy = true;
    const btn = $("guoman-generate");
    const original = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 生成中…';
    }
    setStatus(`生成中（${n} 条）…`);

    try {
      if (n > 1) {
        // 批量：调性/场景池从当前下拉取，其余选项照旧
        // __random__ 是前端哨兵值，批量端点不认，这里先展开成具体值
        const TONES = ["仙侠", "宫廷", "战斗", "暗黑", "新中式"];
        let tone = $("guoman-tone")?.value || "仙侠";
        if (tone === "__random__") {
          tone = TONES[Math.floor(Math.random() * TONES.length)];
        }
        let scene = $("guoman-scene")?.value || "";
        if (scene === "__random__") {
          const pool = (state.meta && state.meta.scenes) || [];
          scene = pool.length ? pool[Math.floor(Math.random() * pool.length)] : "";
        }
        const payload = {
          n,
          seed: "random",
          tones: tone,
          scenes: scene,
          leg: $("guoman-leg")?.value || "mild",
        };
        const exposure = $("guoman-exposure")?.value?.trim();
        if (exposure && exposure !== "none") payload.exposure = exposure;
        const shot = $("guoman-shot")?.value?.trim();
        if (shot) payload.shot = shot;
        const pose = $("guoman-pose")?.value?.trim();
        if (pose) payload.pose = pose;
        const slots = collectSlots();
        if (Object.keys(slots).length) payload.slots = slots;

        const r = await apiPost("/batch", payload);
        renderBatch(r);
        setStatus(`已生成 ${r.count} 条`, "ok");
      } else {
        const r = await apiPost("/portrait", collectPortraitPayload());
        renderSingle(r, "portrait");
        setStatus("已生成立绘提示词", "ok");
      }
    } catch (err) {
      setStatus(String(err.message || err), "error");
      if (typeof showToast === "function") showToast("生成失败：" + String(err.message || err).slice(0, 80), "error");
    } finally {
      state.busy = false;
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = original;
      }
    }
  }


  async function doGenerateDirect() {
    if (state.busy) return;
    state.busy = true;
    const btn = $("guoman-generate-direct");
    const original = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 投递中…';
    }
    setStatus("生成并投递…");

    try {
      // 先只生成提示词，拿到服务端实际抽到的 tone/scene
      const gen = await apiPost("/portrait", collectPortraitPayload());
      const prompt = gen.prompt || "";
      if (!prompt) throw new Error("生成结果为空");

      // 用生成结果里的真实 tone/scene 投递，避免服务端二次抽签导致元数据错位
      const payload = {
        prompt,
        tone: gen.tone || "",
        scene: gen.scene || "",
      };
      // 复用当前绑定的卡片，避免列表里多出一条
      if (state.cardId) payload.card_id = state.cardId;

      const r = await apiPost("/direct", payload);
      if (r.card_id) setStickyCard(r.card_id);
      renderSingle({ prompt, breakdown: gen.breakdown, tone: gen.tone, scene: gen.scene }, "portrait");
      setStatus(`已投递 · job ${String(r.job_id || "").slice(0, 12)}`, "ok");
      if (typeof showToast === "function") showToast("已提交到出图队列", "success");
      if (typeof refreshCards === "function") {
        setTimeout(() => refreshCards().catch(() => {}), 1500);
      }
    } catch (err) {
      setStatus(String(err.message || err), "error");
      if (typeof showToast === "function") showToast("投递失败：" + String(err.message || err).slice(0, 80), "error");
    } finally {
      state.busy = false;
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = original;
      }
    }
  }

  function doExport() {
    const rows = state.results.map((r) => r.prompt).filter(Boolean);
    if (!rows.length) {
      setStatus("没有可导出的内容", "warn");
      return;
    }
    const blob = new Blob([rows.join("\n\n")], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `guoman-prompts-${Date.now()}.txt`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 3000);
    setStatus(`已导出 ${rows.length} 条`, "ok");
  }

  // ── 初始化 ────────────────────────────────────────────────────────────

  let initialized = false;

  function initGuoman() {
    if (initialized) return;
    const view = $("view-guoman");
    if (!view) return;
    initialized = true;

    // 模式切换已移除 —— 立绘与批量共用同一套选项

    $("guoman-tone")?.addEventListener("change", async () => {
      updateToneHint();
      fillPoseOptions();       // 姿势池跟随调性
      await loadSlotOptions();
    });

    $("guoman-exposure")?.addEventListener("change", updateExposureHint);

    $("guoman-generate")?.addEventListener("click", doGenerate);
    $("guoman-generate-direct")?.addEventListener("click", doGenerateDirect);
    $("guoman-export")?.addEventListener("click", doExport);

    // 服装槽位：任意一个变化都刷新「已锁 N 槽」角标
    document.querySelectorAll("[data-slot]").forEach((sel) => {
      sel.addEventListener("change", updateSlotCount);
    });

    // 一键清空所有槽位
    $("guoman-slot-clear")?.addEventListener("click", () => {
      document.querySelectorAll("[data-slot]").forEach((sel) => {
        sel.value = "";
      });
      updateSlotCount();
      setStatus("已清空服装槽位", "ok");
    });

    // 卡片上的按钮（复制 / 生成图片）统一事件委托
    view.addEventListener("click", (e) => {
      const copyBtn = e.target.closest("[data-copy]");
      if (copyBtn) {
        copyText(copyBtn.getAttribute("data-copy") || "");
        return;
      }
      const renderBtn = e.target.closest("[data-render]");
      if (renderBtn) {
        doRenderPrompt(
          renderBtn.getAttribute("data-render"),
          renderBtn.getAttribute("data-tone"),
          renderBtn.getAttribute("data-scene"),
          renderBtn
        );
      }
    });

    loadStickyCard();
    renderCardBadge();
    loadMeta();
  }

  window.initGuoman = initGuoman;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initGuoman);
  } else {
    initGuoman();
  }
})();
