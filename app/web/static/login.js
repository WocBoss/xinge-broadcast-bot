const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

function initData() {
  return tg?.initData || '';
}

function messageId() {
  return new URLSearchParams(location.search).get('m') || '';
}

function setMessage(text, className = '') {
  const el = document.getElementById('message');
  el.className = `message ${className}`.trim();
  el.textContent = text;
}

function showStep(stepId) {
  for (const id of ['step-phone', 'step-code', 'step-password']) {
    document.getElementById(id).hidden = id !== stepId;
  }
}

async function post(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ initData: initData(), messageId: messageId(), ...body }),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || '请求失败');
  }
  return data;
}

async function sendCode() {
  try {
    setMessage('正在发送验证码...');
    await post('api/login/phone', { phone: document.getElementById('phone').value });
    showStep('step-code');
    setMessage('验证码已发送。');
  } catch (error) {
    setMessage(error.message, 'error');
  }
}

async function submitCode() {
  try {
    setMessage('正在验证...');
    const data = await post('api/login/code', { code: document.getElementById('code').value });
    if (data.next === 'password') {
      showStep('step-password');
      setMessage('请输入 2FA 密码。');
      return;
    }
    setMessage('账号已连接，可以关闭页面。', 'ok');
    tg?.close();
  } catch (error) {
    setMessage(error.message, 'error');
  }
}

async function submitPassword() {
  try {
    setMessage('正在登录...');
    await post('api/login/password', { password: document.getElementById('password').value });
    setMessage('账号已连接，可以关闭页面。', 'ok');
    tg?.close();
  } catch (error) {
    setMessage(error.message, 'error');
  }
}
