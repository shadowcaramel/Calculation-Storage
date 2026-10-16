/* Explorer: groups, filters, and draws the catalog that catalog.js carries.
 *
 * Plain JS, no dependencies besides the vendored KaTeX, because the page opens
 * from a synced folder over file://. Every decision that needs a rule (which
 * result heads a family, link targets, LaTeX strings, paper checks) is made by
 * the Python build; this file only reads them.
 *
 * Routes live in the hash so the back button and bookmarks work:
 *   #modern                      library overview
 *   #legacy/n/6He                one nucleus
 *   #legacy/f/<family>           one family
 *   #legacy/r/<result id>        one family, with that result in the side panel
 *   #papers                      the papers and their checks
 *   #papers/p/<paper>            one paper
 *   #papers/p/<paper>/r/<id>     one paper, with a result in the side panel
 */

(function () {
  "use strict";

  var CAT = window.CATALOG;
  if (!CAT) {
    document.getElementById("main").innerHTML =
      '<p class="empty">explorer/catalog.js did not load. Rebuild with <code>python -m results_library.cli explorer --with-papers</code>, and open explorer.html from a local copy of the library folder.</p>';
    return;
  }

  var ROWS = CAT.rows;
  var BY_ID = {};
  ROWS.forEach(function (r) { BY_ID[r.id] = r; });
  var LIBS = ["modern", "legacy"];
  var STATUS_ORDER = ["published", "working", "probing", "superseded"];
  var THEME_KEY = "results-theme";

  var PAPERS = CAT.papers ? CAT.papers.papers : [];
  var ISSUES = CAT.papers ? CAT.papers.issues : [];
  var PAPER_BY_ID = {};
  // Every printed number that names a result, so the side panel can show
  // where a result was published and whether the paper agrees with it.
  var CHECKS_BY_RESULT = {};
  PAPERS.forEach(function (p) {
    PAPER_BY_ID[p.id] = p;
    p.materials.forEach(function (m) {
      m.checks.forEach(function (c) { (CHECKS_BY_RESULT[c.result] = CHECKS_BY_RESULT[c.result] || []).push({ paper: p, material: m, check: c }); });
    });
    p.loose.forEach(function (c) { (CHECKS_BY_RESULT[c.result] = CHECKS_BY_RESULT[c.result] || []).push({ paper: p, material: null, check: c }); });
  });

  var state = { lib: "modern", nuc: null, fam: null, sel: null, paper: null, facets: {}, facetFam: null, xaxis: null, zoom: true };

  // ---- helpers ---------------------------------------------------------

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function uniq(list) { var out = []; list.forEach(function (x) { if (x != null && x !== "" && out.indexOf(x) < 0) out.push(x); }); return out; }
  function countBy(list, fn) { var m = {}; list.forEach(function (x) { var k = fn(x); if (k == null) return; m[k] = (m[k] || 0) + 1; }); return m; }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : many); }
  function libRows(lib) { return ROWS.filter(function (r) { return r.lineage === lib; }); }
  function libName(lib) { return lib === "legacy" ? "Legacy" : lib === "papers" ? "Papers" : "Modern"; }
  function nucInfo(n) { return CAT.nuclei[n] || { label: n, order: [9, 999, 999] }; }
  function nucOrder(a, b) {
    var A = nucInfo(a).order, B = nucInfo(b).order;
    return (A[0] - B[0]) || (A[1] - B[1]) || (A[2] - B[2]) || String(a).localeCompare(String(b));
  }
  function units(u) { return u ? String(u).replace(/\^2/g, "²").replace(/\^4/g, "⁴").replace(/\^-1/g, "⁻¹") : ""; }
  // Nmax and ħΩ windows are integers in the catalog; print them as such.
  function num(v) { return v == null ? "" : (Math.abs(v - Math.round(v)) < 1e-9 ? String(Math.round(v)) : String(v)); }
  function win(pair) { return pair && pair[0] != null ? "[" + num(pair[0]) + ", " + num(pair[1]) + "]" : "–"; }
  // Paths in the catalog are library-root relative, and this page sits at the
  // root, so they are used as they are, with each segment escaped.
  function href(path, r) {
    var text = String(path || "");
    if (text.indexOf("@/") === 0) text = r.bundle + text.slice(1);
    return text.split("/").map(encodeURIComponent).join("/");
  }
  function hint(label) { var h = CAT.hints[label]; return h ? '<span class="hint">' + esc(h) + "</span>" : ""; }
  function route(lib, kind, key) { return "#" + lib + (kind ? "/" + kind + "/" + encodeURIComponent(key) : ""); }
  function paperRoute(pid, rid) { return "#papers/p/" + encodeURIComponent(pid) + (rid ? "/r/" + encodeURIComponent(rid) : ""); }
  // Opening a result keeps the reader where they are: on a paper it opens
  // beside the paper, elsewhere it opens beside its family.
  function resultRoute(id) {
    if (state.lib === "papers" && state.paper) return paperRoute(state.paper, id);
    var r = BY_ID[id];
    return route(r ? r.lineage : state.lib, "r", id);
  }
  function paperChip(p) {
    return CAT.papers && PAPER_BY_ID[p.id]
      ? '<a class="pap" href="' + paperRoute(p.id) + '" title="' + esc(p.title) + '">' + esc(p.title) + "</a>"
      : p.href ? '<a class="pap" href="' + href(p.href) + '" title="' + esc(p.title) + '">' + esc(p.title) + "</a>" : '<span class="pap">' + esc(p.title) + "</span>";
  }

  function tex(latex, fallback) {
    var plain = fallback || latex || "";
    if (!latex) return esc(plain);
    return '<span class="tex" data-tex="' + esc(latex) + '">' + esc(plain) + "</span>";
  }
  function typeset(root) {
    if (typeof window.katex === "undefined") return;
    root.querySelectorAll("span.tex[data-tex]").forEach(function (node) {
      try { window.katex.render(node.getAttribute("data-tex"), node, { throwOnError: false }); }
      catch (err) { /* keep the Unicode fallback */ }
    });
  }
  function stateTex(r) { return tex(r.state_latex, r.state_label); }
  function obsTex(r) { return tex(r.observable_latex, r.observable_label); }

  // ---- geometric marks ---------------------------------------------------
  // Series i: colour --s(i+1), shape i mod 4 (circle, square, triangle,
  // diamond). See DESIGN.md.

  function seriesColor(i) { return "var(--s" + (i % 6 + 1) + ")"; }
  function marker(i, x, y, r, fill, extra) {
    extra = extra || "";
    switch (i % 4) {
      case 1: return '<rect x="' + (x - r * 0.9) + '" y="' + (y - r * 0.9) + '" width="' + (r * 1.8) + '" height="' + (r * 1.8) + '" fill="' + fill + '"' + extra + "/>";
      case 2: return '<path d="M' + x + " " + (y - r * 1.1) + "L" + (x + r * 1.05) + " " + (y + r * 0.8) + "L" + (x - r * 1.05) + " " + (y + r * 0.8) + 'Z" fill="' + fill + '"' + extra + "/>";
      case 3: return '<path d="M' + x + " " + (y - r * 1.2) + "L" + (x + r * 1.2) + " " + y + "L" + x + " " + (y + r * 1.2) + "L" + (x - r * 1.2) + " " + y + 'Z" fill="' + fill + '"' + extra + "/>";
      default: return '<circle cx="' + x + '" cy="' + y + '" r="' + r + '" fill="' + fill + '"' + extra + "/>";
    }
  }
  function glyph(i) { return '<svg class="glyph" viewBox="0 0 12 12" aria-hidden="true">' + marker(i, 6, 6.4, 4.6, seriesColor(i)) + "</svg>"; }

  // ---- families --------------------------------------------------------

  var FAMILIES = {};
  function families(lib) {
    if (FAMILIES[lib]) return FAMILIES[lib];
    var by = {};
    libRows(lib).forEach(function (r) { (by[r.family] = by[r.family] || []).push(r); });
    var list = Object.keys(by).map(function (key) {
      var rows = by[key];
      var head = rows.filter(function (r) { return r.headline; })[0] || rows[0];
      return {
        key: key, nucleus: head.nucleus, head: head, rows: rows,
        potentials: uniq(rows.map(function (r) { return r.potential; })),
        ensembles: uniq(rows.map(function (r) { return r.ensemble; })).length,
        latest: rows.reduce(function (m, r) { return (r.run_datetime || "") > m ? r.run_datetime : m; }, "")
      };
    });
    list.sort(function (a, b) {
      return nucOrder(a.nucleus, b.nucleus) || String(a.head.state_label).localeCompare(String(b.head.state_label)) || String(a.head.observable_label).localeCompare(String(b.head.observable_label));
    });
    FAMILIES[lib] = list;
    return list;
  }
  function family(lib, key) { return families(lib).filter(function (f) { return f.key === key; })[0]; }

  // ---- small charts ----------------------------------------------------

  function extent(rows) {
    var lo = Infinity, hi = -Infinity;
    rows.forEach(function (r) {
      if (r.median == null) return;
      lo = Math.min(lo, r.median - (r.err_low || 0));
      hi = Math.max(hi, r.median + (r.err_high || 0));
    });
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    if (hi - lo < 1e-12) { var d = Math.abs(lo) * 0.01 || 0.5; lo -= d; hi += d; }
    var pad = (hi - lo) * 0.06;
    return [lo - pad, hi + pad];
  }

  function strip(f) {
    var e = extent(f.rows), W = 200;
    var x = function (v) { return 4 + (v - e[0]) / (e[1] - e[0]) * (W - 8); };
    var s = '<svg class="strip" viewBox="0 0 ' + W + ' 26" preserveAspectRatio="none" aria-hidden="true"><line x1="0" x2="' + W + '" y1="13" y2="13" stroke="var(--hair)" stroke-width="2"/>';
    f.rows.forEach(function (r) {
      if (r.median == null || r === f.head) return;
      s += '<line x1="' + x(r.median - (r.err_low || 0)) + '" x2="' + x(r.median + (r.err_high || 0)) + '" y1="13" y2="13" stroke="var(--muted)" stroke-opacity=".35" stroke-width="6"/>';
    });
    var h = f.head;
    if (h.median != null) {
      s += '<line x1="' + x(h.median - (h.err_low || 0)) + '" x2="' + x(h.median + (h.err_high || 0)) + '" y1="13" y2="13" stroke="var(--acc)" stroke-width="4"/>';
      s += '<rect x="' + (x(h.median) - 2) + '" y="3" width="4" height="20" fill="var(--ink)"/>';
    }
    return s + "</svg>";
  }

  function niceTicks(a, b, n) {
    var span = b - a, step = Math.pow(10, Math.floor(Math.log10(span / n))), err = span / n / step;
    if (err >= 7.5) step *= 10; else if (err >= 3.5) step *= 5; else if (err >= 1.5) step *= 2;
    var ticks = [];
    for (var v = Math.ceil(a / step) * step; v <= b + step * 1e-6; v += step) ticks.push(+v.toFixed(10));
    return { ticks: ticks, step: step };
  }
  // Integer ticks for an integer axis (Nmax). When every value is even, as in
  // a parity-restricted basis, the ticks are even too.
  function intTicks(a, b, n, even) {
    var step = Math.max(1, Math.round(niceTicks(a, b, n).step));
    if (even && step % 2) step = step === 1 ? 2 : step + 1;
    var ticks = [];
    for (var v = Math.ceil(a / step) * step; v <= b; v += step) ticks.push(v);
    return { ticks: ticks, step: step };
  }
  function tickLabel(v, step) { return v.toFixed(Math.min(Math.max(0, -Math.floor(Math.log10(step))), 5)); }

  function nucleiMap(lib, big) {
    var counts = countBy(libRows(lib), function (r) { return r.nucleus; });
    var cells = Object.keys(CAT.nuclei).filter(function (n) { return CAT.nuclei[n].chart; });
    if (!cells.length) return "";
    var maxZ = 1, maxN = 1;
    cells.forEach(function (n) { var c = CAT.nuclei[n].chart; maxZ = Math.max(maxZ, c.Z); maxN = Math.max(maxN, c.N); });
    var cell = big ? 54 : 30, pad = big ? 34 : 20, top = big ? 6 : 2;
    var W = pad + maxN * cell + 6, H = top + maxZ * cell + pad + (big ? 14 : 4);
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Chart of the nuclei in the library, proton number Z against neutron number N">';
    for (var z = 1; z <= maxZ; z++) s += '<text class="nz-axis" x="' + (pad - 7) + '" y="' + (top + (maxZ - z) * cell + cell / 2 + 4) + '" text-anchor="end">' + z + "</text>";
    for (var n = 1; n <= maxN; n++) s += '<text class="nz-axis" x="' + (pad + (n - 1) * cell + cell / 2) + '" y="' + (top + maxZ * cell + 14) + '" text-anchor="middle">' + n + "</text>";
    if (big) {
      s += '<text class="nz-title" x="' + (pad + maxN * cell) + '" y="' + (top + maxZ * cell + 30) + '" text-anchor="end">N, NEUTRONS →</text>';
      s += '<text class="nz-title" transform="translate(9 ' + (top + 2) + ') rotate(90)">Z, PROTONS →</text>';
    }
    cells.forEach(function (name) {
      var c = CAT.nuclei[name].chart, x = pad + (c.N - 1) * cell, y = top + (maxZ - c.Z) * cell;
      var has = !!counts[name], cur = state.nuc === name && state.lib === lib;
      var open = has ? '<a href="' + route(lib, "n", name) + '" aria-label="' + esc(name) + ", " + plural(counts[name], "result", "results") + '">' : "";
      s += open + '<g class="nz-cell' + (has ? " has" : " empty") + (cur ? " cur" : "") + '">';
      s += '<rect x="' + (x + 2) + '" y="' + (y + 2) + '" width="' + (cell - 4) + '" height="' + (cell - 4) + '"/>';
      if (has && !cur) s += '<rect class="flag" x="' + (x + 2) + '" y="' + (y + 2) + '" width="' + (big ? 8 : 5) + '" height="' + (big ? 8 : 5) + '"/>';
      s += '<text x="' + (x + cell / 2) + '" y="' + (y + cell * (big ? 0.5 : 0.64)) + '" text-anchor="middle" font-size="' + (big ? 16 : 10.5) + '" font-weight="700">';
      s += '<tspan font-size="' + (big ? 10 : 7) + '" dy="-' + (big ? 5 : 3.5) + '">' + c.A + '</tspan><tspan dy="' + (big ? 5 : 3.5) + '">' + esc(c.symbol) + "</tspan></text>";
      if (big) s += '<text class="cnt" x="' + (x + cell / 2) + '" y="' + (y + cell * 0.82) + '" text-anchor="middle" font-size="10.5">' + (counts[name] || "–") + "</text>";
      s += "</g>" + (has ? "</a>" : "");
    });
    return s + "</svg>";
  }

  // ---- rail ------------------------------------------------------------

  function renderRail() {
    if (state.lib === "papers") return renderPaperRail();
    var fams = families(state.lib), byNuc = {};
    fams.forEach(function (f) { (byNuc[f.nucleus] = byNuc[f.nucleus] || []).push(f); });
    var h = '<div class="eyebrow">Nuclei · Z against N</div><div class="nzmap">' + nucleiMap(state.lib, false) + "</div>";
    h += '<div class="eyebrow">' + libName(state.lib) + ' families</div><nav class="tree" aria-label="Families">';
    h += '<a href="' + route(state.lib) + '"' + (!state.nuc ? ' aria-current="page"' : "") + ">Overview</a>";
    Object.keys(byNuc).sort(nucOrder).forEach(function (n) {
      var list = byNuc[n], total = list.reduce(function (a, f) { return a + f.rows.length; }, 0);
      h += '<a href="' + route(state.lib, "n", n) + '"' + (state.nuc === n && !state.fam ? ' aria-current="page"' : "") + '><span class="nuc">' + esc(nucInfo(n).label) + '</span><span class="hint">' + plural(list.length, "family", "families") + '</span><span class="c">' + total + "</span></a>";
      if (state.nuc !== n) return;
      list.forEach(function (f) {
        h += '<a class="fam" href="' + route(state.lib, "f", f.key) + '"' + (state.fam === f.key ? ' aria-current="page"' : "") + "><span>" + obsTex(f.head) + ' <span class="hint">' + stateTex(f.head) + '</span></span><span class="c">' + f.rows.length + "</span></a>";
      });
    });
    $("rail").innerHTML = h + "</nav>";
    typeset($("rail"));
  }

  function renderPaperRail() {
    var h = '<div class="eyebrow">Papers</div><nav class="tree" aria-label="Papers">';
    h += '<a href="#papers"' + (!state.paper ? ' aria-current="page"' : "") + ">All papers</a>";
    PAPERS.forEach(function (p) {
      h += '<a href="' + paperRoute(p.id) + '"' + (state.paper === p.id ? ' aria-current="page"' : "") + '><span class="nuc">' + esc(p.year || "") + '</span><span>' + esc(shortTitle(p.title)) + "</span></a>";
      if (state.paper !== p.id) return;
      p.materials.forEach(function (m) {
        h += '<a class="sub" href="' + paperRoute(p.id) + '" data-scroll="mat-' + esc(m.id) + '"><span>' + esc(m.title) + '</span><span class="c">' + (m.kind === "plot" ? "fig" : "tab") + "</span></a>";
      });
    });
    $("rail").innerHTML = h + "</nav>";
  }
  function shortTitle(t) { t = String(t || ""); return t.length > 64 ? t.slice(0, 62).replace(/\s+\S*$/, "") + "…" : t; }

  // ---- library statistics (page foot) -----------------------------------

  function libFooter(lib) {
    var rows = libRows(lib);
    if (!rows.length) return "";
    var c = countBy(rows, function (r) { return r.status; });
    var present = STATUS_ORDER.filter(function (s) { return c[s]; });
    return '<footer class="foot" aria-label="Library statistics">' +
      "<span><b>" + rows.length + "</b> results</span>" +
      "<span><b>" + families(lib).length + "</b> families</span>" +
      "<span><b>" + uniq(rows.map(function (r) { return r.ensemble; })).length + "</b> trained ensembles</span>" +
      '<span class="statusbar" title="Curation status">' + present.map(function (s) { return '<span class="st-' + s + '" style="width:' + (c[s] / rows.length * 100) + '%"></span>'; }).join("") + "</span>" +
      '<span class="legend">' + present.map(function (s) { return '<span class="inline"><span class="dot st-' + s + '"></span>' + s + " <b>" + c[s] + "</b></span>"; }).join("") + "</span>" +
      '<span class="spacer"></span><span>Built ' + esc(CAT.generated) + "</span></footer>";
  }

  // ---- overview --------------------------------------------------------

  function famRow(f) {
    var h = f.head;
    return '<a class="famrow" href="' + route(state.lib, "f", f.key) + '">' +
      '<div><div class="obs">' + esc(nucInfo(f.nucleus).label) + " " + obsTex(h) + (h.units ? ' <span class="hint">' + esc(units(h.units)) + "</span>" : "") + '</div><div class="meta">' + stateTex(h) + (h.reference_nucleus ? " · vs " + esc(h.reference_nucleus) : "") + "</div></div>" +
      '<div class="chips">' + f.potentials.map(function (p) { return '<span class="tag">' + esc(p) + "</span>"; }).join("") + "</div>" +
      '<div><div class="val">' + esc(h.value_label) + '</div><div class="meta"><span class="dot st-' + h.status + '"></span> ' + esc(h.selection_set) + " · Nmax " + win(h.nmax) + "</div></div>" +
      "<div>" + strip(f) + "</div>" +
      '<div class="n">' + plural(f.rows.length, "result", "results") + "<br>" + f.ensembles + " ens.</div></a>";
  }

  function renderOverview() {
    var rows = libRows(state.lib), fams = families(state.lib);
    var lede = state.lib === "legacy"
      ? "Results from the old TensorFlow cluster scripts, kept apart from the current pipeline."
      : "Results from the current ensemble pipeline.";
    var h = '<div class="stack"><div class="hero"><div class="intro"><div class="eyebrow">Library</div><h1 class="caps" style="margin-top:8px">' + libName(state.lib) + ' library</h1><p class="lede">' + lede + " Pick a nucleus on the chart or in the list.</p>";
    var other = state.lib === "legacy" ? "modern" : "legacy";
    h += '<div class="btnrow" style="margin-top:20px"><a class="btn" href="' + route(other) + '">' + libName(other) + " library</a>" + (PAPERS.length ? '<a class="btn" href="#papers">Papers</a>' : "") + "</div></div>";
    if (!rows.length) return ($("main").innerHTML = h + '</div><p class="empty">No ' + state.lib + " results yet.</p></div>");
    h += '<div class="panel"><div class="panel-h"><h2>Chart of nuclei</h2><span class="hint">The number in each cell is how many results it has.</span></div><div class="panel-b nzmap">' + nucleiMap(state.lib, true) + "</div></div></div>";
    var recent = fams.slice().sort(function (a, b) { return String(b.latest).localeCompare(String(a.latest)); }).slice(0, 8);
    h += '<div class="panel"><div class="panel-h"><h2>Most recent runs</h2></div><div class="fams">' + recent.map(famRow).join("") + "</div></div></div>";
    $("main").innerHTML = h + libFooter(state.lib);
  }

  // ---- nucleus ---------------------------------------------------------

  function renderNucleus() {
    var fams = families(state.lib).filter(function (f) { return f.nucleus === state.nuc; });
    var label = nucInfo(state.nuc).label;
    if (!fams.length) return ($("main").innerHTML = '<p class="empty">No ' + state.lib + " results for " + esc(label) + '. <a href="' + route(state.lib) + '">Back to the overview</a>.</p>');
    var total = fams.reduce(function (a, f) { return a + f.rows.length; }, 0);
    var h = '<div class="stack"><div><div class="crumbs"><a href="' + route(state.lib) + '">' + libName(state.lib) + "</a><span>/</span><span>" + esc(label) + "</span></div>";
    h += "<h1>" + esc(label) + '</h1><p class="lede">' + plural(fams.length, "family", "families") + ", " + plural(total, "result", "results") + ". Each row is one state and observable with its headline value. The strip shows where every other variant lands.</p></div>";
    var byState = {}, order = [];
    fams.forEach(function (f) { var k = f.head.state_label; if (!byState[k]) { byState[k] = []; order.push(k); } byState[k].push(f); });
    h += '<div class="panel fams">';
    order.forEach(function (k) { h += '<div class="statedivider">' + stateTex(byState[k][0].head) + "</div>" + byState[k].map(famRow).join(""); });
    h += "</div>";
    var other = state.lib === "legacy" ? "modern" : "legacy";
    var twins = families(other).filter(function (f) { return f.nucleus === state.nuc; });
    if (twins.length) h += '<p class="hint">' + esc(label) + " also has " + plural(twins.length, "family", "families") + ' in the <a href="' + route(other, "n", state.nuc) + '">' + other + " library</a>.</p>";
    $("main").innerHTML = h + "</div>";
  }

  // ---- family ----------------------------------------------------------

  function facetDefs(f) {
    var sets = uniq(f.rows.map(function (r) { return r.selection_set; }));
    var order = CAT.headline_order;
    sets.sort(function (a, b) {
      var ia = order.indexOf(a), ib = order.indexOf(b);
      return ((ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)) || String(a).localeCompare(String(b));
    });
    return [
      { key: "selection_set", label: "Selection set", vals: sets, get: function (r) { return r.selection_set; } },
      { key: "nmax_from", label: "Nmax from", vals: uniq(f.rows.map(function (r) { return r.nmax[0]; })).sort(function (a, b) { return a - b; }), get: function (r) { return r.nmax[0]; }, show: num },
      { key: "potential", label: "Potential", vals: uniq(f.rows.map(function (r) { return r.potential; })), get: function (r) { return r.potential; } },
      { key: "schedule", label: "LR schedule", vals: uniq(f.rows.map(function (r) { return r.lr_schedule_label; })), get: function (r) { return r.lr_schedule_label; } },
      { key: "status", label: "Status", vals: STATUS_ORDER.filter(function (s) { return f.rows.some(function (r) { return r.status === s; }); }), get: function (r) { return r.status; } },
      { key: "tags", label: "Tags", vals: uniq([].concat.apply([], f.rows.map(function (r) { return r.tags; }))).sort(), get: function (r) { return r.tags; } },
      { key: "papers", label: "Used in", vals: uniq([].concat.apply([], f.rows.map(function (r) { return r.papers.map(function (p) { return p.title; }); }))), get: function (r) { return r.papers.map(function (p) { return p.title; }); } }
    ];
  }
  function matches(def, r, value) {
    var v = def.get(r);
    return Array.isArray(v) ? v.indexOf(value) >= 0 : v === value;
  }
  function passes(r, defs, skip) {
    return defs.every(function (def) {
      if (def.key === skip) return true;
      var on = state.facets[def.key];
      if (!on || !on.length) return true;
      // Several chips in one group widen it (any of them); groups narrow.
      return on.some(function (value) { return matches(def, r, value); });
    });
  }

  function scanPlot(f, rows, sets, xmode) {
    var W = 760, H = 310, L = 70, R = 16, T = 16, B = 46;
    var byDate = xmode === "date";
    var pts = rows.filter(function (r) { return r.median != null && (byDate ? r.run_datetime : r.nmax[1] != null); });
    if (!pts.length) return '<p class="hint">Nothing to draw for these filters.</p>';
    var xv = byDate ? function (r) { return Date.parse(r.run_datetime); } : function (r) { return r.nmax[1]; };
    var xs = pts.map(xv), x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    if (byDate) {
      if (x1 - x0 < 1e-9) { x0 -= 864e5 * 15; x1 += 864e5 * 15; }
      var xp = (x1 - x0) * 0.05; x0 -= xp; x1 += xp;
    } else {
      // Nmax is an integer: pad by whole steps so the edges stay on integers.
      x0 -= 1; x1 += 1;
    }
    var e = extent(pts), clipped = 0;
    if (state.zoom && pts.length > 6) {
      var ms = pts.map(function (r) { return r.median; }).sort(function (a, b) { return a - b; });
      var q = function (p) { return ms[Math.round(p * (ms.length - 1))]; };
      var a = q(0.1), b = q(0.9), pad = Math.max((b - a) * 0.6, Math.abs(a) * 0.002, 1e-9);
      if (a - pad > e[0] || b + pad < e[1]) {
        e = [Math.max(e[0], a - pad), Math.min(e[1], b + pad)];
        clipped = pts.filter(function (r) { return r.median < e[0] || r.median > e[1]; }).length;
      }
    }
    var sx = function (v) { return L + (v - x0) / (x1 - x0) * (W - L - R); };
    var sy = function (v) { return Math.max(T - 6, Math.min(H - B + 6, T + (e[1] - v) / (e[1] - e[0]) * (H - T - B))); };
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Values against ' + (byDate ? "run date" : "upper Nmax bound") + '">';
    var yt = niceTicks(e[0], e[1], 5);
    s += '<g class="grid">' + yt.ticks.map(function (v) { return '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + sy(v) + '" y2="' + sy(v) + '"/>'; }).join("") + "</g>";
    s += '<line class="axis" x1="' + L + '" x2="' + L + '" y1="' + T + '" y2="' + (H - B) + '"/><line class="axis" x1="' + L + '" x2="' + (W - R) + '" y1="' + (H - B) + '" y2="' + (H - B) + '"/><g class="ax">';
    s += yt.ticks.map(function (v) { return '<text x="' + (L - 8) + '" y="' + (sy(v) + 4) + '" text-anchor="end">' + tickLabel(v, yt.step) + "</text>"; }).join("");
    if (byDate) {
      var y0 = new Date(x0).getUTCFullYear(), y1 = new Date(x1).getUTCFullYear(), every = y1 - y0 > 1 ? 6 : 3;
      for (var yy = y0; yy <= y1; yy++) for (var mm = 0; mm < 12; mm += every) {
        var t = Date.UTC(yy, mm, 1);
        if (t >= x0 && t <= x1) s += '<text x="' + sx(t) + '" y="' + (H - B + 18) + '" text-anchor="middle">' + new Date(t).toLocaleString("en", { month: "short", timeZone: "UTC" }) + " " + yy + "</text>";
      }
    } else {
      var even = xs.every(function (v) { return v % 2 === 0; });
      var xt = intTicks(x0, x1, 8, even);
      s += xt.ticks.map(function (v) { return '<line x1="' + sx(v) + '" x2="' + sx(v) + '" y1="' + (H - B) + '" y2="' + (H - B + 5) + '" stroke="var(--ink)" stroke-width="2"/><text x="' + sx(v) + '" y="' + (H - B + 19) + '" text-anchor="middle">' + v + "</text>"; }).join("");
    }
    s += "</g>";
    s += '<text class="lab" x="' + ((L + W - R) / 2) + '" y="' + (H - 6) + '" text-anchor="middle">' + (byDate ? "Run date" : "Upper Nmax of the training window") + "</text>";
    s += '<text class="lab" transform="translate(14 ' + ((T + H - B) / 2) + ') rotate(-90)" text-anchor="middle">' + esc(f.head.observable_label) + (f.head.units ? " (" + esc(units(f.head.units)) + ")" : "") + "</text>";
    pts.forEach(function (r) {
      var i = sets.indexOf(r.selection_set), off = sets.length > 1 ? (i - (sets.length - 1) / 2) * 6 : 0;
      var x = sx(xv(r)) + off, y = sy(r.median), col = seriesColor(i);
      var top = sy(r.median + (r.err_high || 0)), bottom = sy(r.median - (r.err_low || 0));
      s += '<g class="pt" data-id="' + esc(r.id) + '">';
      if (r.median > e[1] || r.median < e[0]) {
        var up = r.median > e[1], edge = up ? T - 2 : H - B + 2;
        s += '<path d="M' + (x - 5) + " " + (up ? edge + 7 : edge - 7) + "L" + x + " " + edge + "L" + (x + 5) + " " + (up ? edge + 7 : edge - 7) + 'Z" fill="' + col + '"/>';
      } else {
        if (r.headline) s += '<circle class="halo" cx="' + x + '" cy="' + y + '" r="9"/>';
        s += '<line x1="' + x + '" x2="' + x + '" y1="' + top + '" y2="' + bottom + '" stroke="' + col + '" stroke-width="1.6"/>';
        s += marker(i, x, y, r.headline ? 4.6 : 4, col);
      }
      if (state.sel === r.id) s += '<circle cx="' + x + '" cy="' + y + '" r="11" fill="none" stroke="var(--ink)" stroke-width="2"/>';
      s += '<rect x="' + (x - 7) + '" y="' + (Math.min(top, y) - 5) + '" width="14" height="' + (Math.abs(bottom - top) + 10) + '" fill="transparent"/></g>';
    });
    s += "</svg>";
    if (clipped) s += '<p class="hint">' + plural(clipped, "value is", "values are") + ' off the scale and drawn as triangles at the edge. <button type="button" class="chip" data-zoom="off">Show the full range</button></p>';
    else if (!state.zoom) s += '<p class="hint"><button type="button" class="chip" data-zoom="on">Zoom to the bulk of the values</button></p>';
    return s;
  }

  function renderFamily() {
    var f = family(state.lib, state.fam);
    if (!f) return ($("main").innerHTML = '<p class="empty">That family is not in the ' + state.lib + ' library. <a href="' + route(state.lib) + '">Back to the overview</a>.</p>');
    if (state.facetFam !== f.key) { state.facets = {}; state.facetFam = f.key; state.xaxis = null; }
    var defs = facetDefs(f), sets = defs[0].vals;
    var rows = f.rows.filter(function (r) { return passes(r, defs); });
    var xmode = state.xaxis || (uniq(f.rows.map(function (r) { return r.nmax[1]; })).length > 1 ? "nmax" : "date");
    var h = f.head, label = nucInfo(f.nucleus).label;

    var o = '<div class="stack"><div><div class="crumbs"><a href="' + route(state.lib) + '">' + libName(state.lib) + '</a><span>/</span><a href="' + route(state.lib, "n", f.nucleus) + '">' + esc(label) + "</a><span>/</span><span>" + obsTex(h) + "</span></div>";
    o += "<h1>" + esc(label) + " " + stateTex(h) + " " + obsTex(h) + "</h1></div>";

    o += '<div class="panel"><div class="headline"><div class="bar"></div><div class="body-h"><div class="eyebrow">Headline value</div><div class="bigval" style="margin-top:10px">' + esc(h.value_label) + "<small>" + esc(units(h.units)) + '</small></div><p class="rule" style="margin-top:10px"><span class="dot st-' + h.status + '"></span> ' + esc(h.status) + " · " + esc(h.selection_set) + " · Nmax " + win(h.nmax) + (h.potential ? " · " + esc(h.potential) : "") + " · " + esc(h.run_date_label) + '</p></div><div class="act"><a class="btn primary" href="' + route(state.lib, "r", h.id) + '">Open</a></div></div>';
    o += '<div class="panel-b" style="border-top:1px solid var(--hair)"><p class="rule">' + (h.pinned ? "Pinned with <code>headline = true</code> in annotations.toml." : "Picked by rule: published first, then the selection set in this order: " + CAT.headline_order.map(esc).join(" › ") + ", then the newest run. Add <code>headline = true</code> to a result in annotations.toml to pin a different one.") + "</p></div></div>";

    o += '<div class="panel"><div class="panel-h"><h2>Scan</h2><div class="chips"><button type="button" class="chip" data-x="nmax" aria-pressed="' + (xmode === "nmax") + '">by Nmax window</button><button type="button" class="chip" data-x="date" aria-pressed="' + (xmode === "date") + '">by run date</button></div><span class="hint">Colour and shape are the selection set; the yellow disc marks the headline. Bars are the asymmetric uncertainty. Click a point to open it.</span></div><div class="panel-b plot">' + scanPlot(f, rows, sets, xmode) + "</div></div>";

    var groups = defs.filter(function (d) { return d.vals.length > 1 || (d.key === "papers" && d.vals.length); });
    if (groups.length) {
      o += '<div class="panel"><div class="panel-h"><h2>Filter</h2><span class="hint">' + rows.length + " of " + f.rows.length + ' results</span><span class="spacer"></span><button type="button" class="btn" data-reset="1">Clear filters</button></div><div class="panel-b stack" style="gap:10px">';
      groups.forEach(function (def) {
        var on = state.facets[def.key] || [];
        o += '<div class="facetgrp"><span>' + def.label + '</span><div class="chips">' + def.vals.map(function (v, i) {
          var n = f.rows.filter(function (r) { return passes(r, defs, def.key) && matches(def, r, v); }).length;
          var sw = def.key === "selection_set" ? glyph(i) : def.key === "status" ? '<span class="dot st-' + v + '"></span>' : "";
          return '<button type="button" class="chip" data-facet="' + def.key + '" data-index="' + i + '" aria-pressed="' + (on.indexOf(v) >= 0) + '">' + sw + esc(def.show ? def.show(v) : v) + ' <span class="c">' + n + "</span></button>";
        }).join("") + "</div></div>";
      });
      o += "</div></div>";
    }

    var byEns = {}, ensOrder = [];
    rows.forEach(function (r) { if (!byEns[r.ensemble]) { byEns[r.ensemble] = []; ensOrder.push(r.ensemble); } byEns[r.ensemble].push(r); });
    var ens = ensOrder.map(function (k) { return byEns[k]; });
    ens.sort(function (a, b) { return ((a[0].nmax[0] || 0) - (b[0].nmax[0] || 0)) || ((a[0].nmax[1] || 0) - (b[0].nmax[1] || 0)) || String(b[0].run_datetime).localeCompare(String(a[0].run_datetime)); });
    var shown = sets.filter(function (s) { return rows.some(function (r) { return r.selection_set === s; }); });
    var showPot = f.potentials.length > 1;
    var showLr = uniq(f.rows.map(function (r) { return r.lr_schedule_label; })).length > 1;
    o += '<div class="panel"><div class="panel-h"><h2>Ensembles</h2><span class="hint">One row per trained ensemble, one column per selection set: ' + rows.length + " results in " + ens.length + ' rows. The value underlined in yellow is the family headline.</span></div><div class="tablewrap"><table class="pivot"><thead><tr><th>Run</th><th>Nmax</th><th>ħΩ</th>' + (showPot ? "<th>Potential</th>" : "") + (showLr ? "<th>LR schedule</th>" : "");
    o += shown.map(function (s) { return "<th>" + glyph(sets.indexOf(s)) + esc(s) + "</th>"; }).join("") + "<th>Used in</th></tr></thead><tbody>";
    ens.forEach(function (g) {
      var r0 = g[0], used = [];
      g.forEach(function (r) { r.papers.forEach(function (p) { if (!used.some(function (u) { return u.id === p.id; })) used.push(p); }); });
      o += '<tr><td class="mono">' + esc(r0.run_date_label) + '</td><td class="mono">' + win(r0.nmax) + '</td><td class="mono">' + win(r0.homega) + "</td>" + (showPot ? "<td>" + esc(r0.potential) + "</td>" : "") + (showLr ? '<td title="' + esc(r0.lr_schedule_detail || "") + '">' + esc(r0.lr_schedule_label || "–") + "</td>" : "");
      shown.forEach(function (s) {
        var cell = g.filter(function (r) { return r.selection_set === s; });
        o += "<td>" + (cell.length ? cell.map(function (r) {
          return '<button type="button" class="cell' + (r.headline ? " head" : "") + (state.sel === r.id ? " sel" : "") + '" data-open="' + esc(r.id) + '" title="' + esc(r.status) + '"><span class="dot st-' + r.status + '"></span>' + esc(r.value_label) + "</button>";
        }).join("<br>") : '<span class="hint">–</span>') + "</td>";
      });
      o += '<td><span class="chips">' + used.map(paperChip).join("") + "</span></td></tr>";
    });
    o += "</tbody></table></div></div>";

    var figs = CAT.figures.filter(function (fig) { return f.rows.some(function (r) { return fig.results.indexOf(r.id) >= 0; }); });
    if (figs.length) o += '<div class="panel"><div class="panel-h"><h2>Comparison figures</h2></div><div class="panel-b thumbs wide">' + figs.map(figureCard).join("") + "</div></div>";

    var other = state.lib === "legacy" ? "modern" : "legacy", twin = family(other, f.key);
    if (twin) o += '<div class="panel"><div class="panel-b"><b>Also computed with ' + other + ' code.</b> <span class="hint">' + plural(twin.rows.length, "result", "results") + ", headline " + esc(twin.head.value_label) + '.</span> <a class="btn" href="' + route(other, "f", f.key) + '">Open in ' + other + "</a></div></div>";

    $("main").innerHTML = o + "</div>";
  }

  function figureCard(fig) {
    return '<a class="thumb" href="' + href(fig.href) + '">' + (fig.image ? '<img src="' + href(fig.href) + '" alt="" loading="lazy">' : "") + "<span><b>" + esc(fig.title) + "</b>" + (fig.caption ? " · " + esc(fig.caption) : "") + "</span></a>";
  }

  // ---- papers ------------------------------------------------------------

  function tallyOf(p) {
    var t = { checks: 0, ok: 0, bad: 0, derived: 0 };
    p.materials.forEach(function (m) {
      m.checks.forEach(function (c) {
        t.checks++;
        if (c.state === "ok") t.ok++;
        else if (c.state === "mismatch" || c.state === "nocell" || c.state === "missing") t.bad++;
        else if (c.state === "derived") t.derived++;
      });
    });
    t.bad += p.loose.filter(function (c) { return c.state === "missing"; }).length;
    t.issues = ISSUES.filter(function (i) { return i.paper === p.id; }).length;
    return t;
  }
  function authors(text) {
    // BibTeX "Last, First and Last, First": shown as "First Last, First Last".
    return String(text || "").split(/\s+and\s+/).map(function (a) {
      var parts = a.split(",");
      return (parts.length === 2 ? parts[1].trim() + " " + parts[0].trim() : a.trim()).replace(/[{}]/g, "");
    }).filter(Boolean).join(", ");
  }
  function issueList(list) {
    if (!list.length) return '<div class="panel-b"><span class="clean">papers.json, the tables and the linked results agree. No problems found.</span></div>';
    return '<ul class="issues">' + list.map(function (i) { return '<li><span class="sev sev-' + esc(i.severity) + '">' + esc(i.severity) + "</span><span>" + esc(i.message) + "</span></li>"; }).join("") + "</ul>";
  }

  function renderPapers() {
    var h = '<div class="stack"><div><div class="eyebrow">Paper storage</div><h1 class="caps" style="margin-top:8px">Papers</h1><p class="lede">Published articles and the stored results behind their numbers. Each printed number that names a result is compared with the stored median, so a wrong link or a changed result shows up here.</p></div>';
    if (!CAT.papers) {
      $("main").innerHTML = h + '<div class="panel"><div class="panel-b"><p>This explorer was built without papers. Rebuild it with</p><pre class="source">python -m results_library.cli explorer --with-papers --bibliography path/to/my_publications.bib</pre><p class="hint">That rewrites only explorer.html and explorer/; the catalog, the classic site and paper-site/ stay as they are.</p></div></div></div>';
      return;
    }
    h += '<div class="panel"><div class="panel-h"><h2>Checks</h2><span class="hint">From the paper build: citations, files, and linked numbers.</span></div>' + issueList(ISSUES) + "</div>";
    h += '<div class="panel"><div class="panel-h"><h2>Articles</h2></div><div>';
    if (!PAPERS.length) h += '<p class="empty">No papers are listed in papers.json.</p>';
    PAPERS.forEach(function (p) {
      var t = tallyOf(p);
      var month = p.year_label && p.year_label !== p.year ? p.year_label.replace(p.year, "").trim() : "";
      h += '<a class="paperrow" href="' + paperRoute(p.id) + '"><div class="yr">' + esc(p.year || "–") + (month ? "<small>" + esc(month) + "</small>" : "") + "</div>";
      h += '<div><div class="t">' + esc(p.title) + '</div><div class="who">' + esc(authors(p.authors)) + (p.journal ? ' · <i>' + esc(p.journal) + "</i>" : "") + "</div>";
      h += '<div class="chips">' + p.nuclei.map(function (n) { return '<span class="tag">' + esc(n) + "</span>"; }).join("") + p.potentials.map(function (n) { return '<span class="tag">' + esc(n) + "</span>"; }).join("") + "</div></div>";
      h += '<div class="tally"><span><b>' + p.materials.length + "</b><i>materials</i></span><span><b>" + p.results.length + "</b><i>results</i></span><span><b>" + t.ok + "</b><i>agree</i></span>" + '<span class="' + (t.bad ? "bad" : "") + '"><b>' + t.bad + "</b><i>problems</i></span></div></a>";
    });
    h += "</div></div></div>";
    var mats = PAPERS.reduce(function (a, p) { return a + p.materials.length; }, 0);
    var links = PAPERS.reduce(function (a, p) { return a + p.results.length; }, 0);
    h += '<footer class="foot"><span><b>' + PAPERS.length + "</b> papers</span><span><b>" + mats + "</b> tables and figures</span><span><b>" + links + '</b> linked results</span><span class="spacer"></span><span>Built ' + esc(CAT.generated) + "</span></footer>";
    $("main").innerHTML = h;
  }

  function checkState(m, result, row) {
    var hit = m.checks.filter(function (c) { return c.result === result && c.row === row; })[0] || m.checks.filter(function (c) { return c.result === result; })[0];
    return hit ? hit.state : "linked";
  }

  function materialPanel(p, m) {
    var o = '<section class="panel material" id="mat-' + esc(m.id) + '"><div class="panel-h"><h2>' + esc(m.title) + '</h2><span class="kind">' + (m.kind === "plot" ? "figure" : "table") + '</span><span class="spacer"></span><div class="btnrow">';
    if (m.pdf_page && p.pdf) o += '<a class="btn" href="' + href(p.pdf) + "#page=" + m.pdf_page + '">PDF p. ' + m.pdf_page + "</a>";
    if (m.file) o += '<a class="btn" href="' + href(m.file) + '">Source file</a>';
    if (m.latex) o += '<button type="button" class="btn" data-copy-mat="' + esc(p.id) + "|" + esc(m.id) + '">Copy LaTeX</button>';
    o += "</div></div>";
    if (m.image) o += '<div class="panel-b figure"><img src="' + href(m.image) + '" alt="' + esc(m.title) + '" loading="lazy" data-pimg="' + esc(m.id) + '"></div>';
    if (m.caption) o += '<div class="panel-b"><p class="caption">' + esc(m.caption) + "</p></div>";
    if (m.rows.length) {
      o += '<div class="tablewrap"><table class="pivot grid"><thead><tr>' + m.columns.map(function (c) { return "<th>" + tex(c.latex, c.text) + "</th>"; }).join("") + "</tr></thead><tbody>";
      m.rows.forEach(function (row, ri) {
        o += "<tr>" + row.map(function (cell) {
          var body = tex(cell.latex, cell.text);
          if (!cell.result) return '<td class="mono">' + body + "</td>";
          var st = checkState(m, cell.result, ri);
          return '<td class="mono linked st-' + st + (state.sel === cell.result ? " sel" : "") + '"><button type="button" data-open="' + esc(cell.result) + '" title="' + esc(st) + " · " + esc(cell.result) + '">' + body + "</button></td>";
        }).join("") + "</tr>";
      });
      o += "</tbody></table></div>";
    }
    if (m.checks.length) {
      var c = countBy(m.checks, function (x) { return x.state; });
      var bad = (c.mismatch || 0) + (c.nocell || 0) + (c.missing || 0);
      var summary = Object.keys(c).map(function (k) { return c[k] + " " + k; }).join(" · ");
      o += '<div class="panel-b"><details' + (bad ? " open" : "") + "><summary>Linked results · " + esc(summary) + '</summary><div class="tablewrap" style="margin-top:8px"><table class="pivot"><thead><tr><th>Number</th><th>Printed</th><th>Stored</th><th>Check</th><th>Note</th></tr></thead><tbody>';
      m.checks.forEach(function (x) {
        o += '<tr><td><button type="button" class="cell" data-open="' + esc(x.result) + '">' + esc(x.label) + '</button></td><td class="mono">' + esc(x.printed || "–") + '</td><td class="mono">' + esc(x.stored || "–") + '</td><td><span class="verdict st-' + esc(x.state) + '">' + esc(x.state === "nocell" ? "no cell" : x.state) + "</span></td><td class=\"hint\">" + esc(x.note) + "</td></tr>";
      });
      o += "</tbody></table></div></details></div>";
    }
    if (m.latex) o += '<div class="panel-b"><details><summary>LaTeX source · ' + esc(m.latex_path) + '</summary><pre class="source">' + esc(m.latex) + "</pre></details></div>";
    return o + "</section>";
  }

  function renderPaper() {
    var p = PAPER_BY_ID[state.paper];
    if (!p) return ($("main").innerHTML = '<p class="empty">That paper is not in papers.json. <a href="#papers">Back to the papers</a>.</p>');
    var t = tallyOf(p);
    var h = '<div class="stack"><div><div class="crumbs"><a href="#papers">Papers</a><span>/</span><span>' + esc(p.id) + "</span></div>";
    h += '<h1 style="font-size:28px;max-width:40ch">' + esc(p.title) + "</h1>";
    h += '<p class="cite">' + esc(authors(p.authors));
    if (p.journal) h += ' · <span class="journal">' + esc(p.journal) + "</span>";
    if (p.volume) h += " " + esc(p.volume);
    if (p.pages) h += ", " + esc(String(p.pages).replace(/-{1,2}/g, "–"));
    if (p.year_label) h += " (" + esc(p.year_label) + ")";
    h += "</p>";
    if (!p.has_citation) h += '<p class="hint">No bibliography entry was read for this paper, so the title is the one in papers.json. Pass <code>--bibliography</code> to show the citation.</p>';
    h += '<div class="btnrow" style="margin-top:14px">' + (p.doi ? '<a class="btn" href="https://doi.org/' + esc(p.doi) + '">DOI ' + esc(p.doi) + "</a>" : "") + (p.pdf ? '<a class="btn primary" href="' + href(p.pdf) + '">Open PDF</a>' : "") + "</div></div>";
    h += '<div class="tally" style="align-self:start"><span><b>' + p.materials.length + "</b><i>materials</i></span><span><b>" + p.results.length + "</b><i>results</i></span><span><b>" + t.ok + "</b><i>agree</i></span><span><b>" + t.derived + '</b><i>derived</i></span><span class="' + (t.bad ? "bad" : "") + '"><b>' + t.bad + "</b><i>problems</i></span></div>";
    var own = ISSUES.filter(function (i) { return i.paper === p.id; });
    if (own.length) h += '<div class="panel"><div class="panel-h"><h2>Problems</h2></div>' + issueList(own) + "</div>";
    h += p.materials.map(function (m) { return materialPanel(p, m); }).join("");
    if (p.loose.length) {
      h += '<div class="panel"><div class="panel-h"><h2>Other linked results</h2><span class="hint">Links that name no table or figure of this paper.</span></div><div class="panel-b chips">' + p.loose.map(function (x) { return '<button type="button" class="chip" data-open="' + esc(x.result) + '">' + esc(x.label) + "</button>"; }).join("") + "</div></div>";
    }
    $("main").innerHTML = h + "</div>";
  }

  // ---- side panel ------------------------------------------------------

  function renderInspector() {
    var panel = $("insp"), layout = $("layout");
    var r = state.sel && BY_ID[state.sel];
    if (!r) {
      panel.hidden = true; layout.classList.remove("has-insp");
      if (state.sel) { panel.hidden = false; layout.classList.add("has-insp"); panel.innerHTML = '<button type="button" class="close" data-close="1" aria-label="Close">×</button><div class="eyebrow">Result</div><h2>Not in the catalog</h2><p class="hint">The paper links to</p><div class="id">' + esc(state.sel) + '</div><p class="hint">which is not among the stored results. Check the id in papers.json.</p>'; }
      return;
    }
    panel.hidden = false; layout.classList.add("has-insp");
    var siblings = ROWS.filter(function (x) { return x.ensemble === r.ensemble && x.lineage === r.lineage && x.id !== r.id; });
    var o = '<button type="button" class="close" data-close="1" aria-label="Close">×</button><div class="eyebrow">' + libName(r.lineage) + " result" + (r.headline ? " · family headline" : "") + "</div>";
    o += "<h2>" + esc(r.title || "") + (r.title ? "" : esc(nucInfo(r.nucleus).label) + " " + stateTex(r) + " " + obsTex(r)) + "</h2>";
    o += '<div class="bigval" style="font-size:28px;margin:14px 0 8px">' + esc(r.value_label) + "<small>" + esc(units(r.units)) + "</small></div>";
    o += '<p class="rule"><span class="dot st-' + r.status + '"></span> ' + esc(r.status) + "</p>";
    o += '<div class="btnrow" style="margin-top:14px">' + (state.lib === "papers" ? '<a class="btn primary" href="' + route(r.lineage, "r", r.id) + '">Open family</a>' : "") + '<button type="button" class="btn" data-copy="latex">Copy LaTeX</button><button type="button" class="btn" data-copy="tsv">Copy TSV</button><button type="button" class="btn" data-copy="annotation">Copy annotation</button></div>';

    o += '<div class="sec"><dl class="kv"><dt>Run</dt><dd class="mono">' + esc(r.run_date_label) + "</dd><dt>Selection set</dt><dd>" + esc(r.selection_set) + "</dd>" + (r.potential ? "<dt>Potential</dt><dd>" + esc(r.potential) + "</dd>" : "") + (r.lr_schedule_detail || r.lr_schedule_label ? "<dt>LR schedule</dt><dd>" + esc(r.lr_schedule_detail || r.lr_schedule_label) + '<span class="hint">Not part of the variant hash, so runs that differ only here share it.</span></dd>' : "");
    r.selection.forEach(function (item) { o += "<dt>" + esc(item[0]) + "</dt><dd>" + esc(item[1]) + hint(item[0]) + "</dd>"; });
    if (r.papers.length) o += "<dt>Published in</dt><dd><span class=\"chips\">" + r.papers.map(paperChip).join("") + "</span></dd>";
    o += "</dl></div>";

    var printed = CHECKS_BY_RESULT[r.id] || [];
    if (printed.length) {
      o += '<div class="sec"><div class="eyebrow">Printed in papers</div><table class="pivot"><tbody>' + printed.map(function (x) {
        return '<tr><td style="white-space:normal"><a href="' + paperRoute(x.paper.id) + '">' + esc(x.material ? x.material.title : x.paper.title) + '</a><div class="hint">' + esc(x.check.label) + (x.check.note ? " · " + esc(x.check.note) : "") + '</div></td><td class="mono">' + esc(x.check.printed || "") + '</td><td><span class="verdict st-' + esc(x.check.state) + '">' + esc(x.check.state === "nocell" ? "no cell" : x.check.state) + "</span></td></tr>";
      }).join("") + "</tbody></table></div>";
    }

    if (siblings.length) o += '<div class="sec"><div class="eyebrow">Same ensemble, other selection sets</div><div class="chips">' + siblings.map(function (x) { return '<button type="button" class="chip" data-open="' + esc(x.id) + '">' + esc(x.selection_set) + ' <span class="c">' + esc(x.value_label) + "</span></button>"; }).join("") + "</div></div>";

    if (r.plots.length) {
      o += '<div class="sec"><div class="eyebrow">Plots</div><div class="thumbs">' + r.plots.map(function (p, i) {
        return p.image
          ? '<button type="button" class="thumb" data-plot="' + i + '"><img src="' + href(p.href, r) + '" alt="' + esc(p.caption) + '" loading="lazy"><span>' + esc(p.caption) + "</span></button>"
          : '<a class="thumb" href="' + href(p.href, r) + '"><span>' + esc(p.caption) + "</span></a>";
      }).join("") + "</div></div>";
    }
    if (r.note) o += '<div class="sec"><div class="eyebrow">Note</div><div class="note">' + esc(r.note) + "</div></div>";
    if (r.outcome) o += '<div class="sec"><div class="eyebrow">Outcome</div><div class="note">' + esc(r.outcome) + "</div></div>";
    if (r.tags.length) o += '<div class="sec"><div class="eyebrow">Tags</div><div class="chips">' + r.tags.map(function (t) { return '<span class="tag">' + esc(t) + "</span>"; }).join("") + "</div></div>";

    var figs = CAT.figures.filter(function (fig) { return fig.results.indexOf(r.id) >= 0; });
    if (figs.length) o += '<div class="sec"><div class="eyebrow">Comparison figures</div><div class="thumbs">' + figs.map(figureCard).join("") + "</div></div>";

    o += '<div class="sec"><details><summary>Value statistics</summary><dl class="kv" style="margin-top:8px">' + r.stats.map(function (s) { return "<dt>" + esc(s[0]) + '</dt><dd class="mono">' + esc(s[1]) + hint(s[0]) + "</dd>"; }).join("") + "</dl></details></div>";
    o += '<div class="sec"><details><summary>How it was produced</summary><dl class="kv" style="margin-top:8px">' + r.provenance.map(function (p) { return "<dt>" + esc(p[0]) + "</dt><dd>" + (p[2] ? '<a href="' + href(p[2], r) + '">' + esc(p[1]) + "</a>" : esc(p[1])) + hint(p[0]) + "</dd>"; }).join("") + "</dl></details></div>";
    o += '<div class="sec"><div class="eyebrow">Files</div><ul class="files">' + r.files.map(function (file) { return '<li><a href="' + href(file.href, r) + '">' + esc(file.name) + "</a>" + (file.label ? ' <span class="hint">' + esc(file.label) + "</span>" : "") + "</li>"; }).join("") + "</ul></div>";
    o += '<div class="sec"><div class="eyebrow">Result id</div><div class="id">' + esc(r.id) + "</div></div>";
    panel.innerHTML = o;
    typeset(panel);
  }

  // ---- image viewer ----------------------------------------------------

  var viewer = null;
  function openViewer(images, index) {
    if (!images.length) return;
    viewer = { images: images, index: Math.max(0, Math.min(index, images.length - 1)) };
    drawViewer();
  }
  function resultImages(r) {
    return r.plots.filter(function (p) { return p.image; }).map(function (p) {
      return { src: href(p.href, r), caption: p.caption, links: [["Open file", href(p.href, r)]].concat(p.csv ? [["Data CSV", href(p.csv, r)]] : []), key: p };
    });
  }
  function paperImages(p) {
    return p.materials.filter(function (m) { return m.image; }).map(function (m) {
      return { src: href(m.image), caption: m.title, links: [["Open image", href(m.image)]].concat(m.file ? [["Source file", href(m.file)]] : []), key: m.id };
    });
  }
  function drawViewer() {
    if (!viewer) { $("overlay").innerHTML = ""; return; }
    var p = viewer.images[viewer.index];
    var links = p.links.map(function (l) { return '<a class="btn" href="' + l[1] + '">' + esc(l[0]) + "</a>"; }).join("");
    $("overlay").innerHTML = '<div class="viewer" data-viewer="1" role="dialog" aria-modal="true" aria-label="' + esc(p.caption) + '"><img src="' + p.src + '" alt="' + esc(p.caption) + '"><div class="bar"><button type="button" class="btn" data-step="-1" aria-label="Previous image">←</button><span>' + esc(p.caption) + " · " + (viewer.index + 1) + " of " + viewer.images.length + '</span><button type="button" class="btn" data-step="1" aria-label="Next image">→</button>' + links + '<button type="button" class="btn" data-shut="1">Close</button></div></div>';
  }

  // ---- copy ------------------------------------------------------------

  function toast(message) {
    var t = document.createElement("div");
    t.className = "toast"; t.textContent = message; document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 1500);
  }
  function copyText(text, what) {
    var fallback = function () {
      viewer = null;
      $("overlay").innerHTML = '<div class="viewer" data-viewer="1"><div class="panel" style="width:min(640px,100%)"><div class="panel-h"><h2>Copy ' + esc(what) + '</h2><span class="hint">The browser blocked the clipboard. Press Ctrl+C.</span><span class="spacer"></span><button type="button" class="btn" data-shut="1">Close</button></div><div class="panel-b"><textarea class="copyfallback" id="copy-fallback" readonly>' + esc(text) + "</textarea></div></div></div>";
      $("copy-fallback").select();
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast("Copied " + what); }, fallback);
    } else {
      // file:// pages often have no async clipboard.
      var scratch = document.createElement("textarea");
      scratch.value = text; scratch.style.position = "fixed"; scratch.style.left = "-9999px";
      document.body.appendChild(scratch); scratch.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      document.body.removeChild(scratch);
      if (ok) toast("Copied " + what); else fallback();
    }
  }
  function annotation(r) {
    var q = function (s) { return '"' + String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n") + '"'; };
    var lines = ['["' + r.id + '"]', "status  = " + q(r.status)];
    if (r.title) lines.push("title   = " + q(r.title));
    if (r.tags.length) lines.push("tags    = [" + r.tags.map(q).join(", ") + "]");
    lines.push("note    = " + q(r.note || ""), "outcome = " + q(r.outcome || ""));
    if (r.pinned) lines.push("headline = true");
    return lines.join("\n") + "\n";
  }

  // ---- routing ---------------------------------------------------------

  function decode(text) { try { return decodeURIComponent(text || ""); } catch (err) { return ""; } }
  function parseHash() {
    var parts = location.hash.replace(/^#/, "").split("/");
    state.nuc = null; state.fam = null; state.sel = null; state.paper = null;
    if (parts[0] === "papers") {
      state.lib = "papers";
      if (parts[1] === "p" && parts[2]) state.paper = decode(parts[2]);
      if (parts[3] === "r" && parts[4]) state.sel = decode(parts.slice(4).join("/"));
      return;
    }
    var lib = LIBS.indexOf(parts[0]) >= 0 ? parts[0] : "modern";
    var kind = parts[1], key = decode(parts.slice(2).join("/"));
    state.lib = lib;
    if (kind === "n" && key) state.nuc = key;
    else if (kind === "f" && key) { var f = family(lib, key); state.fam = key; state.nuc = f ? f.nucleus : null; }
    else if (kind === "r" && BY_ID[key]) { var r = BY_ID[key]; state.lib = r.lineage; state.sel = key; state.fam = r.family; state.nuc = r.nucleus; }
  }

  function render() {
    document.body.setAttribute("data-lib", state.lib);
    document.querySelectorAll("#libs button").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-lib") === state.lib)); });
    renderRail();
    if (state.lib === "papers") { if (state.paper) renderPaper(); else renderPapers(); }
    else if (state.fam) renderFamily(); else if (state.nuc) renderNucleus(); else renderOverview();
    typeset($("main"));
    renderInspector();
  }
  function redrawFamily() { renderFamily(); typeset($("main")); }
  function closeRoute() { return state.lib === "papers" ? (state.paper ? paperRoute(state.paper) : "#papers") : route(state.lib, "f", state.fam); }

  var lastView = null;
  window.addEventListener("hashchange", function () {
    parseHash(); render();
    var view = state.lib + "|" + (state.paper || state.fam || state.nuc || "");
    if (view !== lastView) $("main").scrollTop = 0;
    lastView = view;
  });

  // ---- events ----------------------------------------------------------

  document.addEventListener("click", function (event) {
    var scrollTo = event.target.closest("[data-scroll]");
    if (scrollTo) {
      var target = $(scrollTo.getAttribute("data-scroll"));
      if (target && state.paper) { event.preventDefault(); target.scrollIntoView({ block: "start" }); return; }
    }
    var img = event.target.closest("[data-pimg]");
    if (img) {
      var paper = PAPER_BY_ID[state.paper], images = paperImages(paper);
      openViewer(images, images.map(function (x) { return x.key; }).indexOf(img.getAttribute("data-pimg")));
      return;
    }
    var t = event.target.closest("button, .pt, [data-viewer]");
    if (!t) return;
    if (t.hasAttribute("data-viewer")) { if (event.target === t) { viewer = null; drawViewer(); } return; }
    if (t.hasAttribute("data-shut")) { viewer = null; drawViewer(); return; }
    if (t.hasAttribute("data-step")) { viewer.index = (viewer.index + Number(t.getAttribute("data-step")) + viewer.images.length) % viewer.images.length; drawViewer(); return; }
    if (t.closest("#libs")) { location.hash = t.getAttribute("data-lib") === "papers" ? "#papers" : route(t.getAttribute("data-lib")); return; }
    if (t.id === "theme") { toggleTheme(); return; }
    if (t.classList.contains("pt") || t.hasAttribute("data-open")) { location.hash = resultRoute(t.getAttribute("data-id") || t.getAttribute("data-open")); return; }
    if (t.hasAttribute("data-close")) { location.hash = closeRoute(); return; }
    if (t.hasAttribute("data-plot")) {
      var r0 = BY_ID[state.sel], plot = r0.plots[Number(t.getAttribute("data-plot"))], list = resultImages(r0);
      openViewer(list, list.map(function (x) { return x.key; }).indexOf(plot)); return;
    }
    if (t.hasAttribute("data-copy")) {
      var r = BY_ID[state.sel], kind = t.getAttribute("data-copy");
      if (kind === "latex") copyText(r.latex, "LaTeX");
      else if (kind === "tsv") copyText(r.tsv, "TSV");
      else copyText(annotation(r), "annotation");
      return;
    }
    if (t.hasAttribute("data-copy-mat")) {
      var ids = t.getAttribute("data-copy-mat").split("|"), pm = PAPER_BY_ID[ids[0]];
      var mat = pm && pm.materials.filter(function (m) { return m.id === ids[1]; })[0];
      if (mat) copyText(mat.latex, "LaTeX");
      return;
    }
    if (t.hasAttribute("data-facet")) {
      var f = family(state.lib, state.fam), def = facetDefs(f).filter(function (d) { return d.key === t.getAttribute("data-facet"); })[0];
      var value = def.vals[Number(t.getAttribute("data-index"))];
      var on = state.facets[def.key] = state.facets[def.key] || [], at = on.indexOf(value);
      if (at >= 0) on.splice(at, 1); else on.push(value);
      redrawFamily(); return;
    }
    if (t.hasAttribute("data-reset")) { state.facets = {}; redrawFamily(); return; }
    if (t.hasAttribute("data-x")) { state.xaxis = t.getAttribute("data-x"); redrawFamily(); return; }
    if (t.hasAttribute("data-zoom")) { state.zoom = t.getAttribute("data-zoom") === "on"; redrawFamily(); }
  });

  document.addEventListener("keydown", function (event) {
    if (viewer) {
      if (event.key === "Escape") { viewer = null; drawViewer(); }
      else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        viewer.index = (viewer.index + (event.key === "ArrowRight" ? 1 : -1) + viewer.images.length) % viewer.images.length;
        drawViewer();
      }
      return;
    }
    if (event.key === "Escape") {
      if ($("overlay").innerHTML) { $("overlay").innerHTML = ""; return; }
      if (state.sel) location.hash = closeRoute();
    }
  });

  var tip = $("tip");
  document.addEventListener("mousemove", function (event) {
    var p = event.target.closest && event.target.closest(".pt");
    if (!p) { tip.hidden = true; return; }
    var r = BY_ID[p.getAttribute("data-id")];
    tip.innerHTML = esc(r.value_label) + "<br>" + esc(r.selection_set) + "<br>Nmax " + win(r.nmax) + " · ħΩ " + win(r.homega) + (r.lr_schedule_label ? "<br>" + esc(r.lr_schedule_label) : "") + "<br>" + esc(r.run_date_label) + " · " + esc(r.status);
    tip.hidden = false;
    tip.style.left = Math.min(event.clientX + 14, window.innerWidth - 370) + "px";
    tip.style.top = event.clientY + 14 + "px";
  });

  // ---- theme -----------------------------------------------------------

  function activeTheme() {
    var pinned = document.documentElement.getAttribute("data-theme");
    if (pinned === "dark" || pinned === "light") return pinned;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function labelTheme() { $("theme").textContent = activeTheme() === "dark" ? "Light" : "Dark"; }
  function toggleTheme() {
    var next = activeTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem(THEME_KEY, next); } catch (err) { /* applies to this page only */ }
    labelTheme();
  }

  labelTheme();
  parseHash();
  lastView = state.lib + "|" + (state.paper || state.fam || state.nuc || "");
  render();
})();
