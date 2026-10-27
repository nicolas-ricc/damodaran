(function () {
  "use strict";
  var wide = window.matchMedia("(min-width: 1100px)");
  var lastHref = null;

  // Under 1100px the index shows the ledger alone, so a ticker opens its own page.
  document.addEventListener("click", function (e) {
    var link = e.target instanceof Element ? e.target.closest('a[hx-get][hx-target="#detail"]') : null;
    if (!link) return;
    if (!wide.matches || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) e.stopPropagation();
  }, true);

  // A filter or sort swaps the control that was activated out from under the keyboard;
  // remember which link it was so focus can land on its replacement.
  document.addEventListener("htmx:beforeRequest", function (e) {
    var link = e.detail && e.detail.elt;
    lastHref = link && link.matches && link.matches('a[hx-target="#rows"]') ? link.getAttribute("href") : null;
  });

  function restoreFocus() {
    if (!lastHref) return;
    var href = lastHref;
    lastHref = null;
    if (document.activeElement && document.activeElement !== document.body) return;
    var again = document.querySelector('#filter a[href="' + href + '"], #list-head a[href="' + href + '"]');
    if (again) again.focus({ preventScroll: true });
  }

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

  // One line for screen readers instead of the whole analysis, then focus the heading.
  function announceDetail() {
    var heading = document.querySelector("#detail h1");
    var verdict = document.querySelector("#detail .verdict-text");
    var mos = document.querySelector("#detail .facts .lead-figure dd");
    var out = document.getElementById("announce");
    if (out && heading) {
      out.textContent = heading.textContent.trim() + ". " +
        (verdict ? verdict.textContent.trim() : "") +
        (mos ? ", margin of safety " + mos.textContent.trim() : "") + ".";
    }
    if (heading) heading.focus({ preventScroll: true });
  }

  markSelected();
  wide.addEventListener("change", markSelected);

  document.addEventListener("htmx:afterSettle", function (e) {
    var id = e.target && e.target.id;
    if (id === "rows") {
      markSelected();
      restoreFocus();
      // a filter that has rows again leaves the "no company is ..." pane behind: ask for a pick instead
      var empty = document.querySelector("#detail .empty-detail");
      if (empty && document.querySelector("#rows td.ticker")) {
        empty.innerHTML = "<p>Pick a company from the list to read its analysis.</p>";
      }
    } else if (id === "detail") {
      markSelected();
      announceDetail();
    }
  });
})();
