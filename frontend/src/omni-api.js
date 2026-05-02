(function () {
  const explicitBase = window.OMNIWATCH_API;
  const apiHost = window.location.hostname || "localhost";
  const sameHostBase = `${window.location.protocol === "file:" ? "http:" : window.location.protocol}//${apiHost}:8000`;
  const apiBase = explicitBase || sameHostBase;
  const wsBase = apiBase.replace(/^http/i, "ws");

  async function request(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(options.headers || {})
      }
    });

    if (!response.ok) {
      throw new Error(`OmniWatch API ${response.status}: ${await response.text()}`);
    }

    return response.json();
  }

  function connectAlerts(onMessage, onStatus) {
    let socket;

    try {
      socket = new WebSocket(`${wsBase}/ws/alerts`);
    } catch (err) {
      onStatus?.("offline", err);
      return null;
    }

    socket.addEventListener("open", () => onStatus?.("connected"));
    socket.addEventListener("message", event => {
      try {
        onMessage?.(JSON.parse(event.data));
      } catch (err) {
        console.warn("[OmniWatch API] Bad websocket payload", err);
      }
    });
    socket.addEventListener("close", () => onStatus?.("offline"));
    socket.addEventListener("error", err => onStatus?.("error", err));

    return socket;
  }

  window.OmniWatchAPI = {
    base: apiBase,
    health: () => request("/"),
    stats: () => request("/api/stats"),
    hospitals: () => request("/api/hospitals"),
    incidents: (limit = 20) => request(`/api/incidents?limit=${encodeURIComponent(limit)}`),
    activeIncidents: () => request("/api/incidents/active"),
    route: (lat, lon) => request(`/api/route?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`, { method: "POST" }),
    dispatch: body => request("/api/dispatch", { method: "POST", body: JSON.stringify(body || {}) }),
    resolve: body => request("/api/incidents/resolve", { method: "POST", body: JSON.stringify(body || {}) }),
    processDemoVideo: (cameraId = "CAM-01") => {
      const form = new FormData();
      form.append("camera_id", cameraId);
      return request("/api/process-video", { method: "POST", body: form });
    },
    connectAlerts
  };
})();
