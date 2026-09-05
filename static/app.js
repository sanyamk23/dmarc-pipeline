// ═══════════════════════════════════════════════════════════════════════════
// DMARC Pipeline — dashboard logic
// ═══════════════════════════════════════════════════════════════════════════

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ── Helpers ───────────────────────────────────────────────────────────────────

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

function animateCount(el, target, duration = 1200) {
  const start = performance.now();
  function tick(now) {
    const t = Math.min((now - start) / duration, 1);
    const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
    el.textContent = fmtCount(Math.round(target * eased));
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ── Intersection Observer for scroll reveals ──────────────────────────────────

function observeReveals() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
      }
    });
  }, { threshold: 0.1 });

  $$('.card, .stat-strip').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1), transform 0.6s cubic-bezier(0.16, 1, 0.3, 1)';
    observer.observe(el);
  });
}

// ── Stats ─────────────────────────────────────────────────────────────────────

async function loadStats() {
  try {
    const stats = await fetch('/api/stats').then(r => r.json());
    animateCount($('#stat-reports'), stats.total_reports || 0);
    animateCount($('#stat-records'), stats.total_records || 0);
    animateCount($('#stat-messages'), stats.total_messages || 0);
    animateCount($('#stat-pass'), stats.pass_count || 0);
    animateCount($('#stat-fail'), stats.fail_count || 0);

    animateCount($('#hero-reports'), stats.total_reports || 0);
    animateCount($('#hero-messages'), stats.total_messages || 0);
    animateCount($('#hero-ips'), stats.total_records || 0);
  } catch (e) {
    console.error('Failed to load stats:', e);
  }
}

// ── Reports table ─────────────────────────────────────────────────────────────

async function loadReports() {
  try {
    const reports = await fetch('/api/reports').then(r => r.json());
    const tbody = $('#reports-table');
    tbody.innerHTML = '';
    $('#reports-count').textContent = `${reports.length} total`;

    reports.forEach((r, i) => {
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';
      tr.style.animation = `fadeInUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) ${i * 0.05}s both`;
      tr.innerHTML = `
        <td>${r.id}</td>
        <td>${r.domain || '–'}</td>
        <td>${r.org_name || '–'}</td>
        <td>${fmtDate(r.date_begin)} → ${fmtDate(r.date_end)}</td>
        <td>${r.record_count}</td>
        <td><span class="badge pass">${r.pass_count}</span></td>
        <td><span class="badge fail">${r.fail_count}</span></td>
        <td><a href="/file/${r.id}" style="color: var(--accent); text-decoration: none; font-size: 12px;">Details →</a></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error('Failed to load reports:', e);
  }
}

// ── Records table ─────────────────────────────────────────────────────────────

async function loadRecords(reportId) {
  const section = $('#records-section');
  section.hidden = false;
  $('#records-report-id').textContent = reportId;

  try {
    const filter = $('#result-filter').value;
    const qs = filter ? `?result=${filter}` : '';
    const records = await fetch(`/api/reports/${reportId}/records${qs}`).then(r => r.json());

    const tbody = $('#records-table');
    tbody.innerHTML = '';

    records.forEach(rec => {
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
    });

    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    console.error('Failed to load records:', e);
  }
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
    status.textContent = 'Ingesting...';
    status.className = 'status';
    uploadBtn.disabled = true;
    const result = await fetch('/api/upload', { method: 'POST', body: fd }).then(r => r.json());
    status.textContent = `✓ ${result.status}`;
    status.className = 'status success';
    fileInput.value = '';
    fileName.textContent = '';
    renderUploadResults(result);
  } catch (err) {
    status.textContent = `✗ ${err.message}`;
    status.className = 'status error';
  } finally {
    uploadBtn.disabled = fileInput.files.length === 0;
    await Promise.all([loadStats(), loadReports()]);
  }
});

// ── Render upload results ─────────────────────────────────────────────────────

function renderUploadResults(result) {
  const card = $('#upload-results-card');
  const container = $('#upload-results');
  card.hidden = false;
  $('#upload-results-filename').textContent = result.filename;

  let html = '';

  // Extracted files
  if (result.extracted_files?.length > 0) {
    html += `<div style="margin-bottom: var(--sp-4);">
      <div style="font-family: var(--font-mono); font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-muted); margin-bottom: var(--sp-2);">
        Extracted files (${result.extracted_files.length})
      </div>
      <div style="display: flex; flex-wrap: wrap; gap: var(--sp-1);">`;
    for (const f of result.extracted_files) {
      const failed = result.failed_files?.includes(f);
      html += `<span style="background: var(--bg-2); border: 1px solid var(--border); border-radius: var(--r-sm); padding: 4px 12px; font-family: var(--font-mono); font-size: 12px; ${failed ? 'border-color: var(--danger); color: var(--danger);' : ''}">${f}${failed ? ' (failed)' : ''}</span>`;
    }
    html += `</div></div>`;
  }

  // Collective analysis
  if (result.collective_analysis) {
    const c = result.collective_analysis;
    const o = c.overall;
    const a = c.alignment;
    html += `<div style="background: var(--accent-dim); border: 1px solid rgba(232, 163, 61, 0.2); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: var(--sp-4);">
      <div style="font-family: var(--font-mono); font-size: 13px; font-weight: 600; color: var(--accent); margin-bottom: var(--sp-3);">
        Combined health: ${o.health_score}/100 (${o.health_label})
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: var(--sp-3);">
        <div><div style="font-family: var(--font-mono); font-size: 24px; font-weight: 700;">${fmtCount(o.total_reports)}</div><div style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">Reports</div></div>
        <div><div style="font-family: var(--font-mono); font-size: 24px; font-weight: 700;">${fmtCount(o.total_records)}</div><div style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">Records</div></div>
        <div><div style="font-family: var(--font-mono); font-size: 24px; font-weight: 700;">${fmtCount(o.total_messages)}</div><div style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">Messages</div></div>
        <div><div style="font-family: var(--font-mono); font-size: 24px; font-weight: 700; color: var(--accent);">${fmtPct(a.overall_pass_rate)}</div><div style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">Pass rate</div></div>
      </div>
    </div>`;
  }

  // Per-file analysis
  if (result.per_file_analysis?.length > 0) {
    html += `<div>
      <div style="font-family: var(--font-mono); font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-muted); margin-bottom: var(--sp-2);">Per-file analysis</div>
      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--sp-2);">`;
    for (const file of result.per_file_analysis) {
      const a = file.analysis;
      const o = a.overall;
      const al = a.alignment;
      html += `<div style="background: var(--bg-2); border: 1px solid var(--border); border-radius: var(--r-md); overflow: hidden;">
        <div style="padding: var(--sp-2) var(--sp-3); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
          <span style="font-family: var(--font-mono); font-size: 12px;">${file.xml_filename}</span>
          <span class="badge ${o.health_score >= 70 ? 'pass' : o.health_score >= 40 ? 'warn' : 'fail'}">${o.health_score}/100</span>
        </div>
        <div style="padding: var(--sp-3);">
          <div style="display: flex; justify-content: space-between; padding: 4px 0; font-family: var(--font-mono); font-size: 12px;"><span style="color: var(--text-muted);">Org</span><span>${file.org_name || '–'}</span></div>
          <div style="display: flex; justify-content: space-between; padding: 4px 0; font-family: var(--font-mono); font-size: 12px;"><span style="color: var(--text-muted);">Domain</span><span>${file.domain || '–'}</span></div>
          <div style="display: flex; justify-content: space-between; padding: 4px 0; font-family: var(--font-mono); font-size: 12px;"><span style="color: var(--text-muted);">Messages</span><span>${fmtCount(o.total_messages)}</span></div>
          <div style="display: flex; justify-content: space-between; padding: 4px 0; font-family: var(--font-mono); font-size: 12px;"><span style="color: var(--text-muted);">DKIM</span><span style="color: var(--success);">${fmtPct(al.dkim_pass_rate)}</span></div>
          <div style="display: flex; justify-content: space-between; padding: 4px 0; font-family: var(--font-mono); font-size: 12px;"><span style="color: var(--text-muted);">SPF</span><span style="color: var(--${al.spf_pass_rate > 50 ? 'success' : 'danger'});">${fmtPct(al.spf_pass_rate)}</span></div>
        </div>
        <div style="padding: 0 var(--sp-3) var(--sp-3);">
          <a href="/file/${file.report_id}" class="btn" style="font-size: 11px; padding: 6px 12px; display: inline-block; text-decoration: none;">View full details →</a>
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
  observeReveals();
})();
