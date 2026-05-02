/**
 * OmniWatch Dashboard — WebSocket client + live UI controller
 * Connects to FastAPI backend, renders real-time analysis results.
 */

const API_BASE = window.OMNIWATCH_API || 'http://localhost:8000';
const WS_BASE  = API_BASE.replace('http', 'ws');

class OmniWatchDashboard {
  constructor() {
    this.ws = null;
    this.map = null;
    this.waveformCtx = null;
    this.waveformAnim = null;
    this.currentIncident = null;
    this.hospitals = [];
    this.incidentHistory = [];
    this.particleCanvas = null;
    this.particles = [];

    this._initCursor();
    this._initParticles();
    this._initClock();
    this._initWaveform();
    this._initMap();
    this._connectWebSocket();
    this._initUpload();
    this._loadInitialData();
  }

  // ── Cursor ──────────────────────────────────────────────────
  _initCursor() {
    const cursor = document.getElementById('cursor');
    const trail = document.getElementById('cursor-trail');
    if (!cursor || !trail) return;
    let mx = 0, my = 0, tx = 0, ty = 0;
    document.addEventListener('mousemove', e => {
      mx = e.clientX; my = e.clientY;
      cursor.style.left = mx - 5 + 'px';
      cursor.style.top  = my - 5 + 'px';
    });
    const animTrail = () => {
      tx += (mx - tx) * 0.12;
      ty += (my - ty) * 0.12;
      trail.style.left = tx - 19 + 'px';
      trail.style.top  = ty - 19 + 'px';
      requestAnimationFrame(animTrail);
    };
    animTrail();
    document.querySelectorAll('.glass, .hospital-item, button').forEach(el => {
      el.addEventListener('mouseenter', () => cursor.style.transform = 'scale(3)');
      el.addEventListener('mouseleave', () => cursor.style.transform = 'scale(1)');
    });
  }

  // ── Particle background ─────────────────────────────────────
  _initParticles() {
    const canvas = document.getElementById('particle-canvas');
    if (!canvas) return;
    this.particleCanvas = canvas;
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    window.addEventListener('resize', () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    });

    const N = 80;
    const colors = ['#00FF87', '#1E3AFF', '#E8341A', '#F5C842'];
    for (let i = 0; i < N; i++) {
      this.particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        r: Math.random() * 1.4 + 0.4,
        c: colors[Math.floor(Math.random() * colors.length)],
        o: Math.random() * 0.45 + 0.05,
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      this.particles.forEach(p => {
        p.x = (p.x + p.vx + canvas.width) % canvas.width;
        p.y = (p.y + p.vy + canvas.height) % canvas.height;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = p.c + Math.floor(p.o * 255).toString(16).padStart(2, '0');
        ctx.fill();
      });
      // Connection lines
      for (let i = 0; i < this.particles.length; i++) {
        for (let j = i + 1; j < this.particles.length; j++) {
          const dx = this.particles[i].x - this.particles[j].x;
          const dy = this.particles[i].y - this.particles[j].y;
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d < 90) {
            ctx.beginPath();
            ctx.moveTo(this.particles[i].x, this.particles[i].y);
            ctx.lineTo(this.particles[j].x, this.particles[j].y);
            ctx.strokeStyle = `rgba(255,255,255,${0.025 * (1 - d / 90)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }
      requestAnimationFrame(draw);
    };
    draw();
  }

  // ── Clock ───────────────────────────────────────────────────
  _initClock() {
    const el = document.getElementById('nav-time');
    const update = () => {
      if (el) el.textContent = new Date().toLocaleTimeString('en-US', {
        hour12: false, timeZoneName: 'short'
      });
    };
    update();
    setInterval(update, 1000);
  }

  // ── Waveform ────────────────────────────────────────────────
  _initWaveform() {
    const canvas = document.getElementById('waveform-canvas');
    if (!canvas) return;
    this.waveformCtx = canvas.getContext('2d');
    canvas.width = canvas.offsetWidth * window.devicePixelRatio;
    canvas.height = canvas.offsetHeight * window.devicePixelRatio;
    this.waveformCtx.scale(window.devicePixelRatio, window.devicePixelRatio);
    this._animateWaveform(false);
  }

  _animateWaveform(isAlert = false) {
    if (this.waveformAnim) cancelAnimationFrame(this.waveformAnim);
    const canvas = document.getElementById('waveform-canvas');
    if (!canvas || !this.waveformCtx) return;
    const ctx = this.waveformCtx;
    const w = canvas.offsetWidth;
    const h = canvas.offsetHeight;
    const barCount = 80;
    const barW = w / barCount - 1;
    let frame = 0;

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      for (let i = 0; i < barCount; i++) {
        const noise = Math.sin(frame * 0.05 + i * 0.3) * 0.5
                    + Math.sin(frame * 0.08 + i * 0.15) * 0.3
                    + Math.random() * 0.2;
        let barH = (noise + 1) / 2;
        if (isAlert) barH = Math.min(1, barH * 2.5 + Math.random() * 0.4);
        barH = Math.max(0.05, barH) * (h * 0.85);

        const color = isAlert ? '#E8341A' : '#00FF87';
        ctx.fillStyle = color + 'BB';
        ctx.fillRect(
          i * (barW + 1), (h - barH) / 2,
          barW, barH
        );
      }
      frame++;
      this.waveformAnim = requestAnimationFrame(draw);
    };
    draw();
  }

  // ── Map ─────────────────────────────────────────────────────
  _initMap() {
    if (typeof OmniWatchMap !== 'undefined') {
      this.map = new OmniWatchMap('map');
    } else if (typeof L !== 'undefined') {
      // Minimal Leaflet init if map.js not loaded
      this.map = {
        setIncident: () => {},
        renderHospitals: () => {},
        drawRoutes: () => {},
        fitBounds: () => {},
        startETACountdown: () => {},
      };
    }
  }

  // ── WebSocket ───────────────────────────────────────────────
  _connectWebSocket() {
    const connect = () => {
      this.ws = new WebSocket(`${WS_BASE}/ws/alerts`);

      this.ws.onopen = () => {
        console.log('[OmniWatch] WebSocket connected');
        this._setStatus('CONNECTED', true);
      };

      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        this._handleWSMessage(msg);
      };

      this.ws.onclose = () => {
        this._setStatus('RECONNECTING...', false);
        setTimeout(connect, 3000);
      };

      this.ws.onerror = (err) => {
        console.warn('[OmniWatch] WS error:', err);
      };

      // Keep-alive pings
      setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 25000);
    };
    connect();
  }

  _handleWSMessage(msg) {
    switch (msg.type) {
      case 'connected':
        this._loadHospitals(msg.hospitals);
        if (msg.active_incidents?.length) {
          msg.active_incidents.forEach(i => this._addToFeed(i));
        }
        break;

      case 'analysis_result':
        this._onAnalysisResult(msg);
        break;

      case 'job_started':
        this._onJobStarted(msg);
        break;

      case 'job_complete':
        this._onJobComplete(msg);
        break;

      case 'incident_resolved':
        this._onIncidentResolved(msg.incident_id);
        break;
    }
  }

  _onAnalysisResult(msg) {
    const { fusion, routing, frame } = msg;
    if (!fusion) return;

    // Update live metrics
    this._updateMetrics(fusion);

    // Update live camera frame if provided
    if (frame) {
      const img = document.getElementById('main-cam-img');
      if (img) img.src = `data:image/jpeg;base64,${frame}`;
      this._setCamAlert(fusion.priority !== 'CLEAR');
    }

    // Update waveform alert state
    this._animateWaveform(fusion.priority === 'CRITICAL' || fusion.priority === 'HIGH');

    // If significant event, trigger full UI update
    if (fusion.priority !== 'CLEAR' && fusion.c_fused > 0.25) {
      this.currentIncident = { fusion, routing };
      this._showIncidentAlert(fusion, routing);

      // Update latest alert
      this._setEl('alert-body', fusion.description);

      // Update Gemini output
      this._setEl('gemini-out', `Analysis complete: ${fusion.event_type.replace(/_/g, ' ')} detected with ${(fusion.c_fused * 100).toFixed(1)}% confidence. Audio keywords: ${fusion.audio_keywords?.join(', ') || 'none'}.`);

      if (routing) {
        this._updateRouting(routing);
        this._updateMap(fusion, routing);
      }

      this._addToFeed(fusion, msg.incident_id);
    }
  }

  _onJobStarted(msg) {
    const zone = document.getElementById('upload-status');
    if (zone) {
      zone.innerHTML = `
        <div class="badge badge-HIGH">PROCESSING</div>
        <p style="margin-top:10px;font-size:10px;letter-spacing:2px;color:var(--dim)">
          Analyzing ${msg.total_frames} frames · Job ${msg.job_id}
        </p>
        <div class="progress-bar"><div class="progress-fill" id="job-progress"></div></div>
      `;
    }
  }

  _onJobComplete(msg) {
    const zone = document.getElementById('upload-status');
    if (zone) {
      zone.innerHTML = `
        <div class="badge badge-LOW" style="border-color:var(--green);color:var(--green)">COMPLETE</div>
        <p style="margin-top:10px;font-size:10px;letter-spacing:2px;color:var(--dim)">
          ${msg.frames_processed} frames analyzed · Results above
        </p>
      `;
    }
  }

  _onIncidentResolved(incidentId) {
    const el = document.getElementById(`feed-item-${incidentId}`);
    if (el) el.style.opacity = '0.4';
  }

  // ── UI Updates ──────────────────────────────────────────────
  _updateMetrics(fusion) {
    this._setEl('metric-vision', `${(fusion.c_vision * 100).toFixed(0)}%`);
    this._setEl('metric-audio', `${(fusion.c_audio * 100).toFixed(0)}%`);
    this._setEl('metric-fused', `${(fusion.c_fused * 100).toFixed(0)}%`);
    this._setEl('metric-persons', 1);

    // Confidence fill bar
    const fill = document.getElementById('conf-fill');
    if (fill) fill.style.width = `${fusion.c_fused * 100}%`;

    // Priority badge
    const badge = document.getElementById('priority-badge');
    if (badge) {
      badge.className = `badge badge-${fusion.priority}`;
      badge.textContent = fusion.priority;
    }

    // Flow energy
    this._setEl('flow-energy', fusion.flow_energy?.toFixed(0) || '0');

    // Align bottom section with loader
    const bottom = document.querySelector('.cam-hud-bottom');
    if (bottom) bottom.style.transform = `translateY(${ (1 - fusion.c_fused) * 20 }px)`;
  }

  _showIncidentAlert(fusion, routing) {
    const panel = document.getElementById('incident-panel');
    if (!panel) return;

    const optimal = routing?.optimal;
    panel.className = `glass incident-panel priority-${fusion.priority.toLowerCase()}`;
    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <span class="badge badge-${fusion.priority}">⚠ ${fusion.priority}</span>
        <span style="font-size:9px;letter-spacing:2px;color:var(--dim)" id="incident-elapsed">JUST NOW</span>
      </div>
      <p style="font-size:11px;line-height:1.7;color:rgba(240,237,228,0.8);margin-bottom:16px">
        ${fusion.description.replace(/\[.*?\]/g, '')}
      </p>
      ${fusion.audio_transcript ? `
        <div class="equation" style="border-left-color:var(--yellow)">
          🎧 "${fusion.audio_transcript.slice(0, 100)}"
        </div>
      ` : ''}
      <div style="margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;font-size:9px;letter-spacing:2px;color:var(--dim);margin-bottom:6px">
          <span>C_fused confidence</span>
          <span style="color:var(--green)">${fusion.c_fused.toFixed(3)}</span>
        </div>
        <div class="conf-track"><div class="conf-fill" style="width:${fusion.c_fused*100}%"></div></div>
      </div>
      ${fusion.audio_keywords?.length ? `
        <div style="margin-top:12px">
          ${fusion.audio_keywords.map(k => `<span style="background:rgba(245,200,66,0.15);border:1px solid var(--yellow);color:var(--yellow);font-size:8px;letter-spacing:2px;padding:2px 7px;border-radius:3px;margin-right:6px">${k}</span>`).join('')}
        </div>
      ` : ''}
      ${optimal ? `
        <div style="margin-top:20px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.08)">
          <div style="font-size:9px;letter-spacing:3px;color:var(--dim);margin-bottom:8px">OPTIMAL ROUTE</div>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <div style="font-size:12px;font-weight:bold">${optimal.name}</div>
              <div style="font-size:9px;color:var(--dim);margin-top:2px">${optimal.address || ''}</div>
            </div>
            <div style="text-align:right">
              <div style="font-family:Impact,sans-serif;font-size:24px;color:var(--green)" id="eta-display">${optimal.eta_minutes.toFixed(1)} MIN</div>
              <div style="font-size:8px;color:var(--dim)">${optimal.distance_mi || (optimal.distance_km * 0.621).toFixed(1)} mi</div>
            </div>
          </div>
        </div>
      ` : ''}
      <button onclick="dashboard.resolveIncident()" style="
        margin-top:16px; padding:10px 20px; border:1px solid rgba(255,255,255,0.15);
        background:rgba(255,255,255,0.05); color:var(--cream); font-family:var(--font-mono);
        font-size:9px; letter-spacing:3px; text-transform:uppercase; border-radius:6px;
        cursor:none; width:100%; transition:all 0.2s;
      " onmouseover="this.style.background='rgba(255,255,255,0.1)'"
         onmouseout="this.style.background='rgba(255,255,255,0.05)'">
        MARK RESOLVED
      </button>
    `;

    panel.style.animation = 'none';
    panel.offsetHeight;
    panel.style.animation = 'slideIn 0.4s ease';

    // Elapsed time counter
    const startTime = Date.now();
    const elapsed = setInterval(() => {
      const el = document.getElementById('incident-elapsed');
      if (!el) { clearInterval(elapsed); return; }
      const s = Math.floor((Date.now() - startTime) / 1000);
      el.textContent = s < 60 ? `${s}s AGO` : `${Math.floor(s/60)}m ${s%60}s AGO`;
    }, 1000);
  }

  _updateRouting(routing) {
    const container = document.getElementById('hospital-list');
    if (!container) return;
    container.innerHTML = routing.all_facilities.slice(0, 4).map((h, i) => `
      <div class="hospital-item ${i === 0 ? 'optimal' : ''}" onclick="dashboard.focusHospital(${h.lat}, ${h.lon})">
        <div class="h-rank">${i + 1}</div>
        <div style="flex:1">
          <div class="h-name">${h.name}</div>
          <div class="h-addr">${h.address || ''}</div>
          <span class="trauma-badge t${h.trauma_level}">TRAUMA ${['I', 'II', 'III'][h.trauma_level - 1]}</span>
        </div>
        <div style="text-align:right">
          <div class="h-eta">${h.eta_minutes.toFixed(0)} MIN</div>
          <div class="h-dist">${(h.distance_km * 0.621).toFixed(1)} mi</div>
        </div>
      </div>
    `).join('');
  }

  _updateMap(fusion, routing) {
    if (!this.map || !routing) return;
    const lat = routing.incident_lat || 37.7749;
    const lon = routing.incident_lon || -122.4194;

    this.map.setIncident(lat, lon, fusion.priority);
    this.map.renderHospitals(routing.all_facilities || []);
    this.map.drawRoutes(lat, lon, routing.all_facilities || []);

    if (routing.optimal) {
      this.map.fitBounds(lat, lon, routing.optimal.lat, routing.optimal.lon);
      this.map.startETACountdown(routing.optimal.eta_minutes, () => {
        document.getElementById('eta-display')?.textContent === '0:00'
          && (document.getElementById('eta-display').textContent = 'ARRIVED');
      });
    }
  }

  _addToFeed(fusion, incidentId) {
    const feed = document.getElementById('incident-feed');
    if (!feed) return;
    const ts = new Date().toLocaleTimeString('en-US', { hour12: false });
    const item = document.createElement('div');
    item.className = `feed-item ${fusion.priority}`;
    item.id = `feed-item-${incidentId || Date.now()}`;
    item.innerHTML = `
      <div class="feed-time">${ts}</div>
      <div style="flex:1">
        <div class="feed-title">
          <span class="badge badge-${fusion.priority}" style="font-size:7px;padding:2px 7px">${fusion.priority}</span>
          &nbsp; ${(fusion.event_type || 'event').replace(/_/g, ' ').toUpperCase()}
        </div>
        <div class="feed-desc">${fusion.camera_id} · C_fused=${fusion.c_fused?.toFixed(3)}</div>
      </div>
    `;
    feed.prepend(item);
    // Keep feed at max 20 items
    while (feed.children.length > 20) feed.lastChild.remove();
  }

  _loadHospitals(hospitals) {
    if (!hospitals?.length) return;
    this.hospitals = hospitals;
    if (this.map?.renderHospitals) {
      this.map.renderHospitals(hospitals);
    }
  }

  _setCamAlert(isAlert) {
    const cam = document.getElementById('main-cam');
    if (cam) {
      cam.classList.toggle('alert', isAlert);
    }
    const rec = document.querySelector('#main-cam .cam-rec');
    if (rec) {
      rec.className = `cam-rec ${isAlert ? '' : 'clear'}`;
      rec.innerHTML = `<div class="dot"></div>${isAlert ? 'LIVE' : 'CLEAR'}`;
    }
  }

  // ── Upload ──────────────────────────────────────────────────
  _initUpload() {
    const zone = document.getElementById('upload-zone');
    const input = document.getElementById('video-input');
    if (!zone || !input) return;

    zone.addEventListener('dragover', e => {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) this._uploadVideo(file);
    });
    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
      if (input.files[0]) this._uploadVideo(input.files[0]);
    });
  }

  async _uploadVideo(file) {
    const statusEl = document.getElementById('upload-status');
    if (statusEl) {
      statusEl.innerHTML = `
        <div class="badge badge-MEDIUM">UPLOADING...</div>
        <p style="margin-top:10px;font-size:10px;letter-spacing:2px;color:var(--dim)">${file.name}</p>
        <div class="progress-bar"><div class="progress-fill" id="upload-progress"></div></div>
      `;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('camera_id', 'uploaded-video');

    try {
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = e => {
        const pct = (e.loaded / e.total * 100).toFixed(0);
        const bar = document.getElementById('upload-progress');
        if (bar) bar.style.width = pct + '%';
      };
      xhr.open('POST', `${API_BASE}/api/process-video`);
      xhr.onload = () => {
        const resp = JSON.parse(xhr.responseText);
        if (statusEl) {
          statusEl.innerHTML = `
            <div class="badge badge-HIGH">PROCESSING — JOB ${resp.job_id}</div>
            <p style="margin-top:10px;font-size:10px;letter-spacing:2px;color:var(--dim)">
              Results streaming live via WebSocket
            </p>
          `;
        }
      };
      xhr.send(formData);
    } catch (err) {
      console.error('Upload failed:', err);
      if (statusEl) statusEl.innerHTML = `<div class="badge badge-CRITICAL">UPLOAD FAILED</div>`;
    }
  }

  // ── Initial data load ───────────────────────────────────────
  async _loadInitialData() {
    try {
      const [hospitalsResp, incidentsResp] = await Promise.all([
        fetch(`${API_BASE}/api/hospitals`),
        fetch(`${API_BASE}/api/incidents?limit=10`),
      ]);
      const hospitals = await hospitalsResp.json();
      const incidents = await incidentsResp.json();

      this._loadHospitals(hospitals);
      incidents.forEach(i => this._addToFeed(i, i.id));

      // Load stats
      const statsResp = await fetch(`${API_BASE}/api/stats`);
      const stats = await statsResp.json();
      this._setEl('stat-speedup', `${stats.impact?.speedup_factor?.toFixed(0)}×`);
      this._setEl('stat-survival-gain', `+${stats.impact?.survival_gain_percentage_points}pp`);
    } catch (err) {
      console.warn('[OmniWatch] Backend not reachable — running in demo mode', err);
      this._runDemoMode();
    }
  }

  // ── Demo mode (no backend) ──────────────────────────────────
  _runDemoMode() {
    console.log('[OmniWatch] Demo mode: simulating events');
    const hospitals = [
      { name: 'UCSF Medical Center', lat: 37.7631, lon: -122.4576, trauma_level: 1, address: '505 Parnassus Ave', eta_minutes: 4, distance_km: 1.3, distance_mi: 0.8 },
      { name: "St. Mary's Medical Center", lat: 37.7776, lon: -122.4484, trauma_level: 2, address: '450 Stanyan St', eta_minutes: 6, distance_km: 1.9, distance_mi: 1.2 },
      { name: 'Market St Urgent Care', lat: 37.7765, lon: -122.4172, trauma_level: 3, address: '1144 Market St', eta_minutes: 2, distance_km: 0.6, distance_mi: 0.4 },
    ];
    this._loadHospitals(hospitals);

    const video = document.getElementById('main-video');
    let lastIncidentTime = 0;

    setInterval(() => {
      const t = video.currentTime;
      if (t < lastIncidentTime) {
        this._resetSimulation();
        lastIncidentTime = 0;
      }

      let c_vision = 0.1;
      let c_audio = 0.05;
      let priority = 'CLEAR';
      let flow_energy = 100;
      let step = 0;

      if (t >= 2 && t <= 6) {
        c_vision = 0.3 + Math.sin(t * 2) * 0.2;
        c_audio = 0.4 + Math.sin(t * 1.5) * 0.3;
        step = 1;
      } else if (t >= 7 && t <= 11) {
        c_vision = 0.8;
        c_audio = 0.9 + Math.sin(t * 3) * 0.1;
        priority = 'CRITICAL';
        flow_energy = 4000;
        step = 2;
      } else if (t >= 11) {
        step = 3;
        if (t >= 11 && lastIncidentTime < 11) {
          lastIncidentTime = t;
          const fusion = {
            c_vision: 0.94, c_audio: 0.87, c_fused: 0.916,
            priority: 'CRITICAL', event_type: 'fall',
            description: 'Person motionless — possible fall or medical event. Optical flow spike detected.',
            camera_id: 'CAM-01 LOBBY', audio_transcript: 'Oh my god, are you okay?!',
            audio_keywords: ['help', 'are you okay'],
            flow_energy: 4200, persons_detected: 1,
          };
          const routing = {
            incident_lat: 37.7749, incident_lon: -122.4194,
            optimal: hospitals[0],
            all_facilities: hospitals,
          };
          this._onAnalysisResult({ fusion, routing, frame: null });
        }
      }

      this._updateStateMachine(step);
      const c_fused = 0.65 * c_vision + 0.35 * c_audio;
      this._updateMetrics({
        c_vision, c_audio, c_fused, priority, flow_energy, persons_detected: 1
      });
    }, 100);
  }

  _updateStateMachine(stepIndex) {
    const steps = document.querySelectorAll('#state-bar .state-step');
    steps.forEach((s, i) => {
      s.classList.remove('active', 'done', 'crit');
      if (i < stepIndex) s.classList.add('done');
      else if (i === stepIndex) s.classList.add('active');
    });
    const labels = ['IDLE', 'DETECTING', 'ANALYZING', 'ROUTING'];
    this._setEl('state-label', labels[stepIndex] || 'IDLE');
    this._setEl('state-name', ['Monitoring all feeds', 'Motion detected', 'Processing audio/video', 'Dispatching ambulance'][stepIndex] || 'Monitoring all feeds');
  }

  _resetSimulation() {
    this._updateStateMachine(0);
    this._setEl('alert-body', 'No incidents detected. System monitoring all feeds.');
    this._setEl('gemini-out', 'Awaiting analysis...<span class="gemini-cursor"></span>');
  }

  // ── Helpers ─────────────────────────────────────────────────
  _setEl(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  _setStatus(text, ok) {
    const el = document.getElementById('ws-status');
    if (el) {
      el.textContent = text;
      el.style.color = ok ? 'var(--green)' : 'var(--yellow)';
    }
  }

  focusHospital(lat, lon) {
    this.map?.map?.flyTo([lat, lon], 15, { duration: 1 });
  }

  resolveIncident() {
    const incidentId = this.currentIncident?.id;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'resolve', incident_id: incidentId, notes: 'Resolved by operator' }));
    }
    const panel = document.getElementById('incident-panel');
    if (panel) panel.style.opacity = '0.4';
  }
}

// Init on DOM ready
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
  dashboard = new OmniWatchDashboard();
  window.dashboard = dashboard;
});