/* Explorer: groups, filters, and draws the catalog that catalog.js carries.
 *
 * Plain JS, no dependencies besides the vendored KaTeX, because the page opens
 * from a synced folder over file://. Every decision that needs a rule (which
 * result heads a family, link targets, LaTeX strings) is made by the Python
 * build; this file only reads them.
 *
 * Routes live in the hash so the back button and bookmarks work:
 *   #modern                      library overview
 *   #legacy/n/6He                one nucleus
 *   #legacy/f/<family>           one family
 *   #legacy/r/<result id>        one family, with that result in the side panel
 */

(function () {
  "use strict";

  var CAT = window.CATALOG;
  if (!CAT) {
    document.getElementById("main").innerHTML =
      '<p class="empty">explorer/catalog.js did not load. Rebuild with <code>python -m results_library.cli build</code>, and open explorer.html from a local copy of the library folder.</p>';
    return;
  }

  var ROWS = CAT.rows;
  var BY_ID = {};
  ROWS.forEach(function (r) { BY_ID[r.id] = r; });
  var LIBS = ["modern", "legacy"];
  var STATUS_ORDER = ["published", "working", "probing", "superseded"];
  var THEME_KEY = "results-theme";

  var state = { lib: "modern", nuc: null, fam: null, sel: null, facets: {}, facetFam: null, xaxis: null, zoom: true };

  // ---- helpers ---------------------------------------------------------

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function uniq(list) { var out = []; list.forEach(function (x) { if (x != null && x !== "" && out.indexOf(x) < 0) out.push(x); }); return out; }
  function countBy(list, fn) { var m = {}; list.forEach(function (x) { var k = fn(x); if (k == null) return; m[k] = (m[k] || 0) + 1; }); return m; }
  function libRows(lib) { return ROWS.filter(function (r) { return r.lineage === lib; }); }
  function libName(lib) { return lib === "legacy" ? "Legacy" : "Modern"; }
  function nucInfo(n) { return CAT.nuclei[n] || { label: n, order: [9, 999, 999] }; }
  function nucOrder(a, b) {
    var A = nucInfo(a).order, B = nucInfo(b).order;
    return (A[0] - B[0]) || (A[1] - B[1]) || (A[2] - B[2]) || String(a).localeCompare(String(b));
  }
  function units(u) { return u ? String(u).replace(/\^2/g, "²").replace(/\^4/g, "⁴").replace(/\^-1/g, "⁻¹") : ""; }
  function win(pair) { return pair && pair[0] != null ? "[" + pair[0] + ", " + pair[1] + "]" : "–"; }
  // Paths in the catalog are library-root relative, and this page sits at the
  // root, so they are used as they are, with each segment escaped.
  function href(path, r) {
    var text = String(path || "");
    if (text.indexOf("@/") === 0) text = r.bundle + text.slice(1);
    return text.split("/").map(encodeURIComponent).join("/");
  }
  function hint(label) { var h = CAT.hints[label]; return h ? '<span class="hint">' + esc(h) + "</span>" : ""; }
  function route(lib, kind, key) { return "#" + lib + (kind ? "/" + kind + "/" + encodeURIComponent(key) : ""); }

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
    var s = '<svg class="strip" viewBox="0 0 ' + W + ' 26" preserveAspectRatio="none" aria-hidden="true"><line x1="0" x2="' + W + '" y1="13" y2="13" stroke="var(--line-2)"/>';
    f.rows.forEach(function (r) {
      if (r.median == null || r === f.head) return;
      s += '<line x1="' + x(r.median - (r.err_low || 0)) + '" x2="' + x(r.median + (r.err_high || 0)) + '" y1="13" y2="13" stroke="var(--muted)" stroke-opacity=".35" stroke-width="5"/>';
    });
    var h = f.head;
    if (h.median != null) {
      s += '<line x1="' + x(h.median - (h.err_low || 0)) + '" x2="' + x(h.median + (h.err_high || 0)) + '" y1="13" y2="13" stroke="var(--acc)" stroke-width="3"/>';
      s += '<rect x="' + (x(h.median) - 1.5) + '" y="5" width="3" height="16" fill="var(--acc)"/>';
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
  function tickLabel(v, step) { return v.toFixed(Math.min(Math.max(0, -Math.floor(Math.log10(step))), 5)); }
  function seriesColor(i) { return "var(--s" + (i % 6 + 1) + ")"; }

  function nucleiMap(lib, big) {
    var counts = countBy(libRows(lib), function (r) { return r.nucleus; });
    var cells = Object.keys(CAT.nuclei).filter(function (n) { return CAT.nuclei[n].chart; });
    if (!cells.length) return "";
    var maxZ = 1, maxN = 1;
    cells.forEach(function (n) { var c = CAT.nuclei[n].chart; maxZ = Math.max(maxZ, c.Z); maxN = Math.max(maxN, c.N); });
    var cell = big ? 52 : 30, pad = big ? 26 : 18;
    var W = pad + maxN * cell + 6, H = maxZ * cell + pad + 4;
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Map of the nuclei in the library, proton number against neutron number">';
    for (var z = 1; z <= maxZ; z++) s += '<text class="nz-axis" x="' + (pad - 6) + '" y="' + ((maxZ - z) * cell + cell / 2 + 4) + '" text-anchor="end">' + z + "</text>";
    for (var n = 1; n <= maxN; n++) s += '<text class="nz-axis" x="' + (pad + (n - 1) * cell + cell / 2) + '" y="' + (maxZ * cell + pad - 4) + '" text-anchor="middle">' + n + "</text>";
    cells.forEach(function (name) {
      var c = CAT.nuclei[name].chart, x = pad + (c.N - 1) * cell, y = (maxZ - c.Z) * cell;
      var has = !!counts[name], cur = state.nuc === name && state.lib === lib;
      var open = has ? '<a href="' + route(lib, "n", name) + '" aria-label="' + esc(name) + ", " + counts[name] + ' results">' : "";
      s += open + '<g class="nz-cell' + (has ? " has" : " empty") + (cur ? " cur" : "") + '">';
      s += '<rect x="' + (x + 1.5) + '" y="' + (y + 1.5) + '" width="' + (cell - 3) + '" height="' + (cell - 3) + '" rx="' + (big ? 5 : 3) + '"/>';
      s += '<text x="' + (x + cell / 2) + '" y="' + (y + cell * (big ? 0.5 : 0.62)) + '" text-anchor="middle" font-size="' + (big ? 15 : 10.5) + '" font-weight="600">';
      s += '<tspan font-size="' + (big ? 9.5 : 7) + '" dy="-' + (big ? 5 : 3.5) + '">' + c.A + '</tspan><tspan dy="' + (big ? 5 : 3.5) + '">' + esc(c.symbol) + "</tspan></text>";
      if (big) s += '<text class="cnt" x="' + (x + cell / 2) + '" y="' + (y + cell * 0.8) + '" text-anchor="middle" font-size="10.5">' + (counts[name] || "–") + "</text>";
      s += "</g>" + (has ? "</a>" : "");
    });
    return s + "</svg>";
  }

  // ---- rail ------------------------------------------------------------

  function renderRail() {
    var fams = families(state.lib), byNuc = {};
    fams.forEach(function (f) { (byNuc[f.nucleus] = byNuc[f.nucleus] || []).push(f); });
    var h = '<div class="eyebrow">Nuclei · Z vs N</div><div class="nzmap">' + nucleiMap(state.lib, false) + "</div>";
    h += '<div class="eyebrow">' + libName(state.lib) + ' families</div><nav class="tree" aria-label="Families">';
    h += '<a href="' + route(state.lib) + '"' + (!state.nuc ? ' aria-current="page"' : "") + ">Overview</a>";
    Object.keys(byNuc).sort(nucOrder).forEach(function (n) {
      var list = byNuc[n], total = list.reduce(function (a, f) { return a + f.rows.length; }, 0);
      h += '<a href="' + route(state.lib, "n", n) + '"' + (state.nuc === n && !state.fam ? ' aria-current="page"' : "") + '><span class="nuc">' + esc(nucInfo(n).label) + '</span><span class="hint">' + list.length + ' fam.</span><span class="c">' + total + "</span></a>";
      if (state.nuc !== n) return;
      list.forEach(function (f) {
        h += '<a class="fam" href="' + route(state.lib, "f", f.key) + '"' + (state.fam === f.key ? ' aria-current="page"' : "") + "><span>" + obsTex(f.head) + ' <span class="hint">' + stateTex(f.head) + '</span></span><span class="c">' + f.rows.length + "</span></a>";
      });
    });
    $("rail").innerHTML = h + "</nav>";
    typeset($("rail"));
  }

  // ---- overview --------------------------------------------------------

  function famRow(f) {
    var h = f.head;
    return '<a class="famrow" href="' + route(state.lib, "f", f.key) + '">' +
      '<div><div class="obs">' + esc(nucInfo(f.nucleus).label) + " " + obsTex(h) + (h.units ? ' <span class="hint">' + esc(units(h.units)) + "</span>" : "") + '</div><div class="meta">' + stateTex(h) + (h.reference_nucleus ? " · vs " + esc(h.reference_nucleus) : "") + "</div></div>" +
      '<div class="chips">' + f.potentials.map(function (p) { return '<span class="tag">' + esc(p) + "</span>"; }).join("") + "</div>" +
      '<div><div class="val">' + esc(h.value_label) + '</div><div class="meta"><span class="dot st-' + h.status + '"></span> ' + esc(h.selection_set) + " · " + win(h.nmax) + "</div></div>" +
      "<div>" + strip(f) + "</div>" +
      '<div class="n">' + f.rows.length + (f.rows.length === 1 ? " result" : " results") + "<br>" + f.ensembles + " ens.</div></a>";
  }

  function renderOverview() {
    var rows = libRows(state.lib), fams = families(state.lib);
    var c = countBy(rows, function (r) { return r.status; });
    var present = STATUS_ORDER.filter(function (s) { return c[s]; });
    var lede = state.lib === "legacy"
      ? "Results from the old TensorFlow cluster scripts, kept apart from the current pipeline."
      : "Results from the current ensemble pipeline.";
    var h = '<div class="stack"><div><h1>' + libName(state.lib) + ' library</h1><p class="lede">' + lede + " Pick a nucleus on the map or in the list.</p></div>";
    if (!rows.length) return ($("main").innerHTML = h + '<p class="empty">No ' + state.lib + " results yet.</p></div>");
    h += '<div class="stats">' +
      '<div class="stat"><span class="eyebrow">Results</span><b>' + rows.length + "</b></div>" +
      '<div class="stat"><span class="eyebrow">Families</span><b>' + fams.length + '</b><span class="hint">nucleus · state · observable</span></div>' +
      '<div class="stat"><span class="eyebrow">Trained ensembles</span><b>' + uniq(rows.map(function (r) { return r.ensemble; })).length + "</b></div>" +
      '<div class="stat"><span class="eyebrow">Published</span><b>' + (c.published || 0) + "</b></div></div>";
    h += '<div class="panel"><div class="panel-h"><h2>Status</h2><div class="legend">' + present.map(function (s) { return '<span class="inline"><span class="dot st-' + s + '"></span>' + s + " " + c[s] + "</span>"; }).join("") + '</div></div><div class="panel-b"><div class="statusbar">' + present.map(function (s) { return '<span class="st-' + s + '" style="width:' + (c[s] / rows.length * 100) + '%"></span>'; }).join("") + "</div></div></div>";
    h += '<div class="panel"><div class="panel-h"><h2>Nuclei</h2><span class="hint">Proton number Z up, neutron number N across, sized to the nuclei in the library. The number is how many results each one has.</span></div><div class="panel-b nzmap" style="max-width:640px">' + nucleiMap(state.lib, true) + "</div></div>";
    var recent = fams.slice().sort(function (a, b) { return String(b.latest).localeCompare(String(a.latest)); }).slice(0, 8);
    h += '<div class="panel"><div class="panel-h"><h2>Most recent runs</h2></div><div class="fams">' + recent.map(famRow).join("") + "</div></div></div>";
    $("main").innerHTML = h;
  }

  // ---- nucleus ---------------------------------------------------------

  function renderNucleus() {
    var fams = families(state.lib).filter(function (f) { return f.nucleus === state.nuc; });
    var label = nucInfo(state.nuc).label;
    if (!fams.length) return ($("main").innerHTML = '<p class="empty">No ' + state.lib + " results for " + esc(label) + '. <a href="' + route(state.lib) + '">Back to the overview</a>.</p>');
    var total = fams.reduce(function (a, f) { return a + f.rows.length; }, 0);
    var h = '<div class="stack"><div><div class="crumbs"><a href="' + route(state.lib) + '">' + libName(state.lib) + "</a><span>/</span><span>" + esc(label) + "</span></div>";
    h += "<h1>" + esc(label) + '</h1><p class="lede">' + fams.length + (fams.length === 1 ? " family, " : " families, ") + total + " results. Each row is one state and observable with its headline value. The strip shows where every other variant lands.</p></div>";
    var byState = {}, order = [];
    fams.forEach(function (f) { var k = f.head.state_label; if (!byState[k]) { byState[k] = []; order.push(k); } byState[k].push(f); });
    h += '<div class="panel fams">';
    order.forEach(function (k) { h += '<div class="statedivider">' + stateTex(byState[k][0].head) + "</div>" + byState[k].map(famRow).join(""); });
    h += "</div>";
    var other = state.lib === "legacy" ? "modern" : "legacy";
    var twins = families(other).filter(function (f) { return f.nucleus === state.nuc; });
    if (twins.length) h += '<p class="hint">' + esc(label) + " also has " + twins.length + (twins.length === 1 ? " family" : " families") + ' in the <a href="' + route(other, "n", state.nuc) + '">' + other + " library</a>.</p>";
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
    var defs = [
      { key: "selection_set", label: "Selection set", vals: sets, get: function (r) { return r.selection_set; } },
      { key: "nmax_from", label: "Nmax from", vals: uniq(f.rows.map(function (r) { return r.nmax[0]; })).sort(function (a, b) { return a - b; }), get: function (r) { return r.nmax[0]; } },
      { key: "potential", label: "Potential", vals: uniq(f.rows.map(function (r) { return r.potential; })), get: function (r) { return r.potential; } },
      { key: "status", label: "Status", vals: STATUS_ORDER.filter(function (s) { return f.rows.some(function (r) { return r.status === s; }); }), get: function (r) { return r.status; } },
      { key: "tags", label: "Tags", vals: uniq([].concat.apply([], f.rows.map(function (r) { return r.tags; }))).sort(), get: function (r) { return r.tags; } },
      { key: "papers", label: "Used in", vals: uniq([].concat.apply([], f.rows.map(function (r) { return r.papers.map(function (p) { return p.title; }); }))), get: function (r) { return r.papers.map(function (p) { return p.title; }); } }
    ];
    return defs;
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
    var W = 760, H = 300, L = 66, R = 16, T = 14, B = 42;
    var pts = rows.filter(function (r) { return r.median != null && (xmode === "date" ? r.run_datetime : r.nmax[1] != null); });
    if (!pts.length) return '<p class="hint">Nothing to draw for these filters.</p>';
    var xv = xmode === "date" ? function (r) { return Date.parse(r.run_datetime); } : function (r) { return r.nmax[1]; };
    var xs = pts.map(xv), x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    if (x1 - x0 < 1e-9) { x0 -= xmode === "date" ? 864e5 * 15 : 1; x1 += xmode === "date" ? 864e5 * 15 : 1; }
    var xp = (x1 - x0) * 0.05; x0 -= xp; x1 += xp;
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
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Values against ' + (xmode === "date" ? "run date" : "upper Nmax bound") + '">';
    var yt = niceTicks(e[0], e[1], 5);
    s += '<g class="grid">' + yt.ticks.map(function (v) { return '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + sy(v) + '" y2="' + sy(v) + '"/>'; }).join("") + "</g><g class=\"ax\">";
    s += yt.ticks.map(function (v) { return '<text x="' + (L - 8) + '" y="' + (sy(v) + 4) + '" text-anchor="end">' + tickLabel(v, yt.step) + "</text>"; }).join("");
    if (xmode === "date") {
      var y0 = new Date(x0).getUTCFullYear(), y1 = new Date(x1).getUTCFullYear(), every = y1 - y0 > 1 ? 6 : 3;
      for (var yy = y0; yy <= y1; yy++) for (var mm = 0; mm < 12; mm += every) {
        var t = Date.UTC(yy, mm, 1);
        if (t >= x0 && t <= x1) s += '<text x="' + sx(t) + '" y="' + (H - B + 18) + '" text-anchor="middle">' + new Date(t).toLocaleString("en", { month: "short", timeZone: "UTC" }) + " " + yy + "</text>";
      }
    } else {
      var xt = niceTicks(x0, x1, 8);
      s += xt.ticks.map(function (v) { return '<text x="' + sx(v) + '" y="' + (H - B + 18) + '" text-anchor="middle">' + tickLabel(v, xt.step) + "</text>"; }).join("");
    }
    s += "</g>";
    s += '<text class="lab" x="' + ((L + W - R) / 2) + '" y="' + (H - 6) + '" text-anchor="middle">' + (xmode === "date" ? "Run date" : "Upper Nmax of the training window") + "</text>";
    s += '<text class="lab" transform="translate(14 ' + ((T + H - B) / 2) + ') rotate(-90)" text-anchor="middle">' + esc(f.head.observable_label) + (f.head.units ? " (" + esc(units(f.head.units)) + ")" : "") + "</text>";
    pts.forEach(function (r) {
      var i = sets.indexOf(r.selection_set), off = sets.length > 1 ? (i - (sets.length - 1) / 2) * 5 : 0;
      var x = sx(xv(r)) + off, y = sy(r.median), col = seriesColor(i);
      var top = sy(r.median + (r.err_high || 0)), bottom = sy(r.median - (r.err_low || 0));
      s += '<g class="pt" data-id="' + esc(r.id) + '">';
      s += '<line x1="' + x + '" x2="' + x + '" y1="' + top + '" y2="' + bottom + '" stroke="' + col + '" stroke-width="1.4" stroke-opacity=".75"/>';
      if (r.median > e[1] || r.median < e[0]) {
        var up = r.median > e[1], edge = up ? T - 2 : H - B + 2;
        s += '<path d="M' + (x - 5) + " " + (up ? edge + 6 : edge - 6) + "L" + x + " " + edge + "L" + (x + 5) + " " + (up ? edge + 6 : edge - 6) + 'Z" fill="' + col + '"/>';
      } else {
        s += '<circle cx="' + x + '" cy="' + y + '" r="' + (r.headline ? 5 : 4) + '" fill="' + col + '"' + (r.headline ? ' stroke="var(--ink)" stroke-width="1.5"' : "") + "/>";
      }
      if (state.sel === r.id) s += '<circle cx="' + x + '" cy="' + y + '" r="9" fill="none" stroke="var(--ink)" stroke-width="1.5"/>';
      s += '<rect x="' + (x - 7) + '" y="' + (Math.min(top, y) - 4) + '" width="14" height="' + (Math.abs(bottom - top) + 8) + '" fill="transparent"/></g>';
    });
    s += "</svg>";
    if (clipped) s += '<p class="hint">' + clipped + (clipped === 1 ? " value is" : " values are") + ' off the scale and drawn as triangles at the edge. <button type="button" class="chip" data-zoom="off">Show the full range</button></p>';
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

    o += '<div class="panel"><div class="panel-b headline"><div><div class="eyebrow">Headline value</div><div class="bigval" style="margin-top:8px">' + esc(h.value_label) + "<small>" + esc(units(h.units)) + '</small></div><p class="rule" style="margin-top:8px"><span class="dot st-' + h.status + '"></span> ' + esc(h.status) + " · " + esc(h.selection_set) + " · Nmax " + win(h.nmax) + (h.potential ? " · " + esc(h.potential) : "") + " · " + esc(h.run_date_label) + '</p></div><div class="btnrow"><a class="btn" href="' + route(state.lib, "r", h.id) + '">Open</a></div></div>';
    o += '<div class="panel-b" style="border-top:1px solid var(--line);padding-top:10px"><p class="rule">' + (h.pinned ? "Pinned with <code>headline = true</code> in annotations.toml." : "Picked by rule: published first, then the selection set in this order: " + CAT.headline_order.map(esc).join(" › ") + ", then the newest run. Add <code>headline = true</code> to a result in annotations.toml to pin a different one.") + "</p></div></div>";

    var groups = defs.filter(function (d) { return d.vals.length > 1 || (d.key === "papers" && d.vals.length); });
    if (groups.length) {
      o += '<div class="panel"><div class="panel-h"><h2>Filter</h2><span class="hint">' + rows.length + " of " + f.rows.length + ' results</span><span class="spacer"></span><button type="button" class="btn" data-reset="1">Clear filters</button></div><div class="panel-b stack" style="gap:10px">';
      groups.forEach(function (def) {
        var on = state.facets[def.key] || [];
        o += '<div class="facetgrp"><span>' + def.label + '</span><div class="chips">' + def.vals.map(function (v, i) {
          var n = f.rows.filter(function (r) { return passes(r, defs, def.key) && matches(def, r, v); }).length;
          var sw = def.key === "selection_set" ? '<span class="dot" style="background:' + seriesColor(i) + '"></span>' : def.key === "status" ? '<span class="dot st-' + v + '"></span>' : "";
          return '<button type="button" class="chip" data-facet="' + def.key + '" data-index="' + i + '" aria-pressed="' + (on.indexOf(v) >= 0) + '">' + sw + esc(v) + ' <span class="c">' + n + "</span></button>";
        }).join("") + "</div></div>";
      });
      o += "</div></div>";
    }

    o += '<div class="panel"><div class="panel-h"><h2>Scan</h2><div class="chips"><button type="button" class="chip" data-x="nmax" aria-pressed="' + (xmode === "nmax") + '">by Nmax window</button><button type="button" class="chip" data-x="date" aria-pressed="' + (xmode === "date") + '">by run date</button></div><span class="hint">Colour is the selection set; the outlined dot is the headline. Bars are the asymmetric uncertainty. Click a point to open it.</span></div><div class="panel-b plot">' + scanPlot(f, rows, sets, xmode) + "</div></div>";

    var byEns = {}, ensOrder = [];
    rows.forEach(function (r) { if (!byEns[r.ensemble]) { byEns[r.ensemble] = []; ensOrder.push(r.ensemble); } byEns[r.ensemble].push(r); });
    var ens = ensOrder.map(function (k) { return byEns[k]; });
    ens.sort(function (a, b) { return ((a[0].nmax[0] || 0) - (b[0].nmax[0] || 0)) || ((a[0].nmax[1] || 0) - (b[0].nmax[1] || 0)) || String(b[0].run_datetime).localeCompare(String(a[0].run_datetime)); });
    var shown = sets.filter(function (s) { return rows.some(function (r) { return r.selection_set === s; }); });
    var showPot = f.potentials.length > 1;
    o += '<div class="panel"><div class="panel-h"><h2>Ensembles</h2><span class="hint">One row per trained ensemble, one column per selection set: ' + rows.length + " results in " + ens.length + ' rows. The underlined value is the family headline.</span></div><div class="tablewrap"><table class="pivot"><thead><tr><th>Run</th><th>Nmax</th><th>ħΩ</th>' + (showPot ? "<th>Potential</th>" : "");
    o += shown.map(function (s) { return '<th><span class="sw" style="background:' + seriesColor(sets.indexOf(s)) + '"></span>' + esc(s) + "</th>"; }).join("") + "<th>Used in</th></tr></thead><tbody>";
    ens.forEach(function (g) {
      var r0 = g[0], used = uniq([].concat.apply([], g.map(function (r) { return r.papers.map(function (p) { return p.title; }); })));
      o += '<tr><td class="mono">' + esc(r0.run_date_label) + '</td><td class="mono">' + win(r0.nmax) + '</td><td class="mono">' + win(r0.homega) + "</td>" + (showPot ? "<td>" + esc(r0.potential) + "</td>" : "");
      shown.forEach(function (s) {
        var cell = g.filter(function (r) { return r.selection_set === s; });
        o += "<td>" + (cell.length ? cell.map(function (r) {
          return '<button type="button" class="cell' + (r.headline ? " head" : "") + (state.sel === r.id ? " sel" : "") + '" data-open="' + esc(r.id) + '" title="' + esc(r.status) + '"><span class="dot st-' + r.status + '"></span>' + esc(r.value_label) + "</button>";
        }).join("<br>") : '<span class="hint">–</span>') + "</td>";
      });
      o += '<td><span class="chips">' + used.map(function (p) { return '<span class="pap">' + esc(p) + "</span>"; }).join("") + "</span></td></tr>";
    });
    o += "</tbody></table></div></div>";

    var figs = CAT.figures.filter(function (fig) { return f.rows.some(function (r) { return fig.results.indexOf(r.id) >= 0; }); });
    if (figs.length) o += '<div class="panel"><div class="panel-h"><h2>Comparison figures</h2></div><div class="panel-b thumbs">' + figs.map(figureCard).join("") + "</div></div>";

    var other = state.lib === "legacy" ? "modern" : "legacy", twin = family(other, f.key);
    if (twin) o += '<div class="panel"><div class="panel-b"><b>Also computed with ' + other + ' code.</b> <span class="hint">' + twin.rows.length + " results, headline " + esc(twin.head.value_label) + '.</span> <a class="btn" href="' + route(other, "f", f.key) + '">Open in ' + other + "</a></div></div>";

    $("main").innerHTML = o + "</div>";
  }

  function figureCard(fig) {
    return '<a class="thumb" href="' + href(fig.href) + '">' + (fig.image ? '<img src="' + href(fig.href) + '" alt="" loading="lazy">' : "") + "<span><b>" + esc(fig.title) + "</b>" + (fig.caption ? " · " + esc(fig.caption) : "") + "</span></a>";
  }

  // ---- side panel ------------------------------------------------------

  function renderInspector() {
    var panel = $("insp"), layout = $("layout");
    var r = state.sel && BY_ID[state.sel];
    if (!r) { panel.hidden = true; layout.classList.remove("has-insp"); return; }
    panel.hidden = false; layout.classList.add("has-insp");
    var siblings = ROWS.filter(function (x) { return x.ensemble === r.ensemble && x.lineage === r.lineage && x.id !== r.id; });
    var o = '<button type="button" class="close" data-close="1" aria-label="Close">×</button><div class="eyebrow">' + libName(r.lineage) + " result" + (r.headline ? " · family headline" : "") + "</div>";
    o += "<h2>" + esc(r.title || "") + (r.title ? "" : esc(nucInfo(r.nucleus).label) + " " + stateTex(r) + " " + obsTex(r)) + "</h2>";
    o += '<div class="bigval" style="font-size:26px;margin:12px 0 6px">' + esc(r.value_label) + "<small>" + esc(units(r.units)) + "</small></div>";
    o += '<p class="rule"><span class="dot st-' + r.status + '"></span> ' + esc(r.status) + "</p>";
    o += '<div class="btnrow" style="margin-top:14px"><button type="button" class="btn" data-copy="latex">Copy LaTeX</button><button type="button" class="btn" data-copy="tsv">Copy TSV</button><button type="button" class="btn" data-copy="annotation">Copy annotation</button></div>';

    o += '<div class="sec"><dl class="kv"><dt>Run</dt><dd class="mono">' + esc(r.run_date_label) + "</dd><dt>Selection set</dt><dd>" + esc(r.selection_set) + "</dd>" + (r.potential ? "<dt>Potential</dt><dd>" + esc(r.potential) + "</dd>" : "");
    r.selection.forEach(function (item) { o += "<dt>" + esc(item[0]) + "</dt><dd>" + esc(item[1]) + hint(item[0]) + "</dd>"; });
    if (r.papers.length) o += "<dt>Published in</dt><dd>" + r.papers.map(function (p) { return p.href ? '<a class="pap" href="' + href(p.href, r) + '">' + esc(p.title) + "</a>" : '<span class="pap">' + esc(p.title) + "</span>"; }).join(" ") + "</dd>";
    o += "</dl></div>";

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

  // ---- plot viewer -----------------------------------------------------

  var viewer = null;
  function openViewer(r, index) {
    var images = r.plots.filter(function (p) { return p.image; });
    var start = images.indexOf(r.plots[index]);
    viewer = { images: images, index: start < 0 ? 0 : start, row: r };
    drawViewer();
  }
  function drawViewer() {
    if (!viewer) { $("overlay").innerHTML = ""; return; }
    var p = viewer.images[viewer.index];
    var r = viewer.row;
    var links = '<a class="btn" href="' + href(p.href, r) + '">Open file</a>' + (p.csv ? '<a class="btn" href="' + href(p.csv, r) + '">Data CSV</a>' : "");
    $("overlay").innerHTML = '<div class="viewer" data-viewer="1" role="dialog" aria-modal="true" aria-label="' + esc(p.caption) + '"><img src="' + href(p.href, r) + '" alt="' + esc(p.caption) + '"><div class="bar"><button type="button" class="btn" data-step="-1" aria-label="Previous plot">←</button><span>' + esc(p.caption) + " · " + (viewer.index + 1) + " of " + viewer.images.length + '</span><button type="button" class="btn" data-step="1" aria-label="Next plot">→</button>' + links + '<button type="button" class="btn" data-shut="1">Close</button></div></div>';
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

  function parseHash() {
    var parts = location.hash.replace(/^#/, "").split("/");
    var lib = LIBS.indexOf(parts[0]) >= 0 ? parts[0] : "modern";
    var kind = parts[1], key = parts.slice(2).join("/");
    try { key = decodeURIComponent(key); } catch (err) { key = ""; }
    state.lib = lib; state.nuc = null; state.fam = null; state.sel = null;
    if (kind === "n" && key) state.nuc = key;
    else if (kind === "f" && key) { var f = family(lib, key); state.fam = key; state.nuc = f ? f.nucleus : null; }
    else if (kind === "r" && BY_ID[key]) { var r = BY_ID[key]; state.lib = r.lineage; state.sel = key; state.fam = r.family; state.nuc = r.nucleus; }
  }

  function render() {
    document.body.setAttribute("data-lib", state.lib);
    document.querySelectorAll("#libs button").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-lib") === state.lib)); });
    renderRail();
    if (state.fam) renderFamily(); else if (state.nuc) renderNucleus(); else renderOverview();
    typeset($("main"));
    renderInspector();
  }
  function redrawFamily() { renderFamily(); typeset($("main")); }

  window.addEventListener("hashchange", function () {
    var prevFam = state.fam;
    parseHash(); render();
    if (state.fam !== prevFam) $("main").scrollTop = 0;
  });

  // ---- events ----------------------------------------------------------

  document.addEventListener("click", function (event) {
    var t = event.target.closest("button, .pt, [data-viewer]");
    if (!t) return;
    if (t.hasAttribute("data-viewer")) { if (event.target === t) { viewer = null; drawViewer(); } return; }
    if (t.hasAttribute("data-shut")) { viewer = null; drawViewer(); return; }
    if (t.hasAttribute("data-step")) { viewer.index = (viewer.index + Number(t.getAttribute("data-step")) + viewer.images.length) % viewer.images.length; drawViewer(); return; }
    if (t.closest("#libs")) { location.hash = route(t.getAttribute("data-lib")); return; }
    if (t.id === "theme") { toggleTheme(); return; }
    if (t.classList.contains("pt") || t.hasAttribute("data-open")) { location.hash = route(state.lib, "r", t.getAttribute("data-id") || t.getAttribute("data-open")); return; }
    if (t.hasAttribute("data-close")) { location.hash = route(state.lib, "f", state.fam); return; }
    if (t.hasAttribute("data-plot")) { openViewer(BY_ID[state.sel], Number(t.getAttribute("data-plot"))); return; }
    if (t.hasAttribute("data-copy")) {
      var r = BY_ID[state.sel], kind = t.getAttribute("data-copy");
      if (kind === "latex") copyText(r.latex, "LaTeX");
      else if (kind === "tsv") copyText(r.tsv, "TSV");
      else copyText(annotation(r), "annotation");
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
      if (state.sel) location.hash = route(state.lib, "f", state.fam);
    }
  });

  var tip = $("tip");
  document.addEventListener("mousemove", function (event) {
    var p = event.target.closest && event.target.closest(".pt");
    if (!p) { tip.hidden = true; return; }
    var r = BY_ID[p.getAttribute("data-id")];
    tip.innerHTML = esc(r.value_label) + "<br>" + esc(r.selection_set) + "<br>Nmax " + win(r.nmax) + " · ħΩ " + win(r.homega) + "<br>" + esc(r.run_date_label) + " · " + esc(r.status);
    tip.hidden = false;
    tip.style.left = Math.min(event.clientX + 14, window.innerWidth - 350) + "px";
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

  LIBS.forEach(function (lib) { $("count-" + lib).textContent = libRows(lib).length; });
  labelTheme();
  parseHash();
  render();
})();
