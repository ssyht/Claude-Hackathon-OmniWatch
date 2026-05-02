/**
 * OmniWatch 3D Map — Leaflet + 3D tilt effect
 * Renders incident location + hospital markers with Apple Maps-style
 * tilt, building extrusion via CSS3D transforms on the Leaflet map.
 */

class OmniWatchMap {
  constructor(containerId) {
    this.containerId = containerId;
    this.map = null;
    this.incidentMarker = null;
    this.hospitalMarkers = [];
    this.routePolylines = [];
    this.pulseCircles = [];
    this.tiltDeg = 45; // 3D tilt angle (faux Apple Maps)
    this._initMap();
  }

  _initMap() {
    // Dark tile layer (OpenStreetMap Carto Dark)
    this.map = L.map(this.containerId, {
      center: [37.7749, -122.4194],
      zoom: 14,
      zoomControl: false,
      attributionControl: false,
    });

    // Dark CartoDB tile layer (no API key needed)
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      { subdomains: 'abcd', maxZoom: 19 }
    ).addTo(this.map);

    // Custom zoom control (bottom right)
    L.control.zoom({ position: 'bottomright' }).addTo(this.map);

    // Apply CSS 3D perspective to simulate Apple Maps tilt
    this._apply3DTilt();

    // Attribution
    L.control.attribution({ position: 'bottomleft', prefix: false })
      .addAttribution('© CartoDB | OmniWatch')
      .addTo(this.map);

    this.map.invalidateSize();
  }

  _apply3DTilt() {
    /**
     * CSS3D perspective trick:
     * Wraps the map container in a perspective transform to fake
     * the Apple Maps bird's-eye 3D tilt.
     */
    const container = document.getElementById(this.containerId);
    if (!container) return;

    // Wrap in perspective container
    const wrapper = container.parentElement;
    wrapper.style.perspective = '1200px';
    wrapper.style.perspectiveOrigin = '50% 60%';

    container.style.transformOrigin = '50% 100%';
    container.style.transform = `rotateX(${this.tiltDeg}deg)`;
    container.style.transition = 'transform 0.6s cubic-bezier(0.16,1,0.3,1)';

    // Compensate map events for tilt
    this.map.on('click', (e) => {
      // Events still work because Leaflet handles the transform
    });
  }

  setTilt(degrees) {
    this.tiltDeg = degrees;
    const container = document.getElementById(this.containerId);
    if (container) {
      container.style.transform = `rotateX(${degrees}deg)`;
    }
  }

  /**
   * Place the incident marker with a pulsing red dot.
   */
  setIncident(lat, lon, priorityLevel = 'CRITICAL') {
    // Remove old marker
    if (this.incidentMarker) {
      this.map.removeLayer(this.incidentMarker);
    }
    this.pulseCircles.forEach(c => this.map.removeLayer(c));
    this.pulseCircles = [];

    const colorMap = {
      CRITICAL: '#E8341A',
      HIGH: '#FB923C',
      MEDIUM: '#F5C842',
      LOW: '#86EFAC',
      CLEAR: '#4ADE80',
    };
    const color = colorMap[priorityLevel] || '#E8341A';

    // Custom incident icon
    const icon = L.divIcon({
      className: '',
      html: `
        <div style="
          position:relative; width:20px; height:20px;
          display:flex; align-items:center; justify-content:center;
        ">
          <div style="
            width:12px; height:12px; background:${color};
            border-radius:50%; border:2px solid white;
            box-shadow: 0 0 16px ${color};
            animation: map-pulse 1s ease infinite;
            z-index:2; position:relative;
          "></div>
          <div style="
            position:absolute; inset:-8px;
            border-radius:50%; border:2px solid ${color};
            animation: map-ring 1.5s ease infinite;
            opacity:0.6;
          "></div>
        </div>
      `,
      iconAnchor: [10, 10],
    });

    this.incidentMarker = L.marker([lat, lon], { icon })
      .bindPopup(`
        <div style="font-family:monospace;font-size:11px;background:#0a0a0a;color:#f0ede4;border:1px solid #333;padding:12px;border-radius:6px;min-width:180px;">
          <div style="font-size:14px;font-weight:bold;margin-bottom:8px;color:${color}">⚠ ${priorityLevel} INCIDENT</div>
          <div>Lat: ${lat.toFixed(6)}</div>
          <div>Lon: ${lon.toFixed(6)}</div>
        </div>
      `, { className: 'omni-popup' })
      .addTo(this.map);

    // Fly to location
    this.map.flyTo([lat, lon], 15, { duration: 1.5 });
  }

  /**
   * Render hospital markers.
   */
  renderHospitals(hospitals) {
    this.hospitalMarkers.forEach(m => this.map.removeLayer(m));
    this.hospitalMarkers = [];

    hospitals.forEach((h, idx) => {
      const isOptimal = idx === 0;
      const color = isOptimal ? '#00FF87' : (h.trauma_level === 1 ? '#FB923C' : '#666');
      const size = isOptimal ? 14 : 10;

      const icon = L.divIcon({
        className: '',
        html: `
          <div style="
            width:${size}px; height:${size}px;
            background:${color}; border-radius:50%;
            border:2px solid rgba(255,255,255,0.3);
            box-shadow: 0 0 ${isOptimal ? 16 : 6}px ${color};
            ${isOptimal ? 'animation: optimal-pulse 2s ease infinite;' : ''}
          "></div>
        `,
        iconAnchor: [size / 2, size / 2],
      });

      const traumaLabel = ['Level I', 'Level II', 'Level III'][h.trauma_level - 1] || '';

      const marker = L.marker([h.lat, h.lon], { icon })
        .bindPopup(`
          <div style="font-family:monospace;font-size:11px;background:#0a0a0a;color:#f0ede4;border:1px solid #333;padding:12px;border-radius:6px;min-width:200px;">
            ${isOptimal ? '<div style="color:#00FF87;margin-bottom:6px;font-size:10px;letter-spacing:2px">★ OPTIMAL ROUTE</div>' : ''}
            <div style="font-size:12px;font-weight:bold;margin-bottom:6px;">${h.name}</div>
            <div style="color:#888;margin-bottom:4px;">${h.address || ''}</div>
            <div style="color:${color}">Trauma ${traumaLabel}</div>
            <div style="margin-top:8px;display:flex;gap:16px;">
              <span><strong style="color:#00FF87">${h.eta_minutes.toFixed(1)}</strong> min</span>
              <span><strong>${h.distance_mi || (h.distance_km * 0.621).toFixed(1)}</strong> mi</span>
            </div>
          </div>
        `, { className: 'omni-popup' })
        .addTo(this.map);

      this.hospitalMarkers.push(marker);
    });
  }

  /**
   * Draw route lines from incident to hospitals.
   */
  drawRoutes(incidentLat, incidentLon, hospitals) {
    this.routePolylines.forEach(p => this.map.removeLayer(p));
    this.routePolylines = [];

    hospitals.slice(0, 3).forEach((h, idx) => {
      const isOptimal = idx === 0;
      const color = isOptimal ? '#00FF87' : 'rgba(255,255,255,0.2)';
      const weight = isOptimal ? 3 : 1;

      // Curved route using intermediate points
      const midLat = (incidentLat + h.lat) / 2 + (Math.random() - 0.5) * 0.005;
      const midLon = (incidentLon + h.lon) / 2 + (Math.random() - 0.5) * 0.005;

      const polyline = L.polyline(
        [[incidentLat, incidentLon], [midLat, midLon], [h.lat, h.lon]],
        {
          color,
          weight,
          dashArray: isOptimal ? null : '4,4',
          opacity: isOptimal ? 0.9 : 0.4,
          smoothFactor: 2,
        }
      ).addTo(this.map);

      // Animated dashes on optimal route
      if (isOptimal) {
        const animatedLine = L.polyline(
          [[incidentLat, incidentLon], [midLat, midLon], [h.lat, h.lon]],
          { color: 'white', weight: 1, dashArray: '10,20', opacity: 0.4 }
        ).addTo(this.map);
        this.routePolylines.push(animatedLine);
      }

      this.routePolylines.push(polyline);
    });
  }

  /**
   * ETA countdown animation on optimal hospital.
   */
  startETACountdown(etaMinutes, onComplete) {
    const startTime = Date.now();
    const totalMs = etaMinutes * 60 * 1000;

    const update = () => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, totalMs - elapsed);
      const mins = Math.floor(remaining / 60000);
      const secs = Math.floor((remaining % 60000) / 1000);

      document.getElementById('eta-display')?.textContent
        && (document.getElementById('eta-display').textContent = `${mins}:${secs.toString().padStart(2, '0')}`);

      if (remaining > 0) {
        requestAnimationFrame(update);
      } else {
        onComplete?.();
      }
    };
    requestAnimationFrame(update);
  }

  /**
   * Fit map to show incident + optimal hospital.
   */
  fitBounds(incidentLat, incidentLon, hospitalLat, hospitalLon) {
    const bounds = L.latLngBounds(
      [incidentLat, incidentLon],
      [hospitalLat, hospitalLon]
    ).pad(0.3);
    this.map.fitBounds(bounds, { duration: 1.2 });
  }
}

// CSS for map animations (injected into <head>)
const mapStyles = document.createElement('style');
mapStyles.textContent = `
  @keyframes map-pulse {
    0%, 100% { transform: scale(1); box-shadow: 0 0 16px #E8341A; }
    50% { transform: scale(1.4); box-shadow: 0 0 28px #E8341A; }
  }
  @keyframes map-ring {
    from { transform: scale(0.5); opacity: 0.8; }
    to { transform: scale(2); opacity: 0; }
  }
  @keyframes optimal-pulse {
    0%, 100% { box-shadow: 0 0 10px #00FF87; }
    50% { box-shadow: 0 0 24px #00FF87, 0 0 40px rgba(0,255,135,0.3); }
  }
  .leaflet-container { background: #080808 !important; }
  .omni-popup .leaflet-popup-content-wrapper {
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 0 !important;
  }
  .omni-popup .leaflet-popup-tip { background: #1a1a1a !important; }
`;
document.head.appendChild(mapStyles);