/* ==========================================================================
   Tiny SVG chart engine — no dependencies.

   Every chart built here ships, by contract:
     - a hover/focus layer with a tooltip (values lead, labels follow)
     - a legend whenever there are two or more series
     - a table-view twin, so no value is reachable only by hovering
     - hairline solid gridlines, thin marks, 2px surface gaps and rings

   Colours arrive as CSS custom-property references (e.g. "var(--series-1)")
   so a theme switch repaints without a re-render.
   ========================================================================== */
(function (global) {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";

  /* ------------------------------------------------------------- helpers -- */

  function el(name, attrs, parent) {
    var node = document.createElementNS(SVG_NS, name);
    if (attrs) {
      for (var k in attrs) {
        if (attrs[k] !== null && attrs[k] !== undefined) {
          node.setAttribute(k, String(attrs[k]));
        }
      }
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  /* Text is always inserted as a text node — series and category names come
     from run metadata and are treated as untrusted. */
  function text(parent, str, attrs) {
    var node = el("text", attrs, parent);
    node.appendChild(document.createTextNode(str === null || str === undefined ? "" : String(str)));
    return node;
  }

  function html(name, className, parent) {
    var node = document.createElement(name);
    if (className) node.className = className;
    if (parent) parent.appendChild(node);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function extent(values) {
    var lo = Infinity, hi = -Infinity;
    for (var i = 0; i < values.length; i++) {
      var v = values[i];
      if (v === null || v === undefined || isNaN(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (lo === Infinity) return [0, 1];
    return [lo, hi];
  }

  /* Axis ticks on clean numbers — never raw min/max. */
  function niceTicks(lo, hi, count) {
    if (hi === lo) { hi = lo + 1; }
    var raw = (hi - lo) / Math.max(1, count);
    var mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var norm = raw / mag;
    var step = mag * (norm >= 5 ? 5 : norm >= 2 ? 2 : norm >= 1 ? 1 : 0.5);
    var start = Math.ceil(lo / step) * step;
    var out = [];
    for (var v = start; v <= hi + step * 1e-6; v += step) {
      out.push(Math.abs(v) < step * 1e-6 ? 0 : Number(v.toFixed(10)));
    }
    /* Rounding to a clean step can overshoot the budget; thin rather than
       letting the labels pile up in a narrow plot. */
    while (out.length > count + 1 && out.length > 2) {
      out = out.filter(function (_, i) { return i % 2 === 0; });
    }
    return out;
  }

  /* Approximate text width for the UI sans at a given size. Good enough to
     reserve gutters and decide when a label has to be shortened; the exact
     name always survives in the legend, the tooltip and the table view. */
  function textWidth(str, fontPx) {
    return String(str).length * fontPx * 0.62;
  }

  /* Shorten to fit, with an ellipsis — never let a label run out of its box. */
  function fitLabel(str, maxPx, fontPx) {
    str = String(str);
    if (textWidth(str, fontPx) <= maxPx) return str;
    var perChar = fontPx * 0.62;
    var keep = Math.max(3, Math.floor(maxPx / perChar) - 1);
    return str.slice(0, keep).replace(/[\s·-]+$/, "") + "\u2026";
  }

  /* Fewer ticks in a narrow plot — five labels in 200px is a smear. */
  function tickCount(px) {
    return Math.max(2, Math.min(5, Math.floor(px / 78)));
  }

  var fmt = {
    score: function (v) { return v === null || v === undefined ? "—" : v.toFixed(3); },
    score2: function (v) { return v === null || v === undefined ? "—" : v.toFixed(2); },
    pct: function (v) { return v === null || v === undefined ? "—" : (v * 100).toFixed(1) + "%"; },
    pct0: function (v) { return v === null || v === undefined ? "—" : Math.round(v * 100) + "%"; },
    axisScore: function (v) { return v.toFixed(2); },
    money: function (v) {
      if (v === null || v === undefined) return "—";
      return "$" + (v >= 100 ? Math.round(v).toLocaleString("en-US") : v.toFixed(2));
    },
    moneyAxis: function (v) { return "$" + (v >= 10 ? Math.round(v) : v.toFixed(1)); },
    moneyFine: function (v) {
      if (v === null || v === undefined) return "—";
      return v >= 1 ? fmt.money(v) : "$" + v.toFixed(3);
    },
    /* cost-per-question lives in cents, so the axis has to keep them */
    moneyAxisFine: function (v) {
      if (v >= 10) return "$" + Math.round(v);
      if (v >= 1) return "$" + v.toFixed(1);
      return "$" + v.toFixed(2);
    },
    minutes: function (v) {
      if (v === null || v === undefined) return "—";
      return v >= 10 ? Math.round(v) + "m" : v.toFixed(1) + "m";
    },
    duration: function (secs) {
      if (secs === null || secs === undefined) return "—";
      var s = Math.round(secs), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      s = s % 60;
      if (h) return h + "h " + String(m).padStart(2, "0") + "m";
      if (m) return m + "m " + String(s).padStart(2, "0") + "s";
      return s + "s";
    },
    int: function (v) { return v === null || v === undefined ? "—" : Math.round(v).toLocaleString("en-US"); },
    compact: function (v) {
      if (v === null || v === undefined) return "—";
      var a = Math.abs(v);
      if (a >= 1e9) return (v / 1e9).toFixed(a >= 1e10 ? 0 : 1) + "B";
      if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "M";
      if (a >= 1e3) return (v / 1e3).toFixed(a >= 1e4 ? 0 : 1) + "K";
      return String(v);
    }
  };

  /* --------------------------------------------------------------- tooltip -- */

  var tip = null;

  function tipNode() {
    if (!tip) {
      tip = html("div", "tooltip", document.body);
      tip.setAttribute("role", "status");
      tip.setAttribute("aria-live", "polite");
    }
    return tip;
  }

  /* rows: [{label, value, color, keyShape}] — value is the strong element */
  function showTip(x, y, spec) {
    var node = tipNode();
    clear(node);
    if (spec.title) html("div", "tooltip-title", node).textContent = spec.title;
    if (spec.sub) html("div", "tooltip-sub", node).textContent = spec.sub;
    (spec.rows || []).forEach(function (row) {
      var r = html("div", "tooltip-row", node);
      var key = html("span", "tr-key" + (row.keyShape === "dot" ? " dot" : ""), r);
      key.style.background = row.color || "transparent";
      html("span", "tr-label", r).textContent = row.label;
      html("span", "tr-value", r).textContent = row.value;
    });
    node.style.left = Math.round(x) + "px";
    node.style.top = Math.round(y) + "px";
    node.setAttribute("data-open", "true");
  }

  function hideTip() {
    if (tip) tip.setAttribute("data-open", "false");
  }

  document.addEventListener("scroll", hideTip, true);

  /* Anchor a tooltip on an SVG element's own box, so keyboard focus and
     pointer hover put it in the same place. */
  function anchorOf(node) {
    var box = node.getBoundingClientRect();
    return { x: box.left + box.width / 2, y: box.top };
  }

  /* ----------------------------------------------------------------- frame -- */

  /* Builds plot geometry, gridlines, axis rules and tick labels.
     `pad.bottom` always includes the x-axis band, so the axis can never be
     cropped out of a fixed-height container. */
  function frame(svg, opts) {
    var W = opts.width, H = opts.height;
    var pad = opts.pad;
    var plot = {
      x0: pad.left, y0: pad.top,
      x1: W - pad.right, y1: H - pad.bottom,
      w: W - pad.left - pad.right,
      h: H - pad.top - pad.bottom
    };
    var g = el("g", null, svg);

    if (opts.yTicks) {
      opts.yTicks.forEach(function (t) {
        var y = opts.yScale(t);
        el("line", {
          x1: plot.x0, y1: y, x2: plot.x1, y2: y,
          stroke: "var(--grid)", "stroke-width": 1, "shape-rendering": "crispEdges"
        }, g);
        text(g, opts.yFmt ? opts.yFmt(t) : t, {
          x: plot.x0 - 9, y: y + 4, "text-anchor": "end",
          "font-size": 11, fill: "var(--ink-3)", "font-variant-numeric": "tabular-nums"
        });
      });
    }

    /* baseline / axis rule — solid hairline, one step off the surface */
    el("line", {
      x1: plot.x0, y1: plot.y1, x2: plot.x1, y2: plot.y1,
      stroke: "var(--axis)", "stroke-width": 1, "shape-rendering": "crispEdges"
    }, g);

    if (opts.yLabel) {
      var ly = plot.y0 + plot.h / 2;
      text(g, opts.yLabel, {
        transform: "rotate(-90 12 " + ly + ")", x: 12, y: ly,
        "text-anchor": "middle", "font-size": 11.5, fill: "var(--ink-3)",
        "letter-spacing": "0.04em"
      });
    }
    if (opts.xLabel) {
      text(g, fitLabel(opts.xLabel, W - 10, 11.5), {
        x: W / 2, y: H - 4, "text-anchor": "middle",
        "font-size": 11.5, fill: "var(--ink-3)", "letter-spacing": "0.04em"
      });
    }
    return { g: g, plot: plot };
  }

  /* ----------------------------------------------------------- label layout -- */

  /* Nudge overlapping direct labels apart and draw a leader line back to the
     mark, rather than letting them detach silently or collide.

     Labels only push each other when they actually share horizontal space —
     two labels at opposite ends of the plot can sit at the same height, and
     moving them would detach them from their marks for nothing. Items may
     carry `x0`/`x1`; without them every pair is treated as overlapping, which
     is what a shared right-hand gutter (line end labels) wants. */
  function decollide(items, minGap, lo, hi) {
    items.sort(function (a, b) { return a.y - b.y; });

    function sharesX(a, b) {
      if (a.x0 === undefined || b.x0 === undefined) return true;
      return a.x0 < b.x1 && b.x0 < a.x1;
    }

    for (var i = 1; i < items.length; i++) {
      var floorY = -Infinity;
      for (var j = 0; j < i; j++) {
        if (sharesX(items[i], items[j])) floorY = Math.max(floorY, items[j].y + minGap);
      }
      if (items[i].y < floorY) items[i].y = floorY;
    }

    var overflow = items.length ? items[items.length - 1].y - hi : 0;
    if (overflow > 0) {
      for (var k = items.length - 1; k >= 0; k--) {
        items[k].y -= overflow;
        if (k > 0 && items[k].y - items[k - 1].y >= minGap) break;
      }
    }
    if (items.length && items[0].y < lo) {
      var shift = lo - items[0].y;
      for (var m = 0; m < items.length; m++) items[m].y += shift;
    }
    return items;
  }

  /* ---------------------------------------------------------------- scatter -- */

  /* Emphasis form: the story is the frontier, so frontier points carry the
     accent and dominated points recede to the de-emphasis gray. Identity is
     carried by a direct label on every point (few points by construction),
     never by hue. */
  function renderScatter(svg, spec, size) {
    var pts = spec.points.filter(function (p) {
      return p.x !== null && p.x !== undefined && p.y !== null && p.y !== undefined;
    });
    if (!pts.length) return false;

    var W = size.width, H = spec.height || 320;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("height", H);

    var xs = pts.map(function (p) { return p.x; });
    var ys = pts.map(function (p) { return p.y; });
    var xe = extent(xs), ye = extent(ys);
    var xMin = spec.xZero === false ? Math.max(0, xe[0] - (xe[1] - xe[0] || 1) * 0.25) : 0;
    var xMax = xe[1] + (xe[1] - xMin || 1) * 0.18;
    var yPad = (ye[1] - ye[0] || 0.1) * 0.35;
    var yMin = Math.max(0, ye[0] - yPad);
    var yMax = Math.min(1, ye[1] + yPad);
    if (yMax - yMin < 0.08) { yMin = Math.max(0, yMin - 0.04); yMax = Math.min(1, yMax + 0.04); }

    var pad = { top: 18, right: 26, bottom: 46, left: 52 };
    var plotW = W - pad.left - pad.right, plotH = H - pad.top - pad.bottom;
    var sx = function (v) { return pad.left + ((v - xMin) / (xMax - xMin)) * plotW; };
    var sy = function (v) { return H - pad.bottom - ((v - yMin) / (yMax - yMin)) * plotH; };

    var yTicks = niceTicks(yMin, yMax, tickCount(plotH * 1.6));
    var f = frame(svg, {
      width: W, height: H, pad: pad, yScale: sy, yTicks: yTicks,
      yFmt: spec.yFmt || fmt.axisScore, yLabel: spec.yLabel, xLabel: spec.xLabel
    });
    var g = f.g, plot = f.plot;

    niceTicks(xMin, xMax, tickCount(plotW)).forEach(function (t) {
      var x = sx(t);
      if (x < plot.x0 - 1 || x > plot.x1 + 1) return;
      el("line", {
        x1: x, y1: plot.y0, x2: x, y2: plot.y1,
        stroke: "var(--grid)", "stroke-width": 1, "shape-rendering": "crispEdges"
      }, g);
      text(g, (spec.xFmt || String)(t), {
        x: x, y: plot.y1 + 20, "text-anchor": "middle", "font-size": 11,
        fill: "var(--ink-3)", "font-variant-numeric": "tabular-nums"
      });
    });

    /* frontier path: up-and-over steps through the emphasised points */
    var front = pts.filter(function (p) { return p.emph; })
      .sort(function (a, b) { return a.x - b.x; });
    if (front.length > 1) {
      var d = "M" + sx(front[0].x) + "," + sy(front[0].y);
      for (var i = 1; i < front.length; i++) {
        d += "V" + sy(front[i].y) + "H" + sx(front[i].x);
      }
      el("path", {
        d: d, fill: "none", stroke: "var(--series-1)", "stroke-width": 1.5,
        "stroke-dasharray": "1 4", "stroke-linecap": "round", opacity: 0.55
      }, g);
    }

    /* dominated points first, so accent marks sit on top */
    var ordered = pts.slice().sort(function (a, b) { return (a.emph ? 1 : 0) - (b.emph ? 1 : 0); });
    var labels = [];

    ordered.forEach(function (p) {
      var cx = sx(p.x), cy = sy(p.y);
      var color = p.emph ? "var(--series-1)" : "var(--muted-mark)";
      var hit = el("g", {
        tabindex: 0, role: "img",
        "aria-label": p.label + ": " + (spec.yLabel || "value") + " " + fmt.score(p.y) +
          ", " + (spec.xLabel || "x") + " " + (spec.xFmt ? spec.xFmt(p.x) : p.x)
      }, g);
      /* generous transparent hit area — an 8px dot is not a hover target */
      el("circle", { cx: cx, cy: cy, r: 14, fill: "transparent" }, hit);
      var dot = el("circle", {
        cx: cx, cy: cy, r: p.emph ? 5.5 : 4.5, fill: color,
        stroke: "var(--surface)", "stroke-width": 2
      }, hit);

      function show() {
        dot.setAttribute("r", p.emph ? 7 : 6);
        var a = anchorOf(dot);
        showTip(a.x, a.y, {
          title: p.label,
          sub: p.sub,
          rows: p.rows || []
        });
      }
      function hide() { dot.setAttribute("r", p.emph ? 5.5 : 4.5); hideTip(); }
      hit.addEventListener("pointerenter", show);
      hit.addEventListener("pointerleave", hide);
      hit.addEventListener("focus", show);
      hit.addEventListener("blur", hide);

      labels.push({ p: p, cx: cx, cy: cy, y: cy });
    });

    /* direct labels — right of the mark, flipped left when they would clip */
    var LBL_FONT = 11.5;
    var placed = [];
    labels.forEach(function (L) {
      var w = textWidth(L.p.label, LBL_FONT);
      var fitsRight = L.cx + 11 + w <= plot.x1;
      var fitsLeft = L.cx - 11 - w >= plot.x0;
      /* No room either side: the legend, tooltip and table view still carry
         the name, so a clipped label is the one thing we do not ship. */
      if (!fitsRight && !fitsLeft) return;
      L.side = fitsRight ? 1 : -1;
      L.x0 = fitsRight ? L.cx + 9 : L.cx - 11 - w;
      L.x1 = fitsRight ? L.cx + 11 + w : L.cx - 9;
      placed.push(L);
    });
    decollide(placed, 15, plot.y0 + 6, plot.y1 - 2);
    placed.forEach(function (L) {
      var lx = L.cx + L.side * 11;
      text(g, L.p.label, {
        x: lx, y: L.y + 3.5, "text-anchor": L.side > 0 ? "start" : "end",
        "font-size": LBL_FONT, fill: L.p.emph ? "var(--ink)" : "var(--ink-3)",
        "font-weight": L.p.emph ? 600 : 400
      });
      if (Math.abs(L.y - L.cy) > 4) {
        el("path", {
          d: "M" + (L.cx + L.side * 7) + "," + L.cy + "L" + (lx - L.side * 2) + "," + L.y,
          stroke: "var(--axis)", "stroke-width": 1, fill: "none"
        }, g);
      }
    });

    return true;
  }

  /* ------------------------------------------------------------------ lines -- */

  /* Ordinal or linear x. End-labelled, crosshair-driven: the reader aims at a
     category, never at a 2px line, and one tooltip lists every series there. */
  function renderLines(svg, spec, size) {
    var series = spec.series.filter(function (s) {
      return s.values.some(function (v) { return v !== null && v !== undefined; });
    });
    if (!series.length) return false;

    var cats = spec.categories;
    var W = size.width, H = spec.height || 320;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("height", H);

    var all = [];
    series.forEach(function (s) {
      s.values.forEach(function (v) { if (v !== null && v !== undefined) all.push(v); });
    });
    var ye = extent(all);
    var span = ye[1] - ye[0];
    var yMin = spec.yZero ? 0 : Math.max(0, ye[0] - Math.max(span * 0.25, 0.03));
    var yMax = Math.min(spec.yMaxCap === undefined ? 1 : spec.yMaxCap, ye[1] + Math.max(span * 0.25, 0.03));
    if (yMax - yMin < 0.06) { yMin = Math.max(0, yMin - 0.03); yMax = yMin + 0.09; }

    /* Category labels are centred on their tick, so the first and last need
       half a label of padding or they escape the card. */
    var CAT_FONT = 11.5;
    var catHalf = cats.reduce(function (m, c) {
      return Math.max(m, textWidth(c, CAT_FONT));
    }, 0) / 2 + 4;
    var LABEL_FONT = 11.5;
    var endGutterCap = Math.max(90, Math.min(230, W * 0.28));
    var widestSeries = series.reduce(function (m, s) {
      return Math.max(m, textWidth(s.label, LABEL_FONT));
    }, 0);
    var endGutter = Math.min(endGutterCap, widestSeries + 20);
    var labelRoom = spec.endLabels === false ? Math.max(20, catHalf) : endGutter;
    var pad = {
      top: 18, right: labelRoom, bottom: spec.xLabel ? 52 : 38,
      left: Math.max(52, catHalf)
    };
    var plotW = W - pad.left - pad.right, plotH = H - pad.top - pad.bottom;
    var sy = function (v) { return H - pad.bottom - ((v - yMin) / (yMax - yMin)) * plotH; };
    var n = cats.length;
    var sx = function (i) { return n === 1 ? pad.left + plotW / 2 : pad.left + (i / (n - 1)) * plotW; };

    var f = frame(svg, {
      width: W, height: H, pad: pad, yScale: sy,
      yTicks: niceTicks(yMin, yMax, tickCount(plotH * 1.6)), yFmt: spec.yFmt || fmt.axisScore,
      yLabel: spec.yLabel, xLabel: spec.xLabel
    });
    var g = f.g, plot = f.plot;

    /* Thin the tick labels by measured position rather than a fixed stride, so
       the first and last always survive and nothing ever overlaps. */
    var keep = [], cursor = -Infinity;
    for (var ci = 0; ci < n; ci++) {
      var cwid = textWidth(cats[ci], CAT_FONT);
      if (ci === 0 || sx(ci) - cwid / 2 >= cursor + 6) {
        keep.push(ci);
        cursor = sx(ci) + cwid / 2;
      }
    }
    if (keep[keep.length - 1] !== n - 1) {
      /* the last category always gets a label; drop whatever it would hit */
      var lastW = textWidth(cats[n - 1], CAT_FONT);
      while (keep.length > 1 &&
             sx(keep[keep.length - 1]) + textWidth(cats[keep[keep.length - 1]], CAT_FONT) / 2 + 6 >
             sx(n - 1) - lastW / 2) {
        keep.pop();
      }
      keep.push(n - 1);
    }
    keep.forEach(function (i) {
      var label = cats[i];
      var half = textWidth(label, CAT_FONT) / 2;
      /* pin the end labels inside the frame instead of letting them escape */
      var anchor = "middle", x = sx(i);
      if (x - half < 1) { anchor = "start"; x = 1; }
      else if (x + half > W - 1) { anchor = "end"; x = W - 1; }
      text(g, label, {
        x: x, y: plot.y1 + 22, "text-anchor": anchor, "font-size": CAT_FONT,
        fill: "var(--ink-2)"
      });
    });

    /* crosshair band, one per category — the hit target is the whole column */
    var cross = el("line", {
      x1: 0, y1: plot.y0, x2: 0, y2: plot.y1, stroke: "var(--axis)",
      "stroke-width": 1, opacity: 0, "pointer-events": "none"
    }, g);

    series.forEach(function (s) {
      var d = "", started = false;
      s.values.forEach(function (v, i) {
        if (v === null || v === undefined) { started = false; return; }
        d += (started ? "L" : "M") + sx(i) + "," + sy(v);
        started = true;
      });
      el("path", {
        d: d, fill: "none", stroke: s.color, "stroke-width": 2,
        "stroke-linejoin": "round", "stroke-linecap": "round",
        "stroke-dasharray": s.dash || null
      }, g);
      s.values.forEach(function (v, i) {
        if (v === null || v === undefined) return;
        el("circle", {
          cx: sx(i), cy: sy(v), r: 4.5, fill: s.hollow ? "var(--surface)" : s.color,
          stroke: s.hollow ? s.color : "var(--surface)", "stroke-width": 2
        }, g);
      });
    });

    /* end labels, de-collided with leader lines */
    if (spec.endLabels !== false) {
      var ends = [];
      series.forEach(function (s) {
        for (var i = s.values.length - 1; i >= 0; i--) {
          var v = s.values[i];
          if (v !== null && v !== undefined) {
            ends.push({ s: s, i: i, v: v, cy: sy(v), y: sy(v) });
            break;
          }
        }
      });
      decollide(ends, 15, plot.y0 + 5, plot.y1);
      ends.forEach(function (E) {
        var x = sx(E.i);
        text(g, fitLabel(E.s.label, W - x - 16, LABEL_FONT), {
          x: x + 12, y: E.y + 4, "text-anchor": "start", "font-size": 11.5,
          fill: "var(--ink-2)"
        });
        if (Math.abs(E.y - E.cy) > 3) {
          el("path", {
            d: "M" + (x + 7) + "," + E.cy + "L" + (x + 10) + "," + E.y,
            stroke: "var(--axis)", "stroke-width": 1, fill: "none"
          }, g);
        }
      });
    }

    var bands = el("g", null, g);
    cats.forEach(function (c, i) {
      var bw = n === 1 ? plotW : plotW / (n - 1);
      var bx = Math.max(plot.x0, sx(i) - bw / 2);
      var bw2 = Math.min(plot.x1, sx(i) + bw / 2) - bx;
      var band = el("rect", {
        x: bx, y: plot.y0, width: bw2, height: plotH, fill: "transparent",
        tabindex: 0, role: "img",
        "aria-label": c + ": " + series.map(function (s) {
          return s.label + " " + fmt.score(s.values[i]);
        }).join(", ")
      }, bands);

      function show() {
        cross.setAttribute("x1", sx(i));
        cross.setAttribute("x2", sx(i));
        cross.setAttribute("opacity", 0.5);
        var box = band.getBoundingClientRect();
        var rows = series.map(function (s) {
          return {
            label: s.label, color: s.color,
            value: (spec.tipFmt || fmt.score)(s.values[i])
          };
        });
        /* optional per-category detail, e.g. which run produced this point */
        if (spec.pointRows) rows = rows.concat(spec.pointRows(i) || []);
        showTip(box.left + box.width / 2, box.top + 8, {
          title: c,
          sub: spec.tipSub,
          rows: rows
        });
      }
      function hide() { cross.setAttribute("opacity", 0); hideTip(); }
      band.addEventListener("pointerenter", show);
      band.addEventListener("pointermove", show);
      band.addEventListener("pointerleave", hide);
      band.addEventListener("focus", show);
      band.addEventListener("blur", hide);
    });

    return true;
  }

  /* --------------------------------------------------------------- dumbbell -- */

  /* Before -> after per row: one hue, two shades, connector carries the gap. */
  function renderDumbbell(svg, spec, size) {
    var rows = spec.rows.filter(function (r) {
      return r.a !== null && r.a !== undefined && r.b !== null && r.b !== undefined;
    });
    if (!rows.length) return false;

    var W = size.width;
    var rowH = 30;
    var ROW_FONT = 12;
    var gutterCap = Math.max(110, Math.min(spec.labelWidth || 230, W * 0.34));
    var gutter = Math.min(gutterCap, rows.reduce(function (m, r) {
      return Math.max(m, textWidth(r.label, ROW_FONT));
    }, 0) + 18);
    var pad = { top: 16, right: 54, bottom: 40, left: gutter };
    var H = pad.top + pad.bottom + rows.length * rowH;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("height", H);

    var vals = [];
    rows.forEach(function (r) { vals.push(r.a, r.b); });
    var ve = extent(vals);
    var xMin = spec.xZero ? 0 : Math.max(0, ve[0] - Math.max((ve[1] - ve[0]) * 0.22, 0.04));
    var xMax = Math.min(spec.xMaxCap === undefined ? 1 : spec.xMaxCap,
      ve[1] + Math.max((ve[1] - ve[0]) * 0.22, 0.04));
    if (xMax - xMin < 0.08) { xMin = Math.max(0, xMin - 0.04); xMax = xMin + 0.12; }

    var plotW = W - pad.left - pad.right;
    var sx = function (v) { return pad.left + ((v - xMin) / (xMax - xMin)) * plotW; };
    var g = el("g", null, svg);

    niceTicks(xMin, xMax, tickCount(plotW)).forEach(function (t) {
      var x = sx(t);
      el("line", {
        x1: x, y1: pad.top - 4, x2: x, y2: H - pad.bottom + 4,
        stroke: "var(--grid)", "stroke-width": 1, "shape-rendering": "crispEdges"
      }, g);
      text(g, (spec.xFmt || fmt.axisScore)(t), {
        x: x, y: H - pad.bottom + 21, "text-anchor": "middle", "font-size": 11,
        fill: "var(--ink-3)", "font-variant-numeric": "tabular-nums"
      });
    });
    if (spec.xLabel) {
      text(g, fitLabel(spec.xLabel, W - 10, 11.5), {
        x: W / 2, y: H - 4, "text-anchor": "middle",
        "font-size": 11.5, fill: "var(--ink-3)", "letter-spacing": "0.04em"
      });
    }

    rows.forEach(function (r, i) {
      var cy = pad.top + i * rowH + rowH / 2;
      var xa = sx(r.a), xb = sx(r.b);
      var color = r.color || "var(--series-1)";

      text(g, fitLabel(r.label, pad.left - 14, ROW_FONT), {
        x: pad.left - 12, y: cy + 4, "text-anchor": "end", "font-size": ROW_FONT,
        fill: "var(--ink-2)"
      });

      el("line", {
        x1: Math.min(xa, xb) + 5, y1: cy, x2: Math.max(xa, xb) - 5, y2: cy,
        stroke: color, "stroke-width": 2, opacity: 0.28, "stroke-linecap": "round"
      }, g);

      /* first mark hollow, second filled — two shades of the row's own hue */
      el("circle", {
        cx: xa, cy: cy, r: 5, fill: "var(--surface)", stroke: color, "stroke-width": 2
      }, g);
      el("circle", {
        cx: xb, cy: cy, r: 5, fill: color, stroke: "var(--surface)", "stroke-width": 2
      }, g);

      /* value at the trailing end only — never a number on every mark */
      var lead = xb >= xa ? xb : xa;
      text(g, (spec.valueFmt || fmt.score2)(xb >= xa ? r.b : r.a), {
        x: lead + 11, y: cy + 4, "text-anchor": "start", "font-size": 11.5,
        fill: "var(--ink)", "font-weight": 600, "font-variant-numeric": "tabular-nums"
      });

      var hit = el("rect", {
        x: pad.left - 4, y: cy - rowH / 2, width: plotW + 8, height: rowH,
        fill: "transparent", tabindex: 0, role: "img",
        "aria-label": r.label + ": " + spec.aLabel + " " + fmt.score(r.a) +
          ", " + spec.bLabel + " " + fmt.score(r.b)
      }, g);
      function show() {
        var box = hit.getBoundingClientRect();
        showTip(box.left + box.width / 2, box.top, {
          title: r.label,
          sub: r.sub,
          rows: [
            { label: spec.aLabel, value: (spec.valueFmt || fmt.score)(r.a), color: color, keyShape: "dot" },
            { label: spec.bLabel, value: (spec.valueFmt || fmt.score)(r.b), color: color, keyShape: "dot" },
            { label: "Difference", value: ((r.b - r.a) >= 0 ? "+" : "") + (r.b - r.a).toFixed(3) }
          ]
        });
      }
      hit.addEventListener("pointerenter", show);
      hit.addEventListener("pointerleave", hideTip);
      hit.addEventListener("focus", show);
      hit.addEventListener("blur", hideTip);
    });

    return true;
  }

  /* ---------------------------------------------------------------- heatmap -- */

  /* Magnitude across a grid: one hue, light -> dark. Every cell is labelled,
     so the encoding is never colour-only. */
  var SEQ = ["var(--seq-100)", "var(--seq-200)", "var(--seq-300)", "var(--seq-400)",
             "var(--seq-500)", "var(--seq-600)", "var(--seq-700)"];

  function seqColor(t) {
    if (t === null || t === undefined || isNaN(t)) return "var(--surface-sub)";
    var i = Math.min(SEQ.length - 1, Math.max(0, Math.round(t * (SEQ.length - 1))));
    return SEQ[i];
  }

  function renderHeatmap(svg, spec, size) {
    if (!spec.rows.length || !spec.cols.length) return false;

    var W = size.width;
    var ROW_FONT = 12;
    var labelCap = Math.max(110, Math.min(spec.labelWidth || 230, W * 0.30));
    var labelW = Math.min(labelCap, spec.rows.reduce(function (m, r) {
      return Math.max(m, textWidth(r.label, ROW_FONT));
    }, 0) + 22);
    var cellH = 34;
    /* Header height is measured, not guessed: wrapped column titles get their
       own lines and a "new" badge gets a line of its own beneath them, so a
       badge can never land on top of the title or the first row of cells. */
    var anyBadge = spec.cols.some(function (c) { return !!c.badge; });
    var LINE_H = 15, BADGE_H = 14;
    var gridW = W - labelW - 4;
    var cw = gridW / spec.cols.length;

    /* Below this the grid stops being a chart: nine columns in 300px cannot be
       labelled at any angle, so the table view is the honest answer. */
    if (cw < 46) return "table";

    /* Wrap each column title to the cell width before deciding the height.
       Hyphens break like spaces, and any line still too wide is shortened —
       the full name stays in the tooltip and the table view. */
    var HEAD_FONT = 11;
    var lineMax = cw - 5;
    var wrapped = spec.cols.map(function (c) {
      var words = String(c.label).split(/(?<=-)|\s+/);
      var lines = [], cur = "";
      words.forEach(function (w) {
        var joiner = /-$/.test(cur) ? "" : " ";
        var candidate = cur.length ? cur + joiner + w : w;
        if (!cur.length || textWidth(candidate, HEAD_FONT) <= lineMax) cur = candidate;
        else { lines.push(cur); cur = w; }
      });
      if (cur.length) lines.push(cur);
      return lines.slice(0, 3).map(function (line) {
        return fitLabel(line.trim(), lineMax, HEAD_FONT);
      });
    });
    var maxLines = wrapped.reduce(function (m, l) { return Math.max(m, l.length); }, 1);
    var headH = 6 + maxLines * LINE_H + (anyBadge ? BADGE_H + 3 : 0) + 5;

    var pad = { top: headH, right: 4, bottom: 8, left: labelW };
    var H = pad.top + pad.bottom + spec.rows.length * cellH;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("height", H);

    var g = el("g", null, svg);
    var lo = spec.domain ? spec.domain[0] : 0;
    var hi = spec.domain ? spec.domain[1] : 1;

    spec.cols.forEach(function (c, j) {
      var cx = pad.left + j * cw + cw / 2;
      var lines = wrapped[j];
      /* bottom-align the title block so short and tall titles share a baseline */
      var blockTop = 6 + (maxLines - lines.length) * LINE_H;
      lines.forEach(function (line, li) {
        text(g, line, {
          x: cx, y: blockTop + li * LINE_H + 10,
          "text-anchor": "middle", "font-size": HEAD_FONT, fill: "var(--ink-2)"
        });
      });
      if (c.badge) {
        var bw = c.badge.length * 5.6 + 9;
        var by = 6 + maxLines * LINE_H + 2;
        el("rect", {
          x: cx - bw / 2, y: by, width: bw, height: 12, rx: 3,
          fill: "var(--wash-accent)", stroke: "var(--series-1)",
          "stroke-width": 1, "stroke-opacity": 0.35
        }, g);
        text(g, c.badge, {
          x: cx, y: by + 9, "text-anchor": "middle", "font-size": 8.5,
          fill: "var(--accent-text)", "font-weight": 600, "letter-spacing": "0.07em"
        });
      }
    });

    spec.rows.forEach(function (r, i) {
      var y = pad.top + i * cellH;
      text(g, fitLabel(r.label, pad.left - 16, ROW_FONT), {
        x: pad.left - 12, y: y + cellH / 2 + 4, "text-anchor": "end",
        "font-size": ROW_FONT, fill: "var(--ink-2)"
      });
      if (r.color) {
        el("rect", {
          x: pad.left - 8, y: y + cellH / 2 - 4, width: 3, height: 8, rx: 1.5, fill: r.color
        }, g);
      }

      spec.cols.forEach(function (c, j) {
        var v = r.values[j];
        var x = pad.left + j * cw;
        /* 2px surface gap does the separating — never a stroke around the cell */
        var cell = el("rect", {
          x: x + 1, y: y + 1, width: Math.max(1, cw - 2), height: cellH - 2, rx: 3,
          fill: v === null || v === undefined ? "var(--surface-sub)" : seqColor((v - lo) / (hi - lo)),
          tabindex: 0, role: "img",
          "aria-label": r.label + ", " + c.label + ": " +
            (v === null || v === undefined ? "no data" : fmt.score(v))
        }, g);

        var t = v === null || v === undefined ? null : (v - lo) / (hi - lo);
        /* label inside a filled cell: pick ink or white by the fill's depth */
        var onDark = t !== null && t > 0.55;
        text(g, v === null || v === undefined ? "—" : (spec.valueFmt || fmt.score2)(v), {
          x: x + cw / 2, y: y + cellH / 2 + 4, "text-anchor": "middle",
          "font-size": 11.5, "font-variant-numeric": "tabular-nums",
          fill: v === null || v === undefined ? "var(--ink-3)" : (onDark ? "#ffffff" : "#0b0b0b"),
          "font-weight": 500, "pointer-events": "none"
        });

        function show() {
          cell.setAttribute("stroke", "var(--ink)");
          cell.setAttribute("stroke-width", 1.5);
          var a = anchorOf(cell);
          showTip(a.x, a.y, {
            title: c.label,
            sub: r.label,
            rows: [{
              label: spec.measure || "Score",
              value: v === null || v === undefined ? "no data" : fmt.score(v)
            }].concat(c.note ? [{ label: "Questions", value: c.note }] : [])
          });
        }
        function hide() { cell.removeAttribute("stroke"); hideTip(); }
        cell.addEventListener("pointerenter", show);
        cell.addEventListener("pointerleave", hide);
        cell.addEventListener("focus", show);
        cell.addEventListener("blur", hide);
      });
    });

    return true;
  }

  /* ------------------------------------------------------------------- hbar -- */

  /* Horizontal bars: one series, one colour. Long category names get the room
     they need, and the value rides the bar tip. */
  function renderHBar(svg, spec, size) {
    var rows = spec.rows.filter(function (r) { return r.value !== null && r.value !== undefined; });
    if (!rows.length) return false;

    var W = size.width;
    var rowH = spec.rowHeight || 26;
    var barH = Math.min(14, rowH - 10);
    var ROW_FONT = 12;
    var labelCap = Math.max(100, Math.min(spec.labelWidth || 240, W * 0.36));
    var gutter = Math.min(labelCap, rows.reduce(function (m, r) {
      return Math.max(m, textWidth(r.label, ROW_FONT));
    }, 0) + 16);
    var pad = { top: 8, right: 52, bottom: 38, left: gutter };
    var H = pad.top + pad.bottom + rows.length * rowH;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("height", H);

    var ve = extent(rows.map(function (r) { return r.value; }));
    var xMax = spec.xMax !== undefined ? spec.xMax : Math.min(1, ve[1] * 1.08);
    var plotW = W - pad.left - pad.right;
    var sx = function (v) { return (v / xMax) * plotW; };
    var g = el("g", null, svg);

    niceTicks(0, xMax, tickCount(plotW)).forEach(function (t) {
      var x = pad.left + sx(t);
      el("line", {
        x1: x, y1: pad.top, x2: x, y2: H - pad.bottom + 4,
        stroke: "var(--grid)", "stroke-width": 1, "shape-rendering": "crispEdges"
      }, g);
      text(g, (spec.xFmt || fmt.axisScore)(t), {
        x: x, y: H - pad.bottom + 21, "text-anchor": "middle", "font-size": 11,
        fill: "var(--ink-3)", "font-variant-numeric": "tabular-nums"
      });
    });
    if (spec.xLabel) {
      text(g, fitLabel(spec.xLabel, W - 10, 11.5), {
        x: W / 2, y: H - 3, "text-anchor": "middle",
        "font-size": 11.5, fill: "var(--ink-3)", "letter-spacing": "0.04em"
      });
    }
    el("line", {
      x1: pad.left, y1: pad.top, x2: pad.left, y2: H - pad.bottom,
      stroke: "var(--axis)", "stroke-width": 1, "shape-rendering": "crispEdges"
    }, g);

    rows.forEach(function (r, i) {
      var cy = pad.top + i * rowH + rowH / 2;
      var w = Math.max(1.5, sx(r.value));
      var color = r.color || "var(--series-1)";

      text(g, fitLabel(r.label, pad.left - 13, ROW_FONT), {
        x: pad.left - 11, y: cy + 4, "text-anchor": "end", "font-size": ROW_FONT,
        fill: "var(--ink-2)"
      });

      /* 4px rounded data-end, square at the baseline */
      var rr = Math.min(4, w);
      el("path", {
        d: "M" + pad.left + "," + (cy - barH / 2) +
           "H" + (pad.left + w - rr) +
           "a" + rr + "," + rr + " 0 0 1 " + rr + "," + rr +
           "V" + (cy + barH / 2 - rr) +
           "a" + rr + "," + rr + " 0 0 1 " + (-rr) + "," + rr +
           "H" + pad.left + "Z",
        fill: color
      }, g);

      text(g, (spec.valueFmt || fmt.score2)(r.value), {
        x: pad.left + w + 9, y: cy + 4, "text-anchor": "start", "font-size": 11.5,
        fill: "var(--ink)", "font-weight": 600, "font-variant-numeric": "tabular-nums"
      });

      var hit = el("rect", {
        x: pad.left - 4, y: cy - rowH / 2, width: plotW + 8, height: rowH,
        fill: "transparent", tabindex: 0, role: "img",
        "aria-label": r.label + ": " + fmt.score(r.value)
      }, g);
      function show() {
        var box = hit.getBoundingClientRect();
        showTip(box.left + Math.min(box.width, pad.left + w), box.top, {
          title: r.label,
          sub: r.sub,
          rows: [{ label: spec.measure || "Value", value: (spec.tipFmt || fmt.score)(r.value), color: color }]
            .concat(r.rows || [])
        });
      }
      hit.addEventListener("pointerenter", show);
      hit.addEventListener("pointerleave", hideTip);
      hit.addEventListener("focus", show);
      hit.addEventListener("blur", hideTip);
    });

    return true;
  }

  /* ------------------------------------------------------------ table twin -- */

  function buildTableTwin(spec, type) {
    var cols = [], rows = [];

    if (type === "scatter") {
      cols = [spec.tableKey || "Series", spec.xLabel || "x", spec.yLabel || "y"];
      rows = spec.points.map(function (p) {
        return [p.label, spec.xFmt ? spec.xFmt(p.x) : String(p.x), fmt.score(p.y)];
      });
    } else if (type === "lines") {
      var lineFmt = spec.tipFmt || fmt.score;
      cols = [spec.tableKey || "Series"].concat(spec.categories);
      rows = spec.series.map(function (s) {
        return [s.label].concat(s.values.map(function (v) { return lineFmt(v); }));
      });
    } else if (type === "dumbbell") {
      cols = [spec.tableKey || "Series", spec.aLabel, spec.bLabel, "Difference"];
      rows = spec.rows.map(function (r) {
        return [r.label, fmt.score(r.a), fmt.score(r.b),
          (r.b - r.a >= 0 ? "+" : "") + (r.b - r.a).toFixed(3)];
      });
    } else if (type === "heatmap") {
      cols = [spec.tableKey || "Series"].concat(spec.cols.map(function (c) { return c.label; }));
      rows = spec.rows.map(function (r) {
        return [r.label].concat(r.values.map(function (v) { return fmt.score(v); }));
      });
    } else if (type === "hbar") {
      cols = [spec.tableKey || "Category", spec.measure || "Value"];
      rows = spec.rows.map(function (r) { return [r.label, fmt.score(r.value)]; });
    }

    var wrap = html("div", "table-scroll chart-table-view");
    var table = html("table", "data", wrap);
    if (spec.title) {
      var cap = html("caption", null, table);
      cap.textContent = spec.title + " — table view";
    }
    var thead = html("thead", null, table);
    var htr = html("tr", null, thead);
    cols.forEach(function (c, i) {
      var th = html("th", i === 0 ? "text" : null, htr);
      th.textContent = c;
      th.setAttribute("scope", "col");
    });
    var tbody = html("tbody", null, table);
    rows.forEach(function (r) {
      var tr = html("tr", null, tbody);
      r.forEach(function (v, i) {
        var cell = html(i === 0 ? "th" : "td", i === 0 ? "text" : null, tr);
        if (i === 0) cell.setAttribute("scope", "row");
        cell.textContent = v;
      });
    });
    return wrap;
  }

  /* ----------------------------------------------------------------- mount -- */

  var RENDERERS = {
    scatter: renderScatter,
    lines: renderLines,
    dumbbell: renderDumbbell,
    heatmap: renderHeatmap,
    hbar: renderHBar
  };

  var registry = [];

  /* Mounts a chart into `host` (a .chart-wrap), wires the table-view toggle,
     and re-renders on container resize so text stays crisp at any width. */
  function mount(host, type, spec, opts) {
    opts = opts || {};
    clear(host);
    var userView = opts.view || "chart";
    host.setAttribute("data-view", userView);
    host.addEventListener("chart:view", function (e) { userView = e.detail; });

    var svg = el("svg", { class: "chart-svg", role: "group", "aria-label": spec.title || "chart" });
    host.appendChild(svg);

    function notice(message) {
      var node = host.querySelector(".chart-empty");
      if (!message) { if (node) node.remove(); return; }
      if (!node) {
        node = html("div", "chart-empty", host);
        host.insertBefore(node, svg);
      }
      node.textContent = message;
    }

    function draw() {
      clear(svg);
      var width = Math.max(240, host.clientWidth || 560);
      var ok = RENDERERS[type](svg, spec, { width: width });
      if (ok === "table") {
        /* too cramped to draw honestly — show the values instead */
        svg.setAttribute("height", 0);
        host.setAttribute("data-view", "table");
        notice("Too narrow for the grid at this width — showing the values as a table.");
      } else if (!ok) {
        svg.setAttribute("height", 0);
        host.setAttribute("data-view", "chart");
        notice(spec.emptyMessage || "No runs match the current filters.");
      } else {
        host.setAttribute("data-view", userView);
        notice(null);
      }
      return ok;
    }

    var drew = draw();

    /* legend — always for two or more series; a lone series is named by the title */
    if (drew === true && spec.legend && spec.legend.length > 1) {
      var lg = html("div", "legend", host);
      lg.setAttribute("role", "list");
      spec.legend.forEach(function (item) {
        var li = html("span", "legend-item", lg);
        li.setAttribute("role", "listitem");
        var key = html("span", "legend-key " + (item.shape || "line"), li);
        if (item.shape === "hollow") key.style.color = item.color;
        else key.style.background = item.color;
        html("span", null, li).textContent = item.label;
      });
    }

    if (drew === true && spec.scaleLegend) {
      var sl = html("div", "scale-legend", host);
      html("span", null, sl).textContent = spec.scaleLegend[0];
      var ramp = html("span", "scale-ramp", sl);
      SEQ.forEach(function (c) { html("span", null, ramp).style.background = c; });
      html("span", null, sl).textContent = spec.scaleLegend[1];
    }

    host.appendChild(buildTableTwin(spec, type));

    if (host._ro) host._ro.disconnect();
    var last = host.clientWidth;
    host._ro = new ResizeObserver(function () {
      var w = host.clientWidth;
      if (Math.abs(w - last) > 8) { last = w; draw(); }
    });
    host._ro.observe(host);

    registry.push({ host: host, draw: draw });
    return { redraw: draw };
  }

  function redrawAll() {
    registry = registry.filter(function (r) { return document.body.contains(r.host); });
    registry.forEach(function (r) { r.draw(); });
  }

  global.Charts = {
    mount: mount,
    redrawAll: redrawAll,
    fmt: fmt,
    seqColor: seqColor,
    showTip: showTip,
    hideTip: hideTip,
    html: html,
    niceTicks: niceTicks
  };
})(window);
