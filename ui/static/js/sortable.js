/* Reorder lists in the content editor: drag by the handle (mouse) or use the ↑ ↓ buttons (keyboard, touch).
 *
 * <ol data-sortable="stages" data-parent="12" data-url="/teacher/courses/x/reorder/">
 *   <li data-id="5"> <button data-handle>⋮⋮</button> … <button data-move="up"> <button data-move="down"> </li>
 * </ol>
 * The new order is POSTed as JSON {what, parent, ids}; on an error the page reloads to show the saved order.
 */
(function () {
  function csrf() {
    const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function items(list) {
    return Array.from(list.children).filter((el) => el.dataset.id);
  }

  function save(list) {
    const body = { what: list.dataset.sortable, parent: list.dataset.parent || null, ids: items(list).map((el) => Number(el.dataset.id)) };
    list.setAttribute("aria-busy", "true");
    fetch(list.dataset.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(body),
      credentials: "same-origin",
    })
      .then((r) => { if (!r.ok) throw new Error(r.status); })
      .catch(() => window.location.reload())
      .finally(() => list.removeAttribute("aria-busy"));
  }

  function init(list) {
    let dragged = null;
    list.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-move]");
      if (!btn || !list.contains(btn)) return;
      const item = btn.closest("[data-id]");
      if (!item || item.parentElement !== list) return;
      const sibling = btn.dataset.move === "up" ? item.previousElementSibling : item.nextElementSibling;
      if (!sibling || !sibling.dataset.id) return;
      if (btn.dataset.move === "up") list.insertBefore(item, sibling); else list.insertBefore(sibling, item);
      btn.focus();
      save(list);
    });
    items(list).forEach((item) => {
      const handle = item.querySelector(":scope [data-handle]");
      if (!handle) return;
      handle.addEventListener("pointerdown", () => { item.draggable = true; });
      item.addEventListener("dragstart", (e) => {
        if (e.target !== item) return;
        dragged = item;
        e.dataTransfer.effectAllowed = "move";
        item.classList.add("opacity-50");
      });
      item.addEventListener("dragend", () => {
        item.draggable = false;
        item.classList.remove("opacity-50");
        if (dragged) { dragged = null; save(list); }
      });
    });
    list.addEventListener("dragover", (e) => {
      if (!dragged || dragged.parentElement !== list) return;
      e.preventDefault();
      let over = e.target.closest("[data-id]");
      while (over && over.parentElement !== list) over = over.parentElement.closest("[data-id]");  // nested lists
      if (!over || over === dragged) return;
      const box = over.getBoundingClientRect();
      list.insertBefore(dragged, e.clientY > box.top + box.height / 2 ? over.nextElementSibling : over);
    });
  }

  document.querySelectorAll("[data-sortable]").forEach(init);
})();
