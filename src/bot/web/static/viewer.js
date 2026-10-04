(function () {
  "use strict";
  var wide = window.matchMedia("(min-width: 1100px)");
  var calm = window.matchMedia("(prefers-reduced-motion: reduce)");

  document.addEventListener("click", function (e) {
    var link = e.target instanceof Element ? e.target.closest('a[hx-get][hx-target="#detail"]') : null;
    if (!link) return;
    if (!wide.matches || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) {
      e.stopPropagation();
      return;
    }
    if (calm.matches) link.setAttribute("hx-swap", "innerHTML");
  }, true);

  function markSelected() {
    var big = document.querySelector("#detail .big-ticker");
    var listOnly = document.body.classList.contains("page-list") && !wide.matches;
    var ticker = big && !listOnly ? big.textContent.trim() : null;
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

  markSelected();
  wide.addEventListener("change", markSelected);

  document.addEventListener("htmx:afterSwap", function (e) {
    var id = e.target && e.target.id;
    if (id === "detail" || id === "rows") markSelected();
  });
})();
