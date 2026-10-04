(function () {
  "use strict";
  var wide = window.matchMedia("(min-width: 1100px)");
  var calm = window.matchMedia("(prefers-reduced-motion: reduce)");

  document.addEventListener("click", function (e) {
    var link = e.target instanceof Element ? e.target.closest('a[hx-get][hx-target="#detail"]') : null;
    if (!link) return;
    if (!wide.matches) {
      e.stopPropagation();
      return;
    }
    if (calm.matches) link.setAttribute("hx-swap", "innerHTML");
  }, true);

  function markSelected() {
    var big = document.querySelector("#detail .big-ticker");
    var ticker = big ? big.textContent.trim() : null;
    document.querySelectorAll("#rows tr").forEach(function (row) {
      var link = row.querySelector("td.ticker a");
      var on = !!link && link.textContent.trim() === ticker;
      row.classList.toggle("selected", on);
      if (link) {
        if (on) link.setAttribute("aria-current", "true");
        else link.removeAttribute("aria-current");
      }
    });
  }

  document.addEventListener("htmx:afterSwap", function (e) {
    var id = e.target && e.target.id;
    if (id === "detail" || id === "rows") markSelected();
  });
})();
