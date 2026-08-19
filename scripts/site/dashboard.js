/* ==========================================================================
   NF Knowledge Graph Evaluation — dashboard app.

   Reads the JSON payload embedded by scripts/build_site.py, then builds each
   tab: hero + KPI row, one filter row that scopes everything below it, the
   figures, and the detail tables behind disclosures.

   Colour is assigned to a model ONCE, from the full dataset, and never from a
   filtered subset — so filtering a model out can never repaint the survivors.
   ========================================================================== */
(function () {
  "use strict";

  var C = window.Charts;
  var fmt = C.fmt;
  var DATA = JSON.parse(document.getElementById("site-data").textContent);

  /* ------------------------------------------------------------- DOM utils -- */

  function h(tag, cls, parent) { return C.html(tag, cls, parent); }

  function txt(node, str) { node.textContent = str === null || str === undefined ? "" : String(str); return node; }

  function frag() { return document.createDocumentFragment(); }

  /* ------------------------------------------------------------ stat maths -- */

  function mean(values) {
    var out = [], i;
    for (i = 0; i < values.length; i++) {
      if (values[i] !== null && values[i] !== undefined && !isNaN(values[i])) out.push(values[i]);
    }
    if (!out.length) return null;
    var s = 0;
    for (i = 0; i < out.length; i++) s += out[i];
    return s / out.length;
  }

  function median(values) {
    var out = values.filter(function (v) { return v !== null && v !== undefined && !isNaN(v); })
      .sort(function (a, b) { return a - b; });
    if (!out.length) return null;
    var m = Math.floor(out.length / 2);
    return out.length % 2 ? out[m] : (out[m - 1] + out[m]) / 2;
  }

  function meanOf(runs, getter) { return mean(runs.map(getter)); }

  function bestBy(items, getter) {
    var best = null, bestV = -Infinity;
    items.forEach(function (it) {
      var v = getter(it);
      if (v !== null && v !== undefined && v > bestV) { bestV = v; best = it; }
    });
    return best;
  }

  /* Pareto frontier: cheaper is better, higher score is better. */
  function markFrontier(points) {
    points.forEach(function (p) {
      p.emph = !points.some(function (q) {
        return q !== p && q.x <= p.x && q.y >= p.y && (q.x < p.x || q.y > p.y);
      });
    });
    return points;
  }

  /* ------------------------------------------------------------ components -- */

  function sectionHead(parent, title) {
    var head = h("div", "section-head", parent);
    txt(h("h2", null, head), title);
    h("div", "rule", head);
    return head;
  }

  /* A figure card: title, optional subtitle and NEW badge, a chart/table
     toggle, and the chart mount point. */
  function card(parent, opts) {
    var node = h("div", "card" + (opts.span ? " span-2" : ""), parent);
    var head = h("div", "card-head", node);
    var title = h("div", "card-title", head);
    txt(h("span", null, title), opts.title);
    if (opts.badge) {
      var b = h("span", "badge badge-new", title);
      txt(b, opts.badge);
      title.insertBefore(document.createTextNode(" "), b);
    }
    if (opts.sub) txt(h("p", "card-sub", head), opts.sub);

    var actions = h("div", "card-actions", head);
    var wrap = h("div", "chart-wrap", node);

    if (opts.toggle !== false) {
      var btn = h("button", "ghost-btn", actions);
      btn.type = "button";
      btn.setAttribute("aria-pressed", "false");
      txt(btn, "Table");
      btn.title = "Show the same values as a table";
      btn.addEventListener("click", function () {
        var showing = wrap.getAttribute("data-view") === "table";
        var next = showing ? "chart" : "table";
        wrap.setAttribute("data-view", next);
        wrap.dispatchEvent(new CustomEvent("chart:view", { detail: next }));
        btn.setAttribute("aria-pressed", showing ? "false" : "true");
        if (showing) C.redrawAll();
      });
    }
    return { node: node, wrap: wrap, actions: actions, head: head };
  }

  function disclosure(parent, opts) {
    var d = h("details", "disclosure", parent);
    if (opts.open) d.open = true;
    var s = h("summary", null, d);
    txt(h("span", null, s), opts.summary);
    if (opts.note) txt(h("span", "sum-note", s), opts.note);
    return h("div", "disclosure-body", d);
  }

  /* Sortable table with optional column groups.
     columns: [{key,label,group,align,text,fmt,sortValue,className,hidden}] */
  function dataTable(parent, spec) {
    var scroll = h("div", "table-scroll", parent);
    var table = h("table", "data", scroll);
    if (spec.caption) txt(h("caption", null, table), spec.caption);
    var thead = h("thead", null, table);

    var cols = spec.columns.filter(function (c) { return !c.hidden; });

    var hasGroups = cols.some(function (c) { return c.group; });
    if (hasGroups) {
      var grow = h("tr", "group-row", thead);
      var i = 0;
      while (i < cols.length) {
        var g = cols[i].group || "";
        var span = 1;
        while (i + span < cols.length && (cols[i + span].group || "") === g) span++;
        var th = h("th", i > 0 ? "g" : null, grow);
        th.colSpan = span;
        th.className = (i > 0 ? "g " : "") + (cols[i].align === "left" || cols[i].text ? "text" : "");
        txt(th, g);
        i += span;
      }
    }

    var hrow = h("tr", "head-row", thead);
    cols.forEach(function (c, idx) {
      var th = h("th", null, hrow);
      var isGroupStart = hasGroups && idx > 0 && (c.group || "") !== (cols[idx - 1].group || "");
      th.className = [c.text ? "text" : "", isGroupStart ? "g" : "", spec.sortable === false ? "" : "sortable"]
        .filter(Boolean).join(" ");
      th.setAttribute("scope", "col");
      txt(th, c.label);
      if (c.title) th.title = c.title;
      if (spec.sortable !== false) {
        th.tabIndex = 0;
        var sort = function () {
          var asc = th.getAttribute("aria-sort") === "ascending" ? false : th.getAttribute("aria-sort") === "descending" ? true : !!c.text;
          hrow.querySelectorAll("th").forEach(function (o) { o.removeAttribute("aria-sort"); });
          th.setAttribute("aria-sort", asc ? "ascending" : "descending");
          var body = table.querySelector("tbody");
          var rows = Array.prototype.slice.call(body.querySelectorAll("tr"));
          rows.sort(function (a, b) {
            var av = a._row[c.key], bv = b._row[c.key];
            var an = typeof av === "number", bn = typeof bv === "number";
            if (an && bn) return asc ? av - bv : bv - av;
            if (av === null || av === undefined) return 1;
            if (bv === null || bv === undefined) return -1;
            return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
          });
          rows.forEach(function (r) { body.appendChild(r); });
        };
        th.addEventListener("click", sort);
        th.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); }
        });
      }
    });

    var tbody = h("tbody", null, table);
    spec.rows.forEach(function (row) {
      var tr = h("tr", row._class || null, tbody);
      tr._row = row;
      cols.forEach(function (c, idx) {
        var isGroupStart = hasGroups && idx > 0 && (c.group || "") !== (cols[idx - 1].group || "");
        var td = h(idx === 0 ? "th" : "td", null, tr);
        td.className = [c.text ? "text" : "", isGroupStart ? "g" : "", c.className || ""]
          .filter(Boolean).join(" ");
        if (idx === 0) td.setAttribute("scope", "row");
        if (c.render) c.render(td, row);
        else txt(td, c.fmt ? c.fmt(row[c.key], row) : row[c.key]);
      });
    });

    return { scroll: scroll, table: table, tbody: tbody };
  }

  /* ------------------------------------------------------------ model keys -- */

  var MODEL = {};
  DATA.models.forEach(function (m) { MODEL[m.id] = m; });

  function modelColor(id) { return (MODEL[id] && MODEL[id].color) || "var(--muted-mark)"; }
  function modelLabel(id) { return (MODEL[id] && MODEL[id].label) || id; }

  function chipRow(parent, models, state, onChange) {
    var chips = h("div", "chips", parent);
    var buttons = {};
    models.forEach(function (id) {
      var b = h("button", "chip", chips);
      b.type = "button";
      b.setAttribute("aria-pressed", state.has(id) ? "true" : "false");
      h("span", "chip-swatch", b).style.background = modelColor(id);
      txt(h("span", null, b), modelLabel(id));
      buttons[id] = b;
      b.addEventListener("click", function () {
        if (state.has(id)) {
          if (state.size === 1) return;   /* never leave an empty selection */
          state.delete(id);
        } else {
          state.add(id);
        }
        b.setAttribute("aria-pressed", state.has(id) ? "true" : "false");
        onChange();
      });
    });

    /* A chip for a model with nothing in the current slice reads as a bug, so
       say so on the chip rather than leaving the reader to infer it. */
    chips.markAvailability = function (available, reason) {
      Object.keys(buttons).forEach(function (id) {
        var has = available.indexOf(id) >= 0;
        buttons[id].setAttribute("data-empty", has ? "false" : "true");
        buttons[id].title = has ? "" : modelLabel(id) + " — " + reason;
      });
    };
    return chips;
  }

  function segmented(parent, options, current, onChange) {
    var seg = h("div", "segmented", parent);
    seg.setAttribute("role", "group");
    options.forEach(function (o) {
      var b = h("button", null, seg);
      b.type = "button";
      b.setAttribute("aria-pressed", o.value === current() ? "true" : "false");
      txt(b, o.label);
      if (o.title) b.title = o.title;
      b.addEventListener("click", function () {
        if (o.value === current()) return;
        onChange(o.value);
        Array.prototype.forEach.call(seg.children, function (c) {
          c.setAttribute("aria-pressed", c === b ? "true" : "false");
        });
      });
    });
    return seg;
  }

  function filterRow(parent) {
    var row = h("div", "filters", parent);
    row.setAttribute("role", "group");
    row.setAttribute("aria-label", "Filters — these scope every figure and table below");
    return row;
  }

  function filterGroup(parent, label) {
    var g = h("div", "filter-group", parent);
    txt(h("span", "filter-label", g), label);
    return g;
  }

  /* =========================================================================
     TAB 1 — Research tools discovery (nf_rag)
     ========================================================================= */

  var T = DATA.tools;

  function toolsBuild(root) {
    var allModels = [];
    T.runs.forEach(function (r) { if (allModels.indexOf(r.model) < 0) allModels.push(r.model); });
    allModels.sort(function (a, b) { return MODEL[a].slot - MODEL[b].slot; });

    var latestVersion = T.versions.filter(function (v) { return v.isLatest; })[0];

    var state = {
      version: latestVersion ? latestVersion.id : "all",
      models: new Set(allModels)
    };

    /* lede */
    var lede = h("p", "panel-lede", root);
    lede.appendChild(document.createTextNode(
      "An agent answers research-discovery questions against the Synapse portal knowledge graph over SPARQL. " +
      "The score is "));
    txt(h("strong", null, lede), "recall");
    lede.appendChild(document.createTextNode(
      " — the share of the expected resources the agent actually returned. Questions are grouped by " +
      "resource category, by reasoning complexity, and by how painful the same question is on today's portal."));

    var heroHost = h("div", null, root);
    var filters = filterRow(root);
    var body = h("div", null, root);

    /* ---- filter row ---- */
    var vg = filterGroup(filters, "Question set");
    var versionOpts = T.versions.map(function (v) {
      return {
        value: v.id,
        label: v.label + (v.isLatest ? "" : ""),
        title: v.questions + " questions" + (v.isLatest ? " — latest" : "")
      };
    }).concat([{ value: "all", label: "All", title: "Every version — scores are not comparable across sets" }]);
    segmented(vg, versionOpts, function () { return state.version; }, function (v) {
      state.version = v; render();
    });

    var mg = filterGroup(filters, "Models");
    var chips = chipRow(mg, allModels, state.models, render);

    var reset = h("button", "filter-reset", filters);
    reset.type = "button";
    txt(reset, "Reset");
    reset.addEventListener("click", function () {
      state.version = latestVersion ? latestVersion.id : "all";
      state.models = new Set(allModels);
      rebuildFilterUi();
      render();
    });

    var note = h("p", "filter-note", filters);

    function rebuildFilterUi() {
      /* cheapest correct path: rebuild the whole tab */
      C.hideTip();
      root.innerHTML = "";
      toolsBuild(root);
    }

    /* ---- selection ---- */

    function selected() {
      return T.runs.filter(function (r) {
        if (!state.models.has(r.model)) return false;
        if (state.version !== "all" && r.version !== state.version) return false;
        return true;
      });
    }

    /* One entity per model (per version too, when versions are mixed). The
       colour always comes from the model; the version rides a dash pattern and
       a hollow marker, so hue never has to carry two facts at once. */
    function entities(runs) {
      var splitVersion = state.version === "all";
      var map = {}, order = [];
      runs.forEach(function (r) {
        var key = splitVersion ? r.model + "|" + r.version : r.model;
        if (!map[key]) {
          var v = T.versions.filter(function (x) { return x.id === r.version; })[0];
          var older = splitVersion && !(v && v.isLatest);
          map[key] = {
            key: key, model: r.model, version: splitVersion ? r.version : null,
            label: modelLabel(r.model) + (splitVersion ? " · " + r.version : ""),
            color: modelColor(r.model),
            dash: older ? "5 4" : null,
            hollow: older,
            runs: []
          };
          order.push(map[key]);
        }
        map[key].runs.push(r);
      });
      order.forEach(function (e) {
        e.score = meanOf(e.runs, function (r) { return r.score; });
        e.cost = meanOf(e.runs, function (r) { return r.costPerQuestion; });
        e.n = e.runs.length;
      });
      order.sort(function (a, b) { return (b.score || 0) - (a.score || 0); });
      return order;
    }

    function legendOf(ents, shape) {
      return ents.map(function (e) {
        return { label: e.label, color: e.color, shape: e.hollow ? "hollow" : (shape || "line") };
      });
    }

    /* ---- render ---- */

    function render() {
      C.hideTip();
      var runs = selected();
      var ents = entities(runs);
      var vLabel = state.version === "all" ? "all question sets" :
        state.version + " · " + (T.versions.filter(function (v) { return v.id === state.version; })[0] || {}).questions + " questions";

      txt(note, runs.length + " of " + T.runs.length + " scored, complete runs in view · " + vLabel +
        (state.version === "all" ? " — recall is not comparable across question sets, so each set is drawn as its own series" : ""));

      /* which models actually have something to show under this slice? */
      var available = [];
      T.runs.forEach(function (r) {
        if (state.version !== "all" && r.version !== state.version) return;
        if (available.indexOf(r.model) < 0) available.push(r.model);
      });
      chips.markAvailability(available, "no complete run on this question set");

      renderHero(runs);
      body.innerHTML = "";
      renderFigures(body, runs, ents);
      renderDetail(body, runs, ents);
    }

    /* ---- hero + KPIs ---- */

    function renderHero(runs) {
      heroHost.innerHTML = "";
      var hero = h("div", "hero", heroHost);
      var fig = h("div", "hero-figure", hero);
      var kpis = h("div", "kpis", hero);

      var best = bestBy(runs, function (r) { return r.score; });
      txt(h("div", "hero-label", fig), "Best recall");
      if (!best) {
        txt(h("div", "hero-value", fig), "—");
        txt(h("p", "hero-caption", fig), "No runs match the current filters.");
        return;
      }
      txt(h("div", "hero-value", fig), fmt.score2(best.score));
      var cap = h("p", "hero-caption", fig);
      txt(h("span", "hero-model", cap), modelLabel(best.model));
      cap.appendChild(document.createTextNode(
        " · " + best.samples + " questions · " + best.version + " · " + best.date));
      txt(h("p", "hero-note", fig),
        best.stderr === null || best.stderr === undefined ? "" : "± " + best.stderr.toFixed(3) + " standard error");

      function kpi(label, value, caption) {
        var box = h("div", null, kpis);
        txt(h("div", "kpi-label", box), label);
        txt(h("div", "kpi-value", box), value);
        if (caption) txt(h("div", "kpi-caption", box), caption);
        return box;
      }

      var modelsInView = {};
      runs.forEach(function (r) { modelsInView[r.model] = 1; });
      kpi("Models", String(Object.keys(modelsInView).length),
        "of " + DATA.models.length + " ever evaluated");
      kpi("Cost / question", fmt.moneyFine(best.costPerQuestion),
        fmt.money(best.cost) + " for the best run");
      kpi("Time / question", fmt.duration(best.avgSampleTime),
        fmt.duration(best.duration) + " end to end");
      var med = median(runs.map(function (r) { return r.score; }));
      kpi("Median recall", fmt.score2(med), "across " + runs.length + " runs in view");
    }

    /* Per-date bests across every question set, from complete runs only.
       Scored-best and cheapest are tracked separately, because they are often
       different runs. */
    function buildTimeline() {
      var byDate = {};
      T.runs.forEach(function (r) {
        if (!state.models.has(r.model)) return;
        var day = byDate[r.date];
        if (!day) day = byDate[r.date] = { date: r.date, best: null, cheapest: null };
        if (r.score !== null && (day.best === null || r.score > day.best.score)) {
          day.best = r;
        }
        if (r.costPerQuestion !== null &&
            (day.cheapest === null || r.costPerQuestion < day.cheapest.costPerQuestion)) {
          day.cheapest = r;
        }
      });
      return Object.keys(byDate).sort().map(function (k) { return byDate[k]; });
    }

    /* The chart's table twin carries the values but not which run produced
       them, so the headline attribution is stated in plain text as well. */
    function captionFor(cardRef, timeline, which) {
      var note = h("p", "card-sub", cardRef.node);
      note.style.marginTop = "10px";
      var withData = timeline.filter(function (p) { return p[which]; });
      if (!withData.length) { txt(note, ""); return; }

      if (which === "best") {
        var latest = withData[withData.length - 1];
        txt(note, "Latest best: " + modelLabel(latest.best.model) + " on " +
          latest.best.version + " · " + fmt.score(latest.best.score) + " recall");
        return;
      }
      var cheapest = withData.reduce(function (a, b) {
        return b.cheapest.costPerQuestion < a.cheapest.costPerQuestion ? b : a;
      });
      var first = withData[0].cheapest.costPerQuestion;
      var last = withData[withData.length - 1].cheapest.costPerQuestion;
      var text = "Cheapest to date: " + modelLabel(cheapest.cheapest.model) + " · " +
        fmt.moneyFine(cheapest.cheapest.costPerQuestion) + " on " + cheapest.date;
      if (withData.length > 1 && first > 0) {
        var change = Math.round(((last - first) / first) * 100);
        text += " · " + (change <= 0 ? "down " + Math.abs(change) : "up " + change) +
          "% since " + withData[0].date;
      }
      txt(note, text);
    }

    /* ---- figures ---- */

    function renderFigures(parent, runs, ents) {
      sectionHead(parent, "Headline");
      var g1 = h("div", "grid", parent);

      /* cost vs recall — emphasis on the frontier, never eight hues */
      var scatterPoints = markFrontier(ents.filter(function (e) {
        return e.score !== null && e.cost !== null;
      }).map(function (e) {
        return {
          x: e.cost, y: e.score, label: e.label,
          sub: e.n + (e.n === 1 ? " run" : " runs" ) + " averaged",
          rows: [
            { label: "Recall", value: fmt.score(e.score) },
            { label: "Cost / question", value: fmt.moneyFine(e.cost) },
            { label: "Total cost", value: fmt.money(mean(e.runs.map(function (r) { return r.cost; }))) }
          ]
        };
      }));
      var c1 = card(g1, {
        title: "Recall against cost",
        sub: "Cost is per question, so runs on different question sets stay comparable. Solid marks sit on the cost/recall frontier — nothing in view is both cheaper and better."
      });
      C.mount(c1.wrap, "scatter", {
        title: "Recall against cost per question",
        points: scatterPoints,
        xLabel: "Cost per question (USD)",
        yLabel: "Recall",
        xFmt: fmt.moneyAxisFine,
        tableKey: "Model",
        legend: [
          { label: "On the cost/recall frontier", color: "var(--series-1)", shape: "dot" },
          { label: "Dominated by another run", color: "var(--muted-mark)", shape: "dot" }
        ]
      });

      /* complexity */
      var complexCats = T.complexities.map(function (c) { return c.label; });
      var c2 = card(g1, {
        title: "Recall by reasoning complexity",
        sub: "How far the agent must travel through the graph: a direct lookup, one hop, or two."
      });
      C.mount(c2.wrap, "lines", {
        title: "Recall by reasoning complexity",
        categories: complexCats,
        series: ents.map(function (e) {
          return {
            label: e.label, color: e.color, dash: e.dash, hollow: e.hollow,
            values: T.complexities.map(function (c) {
              return meanOf(e.runs, function (r) { return r.difficulty[c.key]; });
            })
          };
        }),
        yLabel: "Recall",
        tableKey: "Model",
        legend: legendOf(ents)
      });

      sectionHead(parent, "Where the graph is strong, and where it is not");
      var g2 = h("div", "grid", parent);

      /* category heatmap — data-driven, so a newly added module shows up here
         the first time it appears in a run */
      var catCols = T.categories.map(function (c) {
        return {
          label: c.label,
          badge: c.isNew ? "new" : null,
          note: c.questions ? String(c.questions) : null
        };
      });
      var c3 = card(g2, {
        title: "Recall by resource category",
        sub: "Mean recall per category. Darker is better. Categories marked new arrived with the latest question set.",
        span: true
      });
      C.mount(c3.wrap, "heatmap", {
        title: "Recall by resource category",
        rows: ents.map(function (e) {
          return {
            label: e.label, color: e.color,
            values: T.categories.map(function (c) {
              return meanOf(e.runs, function (r) { return r.category[c.key]; });
            })
          };
        }),
        cols: catCols,
        measure: "Recall",
        tableKey: "Model",
        scaleLegend: ["0.0 recall", "1.0"]
      });

      var g3 = h("div", "grid", parent);

      /* baseline -> advanced dumbbell — needs two levels to have a gap to show */
      var lvlBase = T.levels[0], lvlAdv = T.levels[T.levels.length - 1];
      if (T.levels.length > 1) {
      var c4 = card(g3, {
        title: "Baseline questions against advanced",
        sub: "Each row is one model: the hollow mark is the baseline question set, the filled mark the advanced one."
      });
      C.mount(c4.wrap, "dumbbell", {
        title: "Baseline against advanced recall",
        rows: ents.map(function (e) {
          return {
            label: e.label, color: e.color,
            a: meanOf(e.runs, function (r) { return r.difficulty[lvlBase.key]; }),
            b: meanOf(e.runs, function (r) { return r.difficulty[lvlAdv.key]; })
          };
        }),
        aLabel: lvlBase.label,
        bLabel: lvlAdv.label,
        xLabel: "Recall",
        tableKey: "Model",
        legend: [
          { label: lvlBase.label, color: "var(--ink-3)", shape: "hollow" },
          { label: lvlAdv.label, color: "var(--ink-3)", shape: "dot" }
        ]
      });
      }

      /* frustration */
      var c5 = card(g3, {
        title: "Recall against portal pain",
        sub: "Questions are graded by how hard the same question is on today's portal. A flat line means the graph is indifferent to what the portal finds difficult."
      });
      C.mount(c5.wrap, "lines", {
        title: "Recall by user frustration on the current portal",
        categories: T.frustrations.map(function (f) { return f.label; }),
        series: ents.map(function (e) {
          return {
            label: e.label, color: e.color, dash: e.dash, hollow: e.hollow,
            values: T.frustrations.map(function (f) {
              return meanOf(e.runs, function (r) { return r.frustration[f.key]; });
            })
          };
        }),
        yLabel: "Recall",
        xLabel: "User frustration with the current portal",
        tableKey: "Model",
        legend: legendOf(ents)
      });
      var nd = h("details", "inline-note", c5.node);
      txt(h("summary", null, nd), "How frustration is graded");
      var nb = h("div", "note-body", nd);
      txt(h("p", null, nb),
        "Each question carries an estimate of how hard it is to answer with the current portal's faceted and text search.");
      var dl = h("dl", null, nb);
      T.frustrationHelp.forEach(function (row) {
        txt(h("dt", null, dl), row[0]);
        txt(h("dd", null, dl), row[1]);
      });

      /* ---- the new PUB module gets its own section ---- */
      var newCats = T.categories.filter(function (c) { return c.isNew; });
      if (newCats.length) {
        sectionHead(parent, "New in the latest question set");
        var g4 = h("div", "grid", parent);
        newCats.forEach(function (cat) {
          var rows = ents.map(function (e) {
            return {
              label: e.label,
              value: meanOf(e.runs, function (r) { return r.category[cat.key]; }),
              color: e.color,
              sub: e.n + (e.n === 1 ? " run" : " runs") + " averaged"
            };
          }).filter(function (r) { return r.value !== null; })
            .sort(function (a, b) { return b.value - a.value; });

          var cc = card(g4, {
            title: cat.label + " module",
            badge: "new",
            sub: cat.blurb || (cat.questions + " questions added in " + (latestVersion ? latestVersion.id : "the latest set") + ".")
          });
          C.mount(cc.wrap, "hbar", {
            title: cat.label + " recall by model",
            rows: rows,
            measure: "Recall",
            xLabel: "Recall",
            xMax: 1,
            tableKey: "Model",
            emptyMessage: "No run in view covers the " + cat.label + " questions yet."
          });

          if (cat.items && cat.items.length) {
            var qd = h("details", "inline-note", cc.node);
            txt(h("summary", null, qd), "The " + cat.items.length + " questions in this module");
            var qb = h("div", "note-body", qd);
            var ol = h("ol", null, qb);
            ol.style.margin = "0";
            ol.style.paddingLeft = "20px";
            cat.items.forEach(function (it) {
              var li = h("li", null, ol);
              li.style.marginBottom = "5px";
              var code = h("code", null, li);
              txt(code, it.id);
              li.appendChild(document.createTextNode(" " + it.question));
            });
          }
        });
      }

      /* ---- progress ---- */
      /* Recomputed per render from the runs themselves, so deselecting a model
         re-picks that day's best rather than dropping the day entirely. The
         question-set filter is deliberately ignored: this is the arc of the
         pipeline across sets, which is why each point names its own set. */
      var timeline = buildTimeline();
      if (timeline.length > 1) {
        sectionHead(parent, "Progress");
        var g5 = h("div", "grid", parent);
        var dates = timeline.map(function (p) { return p.date; });

        /* Two measures on two different scales, so two charts sharing one time
           axis — never one plot with two y-axes. */
        var c6 = card(g5, {
          title: "Best recall over time",
          sub: "The highest-scoring complete run on each evaluation date, across every question set. The set changes along the way, so this tracks the pipeline rather than one fixed benchmark."
        });
        C.mount(c6.wrap, "lines", {
          title: "Best recall by evaluation date",
          categories: dates,
          series: [{
            label: "Best recall",
            color: "var(--series-1)",
            values: timeline.map(function (p) { return p.best ? p.best.score : null; })
          }],
          yLabel: "Recall",
          endLabels: false,
          tipSub: "highest-scoring run that day",
          tableKey: "Date",
          pointRows: function (i) {
            var run = timeline[i].best;
            if (!run) return [];
            return [
              { label: "Model", value: modelLabel(run.model) },
              { label: "Question set", value: run.version },
              { label: "Cost / question", value: fmt.moneyFine(run.costPerQuestion) }
            ];
          },
          emptyMessage: "No scored runs for the selected models."
        });
        captionFor(c6, timeline, "best");

        var c7 = card(g5, {
          title: "Best cost per question over time",
          sub: "The lowest cost per question among complete runs each date — lower is better. Read it beside recall: the cheapest run of the day is not always the best one, so each point names both."
        });
        C.mount(c7.wrap, "lines", {
          title: "Best cost per question by evaluation date",
          categories: dates,
          series: [{
            label: "Lowest cost / question",
            color: "var(--series-2)",
            values: timeline.map(function (p) {
              return p.cheapest ? p.cheapest.costPerQuestion : null;
            })
          }],
          yLabel: "Cost per question (USD)",
          yFmt: fmt.moneyAxisFine,
          yMaxCap: Infinity,
          tipFmt: fmt.moneyFine,
          endLabels: false,
          tipSub: "cheapest complete run that day",
          tableKey: "Date",
          pointRows: function (i) {
            var point = timeline[i];
            if (!point.cheapest) return [];
            var rows = [
              { label: "Model", value: modelLabel(point.cheapest.model) },
              { label: "Recall", value: fmt.score(point.cheapest.score) }
            ];
            /* pair it with the day's best run, so cheap-but-weak is visible */
            if (point.best && point.best !== point.cheapest) {
              rows.push({
                label: "Best run cost",
                value: fmt.moneyFine(point.best.costPerQuestion) +
                  " (" + modelLabel(point.best.model) + ")"
              });
            }
            return rows;
          },
          emptyMessage: "No costed runs for the selected models."
        });
        captionFor(c7, timeline, "cheapest");
      }
    }

    /* ---- detail, behind disclosures ---- */

    function renderDetail(parent, runs, ents) {
      sectionHead(parent, "Detail");

      /* high-impact questions — the argument for the graph */
      if (T.highImpact && T.highImpact.length) {
        var hiBody = disclosure(parent, {
          summary: "High-impact questions",
          note: T.highImpact.length + " questions the portal handles badly and the graph handles well",
          open: true
        });
        txt(h("p", "card-sub", hiBody),
          "Questions rated high or very high frustration on the current portal where the best model reached at least " +
          Math.round(T.highImpactThreshold * 100) + "% recall. Best recall is taken across the models selected above " +
          "and across every scored, complete run — this table deliberately ignores the question-set filter, because a " +
          "question the graph has answered well once is answered well.");
        var hiRows = T.highImpact.map(function (q) {
          var scores = {};
          var bestScore = null, bestModels = [];
          Object.keys(q.byModel).forEach(function (m) {
            if (!state.models.has(m)) return;
            var v = q.byModel[m];
            scores[m] = v;
            if (bestScore === null || v > bestScore) { bestScore = v; bestModels = [m]; }
            else if (v === bestScore) bestModels.push(m);
          });
          return {
            qid: q.id, question: q.question, frustration: q.frustration,
            complexity: q.complexity, category: q.category,
            best: bestScore,
            bestModels: bestModels.map(modelLabel).sort().join(", ")
          };
        }).filter(function (r) { return r.best !== null && r.best >= T.highImpactThreshold; })
          .sort(function (a, b) { return b.best - a.best || a.qid.localeCompare(b.qid); });

        if (!hiRows.length) {
          txt(h("p", "chart-empty", hiBody), "No question clears the threshold for the selected models.");
        } else {
          dataTable(hiBody, {
            columns: [
              { key: "qid", label: "Question", text: true, className: "mono" },
              { key: "question", label: "Asked", text: true, render: function (td, row) {
                td.style.whiteSpace = "normal";
                td.style.minWidth = "320px";
                td.style.maxWidth = "560px";
                txt(td, row.question);
              } },
              { key: "category", label: "Category", text: true },
              { key: "complexity", label: "Complexity", text: true },
              { key: "frustration", label: "Portal pain", text: true, render: function (td, row) {
                var p = h("span", "pill warn", td);
                txt(p, row.frustration);
              } },
              { key: "best", label: "Best recall", fmt: fmt.score2, className: "num-strong" },
              { key: "bestModels", label: "Achieved by", text: true }
            ],
            rows: hiRows
          });
        }
      }

      /* full run table */
      var runBody = disclosure(parent, {
        summary: "All runs in view",
        note: runs.length + (runs.length === 1 ? " run" : " runs")
      });
      var runActions = h("div", null, runBody);
      runActions.style.display = "flex";
      runActions.style.gap = "8px";
      runActions.style.margin = "4px 0 2px";
      var tokBtn = h("button", "ghost-btn", runActions);
      tokBtn.type = "button";
      tokBtn.setAttribute("aria-pressed", "false");
      txt(tokBtn, "Show token accounting");

      var runRows = runs.slice().sort(function (a, b) {
        return b.score - a.score || String(b.date).localeCompare(String(a.date));
      }).map(function (r) {
        return Object.assign({}, r, { modelLabel: modelLabel(r.model) });
      });
      var bestScore = Math.max.apply(null, runRows.map(function (r) { return r.score; }));

      var tokenCols = [
        { key: "tokIn", label: "Input", group: "Tokens", fmt: fmt.compact },
        { key: "tokOut", label: "Output", group: "Tokens", fmt: fmt.compact },
        { key: "tokCacheWrite", label: "Cache write", group: "Tokens", fmt: fmt.compact },
        { key: "tokCacheRead", label: "Cache read", group: "Tokens", fmt: fmt.compact },
        { key: "tokTotal", label: "Total", group: "Tokens", fmt: fmt.compact }
      ];
      tokenCols.forEach(function (c) { c.hidden = true; });

      function drawRunTable() {
        if (runTable) runTable.scroll.remove();
        runTable = dataTable(runBody, {
          caption: "Every scored, complete run. Click a column heading to sort.",
          columns: [
            { key: "modelLabel", label: "Model", text: true, group: "Run", render: function (td, row) {
              var sw = h("span", "cell-swatch", td);
              sw.style.background = modelColor(row.model);
              td.appendChild(document.createTextNode(row.modelLabel));
            } },
            { key: "version", label: "Set", text: true, group: "Run" },
            { key: "date", label: "Date", text: true, group: "Run", className: "mono" },
            { key: "samples", label: "Questions", group: "Run", fmt: fmt.int },
            { key: "score", label: "Recall", group: "Score", className: "num-strong", render: function (td, row) {
              var span = h("span", row.score === bestScore ? "best" : null, td);
              txt(span, fmt.score(row.score) +
                (row.stderr === null || row.stderr === undefined ? "" : " ± " + row.stderr.toFixed(3)));
            } },
            { key: "cost", label: "Cost", group: "Score", fmt: fmt.money },
            { key: "costPerQuestion", label: "Cost / question", group: "Score", fmt: fmt.moneyFine },
            { key: "duration", label: "Wall clock", group: "Time", fmt: fmt.duration },
            { key: "avgSampleTime", label: "Mean / question", group: "Time", fmt: fmt.duration },
            { key: "minSampleTime", label: "Fastest", group: "Time", fmt: fmt.duration },
            { key: "maxSampleTime", label: "Slowest", group: "Time", fmt: fmt.duration }
          ].concat(tokenCols).concat([
            { key: "commit", label: "Harness commit", text: true, group: "Provenance", className: "mono" },
            { key: "id", label: "Run", text: true, group: "Provenance", className: "mono" }
          ]),
          rows: runRows
        });
      }
      var runTable = null;
      drawRunTable();

      tokBtn.addEventListener("click", function () {
        var on = tokBtn.getAttribute("aria-pressed") === "true";
        tokenCols.forEach(function (c) { c.hidden = on; });
        tokBtn.setAttribute("aria-pressed", on ? "false" : "true");
        txt(tokBtn, on ? "Show token accounting" : "Hide token accounting");
        drawRunTable();
      });

      /* per-question detail */
      if (T.questions && T.questions.length) {
        var qBody = disclosure(parent, {
          summary: "Every question, every model",
          note: T.questions.length + " questions with per-model recall"
        });
        txt(h("p", "card-sub", qBody),
          "Mean recall per question across the runs in view. Blank cells mean the question is not in the " +
          "selected question set, or the harness recorded no per-question score for it.");
        var qEnts = ents;
        dataTable(qBody, {
          columns: [
            { key: "id", label: "Question", text: true, className: "mono" },
            { key: "category", label: "Category", text: true },
            { key: "level", label: "Level", text: true },
            { key: "complexity", label: "Complexity", text: true },
            { key: "frustration", label: "Portal pain", text: true }
          ].concat(qEnts.map(function (e) {
            return {
              key: "m_" + e.key, label: modelLabel(e.model) + (e.version ? " " + e.version : ""),
              group: "Recall", render: function (td, row) {
                var v = row["m_" + e.key];
                if (v === null || v === undefined) { txt(td, ""); return; }
                var wrap = h("div", "cell-bar", td);
                var track = h("div", "cell-bar-track", wrap);
                var fill = h("div", "cell-bar-fill", track);
                fill.style.width = Math.round(v * 100) + "%";
                fill.style.background = e.color;
                txt(h("span", null, wrap), fmt.score2(v));
              }
            };
          })),
          rows: T.questions.map(function (q) {
            var row = {
              id: q.id, category: q.categoryLabel, level: q.level || "",
              complexity: q.complexity || "", frustration: q.frustration || ""
            };
            qEnts.forEach(function (e) {
              var vals = [];
              e.runs.forEach(function (r) {
                var v = r.questionScores && r.questionScores[q.id];
                if (v !== null && v !== undefined) vals.push(v);
              });
              row["m_" + e.key] = vals.length ? mean(vals) : null;
            });
            return row;
          })
        });
      }

      /* about */
      var aboutBody = disclosure(parent, { summary: "About this benchmark" });
      T.about.forEach(function (para) {
        var p = h("p", "card-sub", aboutBody);
        p.style.marginBottom = "8px";
        p.style.maxWidth = "80ch";
        txt(p, para);
      });
      var links = h("p", "card-sub", aboutBody);
      links.appendChild(document.createTextNode("Raw data: "));
      var a1 = h("a", null, links);
      a1.href = "runs.json";
      txt(a1, "runs.json");
    }

    render();
  }

  /* =========================================================================
     TAB 2 — Publication QA (nf_rag_pubs)
     ========================================================================= */

  var P = DATA.pubs;

  function pubsBuild(root) {
    if (!P || !P.runs.length) {
      txt(h("p", "chart-empty", root), "No publication QA runs have been recorded yet.");
      return;
    }

    var allModels = [];
    P.runs.forEach(function (r) { if (allModels.indexOf(r.model) < 0) allModels.push(r.model); });
    allModels.sort(function (a, b) { return MODEL[a].slot - MODEL[b].slot; });

    var state = { style: P.defaultStyle, models: new Set(allModels) };

    var lede = h("p", "panel-lede", root);
    lede.appendChild(document.createTextNode(
      "An agent answers multiple-choice questions over full-text publications, retrieved with SPARQL over a " +
      "text-indexed graph. Two things are scored: whether the answer is right, and whether the agent "));
    txt(h("strong", null, lede), "cited the passages that support it");
    lede.appendChild(document.createTextNode(
      ". Answer accuracy is close to saturated; attribution is where the work is."));

    var heroHost = h("div", null, root);
    var filters = filterRow(root);
    var body = h("div", null, root);

    var stg = filterGroup(filters, "Question phrasing");
    segmented(stg, P.styles.map(function (s) {
      return { value: s.id, label: s.label, title: s.title };
    }).concat(P.styles.length > 1 ? [{ value: "both", label: "Compare", title: "Show both phrasings side by side" }] : []),
      function () { return state.style; }, function (v) { state.style = v; render(); });

    var mg = filterGroup(filters, "Models");
    var chips = chipRow(mg, allModels, state.models, render);

    var reset = h("button", "filter-reset", filters);
    reset.type = "button";
    txt(reset, "Reset");
    reset.addEventListener("click", function () {
      C.hideTip();
      root.innerHTML = "";
      pubsBuild(root);
    });

    var note = h("p", "filter-note", filters);

    function selected() {
      return P.runs.filter(function (r) {
        if (!state.models.has(r.model)) return false;
        if (state.style !== "both" && r.style !== state.style) return false;
        return true;
      });
    }

    function entities(runs) {
      var split = state.style === "both";
      var map = {}, order = [];
      runs.forEach(function (r) {
        var key = split ? r.model + "|" + r.style : r.model;
        if (!map[key]) {
          var older = split && r.style !== P.defaultStyle;
          map[key] = {
            key: key, model: r.model, style: split ? r.style : null,
            label: modelLabel(r.model) + (split ? " · " + P.styleLabel[r.style] : ""),
            color: modelColor(r.model),
            dash: older ? "5 4" : null, hollow: older, runs: []
          };
          order.push(map[key]);
        }
        map[key].runs.push(r);
      });
      order.forEach(function (e) {
        e.f1 = meanOf(e.runs, function (r) { return r.f1; });
        e.accuracy = meanOf(e.runs, function (r) { return r.accuracy; });
        e.cost = meanOf(e.runs, function (r) { return r.costPerQuestion; });
        e.n = e.runs.length;
      });
      order.sort(function (a, b) { return (b.f1 || 0) - (a.f1 || 0); });
      return order;
    }

    function legendOf(ents) {
      return ents.map(function (e) {
        return { label: e.label, color: e.color, shape: e.hollow ? "hollow" : "line" };
      });
    }

    function render() {
      C.hideTip();
      var runs = selected();
      var ents = entities(runs);
      txt(note, runs.length + " of " + P.runs.length + " runs in view · " +
        P.questionCount + " questions across " + P.paperCount + " papers" +
        (state.style === "both" ? " · both phrasings drawn as separate series" : ""));

      var available = [];
      P.runs.forEach(function (r) {
        if (state.style !== "both" && r.style !== state.style) return;
        if (available.indexOf(r.model) < 0) available.push(r.model);
      });
      chips.markAvailability(available, "no run with this phrasing");
      renderHero(runs);
      body.innerHTML = "";
      renderFigures(body, runs, ents);
      renderDetail(body, runs, ents);
    }

    function renderHero(runs) {
      heroHost.innerHTML = "";
      var hero = h("div", "hero", heroHost);
      var fig = h("div", "hero-figure", hero);
      var kpis = h("div", "kpis", hero);

      var best = bestBy(runs, function (r) { return r.f1; });
      txt(h("div", "hero-label", fig), "Best citation F1");
      if (!best) {
        txt(h("div", "hero-value", fig), "—");
        txt(h("p", "hero-caption", fig), "No runs match the current filters.");
        return;
      }
      txt(h("div", "hero-value", fig), fmt.score2(best.f1));
      var cap = h("p", "hero-caption", fig);
      txt(h("span", "hero-model", cap), modelLabel(best.model));
      cap.appendChild(document.createTextNode(
        " · " + P.styleLabel[best.style] + " phrasing · " + best.date));
      txt(h("p", "hero-note", fig),
        best.f1Stderr === null || best.f1Stderr === undefined ? "" : "± " + best.f1Stderr.toFixed(3) + " standard error");

      function kpi(label, value, caption) {
        var box = h("div", null, kpis);
        txt(h("div", "kpi-label", box), label);
        txt(h("div", "kpi-value", box), value);
        if (caption) txt(h("div", "kpi-caption", box), caption);
      }

      var bestAcc = bestBy(runs, function (r) { return r.accuracy; });
      kpi("Answer accuracy", fmt.pct0(bestAcc ? bestAcc.accuracy : null),
        "best in view — " + modelLabel(bestAcc ? bestAcc.model : ""));
      kpi("Cost / question", fmt.moneyFine(best.costPerQuestion),
        fmt.money(best.cost) + " for the best run");
      kpi("Time / question", fmt.duration(best.avgSampleTime),
        fmt.duration(best.duration) + " end to end");
      kpi("Corpus", P.paperCount + " papers", P.questionCount + " questions");
    }

    function renderFigures(parent, runs, ents) {
      sectionHead(parent, "Headline");
      var g1 = h("div", "grid", parent);

      /* the gap between getting it right and showing your work */
      var c1 = card(g1, {
        title: "Answering against attributing",
        sub: "Hollow marks are answer accuracy, filled marks citation F1. The connector is the attribution gap — how much of a correct answer the agent can actually point to."
      });
      C.mount(c1.wrap, "dumbbell", {
        title: "Answer accuracy against citation F1",
        rows: ents.map(function (e) {
          return { label: e.label, color: e.color, a: e.accuracy, b: e.f1 };
        }),
        aLabel: "Answer accuracy",
        bLabel: "Citation F1",
        xLabel: "Score",
        xZero: false,
        tableKey: "Model",
        legend: [
          { label: "Answer accuracy", color: "var(--ink-3)", shape: "hollow" },
          { label: "Citation F1", color: "var(--ink-3)", shape: "dot" }
        ]
      });

      var c2 = card(g1, {
        title: "Citation F1 against cost",
        sub: "Cost per question against attribution quality. Solid marks sit on the frontier."
      });
      C.mount(c2.wrap, "scatter", {
        title: "Citation F1 against cost per question",
        points: markFrontier(ents.filter(function (e) {
          return e.f1 !== null && e.cost !== null;
        }).map(function (e) {
          return {
            x: e.cost, y: e.f1, label: e.label,
            sub: e.n + (e.n === 1 ? " run" : " runs") + " averaged",
            rows: [
              { label: "Citation F1", value: fmt.score(e.f1) },
              { label: "Answer accuracy", value: fmt.score(e.accuracy) },
              { label: "Cost / question", value: fmt.moneyFine(e.cost) }
            ]
          };
        })),
        xLabel: "Cost per question (USD)",
        yLabel: "Citation F1",
        xFmt: fmt.moneyAxisFine,
        tableKey: "Model",
        legend: [
          { label: "On the cost/quality frontier", color: "var(--series-1)", shape: "dot" },
          { label: "Dominated by another run", color: "var(--muted-mark)", shape: "dot" }
        ]
      });

      sectionHead(parent, "Where attribution breaks down");
      var g2 = h("div", "grid", parent);

      var c3 = card(g2, {
        title: "Citation F1 by question difficulty",
        sub: "Difficulty is assigned when the question is written, from how much of the paper must be read to answer it."
      });
      C.mount(c3.wrap, "lines", {
        title: "Citation F1 by question difficulty",
        categories: P.difficulties.map(function (d) { return d.label; }),
        series: ents.map(function (e) {
          return {
            label: e.label, color: e.color, dash: e.dash, hollow: e.hollow,
            values: P.difficulties.map(function (d) {
              return meanOf(e.runs, function (r) { return r.difficultyF1[d.key]; });
            })
          };
        }),
        yLabel: "Citation F1",
        tableKey: "Model",
        legend: legendOf(ents)
      });

      var c4 = card(g2, {
        title: "Citation F1 by question type",
        sub: "Darker is better. Answer accuracy is near ceiling for every type, so attribution is the axis that separates models."
      });
      C.mount(c4.wrap, "heatmap", {
        title: "Citation F1 by question type",
        rows: ents.map(function (e) {
          return {
            label: e.label, color: e.color,
            values: P.qtypes.map(function (q) {
              return meanOf(e.runs, function (r) { return r.qtypeF1[q.key]; });
            })
          };
        }),
        cols: P.qtypes.map(function (q) { return { label: q.label }; }),
        measure: "Citation F1",
        tableKey: "Model",
        scaleLegend: ["0.0 F1", "1.0"]
      });

      /* per-paper — one series, one colour, sorted so the tail is obvious */
      var paperRows = P.papers.map(function (p) {
        var vals = [];
        runs.forEach(function (r) {
          var v = r.paperF1[p.id];
          if (v !== null && v !== undefined) vals.push(v);
        });
        var accVals = [];
        runs.forEach(function (r) {
          var v = r.paperAcc[p.id];
          if (v !== null && v !== undefined) accVals.push(v);
        });
        return {
          label: p.id,
          value: vals.length ? mean(vals) : null,
          sub: p.label,
          rows: accVals.length ? [{ label: "Answer accuracy", value: fmt.score(mean(accVals)) }] : []
        };
      }).filter(function (r) { return r.value !== null; })
        .sort(function (a, b) { return b.value - a.value; });

      var g3 = h("div", "grid", parent);
      var c5 = card(g3, {
        title: "Citation F1 by paper",
        sub: "Mean across the runs in view. The spread shows how much attribution quality depends on the paper's own structure rather than the model.",
        span: true
      });
      C.mount(c5.wrap, "hbar", {
        title: "Citation F1 by paper",
        rows: paperRows,
        measure: "Citation F1",
        xLabel: "Citation F1",
        xMax: 1,
        rowHeight: 24,
        labelWidth: 130,
        tableKey: "Paper"
      });
    }

    function renderDetail(parent, runs, ents) {
      sectionHead(parent, "Detail");

      var runBody = disclosure(parent, {
        summary: "All runs in view",
        note: runs.length + (runs.length === 1 ? " run" : " runs")
      });
      var actions = h("div", null, runBody);
      actions.style.margin = "4px 0 2px";
      var tokBtn = h("button", "ghost-btn", actions);
      tokBtn.type = "button";
      tokBtn.setAttribute("aria-pressed", "false");
      txt(tokBtn, "Show token accounting");

      var rows = runs.slice().sort(function (a, b) { return (b.f1 || 0) - (a.f1 || 0); })
        .map(function (r) {
          return Object.assign({}, r, {
            modelLabel: modelLabel(r.model),
            styleLabel: P.styleLabel[r.style]
          });
        });
      var bestF1 = Math.max.apply(null, rows.map(function (r) { return r.f1 === null ? -1 : r.f1; }));
      var bestAcc = Math.max.apply(null, rows.map(function (r) { return r.accuracy === null ? -1 : r.accuracy; }));

      var tokenCols = [
        { key: "tokIn", label: "Input", group: "Tokens", fmt: fmt.compact },
        { key: "tokOut", label: "Output", group: "Tokens", fmt: fmt.compact },
        { key: "tokCacheWrite", label: "Cache write", group: "Tokens", fmt: fmt.compact },
        { key: "tokCacheRead", label: "Cache read", group: "Tokens", fmt: fmt.compact },
        { key: "tokTotal", label: "Total", group: "Tokens", fmt: fmt.compact }
      ];
      tokenCols.forEach(function (c) { c.hidden = true; });

      var table = null;
      function draw() {
        if (table) table.scroll.remove();
        table = dataTable(runBody, {
          caption: "Every scored, complete run. Click a column heading to sort.",
          columns: [
            { key: "modelLabel", label: "Model", text: true, group: "Run", render: function (td, row) {
              var sw = h("span", "cell-swatch", td);
              sw.style.background = modelColor(row.model);
              td.appendChild(document.createTextNode(row.modelLabel));
            } },
            { key: "styleLabel", label: "Phrasing", text: true, group: "Run" },
            { key: "date", label: "Date", text: true, group: "Run", className: "mono" },
            { key: "samples", label: "Questions", group: "Run", fmt: fmt.int },
            { key: "accuracy", label: "Answer accuracy", group: "Score", className: "num-strong", render: function (td, row) {
              var span = h("span", row.accuracy === bestAcc ? "best" : null, td);
              txt(span, fmt.score(row.accuracy) +
                (row.accuracyStderr === null || row.accuracyStderr === undefined ? "" : " ± " + row.accuracyStderr.toFixed(3)));
            } },
            { key: "f1", label: "Citation F1", group: "Score", className: "num-strong", render: function (td, row) {
              var span = h("span", row.f1 === bestF1 ? "best" : null, td);
              txt(span, fmt.score(row.f1) +
                (row.f1Stderr === null || row.f1Stderr === undefined ? "" : " ± " + row.f1Stderr.toFixed(3)));
            } },
            { key: "cost", label: "Cost", group: "Score", fmt: fmt.money },
            { key: "costPerQuestion", label: "Cost / question", group: "Score", fmt: fmt.moneyFine },
            { key: "duration", label: "Wall clock", group: "Time", fmt: fmt.duration },
            { key: "avgSampleTime", label: "Mean / question", group: "Time", fmt: fmt.duration },
            { key: "minSampleTime", label: "Fastest", group: "Time", fmt: fmt.duration },
            { key: "maxSampleTime", label: "Slowest", group: "Time", fmt: fmt.duration }
          ].concat(tokenCols).concat([
            { key: "version", label: "Data set", text: true, group: "Provenance", className: "mono" }
          ]),
          rows: rows
        });
      }
      draw();
      tokBtn.addEventListener("click", function () {
        var on = tokBtn.getAttribute("aria-pressed") === "true";
        tokenCols.forEach(function (c) { c.hidden = on; });
        tokBtn.setAttribute("aria-pressed", on ? "false" : "true");
        txt(tokBtn, on ? "Show token accounting" : "Hide token accounting");
        draw();
      });

      /* per-paper table, both measures */
      var paperBody = disclosure(parent, {
        summary: "Every paper",
        note: P.papers.length + " papers"
      });
      dataTable(paperBody, {
        columns: [
          { key: "id", label: "Paper", text: true, className: "mono" },
          { key: "title", label: "Title", text: true, render: function (td, row) {
            td.style.whiteSpace = "normal";
            td.style.minWidth = "300px";
            td.style.maxWidth = "560px";
            txt(td, row.title || "");
          } },
          { key: "questions", label: "Questions", fmt: fmt.int },
          { key: "acc", label: "Answer accuracy", group: "Mean in view", fmt: fmt.score2 },
          { key: "f1", label: "Citation F1", group: "Mean in view", fmt: fmt.score2, className: "num-strong" }
        ],
        rows: P.papers.map(function (p) {
          var f1s = [], accs = [];
          runs.forEach(function (r) {
            if (r.paperF1[p.id] !== null && r.paperF1[p.id] !== undefined) f1s.push(r.paperF1[p.id]);
            if (r.paperAcc[p.id] !== null && r.paperAcc[p.id] !== undefined) accs.push(r.paperAcc[p.id]);
          });
          return {
            id: p.id, title: p.label, questions: p.questions,
            acc: accs.length ? mean(accs) : null,
            f1: f1s.length ? mean(f1s) : null
          };
        }).sort(function (a, b) { return (b.f1 || 0) - (a.f1 || 0); })
      });

      var aboutBody = disclosure(parent, { summary: "About this benchmark" });
      P.about.forEach(function (para) {
        var p = h("p", "card-sub", aboutBody);
        p.style.marginBottom = "8px";
        p.style.maxWidth = "80ch";
        txt(p, para);
      });
      var links = h("p", "card-sub", aboutBody);
      links.appendChild(document.createTextNode("Raw data: "));
      var a1 = h("a", null, links);
      a1.href = "pubs_runs.json";
      txt(a1, "pubs_runs.json");
    }

    render();
  }

  /* =========================================================================
     Shell — tabs, theme, deep links
     ========================================================================= */

  var TABS = [
    {
      id: "tools", label: "Research tools discovery", task: T.task,
      count: T.runs.length, build: toolsBuild
    },
    {
      id: "pubs", label: "Publication QA", task: P ? P.task : "",
      count: P ? P.runs.length : 0, build: pubsBuild
    }
  ];

  function initShell() {
    var tabBar = document.getElementById("tab-bar");
    var panels = {};
    var built = {};

    TABS.forEach(function (t) {
      var btn = h("button", "tab", tabBar);
      btn.type = "button";
      btn.id = "tab-" + t.id;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-controls", "panel-" + t.id);
      btn.setAttribute("aria-selected", "false");
      /* Spell the accessible name out, so the task id and the bare run count
         are not read as part of the benchmark's title. */
      btn.setAttribute("aria-label",
        t.label + (t.task ? " (" + t.task + ")" : "") + " — " +
        t.count + (t.count === 1 ? " run" : " runs"));
      txt(h("span", "tab-name", btn), t.label);
      if (t.task) txt(h("span", "tab-task", btn), t.task);
      txt(h("span", "tab-count", btn), String(t.count));
      btn.addEventListener("click", function () { select(t.id, true); });
      t.btn = btn;

      var panel = document.getElementById("panel-" + t.id);
      panels[t.id] = panel;
    });

    function select(id, push) {
      TABS.forEach(function (t) {
        var on = t.id === id;
        t.btn.setAttribute("aria-selected", on ? "true" : "false");
        panels[t.id].hidden = !on;
      });
      var t = TABS.filter(function (x) { return x.id === id; })[0];
      if (t && !built[id]) { built[id] = true; t.build(panels[id]); }
      C.hideTip();
      C.redrawAll();
      if (push && window.location.hash !== "#" + id) {
        history.replaceState(null, "", "#" + id);
      }
    }

    var initial = (window.location.hash || "").replace("#", "");
    if (!TABS.some(function (t) { return t.id === initial; })) initial = TABS[0].id;
    select(initial, false);

    window.addEventListener("hashchange", function () {
      var id = (window.location.hash || "").replace("#", "");
      if (TABS.some(function (t) { return t.id === id; })) select(id, false);
    });

    /* keyboard: arrow keys move between tabs */
    tabBar.addEventListener("keydown", function (e) {
      var idx = TABS.map(function (t) { return t.btn.getAttribute("aria-selected") === "true"; }).indexOf(true);
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        var next = (idx + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length;
        TABS[next].btn.focus();
        select(TABS[next].id, true);
      }
    });
  }

  function initTheme() {
    var btn = document.getElementById("theme-toggle");
    var stored = null;
    try { stored = localStorage.getItem("nfkg-theme"); } catch (e) { /* private mode */ }
    if (stored === "light" || stored === "dark") {
      document.documentElement.setAttribute("data-theme", stored);
    }
    function current() {
      var attr = document.documentElement.getAttribute("data-theme");
      if (attr) return attr;
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    function sync() {
      btn.setAttribute("aria-label", current() === "dark" ? "Switch to light theme" : "Switch to dark theme");
      btn.setAttribute("title", btn.getAttribute("aria-label"));
    }
    sync();
    btn.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      var root = document.documentElement;
      root.classList.add("theme-switching");
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("nfkg-theme", next); } catch (e) { /* ignore */ }
      sync();
      C.hideTip();
      /* drop the guard once the new colours have been painted */
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { root.classList.remove("theme-switching"); });
      });
    });
  }

  /* The masthead's height depends on how the brand and tabs wrap, so the
     sticky filter row reads it from a custom property rather than a guess. */
  function trackMastheadHeight() {
    var masthead = document.querySelector(".masthead");
    if (!masthead) return;
    function sync() {
      document.documentElement.style.setProperty(
        "--masthead-h", Math.round(masthead.getBoundingClientRect().height) + "px");
    }
    sync();
    if (window.ResizeObserver) new ResizeObserver(sync).observe(masthead);
    else window.addEventListener("resize", sync);
  }

  initTheme();
  initShell();
  trackMastheadHeight();
})();
