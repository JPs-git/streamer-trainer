const wsUrl = `ws://${location.host}/danmaku`;
let ws = null;
let reconnectTimer = null;

function connect() {
  ws = new WebSocket(wsUrl);
  ws.onopen = () => {
    console.log('Connected');
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  };
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      handleMessage(data);
    } catch (err) { console.error(err); }
  };
  ws.onclose = () => {
    reconnectTimer = setTimeout(connect, 3000);
  };
}

function handleMessage(data) {
  const container = document.getElementById('chat-messages');
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
      div.textContent = `🟢 ${data.name} 进入了直播间`;
    } else if (data.action === 'leave') {
      div.textContent = `🔴 ${data.name} 离开了直播间`;
    }
  }

  if (div.textContent || div.childNodes.length) {
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  while (container.children.length > 200) {
    container.removeChild(container.firstChild);
  }
}

connect();
