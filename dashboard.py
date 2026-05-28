"""
Dashboard web per la gestione dei mockup surge.sh.
Avvia con:  python dashboard.py
Poi apri:   http://localhost:5000
"""

import os, sys, subprocess, datetime, hashlib, re, json, threading, webbrowser, shutil
from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string, jsonify

app  = Flask(__name__)
JOBS = {}   # slug -> {step: str, done: bool, error: bool}

# ── Paths ────────────────────────────────────────────────────────────────────

BASE     = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(BASE, "mockups_registry.json")
MOCKUPS  = os.path.join(BASE, "clienti")
NPX      = "npx.cmd" if sys.platform == "win32" else "npx"

PW_START = "<!-- PW-GATE-START -->"
PW_END   = "<!-- PW-GATE-END -->"

PW_GATE = """\
<!-- PW-GATE-START -->
<div id="pw-gate" style="position:fixed;inset:0;z-index:9999;background:#1C1814;display:flex;align-items:center;justify-content:center;font-family:sans-serif;">
  <div style="text-align:center;color:#fff;max-width:320px;width:90%;padding:20px">
    <div style="font-size:1.4rem;margin-bottom:8px;font-weight:600;">Accesso riservato</div>
    <p style="font-size:.85rem;color:rgba(255,255,255,.5);margin-bottom:24px;">Questa e' una preview privata.</p>
    <input id="pw-in" type="password" placeholder="Password" onkeydown="if(event.key==='Enter')_chk()" style="width:100%;padding:12px 16px;border:1px solid #B8935A;background:transparent;color:#fff;font-size:1rem;border-radius:4px;outline:none;margin-bottom:10px;box-sizing:border-box;" />
    <button onclick="_chk()" style="width:100%;padding:12px;background:#B8935A;color:#fff;border:none;border-radius:4px;font-size:.9rem;cursor:pointer;">Entra</button>
    <div id="pw-err" style="color:#e74c3c;font-size:.8rem;margin-top:8px;visibility:hidden;">Password non corretta</div>
  </div>
</div>
<script>
  (function(){
    const H="{HASH}";
    async function _chk(){
      const v=document.getElementById('pw-in').value;
      const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(v));
      const h=Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('');
      if(h===H){document.getElementById('pw-gate').remove();sessionStorage.setItem('_ok','1');}
      else{document.getElementById('pw-err').style.visibility='visible';}
    }
    window._chk=_chk;
    if(sessionStorage.getItem('_ok')==='1')document.getElementById('pw-gate').remove();
  })();
</script>
<!-- PW-GATE-END -->"""

# ── Registry helpers ──────────────────────────────────────────────────────────

def load_reg():
    if not os.path.exists(REGISTRY):
        return {}
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)

def save_reg(data):
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ── Surge helpers ─────────────────────────────────────────────────────────────

def surge_deploy(slug, domain):
    folder = os.path.join(MOCKUPS, slug)
    r = subprocess.run([NPX, "--yes", "surge", folder, domain], capture_output=True)
    return r.returncode == 0, r.stdout.decode(errors="replace") + r.stderr.decode(errors="replace")

def surge_teardown(domain):
    r = subprocess.run([NPX, "--yes", "surge", "teardown", domain], capture_output=True)
    return r.returncode == 0, r.stdout.decode(errors="replace") + r.stderr.decode(errors="replace")

# ── Password helpers ──────────────────────────────────────────────────────────

def inject_pw(slug, password):
    index = os.path.join(MOCKUPS, slug, "index.html")
    with open(index, encoding="utf-8") as f:
        html = f.read()
    remove_pw(slug)
    with open(index, encoding="utf-8") as f:
        html = f.read()
    h = hashlib.sha256(password.encode()).hexdigest()
    gate = PW_GATE.replace("{HASH}", h)
    html = html.replace("<body>", "<body>\n" + gate, 1)
    with open(index, "w", encoding="utf-8") as f:
        f.write(html)

def remove_pw(slug):
    index = os.path.join(MOCKUPS, slug, "index.html")
    with open(index, encoding="utf-8") as f:
        html = f.read()
    cleaned = re.sub(
        re.escape(PW_START) + r".*?" + re.escape(PW_END) + r"\n?",
        "", html, flags=re.DOTALL
    )
    with open(index, "w", encoding="utf-8") as f:
        f.write(cleaned)

# ── HTML template ─────────────────────────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Mockup Dashboard</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#FAF7F2;color:#1C1814;min-height:100vh}
header{background:#1C1814;color:#fff;padding:20px 32px;display:flex;align-items:center;justify-content:space-between}
header h1{font-size:1.1rem;font-weight:600;letter-spacing:.04em}
header span{font-size:.8rem;color:rgba(255,255,255,.4)}
.main{max-width:960px;margin:0 auto;padding:32px 24px}
.top-bar{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px}
.top-bar h2{font-size:1rem;font-weight:600;color:#5C4E42}
.btn-new{background:#B8935A;color:#fff;border:none;padding:9px 20px;border-radius:4px;font-size:.85rem;cursor:pointer;font-weight:500;text-decoration:none;display:inline-block}
.btn-new:hover{background:#9A7A45}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px}
.card{background:#fff;border:1px solid #E8DDD0;border-radius:8px;overflow:hidden;display:flex;flex-direction:column}
.card-head{padding:18px 20px 14px;border-bottom:1px solid #F0E8DA}
.card-name{font-size:1rem;font-weight:600;color:#1C1814;margin-bottom:6px}
.card-domain{font-size:.78rem;color:#8A7B70;word-break:break-all}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:.7rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;margin-bottom:8px}
.badge-live{background:#d4edda;color:#1a6632}
.badge-teardown{background:#fde;color:#9b2335}
.badge-protected{background:#fff3cd;color:#856404}
.badge-local{background:#d1ecf1;color:#0c5460}
.card-body{padding:14px 20px;flex:1;font-size:.82rem;color:#5C4E42;line-height:1.6}
.card-actions{padding:14px 20px;border-top:1px solid #F0E8DA;display:flex;flex-wrap:wrap;gap:8px}
.btn{padding:7px 14px;border-radius:4px;font-size:.78rem;font-weight:500;cursor:pointer;border:none;text-decoration:none;display:inline-block}
.btn-primary{background:#B8935A;color:#fff}.btn-primary:hover{background:#9A7A45}
.btn-danger{background:#e74c3c;color:#fff}.btn-danger:hover{background:#c0392b}
.btn-success{background:#27ae60;color:#fff}.btn-success:hover{background:#219a52}
.btn-outline{background:transparent;border:1.5px solid #B8935A;color:#B8935A}.btn-outline:hover{background:#B8935A;color:#fff}
.btn-ghost{background:#F0E8DA;color:#5C4E42}.btn-ghost:hover{background:#E0D4C0}
.btn-sm{padding:5px 10px;font-size:.73rem}

/* Toast */
.toast{position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:6px;font-size:.85rem;font-weight:500;z-index:1000;animation:fadein .3s ease,fadeout .4s ease 3.5s forwards}
.toast-ok{background:#1a6632;color:#fff}
.toast-err{background:#9b2335;color:#fff}
@keyframes fadein{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes fadeout{to{opacity:0;transform:translateY(10px)}}

/* Modal */
.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:500;align-items:center;justify-content:center}
.overlay.open{display:flex}
.modal{background:#fff;border-radius:8px;padding:28px;max-width:360px;width:90%}
.modal h3{font-size:1rem;font-weight:600;margin-bottom:16px}
.modal input{width:100%;padding:10px 12px;border:1.5px solid #E8DDD0;border-radius:4px;font-size:.9rem;margin-bottom:12px;outline:none}
.modal input:focus{border-color:#B8935A}
.modal-actions{display:flex;gap:8px;justify-content:flex-end}

/* New site modal */
.form-row{margin-bottom:12px}
.form-row label{display:block;font-size:.78rem;font-weight:600;color:#5C4E42;margin-bottom:4px}
.form-row input,.form-row select{width:100%;padding:9px 12px;border:1.5px solid #E8DDD0;border-radius:4px;font-size:.85rem;outline:none;background:#fff}
.form-row input:focus,.form-row select:focus{border-color:#B8935A}

/* Generating state */
.badge-generating{background:#e8f0fe;color:#1a56db}
.progress-bar{height:4px;background:#E8DDD0;border-radius:2px;margin-top:8px;overflow:hidden}
.progress-bar-inner{height:100%;background:#B8935A;border-radius:2px;animation:progress-pulse 1.5s ease-in-out infinite}
@keyframes progress-pulse{0%,100%{opacity:.5;width:30%}50%{opacity:1;width:80%}}
.step-text{font-size:.75rem;color:#8A7B70;margin-top:6px;font-style:italic}

/* Loader */
.loader-overlay{display:none;position:fixed;inset:0;background:rgba(28,24,20,.6);z-index:900;align-items:center;justify-content:center;flex-direction:column;color:#fff;gap:16px}
.loader-overlay.active{display:flex}
.spinner{width:40px;height:40px;border:3px solid rgba(255,255,255,.2);border-top-color:#B8935A;border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>

<header>
  <h1>Mockup Dashboard</h1>
  <span>{{ sites|length }} sito{{ 'i' if sites|length != 1 else '' }} registrato{{ 'i' if sites|length != 1 else '' }}</span>
</header>

<div class="main">
  <div class="top-bar">
    <h2>I tuoi mockup</h2>
    <button class="btn-new" onclick="openNew()">+ Nuovo sito</button>
  </div>

  {% if sites %}
  <div class="grid">
    {% for slug, s in sites.items() %}
    <div class="card">
      <div class="card-head">
        {% if s.status == 'live' %}
          <span class="badge badge-live">Live</span>
        {% elif s.status == 'teardown' %}
          <span class="badge badge-teardown">Offline</span>
        {% elif s.status == 'protected' %}
          <span class="badge badge-protected">Protetto</span>
        {% elif s.status == 'generating' %}
          <span class="badge badge-generating">Generazione...</span>
        {% elif s.status == 'manual' %}
          <span class="badge" style="background:#e8f4fd;color:#1a5276">In attesa Claude Code</span>
        {% else %}
          <span class="badge badge-local">Locale</span>
        {% endif %}
        <div class="card-name">{{ s.name }}</div>
        <div class="card-domain">{{ s.domain }}</div>
      </div>
      <div class="card-body">
        {% if s.status == 'generating' %}
          <div class="progress-bar"><div class="progress-bar-inner"></div></div>
          <div class="step-text" id="step-{{ slug }}">{{ s.get('step','In corso...') }}</div>
        {% else %}
          Aggiunto il {{ s.deployed_at }}<br>
          {% if s.protected %}<strong>Password attiva</strong> &nbsp;·&nbsp; {% endif %}
          {% if s.cost_usd is defined and s.cost_usd %}<span style="font-size:.78rem;color:#B8935A">Costo generazione: ${{ s.cost_usd }}</span>{% endif %}
        {% endif %}
      </div>
      <div class="card-actions">

        {% if s.status == 'generating' %}
          <span style="font-size:.78rem;color:#8A7B70;padding:4px 0">Attendi il completamento...</span>
        {% elif s.status == 'manual' %}
          <a class="btn btn-ghost btn-sm" href="/preview/{{ slug }}/" target="_blank">Anteprima locale</a>
          <button class="btn btn-sm" style="background:#e8f4fd;color:#1a5276;border:1px solid #aed6f1"
            onclick="showClaudeCmd('{{ slug }}','{{ s.source_url }}','{{ s.name }}','{{ s.category }}')">Vedi comando Claude Code</button>
          <form method="post" action="/action" onsubmit="showLoader('Pubblicazione su surge...')">
            <input type="hidden" name="slug" value="{{ slug }}">
            <input type="hidden" name="action" value="deploy">
            <button class="btn btn-success btn-sm" type="submit">Attiva su surge</button>
          </form>
          <button class="btn btn-sm" style="background:#f8f0f0;color:#9b2335;border:1px solid #f5c6cb" onclick="openDelete('{{ slug }}','{{ s.name }}')">Elimina</button>
        {% else %}
          {% if s.status in ('live', 'protected') %}
            <a class="btn btn-ghost btn-sm" href="https://{{ s.domain }}" target="_blank">Apri</a>
          {% endif %}
          <a class="btn btn-ghost btn-sm" href="/preview/{{ slug }}/" target="_blank">Anteprima locale</a>
          {% if s.status in ('live', 'protected') %}
            <form method="post" action="/action" onsubmit="showLoader('Rimozione da surge...')">
              <input type="hidden" name="slug" value="{{ slug }}">
              <input type="hidden" name="action" value="teardown">
              <button class="btn btn-danger btn-sm" type="submit">Disattiva</button>
            </form>
          {% else %}
            <form method="post" action="/action" onsubmit="showLoader('Pubblicazione su surge...')">
              <input type="hidden" name="slug" value="{{ slug }}">
              <input type="hidden" name="action" value="deploy">
              <button class="btn btn-success btn-sm" type="submit">Attiva</button>
            </form>
          {% endif %}
          {% if s.protected %}
            <form method="post" action="/action" onsubmit="showLoader('Rimozione password...')">
              <input type="hidden" name="slug" value="{{ slug }}">
              <input type="hidden" name="action" value="unprotect">
              <button class="btn btn-outline btn-sm" type="submit">Rimuovi password</button>
            </form>
          {% else %}
            <button class="btn btn-outline btn-sm" onclick="openPw('{{ slug }}')">Aggiungi password</button>
          {% endif %}
          <button class="btn btn-sm" style="background:#f8f0f0;color:#9b2335;border:1px solid #f5c6cb" onclick="openDelete('{{ slug }}','{{ s.name }}')">Elimina</button>
        {% endif %}

      </div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <p style="color:#8A7B70;margin-top:40px">Nessun sito registrato. Clicca "+ Nuovo sito" per iniziare.</p>
  {% endif %}
</div>

{% if msg %}
<div class="toast {{ 'toast-ok' if ok else 'toast-err' }}">{{ msg }}</div>
{% endif %}

<!-- Password modal -->
<div class="overlay" id="pw-overlay">
  <div class="modal">
    <h3>Aggiungi password</h3>
    <form method="post" action="/action" onsubmit="showLoader('Aggiornamento in corso...')">
      <input type="hidden" name="action" value="protect">
      <input type="hidden" name="slug" id="pw-slug" value="">
      <input type="password" name="password" id="pw-input" placeholder="Scegli una password" required autocomplete="new-password">
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" onclick="closePw()">Annulla</button>
        <button type="submit" class="btn btn-primary">Conferma</button>
      </div>
    </form>
  </div>
</div>

<!-- New site modal -->
<div class="overlay" id="new-overlay">
  <div class="modal" style="max-width:460px">

    <!-- Step 1: form -->
    <div id="new-step1">
      <h3>Nuovo mockup</h3>
      <div class="form-row" style="margin-top:16px">
        <label>Nome cliente *</label>
        <input type="text" id="new-name" placeholder="es. Trattoria Mario">
      </div>
      <div class="form-row">
        <label>Sito web da ristrutturare *</label>
        <input type="url" id="new-url" placeholder="https://www.esempio.it">
      </div>
      <div class="form-row">
        <label>Categoria</label>
        <select id="new-category">
          <option value="default">— Seleziona —</option>
          <option value="parrucchiere">Parrucchiere / Salone</option>
          <option value="ristorante">Ristorante / Bar / Pizzeria</option>
          <option value="default">Altra attivita'</option>
        </select>
      </div>
      <div class="form-row">
        <label>Slug URL (lascia vuoto = generato dal nome)</label>
        <input type="text" id="new-slug" placeholder="trattoria-mario" pattern="[a-z0-9-]*">
      </div>
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" onclick="closeNew()">Annulla</button>
        <button type="button" class="btn btn-primary" onclick="analyzeNewSite()">Analizza sito</button>
      </div>
    </div>

    <!-- Step 2: risultati analisi -->
    <div id="new-step2" style="display:none">
      <h3>Analisi completata</h3>
      <div id="analysis-result" style="margin:16px 0;font-size:.88rem;color:#5C4E42;line-height:1.8"></div>
      <form method="post" action="/action" id="new-form-claude" onsubmit="showLoader('Generazione in corso con Claude...')">
        <input type="hidden" name="action"    value="add">
        <input type="hidden" name="mode"      value="claude">
        <input type="hidden" name="name"      id="hid-name">
        <input type="hidden" name="url"       id="hid-url">
        <input type="hidden" name="category"  id="hid-category">
        <input type="hidden" name="slug"      id="hid-slug">
      </form>
      <form method="post" action="/action" id="new-form-template" onsubmit="showLoader('Generazione in corso con template...')">
        <input type="hidden" name="action"    value="add">
        <input type="hidden" name="mode"      value="template">
        <input type="hidden" name="name"      id="hid-name-t">
        <input type="hidden" name="url"       id="hid-url-t">
        <input type="hidden" name="category"  id="hid-category-t">
        <input type="hidden" name="slug"      id="hid-slug-t">
      </form>
      <form method="post" action="/action" id="new-form-manual" onsubmit="showLoader('Scarico immagini e preparo cartella...')">
        <input type="hidden" name="action"    value="add">
        <input type="hidden" name="mode"      value="manual">
        <input type="hidden" name="name"      id="hid-name-m">
        <input type="hidden" name="url"       id="hid-url-m">
        <input type="hidden" name="category"  id="hid-category-m">
        <input type="hidden" name="slug"      id="hid-slug-m">
      </form>
      <div class="modal-actions" style="flex-wrap:wrap;gap:8px;margin-top:16px">
        <button type="button" class="btn btn-ghost" onclick="backToStep1()">Indietro</button>
        <button type="button" class="btn btn-ghost btn-sm" id="btn-manual" onclick="submitManual()" style="border-color:#5C4E42;color:#5C4E42">Manuale (solo immagini)</button>
        <button type="button" class="btn btn-ghost btn-sm" id="btn-template" onclick="submitTemplate()">Template (gratuito)</button>
        <button type="button" class="btn btn-primary" id="btn-claude" onclick="submitClaude()">Genera con Claude</button>
      </div>
    </div>

  </div>
</div>

<!-- Claude Code command modal -->
<div class="overlay" id="cmd-overlay">
  <div class="modal" style="max-width:580px">
    <h3>Comando Claude Code</h3>
    <p style="font-size:.85rem;color:#5C4E42;margin:12px 0 8px">
      Apri il terminale in VS Code nella cartella del progetto e incolla questo comando:
    </p>
    <div style="background:#1C1814;border-radius:6px;padding:16px;margin-bottom:12px;position:relative">
      <pre id="cmd-text" style="color:#FAF7F2;font-size:.78rem;white-space:pre-wrap;word-break:break-all;font-family:monospace;margin:0"></pre>
      <button onclick="copyCmd()" style="position:absolute;top:10px;right:10px;background:#B8935A;color:#fff;border:none;border-radius:4px;padding:4px 10px;font-size:.75rem;cursor:pointer">Copia</button>
    </div>
    <p style="font-size:.78rem;color:#8A7B70;margin-bottom:16px">
      Claude Code analizzera' il sito, creera' il mockup in <code>clienti/&lt;slug&gt;/index.html</code>
      e aggiornera' la dashboard automaticamente al termine.
    </p>
    <div class="modal-actions">
      <button type="button" class="btn btn-ghost" onclick="document.getElementById('cmd-overlay').classList.remove('open')">Chiudi</button>
    </div>
  </div>
</div>

<!-- Delete confirm modal -->
<div class="overlay" id="delete-overlay">
  <div class="modal" style="max-width:380px">
    <h3 style="color:#9b2335">Elimina mockup</h3>
    <p style="font-size:.9rem;color:#5C4E42;margin:16px 0">Stai per eliminare <strong id="delete-name"></strong>.<br/>Verranno cancellati la cartella locale e il sito su surge (se attivo).<br/><br/>L'operazione <strong>non e' reversibile</strong>.</p>
    <form method="post" action="/action" onsubmit="showLoader('Eliminazione in corso...')">
      <input type="hidden" name="action" value="delete">
      <input type="hidden" name="slug" id="delete-slug" value="">
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" onclick="closeDelete()">Annulla</button>
        <button type="submit" class="btn btn-danger">Elimina definitivamente</button>
      </div>
    </form>
  </div>
</div>

<!-- Loader -->
<div class="loader-overlay" id="loader">
  <div class="spinner"></div>
  <span id="loader-msg">Operazione in corso...</span>
</div>

<script>
function openPw(slug){ document.getElementById('pw-slug').value=slug; document.getElementById('pw-overlay').classList.add('open'); document.getElementById('pw-input').focus(); }
function closePw(){ document.getElementById('pw-overlay').classList.remove('open'); }
function openNew(){
  document.getElementById('new-step1').style.display='';
  document.getElementById('new-step2').style.display='none';
  document.getElementById('new-overlay').classList.add('open');
}
function closeNew(){ document.getElementById('new-overlay').classList.remove('open'); }
function backToStep1(){
  document.getElementById('new-step1').style.display='';
  document.getElementById('new-step2').style.display='none';
}
function analyzeNewSite(){
  const name=document.getElementById('new-name').value.trim();
  const url =document.getElementById('new-url').value.trim();
  if(!name||!url){ alert('Inserisci nome e URL del sito.'); return; }
  showLoader('Analisi del sito in corso...');
  fetch('/analyze',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name,url,
      category: document.getElementById('new-category').value,
      slug:     document.getElementById('new-slug').value.trim()
    })
  }).then(r=>r.json()).then(d=>{
    document.getElementById('loader').classList.remove('active');
    if(d.error){alert('Errore: '+d.error);return;}

    const lvlColor = d.level==='semplice'?'#1a6632': d.level==='medio'?'#856404':'#9b2335';
    const lvlLabel = d.level==='semplice'?'Semplice — generazione veloce':
                     d.level==='medio'   ?'Medio — buona qualita\' attesa':
                                          'Complesso — potrebbe richiedere piu\' continuazioni';
    document.getElementById('analysis-result').innerHTML =
      '<table style="width:100%;border-collapse:collapse">'+
      '<tr><td style="padding:5px 0;color:#8A7B70">Sito</td><td><strong>'+d.url+'</strong></td></tr>'+
      '<tr><td style="padding:5px 0;color:#8A7B70">Sezioni trovate</td><td><strong>'+d.sections+'</strong></td></tr>'+
      '<tr><td style="padding:5px 0;color:#8A7B70">Immagini trovate</td><td><strong>'+d.images+'</strong></td></tr>'+
      (d.city?'<tr><td style="padding:5px 0;color:#8A7B70">Citta\'</td><td><strong>'+d.city+'</strong></td></tr>':'')+
      '<tr><td style="padding:5px 0;color:#8A7B70">Complessita\'</td><td><strong style="color:'+lvlColor+'">'+lvlLabel+'</strong></td></tr>'+
      '<tr><td style="padding:5px 0;color:#8A7B70">Costo stimato</td><td><strong style="color:#B8935A">$'+d.cost_min+' – $'+d.cost_max+'</strong></td></tr>'+
      '</table>';

    document.getElementById('btn-claude').textContent = 'Genera con Claude (~$'+d.cost_max+')';

    // Popola i campi hidden di tutti e tre i form
    ['' ,'-t', '-m'].forEach(id=>{
      document.getElementById('hid-name'+id).value     = name;
      document.getElementById('hid-url'+id).value      = url;
      document.getElementById('hid-category'+id).value = document.getElementById('new-category').value;
      document.getElementById('hid-slug'+id).value     = document.getElementById('new-slug').value.trim();
    });

    document.getElementById('new-step1').style.display='none';
    document.getElementById('new-step2').style.display='';
  }).catch(e=>{
    document.getElementById('loader').classList.remove('active');
    alert('Errore analisi: '+e);
  });
}
function submitClaude()  { document.getElementById('new-form-claude').submit(); }
function submitTemplate(){ document.getElementById('new-form-template').submit(); }
function submitManual()  { document.getElementById('new-form-manual').submit(); }
function openDelete(slug,name){ document.getElementById('delete-slug').value=slug; document.getElementById('delete-name').textContent=name; document.getElementById('delete-overlay').classList.add('open'); }
function closeDelete(){ document.getElementById('delete-overlay').classList.remove('open'); }
function showClaudeCmd(slug, url, name, category){
  const cmd = 'claude "Sei un web designer senior. Analizza completamente il sito ' + url +
    ' — struttura, design, colori, font, sezioni, testi, servizi, prezzi, orari, contatti, FAQ, tutto.' +
    ' Poi crea un file HTML moderno e professionale in clienti/' + slug + '/index.html' +
    ' che sia un restyling del sito originale: stesse sezioni con gli stessi nomi, stessi contenuti,' +
    ' tutti i testi originali, ma con design moderno responsive e professionale.' +
    ' Le immagini ottimizzate sono gia in clienti/' + slug + '/img/ (usale tutte).' +
    ' Requisiti tecnici: smooth scroll, popup modal con telefono al click su Prenota/Chiama,' +
    ' meta robots noindex, Schema.org JSON-LD, responsive mobile-first.' +
    ' Categoria attivita: ' + category + '."';
  document.getElementById('cmd-text').textContent = cmd;
  document.getElementById('cmd-overlay').classList.add('open');
}
function copyCmd(){
  navigator.clipboard.writeText(document.getElementById('cmd-text').textContent);
  event.target.textContent='Copiato!';
  setTimeout(()=>event.target.textContent='Copia', 2000);
}
function showLoader(msg){ document.getElementById('loader-msg').textContent=msg||'Operazione in corso...'; document.getElementById('loader').classList.add('active'); }
document.querySelectorAll('.overlay').forEach(o=>o.addEventListener('click',e=>{ if(e.target===o) o.classList.remove('open'); }));
{% if msg %}setTimeout(()=>{ const t=document.querySelector('.toast'); if(t) t.style.display='none'; }, 4000);{% endif %}

// Polling per le card in stato "generating"
const generating = {{ generating_slugs | tojson }};
if (generating.length > 0) {
  function pollStatus() {
    generating.forEach(slug => {
      fetch('/status/' + slug)
        .then(r => r.json())
        .then(data => {
          const el = document.getElementById('step-' + slug);
          if (el) el.textContent = data.step || '';
          if (data.done) location.reload();
        }).catch(() => {});
    });
  }
  setInterval(pollStatus, 1500);
}
</script>
</body>
</html>"""

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    sites = load_reg()
    msg   = request.args.get("msg", "")
    ok    = request.args.get("ok", "0") == "1"
    generating_slugs = [s for s, d in sites.items() if d.get("status") == "generating"]
    return render_template_string(TEMPLATE, sites=sites, msg=msg, ok=ok,
                                  generating_slugs=generating_slugs)


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    url  = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL mancante"})
    try:
        from generator import estimate_complexity
        result = estimate_complexity(url)
        if "error" in result:
            return jsonify({"error": result["error"]})
        return jsonify({
            "url":      url,
            "sections": result["sections"],
            "images":   result["images"],
            "city":     result["city"],
            "level":    result["level"],
            "cost_min": result["cost_min"],
            "cost_max": result["cost_max"],
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/status/<slug>")
def status(slug):
    reg = load_reg()
    job = JOBS.get(slug, {})
    return jsonify({
        "step":   job.get("step", reg.get(slug, {}).get("step", "In corso...")),
        "done":   job.get("done", False),
        "error":  job.get("error", False),
    })


@app.route("/action", methods=["POST"])
def action():
    action = request.form.get("action")
    slug   = request.form.get("slug", "").strip()
    reg    = load_reg()

    def redir(msg, ok=True):
        return redirect(url_for("index", msg=msg, ok="1" if ok else "0"))

    if action == "deploy":
        if slug not in reg:
            return redir("Slug non trovato.", ok=False)
        domain = reg[slug]["domain"]
        ok, _ = surge_deploy(slug, domain)
        if ok:
            reg[slug]["status"] = "protected" if reg[slug].get("protected") else "live"
            reg[slug]["deployed_at"] = datetime.date.today().isoformat()
            save_reg(reg)
            return redir(f"{reg[slug]['name']} e' ora online.")
        return redir("Deploy fallito. Controlla che surge sia autenticato.", ok=False)

    elif action == "teardown":
        if slug not in reg:
            return redir("Slug non trovato.", ok=False)
        domain = reg[slug]["domain"]
        ok, _ = surge_teardown(domain)
        if ok:
            reg[slug]["status"] = "teardown"
            save_reg(reg)
            return redir(f"{reg[slug]['name']} rimosso da internet.")
        return redir("Teardown fallito.", ok=False)

    elif action == "protect":
        password = request.form.get("password", "").strip()
        if not password:
            return redir("Inserisci una password.", ok=False)
        if slug not in reg:
            return redir("Slug non trovato.", ok=False)
        inject_pw(slug, password)
        domain = reg[slug]["domain"]
        ok, _ = surge_deploy(slug, domain)
        if ok:
            reg[slug]["status"] = "protected"
            reg[slug]["protected"] = True
            save_reg(reg)
            return redir(f"Password aggiunta a {reg[slug]['name']}.")
        remove_pw(slug)
        return redir("Deploy fallito. Password gate rimosso.", ok=False)

    elif action == "unprotect":
        if slug not in reg:
            return redir("Slug non trovato.", ok=False)
        remove_pw(slug)
        domain = reg[slug]["domain"]
        ok, _ = surge_deploy(slug, domain)
        if ok:
            reg[slug]["status"] = "live"
            reg[slug]["protected"] = False
            save_reg(reg)
            return redir(f"Password rimossa da {reg[slug]['name']}.")
        return redir("Deploy fallito.", ok=False)

    elif action == "add":
        name     = request.form.get("name", "").strip()
        url      = request.form.get("url", "").strip()
        category = request.form.get("category", "default").strip()
        mode     = request.form.get("mode", "claude").strip()   # claude | template | manual
        new_slug = request.form.get("slug", "").strip()

        if not name or not url:
            return redir("Nome e URL del sito sono obbligatori.", ok=False)
        if not new_slug:
            new_slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:40]
        if new_slug in reg:
            return redir(f"'{new_slug}' esiste gia'. Scegli uno slug diverso.", ok=False)

        domain = f"restyling-{new_slug}.surge.sh"

        if mode == "manual":
            # Crea cartella + scarica immagini + registra come "manual"
            from generator import scrape_full, download_images
            client_folder = os.path.join(MOCKUPS, new_slug)
            img_folder    = os.path.join(client_folder, "img")
            os.makedirs(img_folder, exist_ok=True)
            _, manifest, image_urls = scrape_full(url)
            imgs = download_images(image_urls, img_folder)
            img_names = ", ".join(i["file"] for i in imgs)
            # Placeholder minimo (verrà sovrascritto da Claude Code)
            with open(os.path.join(client_folder, "index.html"), "w", encoding="utf-8") as f:
                f.write(f"<!DOCTYPE html><html><head><meta charset='UTF-8'/><title>{name}</title></head>"
                        f"<body><p>In attesa di Claude Code...</p></body></html>")
            with open(os.path.join(client_folder, "robots.txt"), "w", encoding="utf-8") as f:
                f.write("User-agent: *\nDisallow: /\n")
            reg[new_slug] = {
                "name": name, "domain": domain,
                "deployed_at": datetime.date.today().isoformat(),
                "status": "manual", "protected": False,
                "source_url": url, "category": category,
                "images_downloaded": len(imgs),
            }
            save_reg(reg)
            return redir(f"'{name}': cartella pronta, {len(imgs)} immagini scaricate. Ora esegui Claude Code nel terminale.")

        # Mode: claude o template — genera in background
        reg[new_slug] = {
            "name": name, "domain": domain,
            "deployed_at": datetime.date.today().isoformat(),
            "status": "generating", "step": "Avvio...",
            "protected": False, "source_url": url, "category": category,
        }
        save_reg(reg)
        JOBS[new_slug] = {"step": "Avvio...", "done": False, "error": False}

        def run(slug=new_slug, sname=name, surl=url, scat=category, sdom=domain, smode=mode):
            if smode == "template":
                from generator import scrape_full, download_images, _gen_template_html
                gen_fn = lambda: _gen_template_html(slug, sname, surl, scat)
            else:
                from generator import run_pipeline
                gen_fn = None

            def on_step(msg):
                JOBS[slug]["step"] = msg
                r = load_reg()
                if slug in r:
                    r[slug]["step"] = msg
                    save_reg(r)

            if gen_fn:
                try:
                    gen_fn()
                    ok, err, cost = True, "", 0.0
                except Exception as e:
                    ok, err, cost = False, str(e), 0.0
            else:
                ok, err, cost = run_pipeline(slug, sname, surl, scat, sdom, on_step=on_step)

            r = load_reg()
            if slug in r:
                r[slug]["status"]   = "teardown" if ok else "error"
                r[slug]["step"]     = "Completato" if ok else err
                if ok and cost:
                    r[slug]["cost_usd"] = round(cost, 4)
                save_reg(r)
            JOBS[slug] = {"step": "Completato" if ok else err, "done": True, "error": not ok}

        threading.Thread(target=run, daemon=True).start()
        mode_label = "Claude API" if mode == "claude" else "template locale"
        return redir(f"Generazione '{name}' avviata ({mode_label}) — segui il progresso nella card.")

    elif action == "delete":
        if slug not in reg:
            return redir("Slug non trovato.", ok=False)
        name = reg[slug].get("name", slug)
        domain = reg[slug].get("domain", "")

        # Teardown da surge se attivo
        if reg[slug].get("status") in ("live", "protected"):
            surge_teardown(domain)

        # Elimina cartella locale
        client_folder = os.path.join(MOCKUPS, slug)
        if os.path.isdir(client_folder):
            shutil.rmtree(client_folder)

        # Rimuovi dal registry
        del reg[slug]
        save_reg(reg)
        return redir(f"'{name}' eliminato definitivamente.")

    return redir("Azione non riconosciuta.", ok=False)


@app.route("/preview/<slug>/")
@app.route("/preview/<slug>")
def preview_index(slug):
    folder = os.path.join(MOCKUPS, slug)
    if not os.path.isdir(folder):
        return f"Mockup '{slug}' non trovato.", 404
    return send_from_directory(folder, "index.html")


@app.route("/preview/<slug>/<path:filename>")
def preview_file(slug, filename):
    folder = os.path.join(MOCKUPS, slug)
    if not os.path.isdir(folder):
        return f"Mockup '{slug}' non trovato.", 404
    return send_from_directory(folder, filename)


# ── Start ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    def open_browser():
        import time; time.sleep(1)
        webbrowser.open("http://localhost:5000")
    threading.Thread(target=open_browser, daemon=True).start()
    print("\n  Dashboard avviata su http://localhost:5000")
    print("  Premi Ctrl+C per fermare.\n")
    app.run(debug=False, port=5000)
