/* albums.js — 成品库网格与专辑 */

function initAlbum() {
  // 多选工具条（勾选多张后批量删除）
  initAlbumSelection();
  const createBtn = document.getElementById("btn-album-create");
  const confirmBtn = document.getElementById("btn-album-create-confirm");
  const cancelBtn = document.getElementById("btn-album-create-cancel");
  const closeBtn = document.getElementById("btn-close-album-create");
  const modal = document.getElementById("album-create-modal");
  const nameInput = document.getElementById("album-new-name");
  const timeSel = document.getElementById("album-time-filter");

  createBtn?.addEventListener("click", () => openAlbumCreateModal());
  confirmBtn?.addEventListener("click", () => createAlbumFromInput());
  cancelBtn?.addEventListener("click", () => closeAlbumCreateModal());
  closeBtn?.addEventListener("click", () => closeAlbumCreateModal());
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) closeAlbumCreateModal();
  });
  nameInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      createAlbumFromInput();
    }
    if (e.key === "Escape") {
      e.preventDefault();
      closeAlbumCreateModal();
    }
  });
  const reload = () => {
    state.albumLimit = 100;
    loadAlbumPool();
  };
  timeSel?.addEventListener("change", () => {
    state.albumTimeFilter = timeSel.value || "all";
    reload();
  });
}

function openAlbumCreateModal() {
  const modal = document.getElementById("album-create-modal");
  const input = document.getElementById("album-new-name");
  if (!modal) return;
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  if (input) {
    input.value = "";
    setTimeout(() => input.focus(), 40);
  }
}

function closeAlbumCreateModal() {
  const modal = document.getElementById("album-create-modal");
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
}

async function createAlbumFromInput() {
  const input = document.getElementById("album-new-name");
  const name = String(input && input.value || "").trim();
  if (!name) {
    showToast("请先填写专辑名", "warning");
    input?.focus();
    return;
  }
  try {
    const res = await fetch("/api/albums", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "新建失败");
    if (input) input.value = "";
    closeAlbumCreateModal();
    state.albumFilter = data.album && data.album.id;
    state.albumPersonFilter = "";
    await refreshAlbumWorkspace();
    showToast("已新建专辑", "success");
  } catch (err) {
    showToast(`新建专辑失败：${err.message || err}`, "error");
  }
}

async function refreshAlbumWorkspace() {
  await loadAlbumIndex();
  await loadAlbumPool();
}

async function loadAlbumIndex() {
  const res = await fetch("/api/albums");
  if (!res.ok) throw new Error("专辑列表加载失败");
  const data = await res.json();
  state.albums = data.albums || [];
  state.albumVirtual = data.virtual || {};
  state.albumGroups = data.groups || { persons: [] };
  renderAlbumSidebar();
}

async function loadAlbumPool() {
  const params = new URLSearchParams();
  params.set("album_id", state.albumFilter || "all");
  params.set("month", state.albumTimeFilter || "all");
  if (state.albumPersonFilter) params.set("person", state.albumPersonFilter);
  if (state.albumSceneFilter) params.set("scene", state.albumSceneFilter);
  const res = await fetch(`/api/albums/pool?${params.toString()}`);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "成片池加载失败");
  }
  const data = await res.json();
  state.albumPool = data.items || [];
  state.albumPoolTotal = Number(data.total) || state.albumPool.length;
  renderAlbumFacets(data.facets || {});
  renderAlbumGrid();
}

function renderAlbumFacets(facets) {
  const monthSel = document.getElementById("album-time-filter");
  if (monthSel) {
    const current = state.albumTimeFilter || "all";
    monthSel.innerHTML = "";
    const all = document.createElement("option");
    all.value = "all";
    all.textContent = "全部月份";
    monthSel.appendChild(all);
    (facets.months || []).forEach((month) => {
      const opt = document.createElement("option");
      opt.value = month;
      const [year, mon] = String(month).split("-");
      opt.textContent = `${year} 年 ${Number(mon)} 月`;
      monthSel.appendChild(opt);
    });
    monthSel.value = current;
    if (monthSel.value !== current) monthSel.value = "all";
  }
}

function selectAlbumBucket({ albumId, person }) {
  state.albumFilter = albumId || "all";
  state.albumPersonFilter = person || "";
  state.albumLimit = 100;
  renderAlbumSidebar();
  loadAlbumPool().catch((err) => showToast(err.message || err, "error"));
}

function albumBucketActive(kind, value) {
  const albumId = state.albumFilter || "all";
  const person = state.albumPersonFilter || "";
  if (kind === "album") return !person && albumId === value;
  if (kind === "person") return albumId === "all" && person === value;
  return false;
}

function renderAlbumNavEmpty(list, text) {
  const empty = document.createElement("p");
  empty.className = "placeholder-text";
  empty.textContent = text;
  list.appendChild(empty);
}

function renderAlbumSidebar() {
  const list = document.getElementById("album-sidebar-list");
  const personList = document.getElementById("album-person-list");
  if (!list) return;
  const virtual = state.albumVirtual || {};
  const albums = state.albums || [];
  const systemRows = albums
    .filter((album) => album.system || album.id === "favorites")
    .map((album) => ({
      id: album.id,
      name: album.name,
      count: album.count || 0,
      virtual: false,
      system: true,
    }));
  const userRows = albums
    .filter((album) => !(album.system || album.id === "favorites"))
    .map((album) => ({
      id: album.id,
      name: album.name,
      count: album.count || 0,
      virtual: false,
      system: false,
    }));
  const rows = [
    { id: "all", name: (virtual.all && virtual.all.name) || "全部成片", count: (virtual.all && virtual.all.count) || 0, virtual: true },
    ...systemRows,
    { id: "unfiled", name: (virtual.unfiled && virtual.unfiled.name) || "未分辑", count: (virtual.unfiled && virtual.unfiled.count) || 0, virtual: true },
    ...userRows,
  ];
  list.innerHTML = "";
  rows.forEach((row) => {
    const btn = document.createElement("div");
    btn.className = `album-nav-item${row.system ? " is-system" : ""}${albumBucketActive("album", row.id) ? " active" : ""}`;
    btn.setAttribute("data-album-id", row.id);
    btn.innerHTML = `
      <i class="fa-regular ${row.system ? "fa-heart" : row.virtual ? "fa-images" : "fa-folder"}"></i>
      <span class="album-nav-name"></span>
      <span class="album-nav-count">${row.count} 条</span>
      ${row.virtual || row.system ? "" : `<span class="album-nav-tools">
        <button type="button" data-album-act="rename" title="重命名"><i class="fa-solid fa-pen"></i></button>
        <button type="button" data-album-act="delete" title="删除专辑"><i class="fa-solid fa-trash"></i></button>
      </span>`}
    `;
    btn.querySelector(".album-nav-name").textContent = row.name;
    btn.addEventListener("click", (e) => {
      if (e.target.closest("[data-album-act]")) return;
      selectAlbumBucket({ albumId: row.id });
    });
    if (!row.virtual) {
      btn.addEventListener("dragover", (e) => {
        e.preventDefault();
        btn.classList.add("album-drop-target");
      });
      btn.addEventListener("dragleave", () => btn.classList.remove("album-drop-target"));
      btn.addEventListener("drop", async (e) => {
        e.preventDefault();
        btn.classList.remove("album-drop-target");
        const cardId = e.dataTransfer.getData("text/plain");
        if (cardId) await addCardToAlbum(row.id, cardId);
      });
      btn.querySelector('[data-album-act="rename"]')?.addEventListener("click", (e) => {
        e.stopPropagation();
        renameAlbum(row.id, row.name);
      });
      btn.querySelector('[data-album-act="delete"]')?.addEventListener("click", (e) => {
        e.stopPropagation();
        confirmDeleteAlbum(row.id, row.name);
      });
    }
    list.appendChild(btn);
  });

  if (personList) {
    personList.innerHTML = "";
    const persons = (state.albumGroups && state.albumGroups.persons) || [];
    const minMain = Number((state.albumGroups && state.albumGroups.person_min) || 3);
    const main = persons.filter((row) => Number(row.count) >= minMain);
    const rare = persons.filter((row) => Number(row.count) < minMain);
    if (!persons.length) {
      renderAlbumNavEmpty(personList, "暂无角色标签");
    } else {
      const appendPerson = (row, nested) => {
        const btn = document.createElement("div");
        btn.className = `album-nav-item${nested ? " album-nav-nested" : ""}${albumBucketActive("person", row.name) ? " active" : ""}`;
        btn.innerHTML = `
          <i class="fa-regular fa-user"></i>
          <span class="album-nav-name"></span>
          <span class="album-nav-count">${row.count} 条</span>
        `;
        btn.querySelector(".album-nav-name").textContent = row.name;
        const aliases = Array.isArray(row.aliases) ? row.aliases.filter(Boolean) : [];
        btn.title = aliases.length ? `${row.name}（含 ${aliases.join("、")}）` : row.name;
        btn.addEventListener("click", () => selectAlbumBucket({ albumId: "all", person: row.name }));
        personList.appendChild(btn);
      };
      main.forEach((row) => appendPerson(row, false));
      if (rare.length) {
        const rareCount = rare.reduce((sum, row) => sum + Number(row.count || 0), 0);
        const fold = document.createElement("div");
        fold.className = `album-nav-item album-nav-other${albumBucketActive("person", "__other__") ? " active" : ""}`;
        fold.innerHTML = `
          <i class="fa-solid fa-ellipsis"></i>
          <span class="album-nav-name">其他</span>
          <span class="album-nav-count">${rare.length} 人 · ${rareCount} 条</span>
          <i class="fa-solid ${state.albumPersonRareOpen ? "fa-chevron-up" : "fa-chevron-down"} album-nav-caret"></i>
        `;
        fold.title = `不足 ${minMain} 条的角色收在这里`;
        fold.addEventListener("click", (e) => {
          if (e.target.closest(".album-nav-caret")) {
            e.stopPropagation();
            state.albumPersonRareOpen = !state.albumPersonRareOpen;
            renderAlbumSidebar();
            return;
          }
          state.albumPersonRareOpen = true;
          selectAlbumBucket({ albumId: "all", person: "__other__" });
        });
        personList.appendChild(fold);
        const rareOpen =
          state.albumPersonRareOpen ||
          albumBucketActive("person", "__other__") ||
          rare.some((row) => albumBucketActive("person", row.name));
        if (rareOpen) rare.forEach((row) => appendPerson(row, true));
      }
    }
  }
}

// =====================================================================
// 相册多选与批量删除
// =====================================================================

/** 切换多选模式开关。 */
function setAlbumSelectMode(on) {
  state.albumSelectMode = Boolean(on);
  if (!state.albumSelectMode) {
    state.albumSelected.clear();
  }
  const bar = document.getElementById("album-bulkbar");
  const toggle = document.getElementById("album-select-toggle");
  if (bar) bar.hidden = !state.albumSelectMode;
  if (toggle) toggle.classList.toggle("is-on", state.albumSelectMode);
  document.getElementById("view-album")?.classList.toggle("is-selecting", state.albumSelectMode);
  renderAlbumGrid();
  updateAlbumSelectionUI();
}

/** 勾选 / 取消一张卡片。 */
function toggleAlbumSelection(cardId) {
  if (!cardId) return;
  if (state.albumSelected.has(cardId)) {
    state.albumSelected.delete(cardId);
  } else {
    state.albumSelected.add(cardId);
  }
  // 只更新这一张的视觉，避免整格重绘
  const tile = document.querySelector(`#album-grid .album-tile[data-card-id="${CSS.escape(cardId)}"]`);
  if (tile) {
    const on = state.albumSelected.has(cardId);
    tile.classList.toggle("is-selected", on);
    const badge = tile.querySelector("[data-album-check]");
    if (badge) {
      badge.classList.toggle("is-on", on);
      const icon = badge.querySelector("i");
      if (icon) icon.className = on ? "fa-solid fa-square-check" : "fa-regular fa-square";
    }
  }
  updateAlbumSelectionUI();
}

/** 更新底部操作条的计数与按钮状态。 */
function updateAlbumSelectionUI() {
  const n = state.albumSelected.size;
  const countEl = document.getElementById("album-selected-count");
  if (countEl) countEl.textContent = String(n);
  const delBtn = document.getElementById("album-bulk-delete");
  if (delBtn) {
    delBtn.disabled = n === 0;
    delBtn.innerHTML = n
      ? `<i class="fa-regular fa-trash-can"></i> 删除选中 (${n})`
      : `<i class="fa-regular fa-trash-can"></i> 删除选中`;
  }
}

/** 全选当前已渲染的卡片。 */
function selectAllAlbumVisible() {
  document.querySelectorAll("#album-grid .album-tile").forEach((tile) => {
    const id = tile.dataset.cardId;
    if (id) state.albumSelected.add(id);
  });
  renderAlbumGrid();
  updateAlbumSelectionUI();
}

/** 批量删除已勾选的卡片。 */
function confirmBulkDeleteAlbumCards() {
  const ids = Array.from(state.albumSelected);
  if (!ids.length) return;

  openDangerConfirmModal({
    title: `删除 ${ids.length} 张卡片`,
    message:
      `将从相册、卡片列表和磁盘上删除这 ${ids.length} 张图片与卡片。\n` +
      `此操作不可撤销。`,
    confirmLabel: `删除 ${ids.length} 张`,
    onConfirm: async () => {
      const btn = document.getElementById("album-bulk-delete");
      const orig = btn ? btn.innerHTML : "";
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 删除中…';
      }
      try {
        const res = await fetch("/api/cards/batch-delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ card_ids: ids }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

        const okN = data.deleted || 0;
        const failN = data.failed || 0;
        state.albumSelected.clear();
        await refreshAlbumWorkspace();
        updateAlbumSelectionUI();

        if (typeof showToast === "function") {
          showToast(
            failN ? `已删除 ${okN} 张，${failN} 张失败` : `已删除 ${okN} 张`,
            failN ? "error" : "success"
          );
        }
        // 全部删完就自动退出多选
        if (!failN && state.albumSelected.size === 0) {
          setAlbumSelectMode(false);
        }
      } catch (err) {
        if (typeof showToast === "function") {
          showToast(`批量删除失败：${err.message || err}`, "error");
        }
      } finally {
        if (btn) {
          btn.disabled = state.albumSelected.size === 0;
          btn.innerHTML = orig;
          updateAlbumSelectionUI();
        }
      }
    },
  });
}

/** 绑定多选工具条的按钮（初始化时调一次）。 */
function initAlbumSelection() {
  document.getElementById("album-select-toggle")?.addEventListener("click", () => {
    setAlbumSelectMode(!state.albumSelectMode);
  });
  document.getElementById("album-select-all")?.addEventListener("click", selectAllAlbumVisible);
  document.getElementById("album-select-clear")?.addEventListener("click", () => {
    state.albumSelected.clear();
    renderAlbumGrid();
    updateAlbumSelectionUI();
  });
  document.getElementById("album-select-exit")?.addEventListener("click", () => {
    setAlbumSelectMode(false);
  });
  document.getElementById("album-bulk-delete")?.addEventListener("click", confirmBulkDeleteAlbumCards);
  updateAlbumSelectionUI();
}

function renderAlbumGrid() {
  const grid = document.getElementById("album-grid");
  const title = document.getElementById("album-header-title");
  const info = document.getElementById("album-sidebar-info");
  if (!grid) return;
  const items = state.albumPool || [];
  const limit = state.albumLimit || 100;
  const shown = items.slice(0, limit);
  const albumName = albumTitleFor(state.albumFilter);
  if (title) {
    title.innerHTML = `<i class="fa-regular fa-images"></i> ${escapeHtml(albumName)} · ${items.length} 条`;
  }
  if (info) info.textContent = `显示 ${shown.length} / ${items.length} 条`;
  grid.innerHTML = "";
  if (!shown.length) {
    const empty = document.createElement("p");
    empty.className = "placeholder-text";
    empty.textContent = "这个分组里还没有成片。把卡片拖到左侧专辑即可分类。";
    grid.appendChild(empty);
    return;
  }
  const realAlbum = (state.albums || []).some((a) => a.id === state.albumFilter);
  const favoriteIds = new Set(((state.albums || []).find((a) => a.id === "favorites") || {}).card_ids || []);
  shown.forEach((card) => {
    const tile = document.createElement("article");
    tile.className = "album-tile";
    tile.draggable = true;
    tile.dataset.cardId = card.card_id;
    // 多选模式下标记已勾选的卡片
    if (state.albumSelectMode && state.albumSelected.has(card.card_id)) {
      tile.classList.add("is-selected");
    }
    const imgSrc = card.image_url || (card.render_image ? `/images/${encodeURIComponent(card.render_image)}` : "");
    const heading = [card.person, card.scene].filter(Boolean).join(" · ") || card.card_id;
    const frame = document.createElement("div");
    frame.className = "album-tile-frame";
    const favorited = favoriteIds.has(card.card_id);
    // 多选模式下的勾选角标
    const checked = state.albumSelectMode && state.albumSelected.has(card.card_id);
    const checkBadge = state.albumSelectMode
      ? `<button type="button" class="album-tile-check ${checked ? "is-on" : ""}"
                 data-album-check title="勾选 / 取消" aria-label="勾选">
           <i class="fa-${checked ? "solid fa-square-check" : "regular fa-square"}"></i>
         </button>`
      : "";
    frame.innerHTML = `
      ${checkBadge}
      <div class="album-tile-quick">
        <button type="button" data-album-archive title="存进 Obsidian 灵感库" aria-label="存进灵感库">
          <i class="fa-regular fa-bookmark"></i>
        </button>
        <button type="button" data-album-upscale title="转高清（SeedVR2 放大）" aria-label="转高清">
          <i class="fa-solid fa-wand-magic-sparkles"></i>
        </button>
        <button type="button" data-album-fav class="${favorited ? "is-on" : ""}" title="${favorited ? "取消收藏" : "收藏"}" aria-label="${favorited ? "取消收藏" : "收藏"}">
          <i class="fa-${favorited ? "solid" : "regular"} fa-heart"></i>
        </button>
        <button type="button" data-album-del title="删除卡片" aria-label="删除卡片">
          <i class="fa-regular fa-trash-can"></i>
        </button>
      </div>
      <div class="album-tile-meta">
        <div class="album-tile-title"></div>
        <div class="album-tile-sub">${escapeHtml(card.status || "")}</div>
        <div class="album-tile-actions">
          <button type="button" data-album-open>工作台打开</button>
          ${realAlbum ? `<button type="button" data-album-remove>移出</button>` : ""}
          ${realAlbum ? `<button type="button" data-album-cover>封面</button>` : ""}
        </div>
      </div>
    `;
    frame.querySelector(".album-tile-title").textContent = heading;
    if (imgSrc) {
      const img = document.createElement("img");
      img.className = "gallery-img album-thumb loaded";
      img.alt = heading;
      img.decoding = "async";
      img.loading = "lazy";
      img.addEventListener("error", () => {
        img.classList.add("is-missing");
      });
      img.src = imgSrc;
      frame.insertBefore(img, frame.firstChild);
    } else {
      const missing = document.createElement("div");
      missing.className = "album-tile-missing";
      missing.textContent = "无图";
      frame.insertBefore(missing, frame.firstChild);
    }
    tile.appendChild(frame);
    tile.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", card.card_id);
    });
    tile.querySelector("[data-album-open]")?.addEventListener("click", () => openCardInWorkbench(card.card_id));
    tile.querySelector("[data-album-remove]")?.addEventListener("click", () => removeCardFromAlbum(state.albumFilter, card.card_id));
    tile.querySelector("[data-album-cover]")?.addEventListener("click", () => setAlbumCover(state.albumFilter, card.card_id));
    tile.querySelector("[data-album-fav]")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleFavoriteCard(card.card_id, favorited);
    });
    tile.querySelector("[data-album-del]")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      confirmDeleteAlbumCard(card);
    });
    tile.querySelector("[data-album-upscale]")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      upscaleAlbumCard(card, e.currentTarget);
    });
    // 存进 Obsidian 灵感库
    tile.querySelector("[data-album-archive]")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      archiveAlbumCard(card, e.currentTarget);
    });

    // ── 多选：勾选角标 ──
    tile.querySelector("[data-album-check]")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleAlbumSelection(card.card_id);
    });

    // ── 多选模式：点卡片任意位置就是勾选，不打开工作台、不弹大图 ──
    if (state.albumSelectMode) {
      tile.addEventListener("click", (e) => {
        // 快捷按钮（转高清/收藏/删除）仍然各自生效，不触发勾选
        if (e.target.closest("[data-album-quick], [data-album-fav], [data-album-del], [data-album-upscale]")) return;
        e.preventDefault();
        e.stopPropagation();   // 阻止冒泡到 document 的 lightbox 委托
        toggleAlbumSelection(card.card_id);
      });
    }

    grid.appendChild(tile);
  });
  if (items.length > shown.length) {
    const more = document.createElement("div");
    more.className = "load-more-container";
    more.innerHTML = `<button type="button" class="btn-load-more" id="btn-album-load-more"><i class="fa-solid fa-arrow-down-long"></i> 加载更多 (已显示 ${shown.length}/${items.length})</button>`;
    more.querySelector("button").addEventListener("click", () => {
      state.albumLimit = (state.albumLimit || 100) + 100;
      renderAlbumGrid();
    });
    grid.appendChild(more);
  }
}

function albumTitleFor(id) {
  if (state.albumPersonFilter === "__other__") return "角色 · 其他";
  if (state.albumPersonFilter) return `角色 · ${state.albumPersonFilter}`;
  if (id === "unfiled") return "未分辑";
  const found = (state.albums || []).find((a) => a.id === id);
  if (found) return found.name;
  return "全部成片";
}

function favoriteAlbum() {
  return (state.albums || []).find((album) => album.id === "favorites") || null;
}

/**
 * 把这张图的提示词存进 Obsidian 灵感库。
 * 复用卡片存档接口 /api/cards/{id}/archive —— 它会生成笔记 + 复制附件。
 */
async function archiveAlbumCard(card, btnEl) {
  const cardId = card && card.card_id;
  if (!cardId) return;
  if (!card.render_image) {
    if (typeof showToast === "function") showToast("这张卡还没有成片，无法存档", "warning");
    return;
  }

  const orig = btnEl ? btnEl.innerHTML : "";
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
  }

  try {
    const res = await fetch(`/api/cards/${encodeURIComponent(cardId)}/archive`, {
      method: "POST",
    });
    const txt = await res.text();
    let data = {};
    try { data = JSON.parse(txt); } catch (_) {}
    if (!res.ok) {
      const detail = typeof data.detail === "string" ? data.detail : (data.detail?.message || txt);
      throw new Error(String(detail).slice(0, 160));
    }

    const already = data.already_archived;
    if (btnEl) btnEl.innerHTML = '<i class="fa-solid fa-check"></i>';
    if (typeof showToast === "function") {
      showToast(
        already ? "这张已经存过了" : "📸 已存进 Obsidian 灵感库",
        already ? "info" : "success"
      );
    }
    // 1.8 秒后恢复原图标
    if (btnEl) setTimeout(() => { btnEl.innerHTML = orig; }, 1800);
  } catch (err) {
    if (btnEl) btnEl.innerHTML = orig;
    if (typeof showToast === "function") {
      showToast(`存档失败：${err.message || err}`, "error");
    }
  } finally {
    if (btnEl) btnEl.disabled = false;
  }
}

/**
 * 转高清：把卡片图交给 SeedVR2 放大工作流。
 * 后端会复制进 ComfyUI output → 提交 → 轮询 → 回写卡片 render_image。
 */
async function upscaleAlbumCard(card, btnEl) {
  const cardId = card && card.card_id;
  if (!cardId) return;
  if (!card.render_image) {
    showToast("这张卡还没有成片，无法转高清", "warning");
    return;
  }

  const orig = btnEl ? btnEl.innerHTML : "";
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
  }
  if (typeof showToast === "function") {
    showToast("已提交转高清，SeedVR2 放大约需 1-3 分钟…", "info");
  }

  try {
    const res = await fetch("/api/upscale/card", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ card_id: cardId, multiplier: 3 }),
    });
    const txt = await res.text();
    let data = {};
    try { data = JSON.parse(txt); } catch (_) {}
    if (!res.ok) {
      throw new Error(String(data.detail || txt).slice(0, 160));
    }
    if (btnEl) btnEl.innerHTML = '<i class="fa-solid fa-check"></i>';
    if (typeof showToast === "function") {
      showToast(`转高清完成：${data.to || ""}`, "success");
    }
    // 刷新相册 + 卡片列表
    if (typeof loadCards === "function") {
      try { await loadCards(); } catch (_) {}
    }
    if (typeof refreshCards === "function") {
      try { await refreshCards(); } catch (_) {}
    }
    try { renderAlbumGrid(); } catch (_) {}
  } catch (err) {
    if (btnEl) btnEl.innerHTML = orig;
    if (typeof showToast === "function") {
      showToast("转高清失败：" + String(err.message || err).slice(0, 80), "error");
    }
  } finally {
    if (btnEl) btnEl.disabled = false;
  }
}

async function toggleFavoriteCard(cardId, currentlyOn) {
  const album = favoriteAlbum();
  if (!album) {
    showToast("收藏分类还没准备好", "warning");
    return;
  }
  if (currentlyOn) {
    await removeCardFromAlbum(album.id, cardId, { silent: true, toast: "已取消收藏" });
  } else {
    await addCardToAlbum(album.id, cardId, { silent: true, toast: "已收藏" });
  }
}

function confirmDeleteAlbumCard(card) {
  const label = [card.person, card.scene].filter(Boolean).join(" · ") || card.card_id;
  openDangerConfirmModal({
    title: "删除卡片",
    message: `删除「${label}」会拿掉卡片和图片，收藏和专辑里也会去掉。`,
    confirmLabel: "删除",
    onConfirm: async () => {
      if (typeof deleteCard === "function") {
        await deleteCard(card.card_id);
      }
      await refreshAlbumWorkspace();
    },
  });
}

async function addCardToAlbum(albumId, cardId, options = {}) {
  try {
    const res = await fetch(`/api/albums/${encodeURIComponent(albumId)}/cards`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ add: [cardId] }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "移入失败");
    await refreshAlbumWorkspace();
    showToast(options.toast || "已加入专辑", "success");
  } catch (err) {
    showToast(`移入失败：${err.message || err}`, "error");
  }
}

async function removeCardFromAlbum(albumId, cardId, options = {}) {
  try {
    const res = await fetch(`/api/albums/${encodeURIComponent(albumId)}/cards`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ remove: [cardId] }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "移出失败");
    await refreshAlbumWorkspace();
    showToast(options.toast || "已移出专辑", "success");
  } catch (err) {
    showToast(`移出失败：${err.message || err}`, "error");
  }
}

async function setAlbumCover(albumId, cardId) {
  try {
    const res = await fetch(`/api/albums/${encodeURIComponent(albumId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cover_card_id: cardId }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "设置封面失败");
    await loadAlbumIndex();
    showToast("已设为封面", "success");
  } catch (err) {
    showToast(`设置封面失败：${err.message || err}`, "error");
  }
}

async function renameAlbum(albumId, currentName) {
  const next = window.prompt("专辑新名称", currentName || "");
  if (next == null) return;
  const name = String(next).trim();
  if (!name) {
    showToast("专辑名不能为空", "warning");
    return;
  }
  try {
    const res = await fetch(`/api/albums/${encodeURIComponent(albumId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "重命名失败");
    await refreshAlbumWorkspace();
  } catch (err) {
    showToast(`重命名失败：${err.message || err}`, "error");
  }
}

function confirmDeleteAlbum(albumId, name) {
  openDangerConfirmModal({
    title: "删除专辑",
    message: `删除「${name}」只去掉分组，卡片和图片都还在。`,
    confirmLabel: "删除专辑",
    onConfirm: async () => {
      const res = await fetch(`/api/albums/${encodeURIComponent(albumId)}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast(data.detail || "删除失败", "error");
        return;
      }
      if (state.albumFilter === albumId) state.albumFilter = "all";
      await refreshAlbumWorkspace();
      showToast("专辑已删除", "success");
    },
  });
}

function openCardInWorkbench(cardId) {
  switchView("chat");
  if (typeof selectCard === "function") selectCard(cardId);
}

async function ensureAlbumViewLoaded() {
  try {
    await refreshAlbumWorkspace();
  } catch (err) {
    showToast(`相册加载失败：${err.message || err}`, "error");
  }
}
