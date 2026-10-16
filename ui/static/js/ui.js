// Small behaviours shared by every page (components/modal.html).
document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-open-modal]");
  if (!opener) return;
  const dialog = document.getElementById(opener.dataset.openModal);
  if (dialog && typeof dialog.showModal === "function") {
    event.preventDefault();
    dialog.showModal();
  }
});
