// S3 Troubleshooter AI - Chrome Extension Logic

const API_BASE = "http://localhost:5000/api";

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  checkConnection();
  loadBuckets();
  setupEventListeners();
});

function initTabs() {
  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
    });
  });
}

async function apiCall(endpoint, options) {
  try {
    const opts = Object.assign({ headers: { "Content-Type": "application/json" } }, options || {});
    const response = await fetch(API_BASE + endpoint, opts);
    return await response.json();
  } catch (error) {
    console.error("API Error:", error);
    return { error: "Cannot connect to backend. Is api_server.py running?" };
  }
}

async function checkConnection() {
  var dot = document.getElementById("statusDot");
  var text = document.getElementById("statusText");

  var health = await apiCall("/health");
  if (health.error) {
    dot.className = "dot";
    text.textContent = "Disconnected";
    document.getElementById("accountInfo").innerHTML = '<span style="color:#f85149">Backend not running. Start: python api_server.py</span>';
    return;
  }

  var creds = await apiCall("/credentials");
  if (creds.valid) {
    dot.className = "dot connected";
    text.textContent = "Connected";
    document.getElementById("accountInfo").innerHTML =
      "<div>Account: <strong>" + creds.account + "</strong></div>" +
      "<div>Identity: <strong>" + creds.arn + "</strong></div>";
  } else {
    dot.className = "dot";
    text.textContent = "Auth Failed";
    document.getElementById("accountInfo").innerHTML = '<span style="color:#f85149">' + (creds.error || "Invalid") + "</span>";
  }
}

async function loadBuckets() {
  var data = await apiCall("/buckets");
  if (data.error || !data.buckets) {
    document.getElementById("bucketCount").textContent = "Error: " + (data.error || "No data");
    return;
  }

  document.getElementById("bucketCount").innerHTML = "<strong>" + data.count + "</strong> buckets found";

  // Bucket list in dashboard
  var listHtml = "";
  for (var i = 0; i < data.buckets.length; i++) {
    var b = data.buckets[i];
    listHtml += '<div class="bucket-item" data-bucket="' + b + '">' + b + '</div>';
  }
  document.getElementById("bucketList").innerHTML = listHtml;

  // Add click handlers
  document.querySelectorAll(".bucket-item").forEach(function(item) {
    item.addEventListener("click", function() {
      var name = this.getAttribute("data-bucket");
      document.getElementById("bucketSelect").value = name;
      document.querySelector('[data-tab="diagnose"]').click();
    });
  });

  // Populate dropdowns
  var options = '<option value="">Select a bucket...</option>';
  for (var i = 0; i < data.buckets.length; i++) {
    options += '<option value="' + data.buckets[i] + '">' + data.buckets[i] + '</option>';
  }
  document.getElementById("bucketSelect").innerHTML = options;
  document.getElementById("chatBucketSelect").innerHTML = options;
}

function setupEventListeners() {
  document.getElementById("btnDiagnose").addEventListener("click", function() { runDiagnose(false); });
  document.getElementById("btnDiagnoseAI").addEventListener("click", function() { runDiagnose(true); });
  document.getElementById("btnFix").addEventListener("click", runFix);
  document.getElementById("btnChat").addEventListener("click", sendChat);
  document.getElementById("btnScanAll").addEventListener("click", runScanAll);
  document.getElementById("chatInput").addEventListener("keypress", function(e) {
    if (e.key === "Enter") sendChat();
  });
}

async function runDiagnose(withAI) {
  var bucket = document.getElementById("bucketSelect").value;
  if (!bucket) { alert("Select a bucket first"); return; }

  showLoading(withAI ? "Scanning + AI Analysis..." : "Scanning...");

  var endpoint = withAI ? "/diagnose-ai/" : "/diagnose/";
  var data = await apiCall(endpoint + bucket);

  hideLoading();

  if (data.error) { alert("Error: " + data.error); return; }

  displayResults(data);
}

function displayResults(data) {
  document.getElementById("diagnoseResults").classList.remove("hidden");

  var score = data.score || 0;
  var scoreCircle = document.getElementById("scoreCircle");
  document.getElementById("scoreNumber").textContent = score;
  document.getElementById("scoreHealth").textContent = data.overall_health || "UNKNOWN";

  var healthColor = score >= 70 ? "#3fb950" : score >= 50 ? "#d29922" : "#f85149";
  document.getElementById("scoreHealth").style.color = healthColor;

  var circleClass = "score-circle ";
  if (score >= 90) circleClass += "excellent";
  else if (score >= 70) circleClass += "good";
  else if (score >= 50) circleClass += "poor";
  else circleClass += "critical";
  scoreCircle.className = circleClass;

  var results = data.results || [];
  var html = "";
  for (var i = 0; i < results.length; i++) {
    var r = results[i];
    var sc = r.status.toLowerCase();
    html += '<div class="check-item">' +
      '<span class="check-status ' + sc + '">' + r.status + '</span>' +
      '<span class="check-name">' + r.check_name + '</span>' +
      '<span class="check-severity">' + r.severity + '</span>' +
      '</div>';
  }
  document.getElementById("checkResults").innerHTML = html;

  var aiCard = document.getElementById("aiAnalysisCard");
  if (data.ai_analysis && data.ai_analysis.length > 10) {
    aiCard.classList.remove("hidden");
    document.getElementById("aiAnalysis").textContent = data.ai_analysis;
  } else {
    aiCard.classList.add("hidden");
  }
}

async function runFix() {
  var bucket = document.getElementById("bucketSelect").value;
  if (!bucket) { alert("Select a bucket first"); return; }
  if (!confirm("Auto-fix issues on " + bucket + "?")) return;

  showLoading("Fixing " + bucket + "...");
  var data = await apiCall("/fix/" + bucket, { method: "POST" });
  hideLoading();

  if (data.error) { alert("Error: " + data.error); return; }

  var fixCard = document.getElementById("fixResultsCard");
  fixCard.classList.remove("hidden");

  var html = "<div style='margin-bottom:10px'><strong>Score: " +
    data.before_score + " &rarr; " + data.after_score + "</strong>";
  if (data.improvement > 0) {
    html += " <span style='color:#3fb950'>(+" + data.improvement + " points!)</span>";
  }
  html += "</div>";

  var fixes = data.fixes_applied || [];
  for (var i = 0; i < fixes.length; i++) {
    var f = fixes[i];
    var icon = f.success ? "&#x2705;" : "&#x274C;";
    var msg = f.success ? f.message : (f.error || "Failed");
    html += "<div>" + icon + " " + f.check + ": " + msg + "</div>";
  }
  document.getElementById("fixResults").innerHTML = html;

  if (data.report) displayResults(data.report);

  // Show AI recommendations
  if (data.ai_recommendations && data.ai_recommendations.length > 10) {
    var aiCard = document.getElementById("aiAnalysisCard");
    aiCard.classList.remove("hidden");
    document.getElementById("aiAnalysis").textContent = data.ai_recommendations;
  }
}

async function sendChat() {
  var input = document.getElementById("chatInput");
  var bucket = document.getElementById("chatBucketSelect").value;
  var message = input.value.trim();
  if (!message) return;
  if (!bucket) { alert("Select a bucket first"); return; }

  addChatMessage(message, "user");
  input.value = "";

  var thinkingDiv = addChatMessage("Thinking...", "bot");

  var data = await apiCall("/troubleshoot", {
    method: "POST",
    body: JSON.stringify({ bucket_name: bucket, issue: message }),
  });

  thinkingDiv.textContent = data.response || data.error || "No response";
}

function addChatMessage(text, type) {
  var chatBox = document.getElementById("chatBox");
  var div = document.createElement("div");
  div.className = "chat-message " + type;
  div.textContent = text;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
  return div;
}

async function runScanAll() {
  showLoading("Scanning all buckets... This may take a few minutes.");
  var data = await apiCall("/scan-all");
  hideLoading();

  if (data.error) { alert("Error: " + data.error); return; }

  document.getElementById("scanAllResults").classList.remove("hidden");

  var total = data.total || 0;
  var avg = data.average_score || 0;
  var buckets = data.buckets || [];
  var critical = 0;
  for (var i = 0; i < buckets.length; i++) {
    if (buckets[i].score < 50) critical++;
  }
  var good = total - critical;

  document.getElementById("summaryStats").innerHTML =
    '<div class="stat-box avg"><div class="number">' + avg + '</div><div class="label">Avg Score</div></div>' +
    '<div class="stat-box good"><div class="number">' + good + '</div><div class="label">Good</div></div>' +
    '<div class="stat-box bad"><div class="number">' + critical + '</div><div class="label">Critical</div></div>';

  buckets.sort(function(a, b) { return a.score - b.score; });

  var rows = "";
  for (var i = 0; i < buckets.length; i++) {
    var b = buckets[i];
    var hc = b.score >= 70 ? "good" : b.score >= 50 ? "good" : "critical";
    var sc = b.score >= 70 ? "#3fb950" : b.score >= 50 ? "#d29922" : "#f85149";
    rows += '<div class="scan-row">' +
      '<div class="name">' + b.bucket + '</div>' +
      '<div class="score" style="color:' + sc + '">' + b.score + '</div>' +
      '<div class="health"><span class="health-badge ' + hc + '">' + b.health + '</span></div>' +
      '</div>';
  }

  document.getElementById("allBucketsTable").innerHTML =
    '<div class="scan-table">' +
    '<div class="scan-row" style="font-weight:700;border-bottom:2px solid #30363d">' +
    '<div class="name">Bucket</div><div class="score">Score</div><div class="health">Health</div></div>' +
    rows + '</div>';
}

function showLoading(text) {
  document.getElementById("loadingText").textContent = text || "Loading...";
  document.getElementById("loading").classList.remove("hidden");
}

function hideLoading() {
  document.getElementById("loading").classList.add("hidden");
}
