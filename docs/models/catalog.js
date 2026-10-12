(() => {
  "use strict";
  const cards = [...document.querySelectorAll(".portrait-card")];
  const filters = [...document.querySelectorAll(".filters button")];
  const search = document.getElementById("search");
  let family = "all";
  function update() {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    for (const card of cards) {
      const matches = (family === "all" || card.dataset.family === family) &&
        `${card.dataset.name} ${card.dataset.family}`.toLowerCase().includes(query);
      card.hidden = !matches;
      if (matches) visible++;
    }
    document.getElementById("empty").hidden = visible > 0;
  }
  for (const button of filters) button.addEventListener("click", () => {
    family = button.dataset.family;
    for (const filter of filters) {
      filter.classList.toggle("active", filter === button);
      filter.setAttribute("aria-pressed", String(filter === button));
    }
    update();
  });
  search.addEventListener("input", update);
})();
