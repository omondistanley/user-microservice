"use strict";
(function() {
  "use strict";
  function readMeta(name) {
    var meta = document.querySelector('meta[name="' + name + '"]');
    return meta ? meta.getAttribute("content") || "" : "";
  }
  window.EXPENSE_API_BASE = readMeta("expense-api-base");
  window.BUDGET_API_BASE = readMeta("budget-api-base");
  window.PLAID_FLOW = readMeta("plaid-flow") || "hosted";
  var gatewayUrl = readMeta("gateway-public-url");
  window.API_BASE = gatewayUrl || "";
})();
