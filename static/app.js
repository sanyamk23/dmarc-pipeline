// ═══════════════════════════════════════════════════════════════════════════
// DMARC Pipeline — dashboard logic
// ═══════════════════════════════════════════════════════════════════════════

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ── Helpers ───────────────────────────────────────────────────────────────────

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function fmtDate(ts) {
  if (!ts) return '–';
  const d = new Date(typeof ts === 'number' ? ts * 1000 : ts);
  return d.toISOString().slice(0, 10);
}

function fmtCount(n) {
  if (n == null) return '0';
  return n.toLocaleString();
}

function fmtPct(n) {
  if (n == null) return '0%';
  return n.toFixed(1) + '%';
}

function animateCount(el, target, duration = 800) {
  const start = performance.now();
  const from = 0;
  function tick(now) {
    const t = Math.min((now - start) / duration, 1);
    // expo-out easing
    const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
    const val = Math.round(from + (target - from) * eased);
    el.textContent = fmtCount(val);
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ── Stats ─────────────────────────────────────────────────────────────────────

async function loadStats() {
  const stats = await fetchJSON('/api/stats');
  animateCount($('#stat-reports'), stats.total_reports || 0);
  animateCount($('#stat-records'), stats.total_records || 0);
  animateCount($('#stat-messages'), stats.total_messages || 0);
  animateCount($('#stat-pass'), stats.pass_count || 0);
  animateCount($('#stat-fail'), stats.fail_count || 0);

  // Top sources
  const tbody = $('#top-sources-table tbody');
  tbody.innerHTML = '';
  const maxCount = (stats.top_source_ips[0]?.count) || 1;
  for (const ip of stats.top_source_ips) {
    const pct = ((ip.count / maxCount) * 100).toFixed(0);
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${ip.ip}</td>
      <td>${fmtCount(ip.count)}</td>
      <td>
        <div style="display: flex; align-items: center; gap: 8px;">
          <div style="flex: 1; height: 4px; background: var(--bg); border-radius: 0; overflow: hidden;">
            <div style="width: ${pct}%; height: 100%; background: var(--accent);"></div>
          </div>
          <span style="font-size: 11px; color: var(--muted); min-width: 32px; text-align: right;">${pct}%</span>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

// ── Reports table ─────────────────────────────────────────────────────────────

async function loadReports() {
  const reports = await fetchJSON('/api/reports');
  const tbody = $('#reports-table tbody');
  tbody.innerHTML = '';
  $('#reports-count').textContent = `${reports.length} total`;

  for (const r of reports) {
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    tr.innerHTML = `
      <td>${r.id}</td>
      <td>${r.domain || '–'}</td>
      <td>${r.org_name || '–'}</td>
      <td>${fmtDate(r.date_begin)} → ${fmtDate(r.date_end)}</td>
      <td>${r.record_count}</td>
      <td><span class="badge pass">${r.pass_count}</span></td>
      <td><span class="badge fail">${r.fail_count}</span></td>
      <td><a href="/file/${r.id}" style="color: var(--accent); text-decoration: none; font-size: 12px;">Full details →</a></td>
    `;
    tbody.appendChild(tr);
  }
}

// ── Records table ─────────────────────────────────────────────────────────────

async function loadRecords(reportId) {
  const section = $('#records-section');
  section.hidden = false;
  $('#records-report-id').textContent = reportId;

  const filter = $('#result-filter').value;
  const qs = filter ? `?result=${filter}` : '';
  const records = await fetchJSON(`/api/reports/${reportId}/records${qs}`);

  const tbody = $('#records-table tbody');
  tbody.innerHTML = '';

  for (const rec of records) {
    const tr = document.createElement('tr');
    const dkimClass = rec.dkim_aligned ? 'pass' : 'fail';
    const spfClass = rec.spf_aligned ? 'pass' : 'fail';
    tr.innerHTML = `
      <td>${rec.source_ip || '–'}</td>
      <td>${fmtCount(rec.count)}</td>
      <td>${rec.header_from || '–'}</td>
      <td>${rec.disposition || '–'}</td>
      <td><span class="badge ${dkimClass}">${rec.dkim_result || '–'}</span></td>
      <td><span class="badge ${spfClass}">${rec.spf_result || '–'}</span></td>
    `;
    tbody.appendChild(tr);
  }

  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Upload / drop zone ───────────────────────────────────────────────────────

const dropZone = $('#drop-zone');
const fileInput = $('#file-input');
const fileName = $('#file-name');
const uploadBtn = $('#upload-btn');
const status = $('#upload-status');

function setFile(file) {
  if (!file) return;
  fileName.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  uploadBtn.disabled = false;
  status.textContent = '';
  status.className = 'status';
}

fileInput.addEventListener('change', () => setFile(fileInput.files[0]));

dropZone.addEventListener('click', (e) => {
  if (e.target.tagName !== 'LABEL' && e.target.tagName !== 'INPUT') {
    fileInput.click();
  }
});

['dragenter', 'dragover'].forEach((evt) => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });
});

['dragleave', 'drop'].forEach((evt) => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
  });
});

dropZone.addEventListener('drop', (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    setFile(file);
  }
});

$('#upload-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  const fd = new FormData();
  fd.append('file', file);

  try {
    status.textContent = 'Ingesting…';
    status.className = 'status';
    uploadBtn.disabled = true;
    const result = await fetchJSON('/api/upload', { method: 'POST', body: fd });
    status.textContent = `✓ ${result.status}: ${result.filename}`;
    status.className = 'status success';
    fileInput.value = '';
    fileName.textContent = '';
    // Show extracted files + analysis
    renderUploadResults(result);
  } catch (err) {
    status.textContent = `✗ ${err.message}`;
    status.className = 'status error';
  } finally {
    uploadBtn.disabled = fileInput.files.length === 0;
    await Promise.all([loadStats(), loadReports()]);
  }
});

// ── Render upload results (extracted files + per-file + collective analysis) ──

function renderUploadResults(result) {
  const card = $('#upload-results-card');
  const container = $('#upload-results');
  card.hidden = false;
  $('#upload-results-filename').textContent = result.filename;

  let html = '';

  // ── Extracted files list ────────────────────────────────────────────────
  if (result.extracted_files && result.extracted_files.length > 0) {
    const successCount = result.extracted_files.length - (result.failed_files?.length || 0);
    const skippedCount = (result.skipped_duplicates?.length || 0);
    html += `<div class="analysis-section">
      <div class="analysis-section-title">
        Extracted files (${result.extracted_files.length} total)
        ${successCount > 0 ? ` · <span style="color: var(--success);">${successCount} parsed</span>` : ''}
        ${skippedCount > 0 ? ` · <span style="color: var(--warning);">${skippedCount} duplicate</span>` : ''}
      </div>
      <div class="extracted-files">`;
    for (const f of result.extracted_files) {
      const failed = result.failed_files && result.failed_files.includes(f);
      const skipped = result.skipped_duplicates && result.skipped_duplicates.includes(f);
      let status = '';
      let chipClass = '';
      if (failed) { status = ' (failed to parse)'; chipClass = 'failed'; }
      else if (skipped) { status = ' (duplicate, skipped)'; chipClass = 'skipped'; }
      html += `<span class="file-chip ${chipClass}">${f}${status}</span>`;
    }
    html += `</div></div>`;
  }

  // ── Collective analysis ─────────────────────────────────────────────────
  if (result.collective_analysis) {
    const c = result.collective_analysis;
    const o = c.overall;
    const a = c.alignment;
    html += `<div class="analysis-section">
      <div class="analysis-section-title">Collective analysis (all files)</div>
      <div class="collective-banner">
        <div class="collective-banner-title">Combined health: ${o.health_score}/100 (${o.health_label})</div>
        <div class="collective-banner-grid">
          <div class="collective-stat">
            <div class="collective-stat-value">${fmtCount(o.total_reports)}</div>
            <div class="collective-stat-label">Reports</div>
          </div>
          <div class="collective-stat">
            <div class="collective-stat-value">${fmtCount(o.total_records)}</div>
            <div class="collective-stat-label">Records</div>
          </div>
          <div class="collective-stat">
            <div class="collective-stat-value">${fmtCount(o.total_messages)}</div>
            <div class="collective-stat-label">Messages</div>
          </div>
          <div class="collective-stat">
            <div class="collective-stat-value" style="color: var(--success);">${a ? fmtPct(a.overall_pass_rate) : '–'}</div>
            <div class="collective-stat-label">Pass rate</div>
          </div>
        </div>
      </div>
    </div>`;
  }

  // ── Per-file analysis ───────────────────────────────────────────────────
  if (result.per_file_analysis && result.per_file_analysis.length > 0) {
    html += `<div class="analysis-section">
      <div class="analysis-section-title">Per-file analysis</div>
      <div class="per-file-grid">`;
    for (const file of result.per_file_analysis) {
      const a = file.analysis;
      const o = a.overall;
      const al = a.alignment;
      html += `<div class="per-file-card">
        <div class="per-file-header">
          <span>${file.xml_filename}</span>
          <span class="badge ${o.health_score >= 70 ? 'pass' : o.health_score >= 40 ? 'warn' : 'fail'}">${o.health_score}/100</span>
        </div>
        <div class="per-file-body">
          <div class="per-file-metric"><span class="per-file-metric-label">Organisation</span><span class="per-file-metric-value">${file.org_name || '–'}</span></div>
          <div class="per-file-metric"><span class="per-file-metric-label">Domain</span><span class="per-file-metric-value">${file.domain || '–'}</span></div>
          <div class="per-file-metric"><span class="per-file-metric-label">Date range</span><span class="per-file-metric-value">${fmtDate(file.date_begin)} → ${fmtDate(file.date_end)}</span></div>
          <div class="per-file-metric"><span class="per-file-metric-label">Messages</span><span class="per-file-metric-value">${fmtCount(o.total_messages)}</span></div>
          <div class="per-file-metric"><span class="per-file-metric-label">Records</span><span class="per-file-metric-value">${fmtCount(o.total_records)}</span></div>
          <div class="per-file-metric"><span class="per-file-metric-label">DKIM pass</span><span class="per-file-metric-value" style="color: var(--success);">${al ? fmtPct(al.dkim_pass_rate) : '–'}</span></div>
          <div class="per-file-metric"><span class="per-file-metric-label">SPF pass</span><span class="per-file-metric-value" style="color: var(--${al && al.spf_pass_rate > 50 ? 'success' : 'danger'});">${al ? fmtPct(al.spf_pass_rate) : '–'}</span></div>
        </div>
        <div style="margin-top: var(--sp-3);">
          <a href="/file/${file.report_id}" class="btn" style="font-size: 11px; padding: 4px 10px;">View full details →</a>
        </div>
      </div>`;
    }
    html += `</div></div>`;
  }

  container.innerHTML = html;
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

$('#result-filter').addEventListener('change', () => {
  const section = $('#records-section');
  if (section.hidden) return;
  const id = Number($('#records-report-id').textContent);
  loadRecords(id);
});

// ── Init ──────────────────────────────────────────────────────────────────────

(async function init() {
  await Promise.all([loadStats(), loadReports()]);
})();
