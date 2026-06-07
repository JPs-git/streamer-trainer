const CONFIG_API = '/api/config';

if (sessionStorage.getItem('config_saved')) {
  sessionStorage.removeItem('config_saved');
  console.log('[配置] 配置已更新，服务已重启，新配置已生效');
}

document.addEventListener('DOMContentLoaded', async () => {
  const statusEl = document.getElementById('config-status');
  const btnSave = document.getElementById('btn-save-config');
  const btnReset = document.getElementById('btn-reset-config');

  function showStatus(msg, type) {
    statusEl.textContent = msg;
    statusEl.className = type === 'error' ? 'status-error' : type === 'success' ? 'status-success' : 'status-hidden';
    if (type !== 'error') {
      setTimeout(() => { statusEl.className = 'status-hidden'; }, 5000);
    }
  }

  async function loadConfig() {
    try {
      const resp = await fetch(CONFIG_API);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      document.getElementById('llm-base-url').value = data.llm.base_url || '';
      document.getElementById('llm-api-key').value = data.llm.api_key || '';
      document.getElementById('viewer-min-active').value = data.viewer.min_active;
      document.getElementById('viewer-max-active').value = data.viewer.max_active;
      document.getElementById('viewer-entry-interval').value = data.viewer.entry_interval_sec;
      document.getElementById('viewer-cooldown').value = data.viewer.cooldown_sec;
      document.getElementById('viewer-tick-interval').value = data.viewer.tick_interval_sec;
      document.getElementById('viewer-engagement').value = data.viewer.engagement_threshold;
      console.log('[配置] 当前配置:', JSON.parse(JSON.stringify(data)));
    } catch (err) {
      showStatus('加载配置失败: ' + err.message, 'error');
    }
  }

  async function saveConfig() {
    btnSave.disabled = true;
    showStatus('保存中...', '');
    try {
      const payload = {
        llm: {
          base_url: document.getElementById('llm-base-url').value.trim(),
          api_key: document.getElementById('llm-api-key').value.trim(),
        },
        viewer: {
          min_active: parseInt(document.getElementById('viewer-min-active').value) || 3,
          max_active: parseInt(document.getElementById('viewer-max-active').value) || 8,
          entry_interval_sec: parseInt(document.getElementById('viewer-entry-interval').value) || 180,
          cooldown_sec: parseInt(document.getElementById('viewer-cooldown').value) || 300,
          tick_interval_sec: parseInt(document.getElementById('viewer-tick-interval').value) || 15,
          engagement_threshold: parseInt(document.getElementById('viewer-engagement').value) || 20,
        },
      };
      const resp = await fetch(CONFIG_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await resp.json();
      if (result.status === 'ok') {
        showStatus('保存成功，服务即将重启...', 'success');
        sessionStorage.setItem('config_saved', 'true');
        setTimeout(() => {
          showStatus('服务重启中，请稍候...', '');
          location.reload();
        }, 3000);
      } else {
        showStatus('保存失败: ' + (result.message || '未知错误'), 'error');
      }
    } catch (err) {
      showStatus('保存失败: ' + err.message, 'error');
    } finally {
      btnSave.disabled = false;
    }
  }

  async function resetConfig() {
    if (!confirm('确定恢复默认配置吗？当前配置将被覆盖。')) return;
    btnReset.disabled = true;
    showStatus('恢复中...', '');
    try {
      const resp = await fetch('/api/config/reset', { method: 'POST' });
      const result = await resp.json();
      if (result.status === 'ok') {
        showStatus('已恢复默认，服务即将重启...', 'success');
        sessionStorage.setItem('config_saved', 'true');
        setTimeout(() => {
          showStatus('服务重启中，请稍候...', '');
          location.reload();
        }, 3000);
      } else {
        showStatus('恢复失败: ' + (result.message || '未知错误'), 'error');
      }
    } catch (err) {
      showStatus('恢复失败: ' + err.message, 'error');
    } finally {
      btnReset.disabled = false;
    }
  }

  btnSave.addEventListener('click', saveConfig);
  btnReset.addEventListener('click', resetConfig);

  await loadConfig();
});
