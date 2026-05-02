"""
OmniWatch Dispatch Map — Pure Python/Pygame with OSM tiles
"""

import pygame
import threading
import math
import time
import requests
import os
import io

# ── COLORS ────────────────────────────────────────────────────────
BG        = (5, 4, 10)
BG2       = (13, 11, 20)
LAVENDER  = (199, 125, 255)
ALERT     = (255, 51, 102)
GREEN     = (0, 255, 170)
YELLOW    = (245, 200, 66)
ORANGE    = (251, 146, 60)
DIM       = (58, 53, 80)
TEXT      = (232, 224, 240)
TEXTDIM   = (107, 96, 128)
WHITE     = (255, 255, 255)
AMBULANCE = (0, 180, 255)

OSRM_BASE = "http://router.project-osrm.org/route/v1/driving"
TILE_URL  = "https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png"
TILE_SIZE = 256
ZOOM      = 13

# ── SF HOSPITALS ─────────────────────────────────────────────────
HOSPITALS = [
    {"name": "UCSF Medical Center",        "lat": 37.7631, "lon": -122.4586, "trauma": 1, "eta": 4.0},
    {"name": "Zuckerberg SF General",      "lat": 37.7556, "lon": -122.4041, "trauma": 1, "eta": 7.0},
    {"name": "California Pacific Medical", "lat": 37.7851, "lon": -122.4378, "trauma": 2, "eta": 6.0},
    {"name": "Saint Francis Memorial",     "lat": 37.7931, "lon": -122.4148, "trauma": 2, "eta": 8.0},
    {"name": "St. Mary's Medical Center",  "lat": 37.7776, "lon": -122.4484, "trauma": 2, "eta": 5.0},
    {"name": "Kaiser SF Medical Center",   "lat": 37.7836, "lon": -122.4324, "trauma": 3, "eta": 9.0},
]

INCIDENT = {"lat": 37.7749, "lon": -122.4194, "label": "Mission District"}

# ── TILE MATH ─────────────────────────────────────────────────────
def latlon_to_tile(lat, lon, zoom):
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) +
             1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return x, y

def latlon_to_pixel(lat, lon, zoom, origin_tx, origin_ty):
    n      = 2 ** zoom
    tile_x = (lon + 180) / 360 * n
    tile_y = (1 - math.log(math.tan(math.radians(lat)) +
               1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    px = int((tile_x - origin_tx) * TILE_SIZE)
    py = int((tile_y - origin_ty) * TILE_SIZE)
    return px, py

# ── TILE CACHE ────────────────────────────────────────────────────
tile_cache = {}
tile_lock  = threading.Lock()

def fetch_tile(z, x, y):
    key = (z, x, y)
    with tile_lock:
        if key in tile_cache:
            return tile_cache[key]
    try:
        url = TILE_URL.format(z=z, x=x, y=y)
        r   = requests.get(url, timeout=5,
                           headers={"User-Agent": "OmniWatch/1.0"})
        if r.status_code == 200:
            img = pygame.image.load(io.BytesIO(r.content))
            img = pygame.transform.scale(img, (TILE_SIZE, TILE_SIZE))
            with tile_lock:
                tile_cache[key] = img
            return img
    except Exception as e:
        print(f"Tile error {z}/{x}/{y}: {e}")
    return None

def preload_tiles(center_lat, center_lon, zoom, radius=2):
    cx, cy = latlon_to_tile(center_lat, center_lon, zoom)
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            threading.Thread(
                target=fetch_tile, args=(zoom, cx+dx, cy+dy), daemon=True
            ).start()

# ── HELPERS ───────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R     = 3958.8
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a     = (math.sin(d_lat/2)**2 +
             math.cos(math.radians(lat1)) *
             math.cos(math.radians(lat2)) *
             math.sin(d_lon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))

def pick_best_hospital():
    scored = []
    for h in HOSPITALS:
        dist  = haversine(INCIDENT["lat"], INCIDENT["lon"], h["lat"], h["lon"])
        score = (4 - h["trauma"]) * 30 - dist * 10 - h["eta"] * 2
        scored.append({**h, "dist_mi": round(dist, 1), "score": score})
    return sorted(scored, key=lambda x: -x["score"])[0]

def fetch_route(olat, olon, dlat, dlon):
    try:
        url = (f"{OSRM_BASE}/{olon},{olat};{dlon},{dlat}"
               f"?overview=full&geometries=geojson&steps=false")
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            d        = r.json()
            coords   = d["routes"][0]["geometry"]["coordinates"]
            duration = d["routes"][0]["duration"]
            return [(c[1], c[0]) for c in coords], duration
    except Exception as e:
        print(f"OSRM error: {e}")
    return None, None

# ── SHARED STATE ──────────────────────────────────────────────────
incident_data = {
    "decision":   "CRITICAL",
    "frame":      0,
    "survival":   70.0,
    "fused":      0.0,
    "alert_time": 0,
}

route_points  = []
optimal       = None
eta_remaining = 0
route_loaded  = False
loading       = True

def load_route():
    global route_points, optimal, eta_remaining, route_loaded, loading
    loading = True
    opt     = pick_best_hospital()
    optimal = opt
    route, duration = fetch_route(
        INCIDENT["lat"], INCIDENT["lon"],
        opt["lat"], opt["lon"]
    )
    if route:
        route_points  = route
        eta_remaining = int(duration)
    else:
        route_points  = [(INCIDENT["lat"], INCIDENT["lon"]),
                         (opt["lat"], opt["lon"])]
        eta_remaining = int(opt["eta"] * 60)
    route_loaded = True
    loading      = False
    print(f"✅ Route: {opt['name']} ({opt['dist_mi']} mi)")

# ── MAIN PYGAME LOOP ──────────────────────────────────────────────
def run():
    global eta_remaining

    threading.Thread(target=load_route, daemon=True).start()
    threading.Thread(
        target=preload_tiles,
        args=(INCIDENT["lat"], INCIDENT["lon"], ZOOM, 3),
        daemon=True
    ).start()

    pygame.init()
    W, H   = 1000, 660
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("OmniWatch — Dispatch Map")
    clock  = pygame.time.Clock()

    font_med    = pygame.font.SysFont("Courier New", 11, bold=True)
    font_small  = pygame.font.SysFont("Courier New", 9)
    font_big    = pygame.font.SysFont("Courier New", 22, bold=True)
    font_arr_bg = pygame.font.SysFont("Courier New", 28, bold=True)
    font_arr_md = pygame.font.SysFont("Courier New", 13, bold=True)
    font_arr_sm = pygame.font.SysFont("Courier New", 10)

    MAP_W      = 650
    MAP_RECT   = pygame.Rect(0, 58, MAP_W, H - 58)
    PANEL_RECT = pygame.Rect(MAP_W + 2, 58, W - MAP_W - 2, H - 58)

    center_lat = INCIDENT["lat"]
    center_lon = INCIDENT["lon"]
    origin_tx, origin_ty = latlon_to_tile(center_lat, center_lon, ZOOM)
    origin_tx -= MAP_W // (2 * TILE_SIZE)
    origin_ty -= (H - 58) // (2 * TILE_SIZE)

    # ── ANIMATION STATE ───────────────────────────────────────────
    anim_start    = None
    ANIM_DUR      = 28.0
    anim_pos      = None
    pulse         = 0.0
    running       = True

    arrived       = False
    arrived_time  = None
    arrival_unit  = "AMBULANCE"
    phase         = "ambulance"  # ambulance → wait → police → done

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_r:
                    # replay
                    anim_start   = time.time()
                    arrived      = False
                    arrived_time = None
                    arrival_unit = "AMBULANCE"
                    phase        = "ambulance"

        dt    = clock.tick(30) / 1000.0
        pulse = (pulse + dt * 2) % (2 * math.pi)
        screen.fill(BG)

        # ── HEADER ───────────────────────────────────────────────
        pygame.draw.rect(screen, BG2, (0, 0, W, 56))
        pygame.draw.line(screen, DIM, (0, 56), (W, 56), 1)

        title = font_big.render("OMNIWATCH  DISPATCH", True, LAVENDER)
        screen.blit(title, (14, 14))

        dec          = incident_data.get("decision", "CLEAR")
        status_color = ALERT if dec == "CRITICAL" else GREEN
        status = font_med.render(
            f"● {dec}  —  Frame {incident_data.get('frame',0)}  —  "
            f"Cfused={incident_data.get('fused',0.0):.2f}  —  "
            f"P(t)={incident_data.get('survival',70.0):.1f}%",
            True, status_color
        )
        screen.blit(status, (W - status.get_width() - 14, 16))
        clk = font_small.render(time.strftime("%H:%M:%S"), True, TEXTDIM)
        screen.blit(clk, (W - clk.get_width() - 14, 40))

        # ── MAP TILES ────────────────────────────────────────────
        map_surf  = pygame.Surface((MAP_W, H - 58))
        map_surf.fill((8, 10, 16))
        tiles_x = MAP_W // TILE_SIZE + 2
        tiles_y = (H - 58) // TILE_SIZE + 2

        for dx in range(tiles_x):
            for dy in range(tiles_y):
                img = fetch_tile(ZOOM, origin_tx + dx, origin_ty + dy)
                if img:
                    map_surf.blit(img, (dx * TILE_SIZE, dy * TILE_SIZE))

        def to_map(lat, lon):
            return latlon_to_pixel(lat, lon, ZOOM, origin_tx, origin_ty)

        # ── ROUTE ────────────────────────────────────────────────
        if route_loaded and len(route_points) > 1:
            pts = [to_map(lat, lon) for lat, lon in route_points]
            if len(pts) >= 2:
                unit_color_route = AMBULANCE if phase == "ambulance" else YELLOW
                pygame.draw.lines(map_surf, (0, 60, 80), False, pts, 6)
                pygame.draw.lines(map_surf, unit_color_route, False, pts, 3)

            if anim_start is None:
                anim_start = time.time()

            elapsed = time.time() - anim_start
            t_anim  = min(elapsed / ANIM_DUR, 1.0)

            # ambulance reaches destination
            if t_anim >= 1.0 and not arrived and phase == "ambulance":
                arrived      = True
                arrived_time = time.time()
                arrival_unit = "AMBULANCE"
                eta_remaining = 0
                print("🚑 Ambulance arrived at incident!")

            # after 8s, dispatch police
            if arrived and arrived_time and phase == "ambulance":
                if time.time() - arrived_time > 8:
                    phase        = "police"
                    arrived      = False
                    arrived_time = None
                    arrival_unit = "POLICE"
                    anim_start   = time.time()
                    print("🚔 Police unit dispatched...")

            # police reaches destination
            if t_anim >= 1.0 and not arrived and phase == "police":
                arrived      = True
                arrived_time = time.time()
                arrival_unit = "POLICE"
                eta_remaining = 0
                print("🚔 Police arrived at incident!")

            # ambulance position
            if not arrived or phase == "police":
                idx      = min(int(t_anim * (len(pts) - 1)), len(pts) - 1)
                anim_pos = pts[idx]
            else:
                anim_pos = pts[-1]

            if optimal and not arrived:
                eta_remaining = max(0, int(optimal["eta"] * 60 * (1 - t_anim)))

        # ── HOSPITALS ────────────────────────────────────────────
        for h in HOSPITALS:
            hx, hy    = to_map(h["lat"], h["lon"])
            is_opt    = optimal and h["name"] == optimal["name"]
            if is_opt:
                pr = int(10 + 5 * math.sin(pulse))
                pygame.draw.circle(map_surf, (0, 100, 60), (hx, hy), pr + 5)
                pygame.draw.circle(map_surf, GREEN, (hx, hy), pr)
                lbl = font_small.render(f"★ {h['name'][:18]}", True, GREEN)
            else:
                color = YELLOW if h["trauma"] == 1 else ORANGE if h["trauma"] == 2 else DIM
                pygame.draw.circle(map_surf, color, (hx, hy), 7)
                pygame.draw.circle(map_surf, WHITE, (hx, hy), 3)
                lbl = font_small.render(h["name"][:18], True, TEXTDIM)
            map_surf.blit(lbl, (hx + 10, hy - 6))

        # ── INCIDENT ─────────────────────────────────────────────
        ix, iy = to_map(INCIDENT["lat"], INCIDENT["lon"])
        pr = int(14 + 6 * math.sin(pulse))
        pygame.draw.circle(map_surf, (120, 0, 30), (ix, iy), pr + 6)
        pygame.draw.circle(map_surf, ALERT, (ix, iy), pr)
        pygame.draw.circle(map_surf, WHITE, (ix, iy), 5)
        map_surf.blit(font_small.render("INCIDENT", True, ALERT), (ix + 16, iy - 8))
        map_surf.blit(font_small.render(INCIDENT["label"], True, TEXTDIM), (ix + 16, iy + 6))

        # ── AMBULANCE / POLICE MARKER ────────────────────────────
        if anim_pos:
            ax, ay     = anim_pos
            unit_color = AMBULANCE if phase == "ambulance" else YELLOW
            unit_label = "AMB" if phase == "ambulance" else "POL"
            pygame.draw.circle(map_surf, (0, 40, 100), (ax, ay), 16)
            pygame.draw.circle(map_surf, unit_color, (ax, ay), 12)
            map_surf.blit(font_med.render(unit_label, True, WHITE), (ax - 12, ay - 6))

        # ── LOADING ──────────────────────────────────────────────
        if loading:
            s = pygame.Surface((MAP_W, H - 58), pygame.SRCALPHA)
            s.fill((5, 4, 10, 160))
            map_surf.blit(s, (0, 0))
            lt = font_med.render("Loading map tiles + route...", True, LAVENDER)
            map_surf.blit(lt, (MAP_W//2 - lt.get_width()//2, (H-58)//2))

        screen.blit(map_surf, (0, 58))
        pygame.draw.rect(screen, DIM, MAP_RECT, 1)

        # ── ARRIVAL OVERLAY ──────────────────────────────────────
        if arrived and arrived_time:
            elapsed_since = time.time() - arrived_time
            flash = abs(math.sin(elapsed_since * 3))
            alpha = 200 if elapsed_since > 3 else int(180 * flash)

            unit_color = AMBULANCE if arrival_unit == "AMBULANCE" else YELLOW
            unit_icon  = "AMBULANCE" if arrival_unit == "AMBULANCE" else "POLICE"

            overlay = pygame.Surface((MAP_W, H - 58), pygame.SRCALPHA)
            overlay.fill((0, 20, 10, min(alpha, 120)))
            screen.blit(overlay, (0, 58))

            cx     = MAP_W // 2
            cy     = (H - 58) // 2 + 58

            card_w, card_h = 480, 140
            card_x = cx - card_w // 2
            card_y = cy - card_h // 2

            card = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            card.fill((5, 20, 15, 230))
            screen.blit(card, (card_x, card_y))
            pygame.draw.rect(screen, unit_color,
                             (card_x, card_y, card_w, card_h), 2)

            line1 = font_arr_bg.render(
                f"{unit_icon} ARRIVED", True, unit_color
            )
            line2 = font_arr_md.render(
                "Unit on scene at incident location", True, GREEN
            )
            surv  = incident_data.get("survival", 70.0)
            line3 = font_arr_sm.render(
                f"Survival P(t) = {surv:.1f}%  ·  "
                f"Alert time: {incident_data.get('alert_time', 0)}s",
                True, TEXTDIM
            )

            screen.blit(line1, (cx - line1.get_width()//2, card_y + 14))
            screen.blit(line2, (cx - line2.get_width()//2, card_y + 62))
            screen.blit(line3, (cx - line3.get_width()//2, card_y + 100))

        # ── RIGHT PANEL ──────────────────────────────────────────
        pygame.draw.rect(screen, BG2, PANEL_RECT)
        pygame.draw.line(screen, DIM,
            (PANEL_RECT.x, PANEL_RECT.y),
            (PANEL_RECT.x, PANEL_RECT.y + PANEL_RECT.height), 1)

        py = PANEL_RECT.y + 12
        px = PANEL_RECT.x + 12
        pw = PANEL_RECT.width - 24

        def label(txt, color=TEXTDIM):
            nonlocal py
            s = font_small.render(txt, True, color)
            screen.blit(s, (px, py))
            py += s.get_height() + 4

        def value(txt, color=TEXT):
            nonlocal py
            s = font_med.render(txt, True, color)
            screen.blit(s, (px, py))
            py += s.get_height() + 8

        def div():
            nonlocal py
            pygame.draw.line(screen, DIM, (px, py), (px + pw, py), 1)
            py += 8

        # dispatch status
        label("DISPATCH STATUS", TEXTDIM)
        if arrived:
            unit_c = AMBULANCE if arrival_unit == "AMBULANCE" else YELLOW
            value(f"{arrival_unit} ON SCENE", unit_c)
        else:
            dc = {"CRITICAL": ALERT, "HIGH": ORANGE,
                  "LOW": YELLOW, "CLEAR": GREEN}.get(dec, GREEN)
            value(dec, dc)
        div()

        # unit status
        label("UNIT STATUS", TEXTDIM)
        if phase == "ambulance":
            if arrived:
                value("AMB-04 · Arrived", GREEN)
            else:
                value("AMB-04 · En Route", AMBULANCE)
        elif phase == "police":
            label("AMB-04 · On Scene", GREEN)
            if arrived:
                value("POL-07 · Arrived", YELLOW)
            else:
                value("POL-07 · En Route", YELLOW)
        div()

        # optimal hospital
        label("OPTIMAL HOSPITAL", TEXTDIM)
        if optimal:
            value(optimal["name"][:20], GREEN)
            label(f"Trauma Level {optimal['trauma']}", YELLOW)
            label(f"Distance: {optimal['dist_mi']} mi", TEXT)
        else:
            value("Calculating...", TEXTDIM)
        div()

        # ETA
        label("ETA", TEXTDIM)
        if arrived:
            value("ARRIVED", GREEN)
            label("Unit on scene", TEXTDIM)
        elif eta_remaining > 0:
            mins = eta_remaining // 60
            secs = eta_remaining % 60
            ec   = GREEN if mins < 5 else YELLOW if mins < 10 else ALERT
            et   = font_big.render(f"{mins}:{secs:02d}", True, ec)
            screen.blit(et, (px, py))
            py += et.get_height() + 4
            label("minutes remaining", TEXTDIM)
        else:
            value("Calculating...", TEXTDIM)
        div()

        # survival
        label("SURVIVAL P(t)", TEXTDIM)
        surv = incident_data.get("survival", 70.0)
        sc   = GREEN if surv > 60 else YELLOW if surv > 40 else ALERT
        st   = font_big.render(f"{surv:.1f}%", True, sc)
        screen.blit(st, (px, py))
        py += st.get_height() + 4
        pygame.draw.rect(screen, DIM, (px, py, pw, 6))
        pygame.draw.rect(screen, sc,
                         (px, py, int(pw * min(surv/100, 1.0)), 6))
        py += 14
        div()

        # nearby facilities
        label("NEARBY FACILITIES", TEXTDIM)
        for h in sorted(HOSPITALS,
                key=lambda h: haversine(INCIDENT["lat"], INCIDENT["lon"],
                                        h["lat"], h["lon"]))[:4]:
            dist   = haversine(INCIDENT["lat"], INCIDENT["lon"],
                               h["lat"], h["lon"])
            is_opt = optimal and h["name"] == optimal["name"]
            color  = GREEN if is_opt else (YELLOW if h["trauma"] == 1 else TEXTDIM)
            label(f"{'★' if is_opt else ' '} {h['name'][:18]}", color)
            label(f"  Trauma {h['trauma']} · {dist:.1f} mi", TEXTDIM)
        div()

        label("R = Replay  ·  ESC = Close", DIM)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    print("✅ OmniWatch Dispatch Map")
    run()