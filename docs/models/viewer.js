// Load the author's document after its iframe has a real viewport.
// The artwork source is never modified or injected into.
(() => {
  const frame = document.querySelector("iframe[data-artwork]");
  if (!frame) return;
  requestAnimationFrame(() => {
    frame.getBoundingClientRect();
    frame.src = frame.dataset.artwork;
  });
})();
