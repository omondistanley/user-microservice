"use strict";
(function() {
  var linkBtn = document.getElementById("plaid-link-btn");
  var syncBtn = document.getElementById("plaid-sync-btn");
  var itemsList = document.getElementById("plaid-items-list");
  var errorEl = document.getElementById("plaid-error");
  var successEl = document.getElementById("plaid-success");
  var syncStatus = document.getElementById("plaid-sync-status");
  function showError(msg) {
    if (errorEl) {
      errorEl.textContent = msg || "Something went wrong.";
      errorEl.style.display = "block";
    }
    if (successEl) successEl.style.display = "none";
  }
  function showSuccess(msg) {
    if (successEl) {
      successEl.textContent = msg || "Done.";
      successEl.style.display = "block";
    }
    if (errorEl) errorEl.style.display = "none";
  }
  function escapeQuot(s) {
    return (s || "").replace(/"/g, "&quot;");
  }
  function loadItems() {
    if (!window.PlaidApi || !window.PlaidApi.getItems) return;
    window.PlaidApi.getItems().then(function(data) {
      var items = data && data.items ? data.items : [];
      if (!itemsList) return;
      if (items.length === 0) {
        itemsList.innerHTML = '<p class="empty-state" style="margin:0;">No linked accounts. Click "Link bank account" to add one.</p>';
        return;
      }
      var html = '<ul class="summary-list">';
      items.forEach(function(item) {
        var name = item.institution_name || item.institution_id || "Linked account";
        var created = item.created_at && item.created_at.slice ? item.created_at.slice(0, 10) : "";
        var suffix = created ? " (linked " + created + ")" : "";
        var itemId = escapeQuot(item.item_id);
        html += '<li><span class="summary-label">' + name + suffix + '</span> <button type="button" class="btn btn-secondary btn-sm plaid-delete-btn" data-item-id="' + itemId + '">Remove</button></li>';
      });
      html += "</ul>";
      itemsList.innerHTML = html;
      itemsList.querySelectorAll(".plaid-delete-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
          var id = this.getAttribute("data-item-id");
          if (!id) return;
          if (!confirm("Remove this linked account? You can link it again later.")) return;
          window.PlaidApi.deleteItem(id).then(function() {
            showSuccess("Account removed.");
            loadItems();
          }).catch(function(e) {
            showError(e.message || "Failed to remove.");
          });
        });
      });
    }).catch(function(e) {
      if (itemsList) {
        if (e && e.message && e.message.indexOf("503") !== -1) {
          itemsList.innerHTML = '<p class="empty-state" style="margin:0;">Bank linking is not configured on the server.</p>';
        } else {
          itemsList.innerHTML = '<p class="empty-state" style="margin:0;">Could not load linked accounts.</p>';
        }
      }
    });
  }
  function openPlaidLink() {
    if (!window.PlaidApi || !window.PlaidApi.getLinkToken) return;
    linkBtn.disabled = true;
    showError("");
    window.PlaidApi.getLinkToken().then(function(data) {
      var token = data && data.link_token;
      if (!token) {
        showError("Could not get link token.");
        linkBtn.disabled = false;
        return;
      }
      if (typeof window.Plaid !== "undefined" && window.Plaid.create) {
        var handler = window.Plaid.create({
          token,
          onSuccess: function(publicToken) {
            window.PlaidApi.exchangeItem(publicToken).then(function() {
              window.location.href = "/link-bank/success";
              return;
            }).catch(function(e) {
              showError(e.message || "Failed to save linked account.");
              linkBtn.disabled = false;
            });
          },
          onExit: function() {
            linkBtn.disabled = false;
          }
        });
        if (handler && handler.open) handler.open();
        else linkBtn.disabled = false;
        return;
      }
      showError("Plaid Link script did not load. Please refresh the page.");
      linkBtn.disabled = false;
    }).catch(function(e) {
      showError(e.message || "Failed to get link token.");
      linkBtn.disabled = false;
    });
  }
  if (linkBtn) {
    linkBtn.addEventListener("click", function() {
      if (!window.PlaidApi || !window.PlaidApi.getLinkToken) {
        showError("Plaid not loaded.");
        return;
      }
      openPlaidLink();
    });
  }
  if (syncBtn) {
    syncBtn.addEventListener("click", function() {
      if (!window.PlaidApi || !window.PlaidApi.sync) return;
      syncBtn.disabled = true;
      syncStatus.style.display = "block";
      syncStatus.textContent = "Syncing\u2026";
      window.PlaidApi.sync().then(function(data) {
        var created = data && data.created != null ? data.created : 0;
        syncStatus.textContent = "Sync complete. " + created + " new expense(s) imported.";
        showSuccess("Sync complete.");
        syncBtn.disabled = false;
      }).catch(function(e) {
        syncStatus.textContent = "";
        showError(e.message || "Sync failed.");
        syncBtn.disabled = false;
      });
    });
  }
  if (itemsList) loadItems();
})();
