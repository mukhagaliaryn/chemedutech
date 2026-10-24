/*
 * Rich text fields created in JS (CKEditor 5 from django-ckeditor-5, configs from {% rich_text_assets %}).
 *
 *   <textarea x-model="row.text" x-rich.compact data-rt="line"></textarea>
 *   <textarea name="answer" x-rich.answer="!journalOpen" data-rt="long"></textarea>
 *
 * The modifier is the config (compact | answer, default compact); the optional expression makes the editor
 * read-only while it is true. The textarea keeps the HTML and fires «input», so x-model and plain forms both work.
 * data-rt sets the height (line | short | long, see styles.css).
 * el.dispatchEvent(new CustomEvent("rich-insert", { detail: html })) puts HTML at the cursor (the lesson designer's
 * «Add to the editor»); without the editor the text is appended to the textarea.
 */
(function () {
  "use strict";

  let configs = null;
  function config(name) {
    if (!configs) {
      const el = document.getElementById("rt-configs");
      configs = el ? JSON.parse(el.textContent) : {};
    }
    return { ...(configs[name] || {}), licenseKey: "GPL" };
  }

  document.addEventListener("alpine:init", () => {
    window.Alpine.directive("rich", (el, { modifiers, expression }, { evaluateLater, effect, cleanup }) => {
      let editor = null;
      let destroyed = false;
      el.addEventListener("rich-insert", (e) => {
        if (editor) {
          const fragment = editor.data.toModel(editor.data.processor.toView(e.detail));
          editor.model.insertContent(fragment);
          editor.editing.view.focus();
        } else {
          const box = document.createElement("div");
          box.innerHTML = e.detail;
          el.value = (el.value ? el.value + "\n" : "") + box.innerText;
          el.dispatchEvent(new Event("input", { bubbles: true }));
        }
      });
      if (!window.ClassicEditor) return; // the bundle did not load: the plain textarea still works
      const name = modifiers[0] || "compact";
      const readOnly = expression ? evaluateLater(expression) : null;

      window.Alpine.nextTick(() => {
        // x-model has written the initial value by now
        window.ClassicEditor.create(el, config(name))
          .then((ed) => {
            if (destroyed) return ed.destroy();
            editor = ed;
            ed.model.document.on("change:data", () => {
              el.value = ed.getData();
              el.dispatchEvent(new Event("input", { bubbles: true }));
            });
            if (readOnly) {
              effect(() =>
                readOnly((locked) =>
                  locked ? ed.enableReadOnlyMode("x-rich") : ed.disableReadOnlyMode("x-rich"),
                ),
              );
            }
          })
          .catch((e) => console.error(e));
      });

      cleanup(() => {
        destroyed = true;
        if (editor) editor.destroy();
      });
    });
  });
})();
