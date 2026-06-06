const API_BASE = location.origin;
const WS_URL = `ws://${location.host}/danmaku`;
let ws = null;
let reconnectTimer = null;
let reconnectDelay = 1000;
const MAX_RECONNECT_DELAY = 30000;

function connect() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    reconnectDelay = 1000;
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  };
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      handleMessage(data);
    } catch (err) { console.error(err); }
  };
  ws.onclose = () => {
    reconnectTimer = setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
  };
}

let viewerCount = 0;

function handleMessage(data) {
  const container = document.getElementById('chat-messages');
  const countEl = document.getElementById('viewer-count');
  const div = document.createElement('div');

  if (data.type === 'danmaku') {
    div.className = `msg ${data.effect === 'highlight' ? 'highlight' : ''}`;
    const nameSpan = document.createElement('span');
    nameSpan.className = `name ${data.personality || 'bystander'}`;
    nameSpan.textContent = data.name + ': ';
    const textSpan = document.createElement('span');
    textSpan.className = 'text';
    textSpan.textContent = data.text;
    div.appendChild(nameSpan);
    div.appendChild(textSpan);
  } else if (data.type === 'system') {
    div.className = `msg system ${data.action}`;
    if (data.action === 'enter') {
      viewerCount++;
      div.textContent = `🟢 ${data.name} 进入了直播间`;
    } else if (data.action === 'leave') {
      viewerCount = Math.max(0, viewerCount - 1);
      div.textContent = `🔴 ${data.name} 离开了直播间`;
    }
    countEl.textContent = `${viewerCount}人在线`;
  }

  if (div.textContent || div.childNodes.length) {
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  while (container.children.length > 200) {
    container.removeChild(container.firstChild);
  }
}

// --- Scheduler control ---

let schedulerPaused = true;  // 调度器默认暂停

document.getElementById('btn-toggle-scheduler').addEventListener('click', async () => {
  const btn = document.getElementById('btn-toggle-scheduler');
  const statusEl = document.getElementById('scheduler-status');
  const action = schedulerPaused ? 'resume' : 'pause';
  try {
    const resp = await fetch(`${API_BASE}/control/scheduler`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action}),
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      schedulerPaused = data.paused;
      btn.textContent = schedulerPaused ? '▶ 开始' : '⏸ 暂停';
      statusEl.textContent = schedulerPaused ? '● 已暂停' : '● 运行中';
      statusEl.className = schedulerPaused ? 'status-paused' : 'status-running';
    }
  } catch (err) {
    console.error('Scheduler control failed:', err);
  }
});

connect();
