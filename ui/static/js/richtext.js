/*
 * Rich text fields created in JS (CKEditor 5 from django-ckeditor-5, configs from {% rich_text_assets %}).
 *
 *   <textarea x-model="row.text" x-rich.compact data-rt="line"></textarea>
 *   <textarea name="answer" x-rich.answer="!journalOpen" data-rt="long"></textarea>
 *
 * The modifier is the config (compact | answer, default compact); the optional expression makes the editor
 * read-only while it is true. The textarea keeps the HTML and fires «input», so x-model and plain forms both work.
 * data-rt sets the height (line | short | long, see styles.css).
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
      if (!window.ClassicEditor) return; // the bundle did not load: the plain textarea still works
      const name = modifiers[0] || "compact";
      const readOnly = expression ? evaluateLater(expression) : null;
      let editor = null;
      let destroyed = false;

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
