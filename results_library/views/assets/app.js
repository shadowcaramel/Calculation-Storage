/* Client-side filtering, sorting, and copy-to-clipboard.
 *
 * Plain vanilla JS with no dependencies, because the site has to work opened
 * straight from a synced folder over file:// with no network access.
 *
 * Copy buttons read from hidden textareas holding strings that were generated
 * from the catalog values. They never read the rendered table: selecting HTML
 * and pasting it is exactly what produces mangled LaTeX. */

(function () {
  "use strict";

  // ---- filtering -------------------------------------------------------

  var textInput = document.getElementById("filter-text");
  var statusSelect = document.getElementById("filter-status");
  var hideProbing = document.getElementById("hide-probing");
  var countLabel = document.getElementById("row-count");

  function filterableRows() {
    return Array.prototype.slice.call(
      document.querySelectorAll('table[data-filterable="true"] tbody tr')
    );
  }

  function applyFilters() {
    var needle = (textInput && textInput.value ? textInput.value : "")
      .trim()
      .toLowerCase();
    var wantedStatus = statusSelect ? statusSelect.value : "";
    var skipProbing = hideProbing ? hideProbing.checked : false;
    var shown = 0;

    filterableRows().forEach(function (row) {
      var status = row.getAttribute("data-status") || "";
      var haystack = (row.getAttribute("data-search") || "").toLowerCase();

      var visible = true;
      if (needle && haystack.indexOf(needle) === -1) visible = false;
      if (wantedStatus && status !== wantedStatus) visible = false;
      // An explicit status choice wins over the hide-probing shortcut.
      if (skipProbing && status === "probing" && wantedStatus !== "probing") {
        visible = false;
      }

      row.hidden = !visible;
      if (visible) shown += 1;
    });

    if (countLabel) {
      var total = filterableRows().length;
      countLabel.textContent =
        shown === total ? total + " results" : shown + " of " + total + " results";
    }
  }

  if (textInput) textInput.addEventListener("input", applyFilters);
  if (statusSelect) statusSelect.addEventListener("change", applyFilters);
  if (hideProbing) hideProbing.addEventListener("change", applyFilters);

  // ---- sorting ---------------------------------------------------------

  function cellSortValue(row, index, kind) {
    var cell = row.cells[index];
    if (!cell) return kind === "number" ? Number.NEGATIVE_INFINITY : "";
    if (kind === "number") {
      var raw = cell.getAttribute("data-value");
      var value = parseFloat(raw === null ? cell.textContent : raw);
      return isNaN(value) ? Number.NEGATIVE_INFINITY : value;
    }
    return cell.textContent.trim().toLowerCase();
  }

  document.querySelectorAll("table thead th[data-sort]").forEach(function (header) {
    header.addEventListener("click", function () {
      var table = header.closest("table");
      var body = table.tBodies[0];
      if (!body) return;

      var index = Array.prototype.indexOf.call(header.parentNode.cells, header);
      var kind = header.getAttribute("data-sort");
      var ascending = !header.classList.contains("sorted-asc");

      header.parentNode.querySelectorAll("th").forEach(function (other) {
        other.classList.remove("sorted-asc", "sorted-desc");
      });
      header.classList.add(ascending ? "sorted-asc" : "sorted-desc");

      var rows = Array.prototype.slice.call(body.rows);
      rows.sort(function (a, b) {
        var left = cellSortValue(a, index, kind);
        var right = cellSortValue(b, index, kind);
        if (left < right) return ascending ? -1 : 1;
        if (left > right) return ascending ? 1 : -1;
        return 0;
      });
      rows.forEach(function (row) {
        body.appendChild(row);
      });
    });
  });

  // ---- copy ------------------------------------------------------------

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    // file:// pages often have no async clipboard, so fall back to a temporary
    // textarea and execCommand.
    return new Promise(function (resolve, reject) {
      var scratch = document.createElement("textarea");
      scratch.value = text;
      scratch.setAttribute("readonly", "");
      scratch.style.position = "fixed";
      scratch.style.left = "-9999px";
      document.body.appendChild(scratch);
      scratch.select();
      var ok = false;
      try {
        ok = document.execCommand("copy");
      } catch (err) {
        ok = false;
      }
      document.body.removeChild(scratch);
      ok ? resolve() : reject(new Error("copy failed"));
    });
  }

  document.querySelectorAll("button.copy").forEach(function (button) {
    button.addEventListener("click", function () {
      var source = document.getElementById(button.getAttribute("data-target"));
      if (!source) return;
      var original = button.textContent;
      copyText(source.value).then(
        function () {
          button.textContent = "Copied";
          button.classList.add("copied");
          setTimeout(function () {
            button.textContent = original;
            button.classList.remove("copied");
          }, 1400);
        },
        function () {
          // Leave the text selected so Ctrl+C still works.
          source.style.position = "static";
          source.style.width = "100%";
          source.style.height = "8rem";
          source.select();
          button.textContent = "Press Ctrl+C";
        }
      );
    });
  });

  applyFilters();
})();
