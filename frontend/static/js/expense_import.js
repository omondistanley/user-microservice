"use strict";
(function() {
  "use strict";
  var API = window.API_BASE || "";
  var currentJobId = null;
  function authHeaders() {
    return window.Auth && window.Auth.getAuthHeaders ? window.Auth.getAuthHeaders() : {};
  }
  document.getElementById("import-form").addEventListener("submit", function(e) {
    e.preventDefault();
    var fileInput = document.getElementById("csv-file");
    if (!fileInput.files || !fileInput.files[0]) {
      alert("Please select a CSV file.");
      return;
    }
    var btn = document.getElementById("btn-upload");
    btn.disabled = true;
    var formData = new FormData();
    formData.append("file", fileInput.files[0]);
    var url = API + "/api/v1/expenses/import?dry_run=true";
    fetch(url, {
      method: "POST",
      headers: authHeaders(),
      body: formData
    }).then(function(r) {
      return r.json().then(function(data) {
        if (!r.ok) throw new Error(data.detail || r.statusText);
        return data;
      });
    }).then(function(data) {
      currentJobId = data.job_id;
      return fetch(API + "/api/v1/expenses/import/" + encodeURIComponent(data.job_id), {
        headers: authHeaders()
      }).then(function(r) {
        return r.json();
      });
    }).then(function(job) {
      var preview = document.getElementById("import-preview");
      var summary = document.getElementById("import-summary");
      var tbody = document.getElementById("import-preview-tbody");
      tbody.innerHTML = "";
      var rows = job.rows || [];
      var valid = 0, invalid = 0, dup = 0;
      rows.forEach(function(r) {
        if (r.validation_error) invalid++;
        else if (r.is_duplicate) dup++;
        else valid++;
        var np = r.normalized_payload || {};
        var status = r.validation_error || (r.is_duplicate ? "Duplicate" : "OK");
        var tr = document.createElement("tr");
        tr.innerHTML = "<td>" + r.row_number + "</td><td>" + (np.date || "\u2014") + "</td><td>" + (np.amount != null ? np.amount : "\u2014") + "</td><td>" + (np.category_name || "\u2014") + "</td><td>" + status + "</td>";
        tbody.appendChild(tr);
      });
      summary.textContent = "Total: " + rows.length + " | Valid: " + valid + " | Invalid: " + invalid + " | Duplicates: " + dup;
      preview.style.display = "block";
    }).catch(function(err) {
      alert(err.message || "Upload failed");
    }).finally(function() {
      btn.disabled = false;
    });
  });
  document.getElementById("btn-commit").addEventListener("click", function() {
    if (!currentJobId) return;
    var btn = document.getElementById("btn-commit");
    var msg = document.getElementById("import-commit-msg");
    btn.disabled = true;
    msg.style.display = "none";
    fetch(API + "/api/v1/expenses/import/" + encodeURIComponent(currentJobId) + "/commit", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, authHeaders())
    }).then(function(r) {
      return r.json().then(function(d) {
        return { ok: r.ok, data: d };
      });
    }).then(function(result) {
      if (result.ok) {
        var d = result.data;
        msg.textContent = "Imported " + (d.inserted_rows || 0) + " expense(s). Total: " + (d.total_rows || 0) + ", Valid: " + (d.valid_rows || 0) + ", Invalid: " + (d.invalid_rows || 0) + ", Duplicates skipped: " + (d.duplicate_rows || 0);
        msg.style.display = "block";
        msg.className = "message-success";
      } else {
        msg.textContent = result.data.detail || "Commit failed";
        msg.style.display = "block";
        msg.className = "message-error";
      }
    }).catch(function() {
      msg.textContent = "Commit failed";
      msg.style.display = "block";
      msg.className = "message-error";
    }).finally(function() {
      btn.disabled = false;
    });
  });
})();
