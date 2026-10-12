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
  for (const [id, open, close] of [
    ["prompt-dialog", "data-open-prompts", "data-close-prompts"],
    ["cost-dialog", "data-open-cost", "data-close-cost"],
  ]) {
    const dialog = document.getElementById(id);
    const openButton = document.querySelector(`[${open}]`);
    if (!dialog || !openButton) continue;
    openButton.addEventListener("click", () => dialog.showModal());
    dialog.querySelector(`[${close}]`).addEventListener("click", () => dialog.close());
  }
})();
