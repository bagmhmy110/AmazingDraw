/**
 * 批量出图：把批量生成的提示词一次性投进渲染队列。
 *
 * 各 skill 的「批量生成」只产出提示词文本，逐条点「生成图片」太慢。
 * 这个模块给结果区加一个「批量出图」按钮，一键全部投递。
 *
 * 用法：
 *   BatchDraw.attach(hostEl, getPrompts, opts)
 *
 *   getPrompts : () => string[]        取当前批量结果里的提示词
 *   opts       : { person, scene, tone, theme, label }
 */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  function esc(t) {
    const d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }

  /** 在结果区顶部插入「批量出图」按钮条。重复调用会替换旧的。 */
  function attach(hostEl, getPrompts, opts) {
    if (!hostEl) return;
    const o = opts || {};

    // 去掉旧的按钮条
    hostEl.querySelectorAll("[data-batchdraw-bar]").forEach((el) => el.remove());

    const bar = document.createElement("div");
    bar.className = "batchdraw-bar";
    bar.setAttribute("data-batchdraw-bar", "1");
    bar.innerHTML = `
      <span class="batchdraw-count">共 <b data-batchdraw-n>0</b> 条</span>
      <label class="batchdraw-limit">
        出图上限
        <input type="number" min="1" max="60" value="10" data-batchdraw-limit>
      </label>
      <button class="skill-mini-btn primary" data-batchdraw-go>
        <i class="fa-solid fa-images"></i> 批量出图
      </button>
      <span class="batchdraw-status" data-batchdraw-status></span>
    `;
    hostEl.insertBefore(bar, hostEl.firstChild);

    const nEl = bar.querySelector("[data-batchdraw-n]");
    const limitEl = bar.querySelector("[data-batchdraw-limit]");
    const goBtn = bar.querySelector("[data-batchdraw-go]");
    const statusEl = bar.querySelector("[data-batchdraw-status]");

    const refreshCount = () => {
      const list = (getPrompts && getPrompts()) || [];
      if (nEl) nEl.textContent = String(list.length);
      if (limitEl && list.length && Number(limitEl.value) > list.length) {
        limitEl.value = String(Math.min(list.length, 60));
      }
    };
    refreshCount();

    goBtn?.addEventListener("click", async () => {
      const prompts = (getPrompts && getPrompts()) || [];
      if (!prompts.length) {
        if (statusEl) statusEl.textContent = "没有可投递的提示词";
        return;
      }
      const limit = Math.max(1, Math.min(Number(limitEl?.value || 10), 60));

      goBtn.disabled = true;
      const old = goBtn.innerHTML;
      goBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 投递中…';
      if (statusEl) statusEl.textContent = `正在投递 ${Math.min(limit, prompts.length)} 条…`;

      try {
        const res = await fetch("/api/batch-draw", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompts,
            limit,
            person: o.person || "",
            scene: o.scene || "",
            tone: o.tone || "",
            theme: o.theme || "",
            skip_dupes: true,
          }),
        });
        const txt = await res.text();
        let data = {};
        try {
          data = JSON.parse(txt);
        } catch (e) {
          throw new Error(txt.slice(0, 160) || `HTTP ${res.status}`);
        }
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

        const okN = data.submitted || 0;
        const failN = data.failed || 0;
        if (statusEl) {
          statusEl.className = "batchdraw-status " + (failN ? "warn" : "ok");
          statusEl.textContent = failN
            ? `已投递 ${okN} 条，${failN} 条失败`
            : `已投递 ${okN} 条，去队列看进度`;
        }
        if (typeof window.refreshQueue === "function") {
          try { window.refreshQueue(); } catch (e) {}
        }
        if (typeof window.showToast === "function") {
          window.showToast(
            failN ? `投递 ${okN} 条，失败 ${failN} 条` : `已投递 ${okN} 条`,
            failN ? "warn" : "success"
          );
        }
      } catch (err) {
        if (statusEl) {
          statusEl.className = "batchdraw-status warn";
          statusEl.textContent = String(err.message || err).slice(0, 120);
        }
      } finally {
        goBtn.disabled = false;
        goBtn.innerHTML = old;
      }
    });
  }

  /** 从一组卡片 DOM 里收集（可能被用户编辑过的）提示词。 */
  function promptsFromCards(hostEl) {
    if (!hostEl) return [];
    return Array.from(hostEl.querySelectorAll("[data-prompt-editable]"))
      .map((el) => (el.innerText || el.textContent || "").trim())
      .filter(Boolean);
  }

  window.BatchDraw = { attach, promptsFromCards };
})();
