(function () {
  const app = document.getElementById("app");
  const src = app.getAttribute("data-src");

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  function recordText(rec) {
    return `${rec.wins}-${rec.losses}-${rec.ties}`;
  }

  function pctText(rec) {
    return rec.pct.toFixed(3);
  }

  function gameLogTable(log) {
    if (!log.length) return `<div>No games yet.</div>`;
    const rows = log.map((g) => {
      const vs = g.home ? "vs" : "@";
      return `<tr>
        <td>Wk ${g.week}</td>
        <td>${vs} ${escapeHtml(g.opponent)}</td>
        <td>${g.team_score}-${g.opp_score}</td>
        <td class="res-${g.result}">${g.result}</td>
      </tr>`;
    }).join("");
    return `<table>${rows}</table>`;
  }

  function teamRow(row) {
    const delta = row.this_week_delta;
    const winCls = delta === 1 ? "win" : "";
    const lossCls = delta === -1 ? "loss" : "";
    const logo = row.logo
      ? `<img class="logo" src="${escapeHtml(row.logo)}" alt="${escapeHtml(row.team)} logo" loading="lazy" />`
      : `<div class="logo"></div>`;
    return `
      <div class="team-row">
        ${logo}
        <div class="team-name">${escapeHtml(row.team)}</div>
        <div class="record">
          <span class="${winCls}">${row.record.wins}</span>-<span class="${lossCls}">${row.record.losses}</span>-${row.record.ties}
          &nbsp;(${pctText(row.record)})
        </div>
        <div class="game-log-tooltip">${gameLogTable(row.game_log)}</div>
      </div>`;
  }

  function renderColumn(title, rows) {
    return `
      <div class="column">
        <h2>${escapeHtml(title)}</h2>
        ${rows.map(teamRow).join("")}
      </div>`;
  }

  function renderSummary(data) {
    const leftPct = data.totals_left.pct;
    const rightPct = data.totals_right.pct;
    let verdict = "Tied";
    if (leftPct > rightPct) verdict = `${data.owner_left} leads`;
    else if (rightPct > leftPct) verdict = `${data.owner_right} leads`;
    return `
      <div class="summary">
        <h2>Combined Records</h2>
        <div class="line">${escapeHtml(data.owner_left)}: ${recordText(data.totals_left)} (${pctText(data.totals_left)})</div>
        <div class="line">${escapeHtml(data.owner_right)}: ${recordText(data.totals_right)} (${pctText(data.totals_right)})</div>
        <hr />
        <div class="line verdict">Verdict: ${verdict}</div>
      </div>`;
  }

  function renderHeader(data) {
    const wk = data.display_week != null ? data.display_week : "N/A";
    return `
      <header class="page-header">
        <h1>${escapeHtml(data.owner_left)} vs ${escapeHtml(data.owner_right)}</h1>
        <div class="sub">${data.season} Season · Through Week ${wk}</div>
      </header>`;
  }

  function makeCumulativeChart(canvas, data) {
    new Chart(canvas, {
      type: "line",
      data: {
        labels: data.weeks,
        datasets: [
          {
            label: `${data.owner_left} cumulative`,
            data: data.cumulative_left,
            borderColor: "#2455c9",
            backgroundColor: "#2455c9",
            tension: 0.15,
          },
          {
            label: `${data.owner_right} cumulative`,
            data: data.cumulative_right,
            borderColor: "#c43434",
            backgroundColor: "#c43434",
            tension: 0.15,
          },
        ],
      },
      options: {
        responsive: true,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { title: { display: true, text: "Week" } },
          y: { title: { display: true, text: "Total Wins to Date" }, beginAtZero: true },
        },
      },
    });
  }

  function makeWeeklyBarChart(canvas, data) {
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: data.weeks,
        datasets: [
          {
            label: data.owner_left,
            data: data.weekly_counts_left,
            backgroundColor: "#2455c9",
          },
          {
            label: data.owner_right,
            data: data.weekly_counts_right,
            backgroundColor: "#c43434",
          },
        ],
      },
      options: {
        responsive: true,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { title: { display: true, text: "Week" } },
          y: { title: { display: true, text: "Wins that Week" }, beginAtZero: true },
        },
      },
    });
  }

  function render(data) {
    app.innerHTML = `
      ${renderHeader(data)}
      <div class="columns">
        ${renderColumn(`${data.owner_left}'s Teams`, data.rows_left)}
        ${renderSummary(data)}
        ${renderColumn(`${data.owner_right}'s Teams`, data.rows_right)}
      </div>
      <div class="charts">
        <div class="chart-card">
          <h3>Cumulative Wins</h3>
          <canvas id="cumulative-chart"></canvas>
        </div>
        <div class="chart-card">
          <h3>Weekly Wins per Owner</h3>
          <canvas id="weekly-chart"></canvas>
        </div>
      </div>
      <footer class="updated">Last updated ${new Date(data.generated_at).toLocaleString()}</footer>
    `;
    makeCumulativeChart(document.getElementById("cumulative-chart"), data);
    makeWeeklyBarChart(document.getElementById("weekly-chart"), data);
  }

  // Cache-bust: GitHub Pages' CDN caches data.json for ~10 minutes, so without
  // this, viewers loading the page soon after a Tuesday update could see stale
  // data until that window expires. The unique query string + no-store forces
  // a fresh fetch every time, from both the CDN and the browser's own cache.
  fetch(`${src}?v=${Date.now()}`, { cache: "no-store" })
    .then((r) => r.json())
    .then(render)
    .catch((err) => {
      app.innerHTML = `<p>Could not load data: ${escapeHtml(err.message)}</p>`;
    });
})();
