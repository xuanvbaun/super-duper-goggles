// 万能视频嗅探面板 v3.1
// 启动: node 视频嗅探面板.js   |   浏览器: http://localhost:8765

const http = require('http');
const https = require('https');
const zlib = require('zlib');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PORT = 8765;

let FFMPEG = 'ffmpeg';
try { require('child_process').execSync('ffmpeg -version', { stdio: 'ignore' }); } catch {
    FFMPEG = path.join(__dirname, 'ffmpeg', 'bin', 'ffmpeg.exe');
}

// ============ 辅助 ============
function apiGet(url, referer) {
    return new Promise((resolve, reject) => {
        https.get(url, {
            headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': referer || 'https://www.bilibili.com' }
        }, res => {
            const chunks = [];
            res.on('data', c => chunks.push(c));
            res.on('end', () => {
                let body = Buffer.concat(chunks);
                if (res.headers['content-encoding'] === 'gzip') try { body = zlib.gunzipSync(body); } catch {}
                try { resolve(JSON.parse(body.toString('utf8'))); } catch (e) { reject(new Error('JSON parse error')); }
            });
        }).on('error', reject);
    });
}

async function extractBilibili(bvid) {
    const info = await apiGet('https://api.bilibili.com/x/web-interface/view?bvid=' + bvid);
    if (info.code !== 0) throw new Error('视频不存在或API错误: ' + (info.message || info.code));
    const vd = info.data;
    if (!vd || !vd.cid) throw new Error('未找到视频数据');

    const title = vd.title || 'bilibili_video';
    const duration = vd.duration || 0;

    // 获取可用画质列表
    const playApi = 'https://api.bilibili.com/x/player/playurl?bvid=' + bvid + '&cid=' + vd.cid + '&qn=127&fnval=4048&fourk=1&platform=html5&high_quality=1';
    const play = await apiGet(playApi);
    if (play.code !== 0) throw new Error('PlayURL API 错误: ' + play.code);

    const qualities = (play.data?.support_formats || []).map(f => ({
        quality: f.quality,
        label: f.new_description || f.display_desc || '',
    }));

    // 如果 support_formats 为空，用 accept 列表
    if (qualities.length === 0 && play.data?.accept_quality) {
        play.data.accept_quality.forEach((q, i) => {
            qualities.push({ quality: q, label: (play.data.accept_description || [])[i] || ('画质' + q) });
        });
    }

    return {
        success: true, bilibili: true,
        title, bvid, cid: vd.cid,
        durationText: Math.floor(duration / 60) + '分' + (duration % 60) + '秒',
        qualities: qualities.slice(0, 8)
    };
}

async function getDownloadUrl(bvid, cid, quality) {
    const api = 'https://api.bilibili.com/x/player/playurl?bvid=' + bvid + '&cid=' + cid + '&qn=' + quality + '&fnval=1&fourk=1&platform=html5&high_quality=1';
    const play = await apiGet(api);
    if (play.code !== 0) throw new Error('获取下载链接失败: ' + play.code);
    const durl = play.data?.durl || [];
    if (durl.length === 0) throw new Error('该画质无可用流');
    return durl.map(u => ({ url: u.url || '', size: u.size || 0, sizeText: u.size > 0 ? (u.size / 1048576).toFixed(1) + ' MB' : '未知' }));
}

// ============ HTTP 服务器 ============
const server = http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    if (req.method === 'OPTIONS') {
        res.writeHead(200, { 'Access-Control-Allow-Methods': 'GET,POST' });
        return res.end();
    }

    const u = new URL(req.url, 'http://localhost:' + PORT);

    if (u.pathname === '/ping') {
        res.writeHead(200); return res.end('pong');
    }

    if (u.pathname === '/extract') {
        const url = u.searchParams.get('url') || '';
        const m = url.match(/bilibili\.com\/video\/([A-Za-z0-9]+)/);
        if (!m) {
            res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
            return res.end(JSON.stringify({ success: false, error: '仅支持B站链接' }));
        }
        return extractBilibili(m[1]).then(d => {
            res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify(d));
        }).catch(e => {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ success: false, error: e.message }));
        });
    }

    if (u.pathname === '/geturl') {
        const bvid = u.searchParams.get('bvid'), cid = u.searchParams.get('cid'), q = parseInt(u.searchParams.get('quality') || '80');
        return getDownloadUrl(bvid, cid, q).then(r => {
            res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify({ success: true, urls: r }));
        }).catch(e => {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ success: false, error: e.message }));
        });
    }

    if (u.pathname === '/download') {
        const videoUrl = u.searchParams.get('url') || '';
        const filename = (u.searchParams.get('name') || 'video').replace(/[\\/:*?"<>|]/g, '_');
        const toMp4 = u.searchParams.get('format') === 'mp4';

        if (!videoUrl) { res.writeHead(400); return res.end('missing url'); }

        if (!toMp4) {
            res.writeHead(302, { 'Location': videoUrl });
            return res.end();
        }

        // 转MP4: 返回加载页面 → 后台转换 → 完成后自动开始下载
        const jobId = Date.now().toString(36) + Math.random().toString(36).slice(2);
        console.log('[转MP4] job=' + jobId, filename);

        // 先返回加载页面
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(`<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>正在准备下载...</title><style>
body{font-family:"Microsoft YaHei",sans-serif;background:#1a1a2e;color:#e0e0e0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column}
.spin{width:40px;height:40px;border:3px solid #333;border-top-color:#667eea;border-radius:50%;animation:s .8s linear infinite;margin-bottom:16px}
@keyframes s{to{transform:rotate(360deg)}}
.progress{width:300px;background:#333;border-radius:4px;height:6px;margin-top:12px;overflow:hidden}
.progress .bar{height:100%;background:linear-gradient(90deg,#667eea,#764ba2);width:0;transition:width .3s}
.info{font-size:13px;color:#888;margin-top:8px}
</style></head><body>
<div class="spin"></div><h3>正在准备下载...</h3>
<div class="progress"><div class="bar" id="bar"></div></div>
<div class="info" id="info">连接CDN...</div>
<script>
var jobId='${jobId}';
var bar=document.getElementById('bar');
var info=document.getElementById('info');
var stages=['连接CDN...','下载源文件...','FFmpeg转码中...','处理完成!'];
var si=0;
var iv=setInterval(function(){
  si=Math.min(si+1,stages.length-1);
  info.textContent=stages[si];
  bar.style.width=(si*25)+'%';
  fetch('/progress?job='+jobId).then(r=>r.json()).then(d=>{
    if(d.done){clearInterval(iv);bar.style.width='100%';info.textContent='✅ 转码完成, 开始下载...';
      var a=document.createElement('a');a.href='/result?job='+jobId;a.download='${filename.replace(/'/g,"\\'").replace(/\.[^.]+$/, '')}.mp4';
      document.body.appendChild(a);a.click();
      setTimeout(function(){window.close();},2000);
    }
  });
},2000);
</script></body></html>`);

        // 清理超过5分钟的旧 job
        if (server._jobs) {
            const now = Date.now();
            for (const [id, j] of Object.entries(server._jobs)) {
                if (now - j.createdAt > 300000) { try { fs.unlinkSync(j.tmpOut); } catch {} delete server._jobs[id]; }
            }
        }

        // 后台异步处理转换
        const tmpIn = path.join(os.tmpdir(), 'vdin_' + jobId + '.tmp');
        const tmpOut = path.join(os.tmpdir(), 'vdout_' + jobId + '.mp4');

        // 存储 job 状态
        if (!server._jobs) server._jobs = {};
        server._jobs[jobId] = { status: 'downloading', tmpOut, filename, createdAt: Date.now() };

        const proto = videoUrl.startsWith('https') ? https : http;
        proto.get(videoUrl, {
            headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com' }
        }, (proxyRes) => {
            const ws = fs.createWriteStream(tmpIn);
            proxyRes.pipe(ws);
            ws.on('finish', () => {
                server._jobs[jobId].status = 'converting';
                const ffmpeg = spawn(FFMPEG, [
                    '-i', tmpIn, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k',
                    '-movflags', 'faststart', '-y', tmpOut
                ]);
                ffmpeg.on('close', (code) => {
                    try { fs.unlinkSync(tmpIn); } catch {}
                    server._jobs[jobId].status = code === 0 ? 'done' : 'error';
                    server._jobs[jobId].error = code !== 0 ? ('FFmpeg exit ' + code) : null;
                    if (code === 0) console.log('[完成]', filename);
                    else console.error('[失败]', filename, 'code=' + code);
                });
                ffmpeg.stderr.on('data', () => {});
            });
        }).on('error', (err) => {
            server._jobs[jobId].status = 'error';
            server._jobs[jobId].error = err.message;
            try { fs.unlinkSync(tmpIn); } catch {}
        });
        return;
    }

    if (u.pathname === '/progress') {
        const jobId = u.searchParams.get('job') || '';
        const job = (server._jobs || {})[jobId];
        res.writeHead(200, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify({ done: job && job.status === 'done', status: job ? job.status : 'notfound' }));
    }

    if (u.pathname === '/result') {
        const jobId = u.searchParams.get('job') || '';
        const job = (server._jobs || {})[jobId];
        if (!job || job.status !== 'done' || !fs.existsSync(job.tmpOut)) {
            res.writeHead(404, { 'Content-Type': 'application/json' });
            return res.end(JSON.stringify({ error: 'file not ready', status: job ? job.status : 'notfound' }));
        }
        try {
            const out = fs.readFileSync(job.tmpOut);
            res.writeHead(200, {
                'Content-Type': 'video/mp4',
                'Content-Disposition': "attachment; filename*=UTF-8''" + encodeURIComponent((job.filename || 'video').replace(/\.[^.]+$/, '') + '.mp4'),
                'Content-Length': out.length,
            });
            res.end(out);
            try { fs.unlinkSync(job.tmpOut); } catch {}
            delete server._jobs[jobId];
        } catch (e) {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: e.message }));
        }
        return;
    }

    // 主页
    serveIndex(res);
});

function serveIndex(res) {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(`<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>视频嗅探下载器 v3.1</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh}
.header{background:#252538;padding:20px;border-bottom:1px solid #313145;text-align:center}
.header h1{font-size:22px;color:#7bed9f}.header p{color:#888;font-size:13px}
.container{max-width:800px;margin:0 auto;padding:20px}
.input-row{display:flex;gap:10px;margin-bottom:20px}
.input-row input{flex:1;padding:12px 16px;background:#252538;border:1px solid #313145;border-radius:8px;color:#fff;font-size:14px;outline:none}
.input-row input:focus{border-color:#667eea}
.input-row button{padding:12px 20px;background:linear-gradient(135deg,#667eea,#764ba2);border:none;border-radius:8px;color:#fff;font-size:14px;cursor:pointer;font-weight:600;white-space:nowrap}
.input-row button:hover{opacity:0.9}.input-row button:disabled{opacity:0.4}
#status{text-align:center;color:#888;padding:8px;font-size:13px;min-height:28px}
#status .g{color:#7bed9f}#status .r{color:#ff6b6b}
.card{background:#252538;border-radius:10px;padding:16px;margin-bottom:12px;border:1px solid #313145}
.card .t{font-size:16px;color:#fff;font-weight:600;margin-bottom:4px}
.card .m{color:#888;font-size:12px}
.qgrid{display:grid;gap:8px}
.qrow{background:#1e1e30;border-radius:8px;padding:12px;border:1px solid #313145;display:flex;align-items:center;gap:12px}
.qrow:hover{border-color:#667eea}
.qrow .ql{font-size:14px;font-weight:600;min-width:100px}
.qrow .qs{flex:1;font-size:12px;color:#888}
.qrow .qz{font-size:12px;color:#ffa502;min-width:80px;text-align:right}
.btn{padding:8px 14px;border:none;border-radius:6px;font-size:12px;cursor:pointer;color:#fff;font-weight:500;white-space:nowrap;text-decoration:none;display:inline-block}
.btn:hover{opacity:0.85}.btn:disabled{opacity:0.4;cursor:not-allowed}
.btn-dl{background:#2d5a27;color:#7bed9f}.btn-mp4{background:#4a2060;color:#c084fc}
.dl-progress{background:#111;border-radius:6px;height:8px;margin-top:8px;overflow:hidden;display:none}
.dl-progress .bar{background:linear-gradient(90deg,#667eea,#764ba2);height:100%;width:0;transition:width .3s}
.dl-info{font-size:11px;color:#888;margin-top:4px;display:none}
.spin{display:inline-block;width:16px;height:16px;border:2px solid #333;border-top-color:#667eea;border-radius:50%;animation:s .6s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
.footer{text-align:center;color:#555;padding:20px;font-size:11px}
a{color:#70a1ff}
</style>
</head>
<body>
<div class="header"><h1>🎬 视频嗅探下载器 v3.1</h1><p>粘贴 B站 视频链接 → 选择画质 → 一键下载或转MP4 | Ctrl+J 查看下载</p></div>
<div class="container">
  <div class="input-row">
    <input id="url" placeholder="B站视频链接, 如 https://www.bilibili.com/video/BVxxx" />
    <button id="btn" onclick="extract()">🔍 提取</button>
  </div>
  <div id="status"></div>
  <div id="out"></div>
</div>
<div class="footer">本地服务 :${PORT} | FFmpeg 实时转码 | 下载保存到浏览器默认下载文件夹</div>
<script>
var info = null;

document.getElementById('url').onkeydown = function(e) { if(e.key==='Enter') extract(); };

function st(msg, cls) { document.getElementById('status').innerHTML = msg ? '<span class="'+(cls||'')+'">'+msg+'</span>' : ''; }

async function extract() {
  var url = document.getElementById('url').value.trim();
  if (!url) return st('请输入链接', 'r');
  if (!url.startsWith('http')) url = 'https://' + url;
  st('<span class="spin"></span>获取视频信息...', '');
  document.getElementById('out').innerHTML = '';
  document.getElementById('btn').disabled = true;
  try {
    var r = await fetch('/extract?url=' + encodeURIComponent(url));
    var d = await r.json();
    document.getElementById('btn').disabled = false;
    if (d.success) { info = d; st('✅ ' + d.title + ' | ' + d.durationText + ' | ' + d.qualities.length + ' 种画质', 'g'); render(); }
    else st('❌ ' + (d.error||'失败'), 'r');
  } catch(e) { document.getElementById('btn').disabled = false; st('❌ ' + e.message, 'r'); }
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function render() {
  var h = '<div class="card"><div class="t">📺 ' + esc(info.title) + '</div><div class="m">时长 ' + info.durationText + ' | ' + info.qualities.length + ' 种画质可选 | 点击后实时获取链接</div></div><div class="qgrid">';
  info.qualities.forEach(function(q) {
    h += '<div class="qrow" id="r'+q.quality+'"><div class="ql">🎯 '+esc(q.label)+'</div><div class="qs"></div><div class="qz" id="z'+q.quality+'">-</div><button class="btn btn-dl" id="bdl'+q.quality+'" onclick="dl('+q.quality+',0)">⬇ 下载</button><button class="btn btn-mp4" id="bmp4'+q.quality+'" onclick="dl('+q.quality+',1)">⬇ 转MP4</button></div><div class="dl-progress" id="p'+q.quality+'"><div class="bar"></div></div><div class="dl-info" id="i'+q.quality+'"></div>';
  });
  h += '</div>';
  document.getElementById('out').innerHTML = h;
}

async function dl(quality, toMp4) {
  if (!info) return;
  var bvid = info.bvid, cid = info.cid;
  var zEl = document.getElementById('z'+quality);
  var iEl = document.getElementById('i'+quality);
  var bDl = document.getElementById('bdl'+quality);
  var bMp4 = document.getElementById('bmp4'+quality);

  bDl.disabled = bMp4.disabled = true;
  iEl.style.display = 'block';
  iEl.textContent = '正在获取最新下载链接...';

  try {
    var r = await fetch('/geturl?bvid='+bvid+'&cid='+cid+'&quality='+quality);
    var d = await r.json();
    if (!d.success || !d.urls || !d.urls.length) { iEl.textContent = '❌ '+(d.error||'获取失败'); bDl.disabled=bMp4.disabled=false; return; }

    var u = d.urls[0];
    zEl.textContent = u.sizeText;

    var dlUrl = '/download?url=' + encodeURIComponent(u.url) + '&name=' + encodeURIComponent(info.title) + (toMp4 ? '&format=mp4' : '');

    // 新窗口打开下载链接，服务端 Content-Disposition 触发下载，面板保持不动
    window.open(dlUrl, '_blank');

    iEl.textContent = '✅ 下载已触发 (' + u.sizeText + ') | 新窗口会自动关闭并开始下载 | Ctrl+J 查看进度';
  } catch(e) {
    iEl.textContent = '❌ ' + e.message;
  }
  bDl.disabled = bMp4.disabled = false;
}
</script>
</body>
</html>`);
}

server.listen(PORT, () => {
    console.log('═'.repeat(55));
    console.log('  视频嗅探面板 v3.1  http://localhost:' + PORT);
    console.log('  提取 → 选择画质 → 下载/转MP4');
    console.log('═'.repeat(55));
});
