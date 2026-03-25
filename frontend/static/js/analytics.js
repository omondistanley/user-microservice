"use strict";
(function() {
  "use strict";
  var API = window.API_BASE || "";
  function headers() {
    return window.Auth && window.Auth.getAuthHeaders ? window.Auth.getAuthHeaders() : {};
  }
  document.addEventListener("DOMContentLoaded", function() {
    var st = document.getElementById("analytics-status");
    fetch(API + "/api/v1/analytics/overview?days=30", { headers: headers() }).then(function(r) {
      if (!r.ok) throw new Error("fail");
      return r.json();
    }).then(function(d) {
      if (st) st.textContent = d.period && d.period.date_from ? "Period: " + d.period.date_from + " \u2192 " + d.period.date_to : "";
      var inc = document.getElementById("an-income");
      var exp = document.getElementById("an-expense");
      var net = document.getElementById("an-net");
      if (inc) inc.textContent = "$" + fmt(d.income_total);
      if (exp) exp.textContent = "$" + fmt(d.expense_total);
      if (net) net.textContent = "$" + fmt(d.net);
      var ul = document.getElementById("an-cats");
      var rows = d.spend_by_category || [];
      if (ul) {
        ul.innerHTML = rows.length ? rows.map(function(c) {
          return '<li class="flex justify-between py-2 border-b border-slate-100 dark:border-slate-800"><span>' + esc(c.label || c.category_code) + '</span><span class="font-semibold">$' + fmt(c.total) + "</span></li>";
        }).join("") : '<li class="text-slate-500">No expense data in this period.</li>';
      }
    }).catch(function() {
      if (st) st.textContent = "Could not load analytics.";
    });
  });
  function fmt(v) {
    var n = Number(v);
    if (!isFinite(n)) return "0.00";
    return n.toFixed(2);
  }
  function esc(s) {
    if (s == null) return "";
    var d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  }
})();
