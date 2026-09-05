// ═══════════════════════════════════════════════════════════════════════════
// DMARC Pipeline — analysis report logic
// ═══════════════════════════════════════════════════════════════════════════

const $ = (sel) => document.querySelector(sel);

function fmtCount(n) {
  if (n == null) return '0';
  return n.toLocaleString();
}

function fmtPct(n) {
  if (n == null) return '0%';
  return n.toFixed(1) + '%';
}

function animateCount(el, target, duration = 1000) {
  const start = performance.now();
  function tick(now) {
    const t = Math.min((now - start) / duration, 1);
    const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
    el.textContent = fmtCount(Math.round(target * eased));
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

async function loadAnalysis() {
  try {
    const data = await fetch('/api/analysis').then(r => r.json());
    render(data);
  } catch (err) {
    $('#summary-text').textContent = `Error loading analysis: ${err.message}`;
    $('#summary-text').style.color = 'var(--danger)';
  }
}

function render(data) {
  const o = data.overall || {};
  const a = data.alignment || {};

  // ── Health ring ─────────────────────────────────────────────────────────
  const ring = $('#health-ring');
  const score = o.health_score || 0;
  ring.style.setProperty('--score', score);

  const ringColor = score >= 90 ? 'var(--success)' : score >= 70 ? 'var(--accent)' : score >= 50 ? 'var(--warning)' : 'var(--danger)';
  ring.style.background = `conic-gradient(${ringColor} ${score}%, var(--border) ${score}%)`;

  animateCount($('#health-score'), score, 1000);

  $('#summary-text').textContent = `Across ${fmtCount(o.total_records || 0)} evaluated sources, your ${o.unique_domains === 1 ? 'domain has' : 'domains have'} a health score of ${score}/100.`;
  $('#health-meta').textContent = `${fmtCount(o.total_reports || 0)} reports · ${fmtCount(o.total_records || 0)} records · ${fmtCount(o.total_messages || 0)} messages · ${o.unique_domains || 0} domains · ${o.unique_ips || 0} IPs`;

  // ── Alignment strip ─────────────────────────────────────────────────────
  animateCount($('#dkim-pass'), a.dkim_pass || 0);
  animateCount($('#spf-pass'), a.spf_pass || 0);
  animateCount($('#both-pass'), a.both_pass || 0);
  animateCount($('#either-pass'), a.either_pass || 0);
  animateCount($('#both-fail'), a.both_fail || 0);

  // ── Recommendations ─────────────────────────────────────────────────────
  const recsEl = $('#recommendations');
  recsEl.innerHTML = '';
  for (const rec of data.recommendations || []) {
    const div = document.createElement('div');
    div.className = `rec-item ${rec.severity}`;
    div.innerHTML = `
      <div class="rec-title">${rec.title}</div>
      <div class="rec-detail">${rec.detail}</div>
      <span class="rec-action">→ ${rec.action}</span>
    `;
    recsEl.appendChild(div);
  }

  // ── Domains table ───────────────────────────────────────────────────────
  const domainsBody = $('#domains-table');
  domainsBody.innerHTML = '';
  for (const d of data.domains || []) {
    const tr = document.createElement('tr');
    const rateColor = d.overall_pass_rate >= 90 ? 'var(--success)' : d.overall_pass_rate >= 50 ? 'var(--warning)' : 'var(--danger)';
    tr.innerHTML = `
      <td>${d.domain}</td>
      <td>${fmtCount(d.messages)}</td>
      <td>${fmtCount(d.records)}</td>
      <td><span class="badge pass">${d.dkim_pass}</span> / <span class="badge fail">${d.dkim_fail}</span></td>
      <td><span class="badge pass">${d.spf_pass}</span> / <span class="badge fail">${d.spf_fail}</span></td>
      <td>${d.both_fail > 0 ? `<span class="badge fail">${d.both_fail}</span>` : '<span class="badge pass">0</span>'}</td>
      <td style="color: ${rateColor}; font-weight: 600;">${fmtPct(d.overall_pass_rate)}</td>
    `;
    domainsBody.appendChild(tr);
  }

  // ── IPs table ───────────────────────────────────────────────────────────
  const ipsBody = $('#ips-table');
  ipsBody.innerHTML = '';
  for (const ip of data.top_ips || []) {
    const tr = document.createElement('tr');
    const disp = Object.keys(ip.dispositions || {})[0] || '–';
    const dispClass = disp === 'reject' ? 'fail' : disp === 'quarantine' ? 'warn' : 'pass';
    tr.innerHTML = `
      <td>${ip.ip}</td>
      <td>${fmtCount(ip.messages)}</td>
      <td>${fmtPct(ip.dkim_pass_rate)}</td>
      <td>${fmtPct(ip.spf_pass_rate)}</td>
      <td><span class="badge ${dispClass}">${disp}</span></td>
    `;
    ipsBody.appendChild(tr);
  }

  // ── Sending services ────────────────────────────────────────────────────
  const servicesEl = $('#services');
  servicesEl.innerHTML = '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: var(--sp-2);">';
  for (const svc of data.sending_services || []) {
    servicesEl.innerHTML += `
      <div style="background: var(--bg-2); border: 1px solid var(--border); border-radius: var(--r-md); padding: var(--sp-3);">
        <div style="font-family: var(--font-mono); font-size: 13px; font-weight: 600; margin-bottom: var(--sp-1);">${svc.service}</div>
        <div style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted);">${fmtCount(svc.messages)} messages · ${svc.ip_count} IP${svc.ip_count !== 1 ? 's' : ''}</div>
      </div>`;
  }
  servicesEl.innerHTML += '</div>';

  // ── Dispositions ────────────────────────────────────────────────────────
  const dispEl = $('#dispositions');
  dispEl.innerHTML = '';
  const totalDisp = Object.values(data.dispositions || {}).reduce((a, b) => a + b, 0) || 1;
  const dispColors = { none: 'pass', reject: 'fail', quarantine: 'warn' };
  for (const [name, count] of Object.entries(data.dispositions || {}).sort((a, b) => b[1] - a[1])) {
    const pct = (count / totalDisp * 100).toFixed(1);
    const div = document.createElement('div');
    div.style.marginBottom = 'var(--sp-2)';
    div.innerHTML = `
      <div style="display: flex; align-items: center; gap: var(--sp-2); margin-bottom: var(--sp-1);">
        <span style="font-family: var(--font-mono); font-size: 12px; min-width: 80px;">${name}</span>
        <div style="flex: 1; height: 8px; background: var(--bg-2); border-radius: 4px; overflow: hidden;">
          <div style="width: ${pct}%; height: 100%; background: var(--${dispColors[name] || 'accent'}); border-radius: 4px;"></div>
        </div>
        <span style="font-family: var(--font-mono); font-size: 12px; min-width: 60px; text-align: right;">${fmtCount(count)}</span>
      </div>`;
    dispEl.appendChild(div);
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

loadAnalysis();
