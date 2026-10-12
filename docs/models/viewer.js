// Load the author's document after its iframe has a real viewport.
// The artwork source is never modified or injected into.
(() => {
  const frame = document.querySelector("iframe[data-artwork]");
  if (frame) {
    requestAnimationFrame(() => {
      frame.getBoundingClientRect();
      frame.src = frame.dataset.artwork;
    });
  }
  const dialog = document.querySelector("#prompt-dialog");
  const openButton = document.querySelector("[data-open-prompts]");
  if (!dialog || !openButton) return;
  openButton.addEventListener("click", () => dialog.showModal());
  dialog.querySelector("[data-close-prompts]").addEventListener("click", () => dialog.close());
})();
