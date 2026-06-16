const state = {
  paused: false,
  eventSource: null,
  snapshot: null,
};

const els = {
  streamState: document.getElementById("streamState"),
  refreshButton: document.getElementById("refreshButton"),
  pauseButton: document.getElementById("pauseButton"),
  statusPanel: document.getElementById("statusPanel"),
  currentStatus: document.getElementById("currentStatus"),
  statusSummary: document.getElementById("statusSummary"),
  statusScore: document.getElementById("statusScore"),
  lastSeen: document.getElementById("lastSeen"),
  flowCount: document.getElementById("flowCount"),
  uniqueDstIps: document.getElementById("uniqueDstIps"),
  uniqueDstPorts: document.getElementById("uniqueDstPorts"),
  synCount: document.getElementById("synCount"),
  failedRatio: document.getElementById("failedRatio"),
  topPorts: document.getElementById("topPorts"),
  sourceIp: document.getElementById("sourceIp"),
  targetNetwork: document.getElementById("targetNetwork"),
  targetIps: document.getElementById("targetIps"),
  sensorId: document.getElementById("sensorId"),
  eventCount: document.getElementById("eventCount"),
  timeline: document.getElementById("timeline"),
  eventsTable: document.getElementById("eventsTable"),
  lastUpdated: document.getElementById("lastUpdated"),
};

function titleCase(value) {
  if (!value) return "-";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function formatScore(value) {
  return Number(value || 0).toFixed(2);
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatList(values, limit = 4) {
  if (!Array.isArray(values) || values.length === 0) return "-";
  const shown = values.slice(0, limit);
  const suffix = values.length > limit ? ` +${values.length - limit}` : "";
  return `${shown.join(", ")}${suffix}`;
}

function targetLabel(event) {
  if (event.primary_dst_ip) return event.primary_dst_ip;
  if (Array.isArray(event.top_dst_ips) && event.top_dst_ips.length > 0) return formatList(event.top_dst_ips, 2);
  return event.target_network || "-";
}

function setStreamState(online) {
  els.streamState.textContent = online ? "Connected" : "Disconnected";
  els.streamState.className = online ? "stream-state online" : "stream-state offline";
}

function statusSummary(status, snapshotStatus) {
  if (status === "scanning") {
    const target = snapshotStatus.primary_dst_ip || snapshotStatus.target_network || "unknown target";
    return `Scan-like activity from ${snapshotStatus.src_ip || "unknown source"} toward ${target}.`;
  }
  if (status === "warning") {
    return `Recon indicators are rising for ${snapshotStatus.src_ip || "unknown source"}.`;
  }
  return "No active scanning signal in the current display window.";
}

function render(snapshot) {
  if (!snapshot || state.paused) return;
  state.snapshot = snapshot;

  const current = snapshot.status || {};
  const evidence = current.evidence || {};
  const status = current.status || "normal";
  const events = snapshot.events || [];
  const metrics = snapshot.metrics || {};

  els.statusPanel.className = `status-panel ${status}`;
  els.currentStatus.textContent = titleCase(status);
  els.statusSummary.textContent = statusSummary(status, current);
  els.statusScore.textContent = formatScore(current.score);
  els.lastSeen.textContent = formatTime(current.last_seen);

  els.flowCount.textContent = formatNumber(evidence.flow_count);
  els.uniqueDstIps.textContent = formatNumber(evidence.unique_dst_ips);
  els.uniqueDstPorts.textContent = formatNumber(evidence.unique_dst_ports);
  els.synCount.textContent = formatNumber(evidence.syn_count);
  els.failedRatio.textContent = formatPercent(evidence.failed_connection_ratio);
  els.topPorts.textContent = (evidence.top_dst_ports || []).slice(0, 6).join(", ") || "-";

  els.sourceIp.textContent = current.src_ip || "-";
  els.targetNetwork.textContent = current.target_network || "-";
  els.targetIps.textContent = formatList(current.top_dst_ips || evidence.top_dst_ips, 5);
  els.sensorId.textContent = current.sensor_id || "-";
  els.eventCount.textContent = formatNumber(metrics.event_count || events.length);
  els.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;

  renderTimeline(events);
  renderEvents(events);
}

function renderTimeline(events) {
  const latest = events.slice(0, 8);
  els.timeline.replaceChildren(
    ...latest.map((event) => {
      const item = document.createElement("li");
      const time = document.createElement("span");
      const pill = document.createElement("span");
      const label = document.createElement("span");
      time.textContent = formatTime(event.received_at);
      pill.className = `pill ${event.status}`;
      pill.textContent = titleCase(event.status);
      label.textContent = `${event.src_ip || "-"} -> ${targetLabel(event)}`;
      item.append(time, pill, label);
      return item;
    })
  );
}

function renderEvents(events) {
  els.eventsTable.replaceChildren(
    ...events.slice(0, 80).map((event) => {
      const row = document.createElement("tr");
      const cells = [
        formatTime(event.received_at),
        titleCase(event.status),
        formatScore(event.score),
        event.src_ip || "-",
        event.target_network || "-",
        formatList(event.top_dst_ips, 3),
        formatNumber(event.flow_count),
        formatNumber(event.unique_dst_ips),
        formatNumber(event.unique_dst_ports),
      ];
      cells.forEach((value, index) => {
        const cell = document.createElement("td");
        if ([2, 6, 7, 8].includes(index)) cell.className = "number";
        if (index === 1) {
          const pill = document.createElement("span");
          pill.className = `pill ${event.status}`;
          pill.textContent = value;
          cell.appendChild(pill);
        } else {
          cell.textContent = value;
        }
        row.appendChild(cell);
      });
      return row;
    })
  );
}

async function loadSnapshot() {
  const response = await fetch("/api/snapshot", { cache: "no-store" });
  if (!response.ok) throw new Error(`snapshot failed: ${response.status}`);
  render(await response.json());
}

function connectStream() {
  if (state.eventSource) {
    state.eventSource.close();
  }
  const source = new EventSource("/api/stream");
  state.eventSource = source;

  source.addEventListener("open", () => setStreamState(true));
  source.addEventListener("error", () => setStreamState(false));
  source.addEventListener("snapshot", (message) => render(JSON.parse(message.data)));
  source.addEventListener("event", (message) => {
    const payload = JSON.parse(message.data);
    render(payload.snapshot);
  });
}

els.refreshButton.addEventListener("click", () => {
  loadSnapshot().catch(() => setStreamState(false));
});

els.pauseButton.addEventListener("click", () => {
  state.paused = !state.paused;
  els.pauseButton.classList.toggle("active", state.paused);
  els.pauseButton.title = state.paused ? "Resume live updates" : "Pause live updates";
  els.pauseButton.setAttribute("aria-label", els.pauseButton.title);
  if (!state.paused && state.snapshot) render(state.snapshot);
});

loadSnapshot().catch(() => setStreamState(false));
connectStream();
