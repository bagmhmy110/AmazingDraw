/**
 * 提示词可编辑组件：所有 skill 页面共用。
 *
 * 把只读的提示词区变成可直接编辑的 textarea 风格区块，
 * 编辑后自动同步到同一张卡片上的「生成图片」「复制」按钮。
 *
 * 用法（渲染 HTML 时）：
 *   PromptEdit.html(prompt, extraClass)
 *
 * 事件委托（页面初始化时调一次）：
 *   PromptEdit.bind(viewElement)
 */

(function () {
  "use strict";

  function esc(t) {
    const d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }

  /**
   * 渲染可编辑提示词块。
   * 用 contenteditable 而不是 textarea —— 高度能自动撑开，长提示词不用滚动。
   */
  function html(prompt, extraClass) {
    const cls = "skill-prompt is-editable" + (extraClass ? " " + extraClass : "");
    return (
      `<div class="${cls}" contenteditable="true" spellcheck="false"` +
      ` data-prompt-editable="1">${esc(prompt)}</div>`
    );
  }

  /** 取某个卡片容器里当前的提示词文本（已编辑的话取编辑后的）。 */
  function read(cardEl) {
    if (!cardEl) return "";
    const box = cardEl.querySelector("[data-prompt-editable]");
    if (!box) return "";
    // contenteditable 会产生 <div>/<br>，用 innerText 拿纯文本更稳
    return (box.innerText || box.textContent || "").trim();
  }

  /** 把编辑后的文本同步到同卡片里的按钮属性。 */
  function syncButtons(cardEl) {
    if (!cardEl) return;
    const text = read(cardEl);
    if (!text) return;
    cardEl.querySelectorAll("[data-render]").forEach((b) => {
      b.setAttribute("data-render", text);
    });
    cardEl.querySelectorAll("[data-copy]").forEach((b) => {
      b.setAttribute("data-copy", text);
    });
  }

  /** 事件委托：输入时实时同步按钮，粘贴时去掉富文本格式。 */
  function bind(root) {
    if (!root) return;

    // 输入/失焦都同步一次
    const onEdit = (e) => {
      const box = e.target.closest("[data-prompt-editable]");
      if (!box) return;
      syncButtons(box.closest(".skill-card") || box.closest(".guoman-card") || box.parentElement);
    };
    root.addEventListener("input", onEdit);
    root.addEventListener("blur", onEdit, true);

    // 粘贴时只保留纯文本，避免带进样式
    root.addEventListener("paste", (e) => {
      const box = e.target.closest("[data-prompt-editable]");
      if (!box) return;
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, text);
    });

    // Ctrl+Enter 直接出图
    root.addEventListener("keydown", (e) => {
      const box = e.target.closest("[data-prompt-editable]");
      if (!box) return;
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        syncButtons(box.closest(".skill-card") || box.closest(".guoman-card") || box.parentElement);
        const btn = box
          .closest(".skill-card")
          ?.querySelector("[data-render]");
        if (btn) btn.click();
      }
    });
  }

  window.PromptEdit = { html, read, syncButtons, bind };
})();
