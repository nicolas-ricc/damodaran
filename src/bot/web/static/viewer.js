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
      if (row.hidden) return;
      var link = row.querySelector("td.ticker a");
      var on = !!link && link.textContent.trim() === ticker;
      row.classList.toggle("selected", on);
      row.classList.toggle("bg-base-300", on);
      if (link) {
        if (on) link.setAttribute("aria-current", "true");
        else link.removeAttribute("aria-current");
      }
    });
  }

  // On a deep link, bring the selected row into the list pane's box; only the pane scrolls, never the window.
  function revealSelected() {
    var row = document.querySelector("#rows tr.selected");
    var pane = document.querySelector(".list-pane");
    if (!row || !pane || !wide.matches) return;
    var p = pane.getBoundingClientRect();
    var r = row.getBoundingClientRect();
    if (r.top >= p.top && r.bottom <= p.bottom) return;
    pane.scrollTop += r.top - p.top - p.height / 3;
  }

  // Hide the rows the box does not match; swaps and Back replace these nodes, so look them up every time.
  function applySearch() {
    var input = document.querySelector("#search input");
    if (!input) return;
    var rows = document.getElementById("rows");
    var count = document.getElementById("count");
    if (!rows) return;
    var raw = input.value.trim();
    var q = raw.toLowerCase();
    var visible = 0;
    rows.querySelectorAll("tr").forEach(function (row) {
      var ticker = row.querySelector("td.ticker");
      if (!ticker) return;
      var name = row.querySelector("td.name");
      var inTicker = ticker.textContent.toLowerCase().indexOf(q) !== -1;
      var inName = !!name && name.textContent.toLowerCase().indexOf(q) !== -1;
      row.hidden = !!q && !inTicker && !inName;
      if (!row.hidden) visible++;
    });
    if (count) count.textContent = visible + " of " + count.dataset.total;
    var none = document.getElementById("search-empty");
    if (q && visible === 0) {
      if (!none) {
        none = document.createElement("tr");
        none.id = "search-empty";
        none.innerHTML = '<td colspan="9" class="none">No company matches "<span></span>". <button type="button" class="btn btn-link btn-xs">Clear search</button></td>';
        none.querySelector("button").addEventListener("click", function () {
          input.value = "";
          applySearch();
          input.focus();
        });
      }
      none.querySelector("span").textContent = raw;
      rows.appendChild(none);
    } else if (none) {
      none.remove();
    }
    markSelected();
  }

  // One line for screen readers instead of the whole analysis, then focus the heading.
  function announceDetail() {
    var heading = document.querySelector("#detail h1");
    var verdict = document.querySelector("#detail .verdict-text");
    var mos = document.querySelector("#detail .facts .lead-figure .stat-value");
    var out = document.getElementById("announce");
    if (out && heading) {
      out.textContent = heading.textContent.trim().replace(/\.$/, "") + ". " +
        (verdict ? verdict.textContent.trim() : "") +
        (mos ? ", margin of safety " + mos.textContent.trim() : "") + ".";
    }
    if (heading) heading.focus({ preventScroll: true });
  }

  markSelected();
  revealSelected();
  wide.addEventListener("change", markSelected);

  // Show the box only where the script runs; Back restores a snapshot whose rows may still be hidden.
  function initSearch() {
    var search = document.getElementById("search");
    if (!search) return;
    search.removeAttribute("hidden");
    applySearch();
  }

  initSearch();
  document.addEventListener("htmx:historyRestore", initSearch);

  document.addEventListener("input", function (e) {
    if (e.target instanceof Element && e.target.matches("#search input")) applySearch();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !(e.target instanceof Element) || !e.target.matches("#search input")) return;
    e.preventDefault();
    e.target.value = "";
    applySearch();
  });

  // A rows fragment ends with its page title (a leading one breaks the table parse), and htmx would pick an svg's title first.
  document.addEventListener("htmx:beforeSwap", function (e) {
    if (!e.detail || !e.detail.target || e.detail.target.id !== "rows") return;
    var m = /<title>([^<]*)<\/title>\s*$/.exec(e.detail.serverResponse || "");
    if (m) document.title = m[1];
  });

  document.addEventListener("htmx:afterSettle", function (e) {
    var id = e.target && e.target.id;
    if (id === "rows") {
      applySearch();
      markSelected();
      restoreFocus();
      // a filter that has rows again leaves the "no company is ..." pane behind: ask for a pick instead
      var empty = document.querySelector("#detail .empty-detail");
      if (empty && document.querySelector("#rows td.ticker")) {
        empty.innerHTML = '<div class="hero-content"><div><p>Pick a company from the list to read its analysis.</p></div></div>';
      }
    } else if (id === "detail") {
      markSelected();
      announceDetail();
    }
  });
})();
