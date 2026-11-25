-- ACR Daily ghost cars, in the game (a UE4SS Lua mod).
--
-- The ACR Daily app writes where the other drivers' cars are (live) to %APPDATA%\ACR Daily\ingame-ghosts.txt about
-- 60 times a second; this mod puts a real car there for each: the driver's own car model (its physics off, nothing
-- to hit), moved every frame, its wheels set where that car's wheels sit at rest (wheels.lua). It also writes the
-- game's camera to %APPDATA%\ACR Daily\ingame-camera.txt, so the app can put the names above the cars exactly.
--
-- ingame-ghosts.txt:   ACRDG 2 <seq> [<when>]
--                      <id> <class> <X> <Y> <Z> <Pitch> <Yaw> <Roll> [<VX> <VY> <VZ> <VPitch> <VYaw> <VRoll> [<seq>]]
--                      end [<seq>]
--   the game's units: cm, degrees (one line per car); <class>: the driver's own car ('/Game/Data/Vehicles/.../
--   BC_X.BC_X_C'), or '-' (unknown: your car's). <when>: the app's clock (s) at that pose; V..: how it moves, per
--   second. With them the car is moved on every frame between the app's updates, from where the app said it was at
--   <when> (the app's clock mapped onto this one), and a small difference when the next update comes is eased out
--   instead of jumped: smooth at any frame rate. Without them (an older app): placed where it says, when read.
--   The update's <seq> again at the end of each line and after "end": the app overwrites the file in place, so a read
--   in the middle of a write (lines of two updates) is told and skipped.
--                      warm <class> <how many> <seq>   (the models of the drivers on the stage: made ahead of time)
--                      name <id> <seq> <shown> <colour> <the name>   (the driver's name, drawn over their car by the
--                      game: hud.lua; shown 0: out of sight behind trees or a hill, as the app works it out)
-- ingame-camera.txt:   CAM <seq> <X> <Y> <Z> <Pitch> <Yaw> <Roll> <horizontal fov> <seq> M <mode> <seq> [N 1 <seq>]
--                      [S ... <seq>] [A ... <seq>] [V ... <seq>] [H <id>... <seq>]
--                      (padded to 160 characters; M: the game's mode, race_mode; N: the game draws the names, hud.lua,
--                      the app's window then doesn't; S / A / V: the race's settings and the player's driving aids,
--                      read_settings / read_aids; H: the cars hidden while in yours, near_hide: no name over them)
--
-- Both files are kept open for the game's whole life, and overwritten in place: opening a file that was just changed
-- costs the game several ms each time (Windows' virus check: the game thread went from 5 to 10 ms a frame with the
-- app's 60 updates a second, measured 2026-11-10); read and written through the open files, about 0.1 ms.
local UEHelpers = require("UEHelpers")

local TAG = "[ACRDailyGhosts] "
local DIR = (os.getenv("APPDATA") or ".") .. "\\ACR Daily\\"
local GHOSTS_FILE = DIR .. "ingame-ghosts.txt"
local CAMERA_FILE = DIR .. "ingame-camera.txt"
local TRACE_FLAG = DIR .. "ghost-trace.on"   -- (for testing: while it exists, each frame's cars go to ghost-trace.txt)
local STALE_S = 1.5              -- the app's file not changing for this long: ghosts hidden
local GONE_S = 0.5               -- a ghost missing from the file this long: removed
local AHEAD_S = 0.25             -- carried on at its speed at most this long past the app's last word
local EASE_S = 0.06              -- a difference between where a car was carried and the app's next word: eased out
local SNAP_CM = 300              -- a bigger one (a reset onto the road): jumped

local cars = {}                  -- id -> {actor, leader, cls, base, vel, t, err, err_t, seen_t}
local ghost_names = {}           -- id -> {text, shown, colour}: the drivers' names, from the app's file
local names_by_game = false      -- hud.lua loaded: it draws the names over the cars (camera line: N)
local NAME_UP = 170              -- a name this far over its car's root (cm)
local trace = nil                -- (testing: ghost-trace.txt open while ghost-trace.on exists)
local last_seq, last_new_t = nil, nil
local frame = 0
local cam_seq = 0
local spawned_this_frame = false

local function log(fmt, ...) print(TAG .. string.format(fmt, ...) .. "\n") end
log("loaded")

-- This mod's clock (seconds, wall time since the game started: the C library's clock() on Windows), and the app's
-- clock mapped onto it: the app writes a file at most a frame or so before it is read here, so the smallest
-- (read here - written there) seen is the gap between the two clocks (it creeps up 1 ms a second, in case).
local now = os.clock
-- The cars are moved by the frame's own time (the game's frame length added up, kept to the wall clock): os.clock()
-- counts whole milliseconds, so at 100+ frames a second each frame's step was off by up to 15 %, a judder on a car the
-- camera follows (the user, 22 Nov 2026: "the car still stutters when broadcasting").
-- (Not the game's frame length: this mod runs at the start of a frame, before the game has measured it, so it read the
-- one before: on the game's uneven frames, 30 ms then 10 ms, the car moved by the wrong one and shook, measured on a
-- live driver, 22 Nov 2026. The wall clock as this frame starts: right but for its whole milliseconds.)
-- WATCH's last step, on disk as it happens (ghost-crumbs.txt): the game crashed while watching (22 Nov 2026) in a call
-- into the game no error catches; the next crash says which step it was in.
local crumbs_f = nil
function crumb(what)
    if not crumbs_f then
        crumbs_f = io.open(DIR .. "ghost-crumbs.txt", "w")
        if not crumbs_f then return end
    end
    crumbs_f:seek("set", 0)
    crumbs_f:write(string.format("%s %d %-40s\n", os.date("%H:%M:%S"), frame, what))
    crumbs_f:flush()
end
local fc_t = nil
local last_delta = 0                                   -- (the game's last frame length: kept for the trace only)
local GS = nil
local function frame_clock(ctx)
    local raw = os.clock()
    if fc_t and raw <= fc_t then raw = fc_t + 0.0002 end   -- (never the same moment twice)
    fc_t = raw
    if trace and ctx then                              -- (testing: the game's own frame length beside it)
        pcall(function()
            if not GS or not GS:IsValid() then GS = UEHelpers.GetGameplayStatics() end
            last_delta = GS:GetWorldDeltaSeconds(ctx)
        end)
    end
    return raw
end
local offset, offset_t = nil, nil
local function app_to_here(app_t, t)
    local d = t - app_t
    if offset == nil or d < offset + (t - offset_t) * 0.001 then
        offset, offset_t = d, t
    else
        offset, offset_t = offset + (t - offset_t) * 0.001, t
    end
    return app_t + offset
end

local function pawn()
    local pc = UEHelpers.GetPlayerController()
    if pc and pc:IsValid() then
        local p = pc.Pawn
        if p and p:IsValid() and p.SetInputEnabled then return p, pc end
        return nil, pc
    end
end

local ghosts_f, ghosts_opened = nil, nil      -- (the app's file, kept open)

local function ghosts_text(t)
    if not ghosts_f then
        if frame % 30 ~= 1 then return nil end      -- (looked for twice a second until the app has made it)
        ghosts_f = io.open(GHOSTS_FILE, "r")
        if not ghosts_f then return nil end
        ghosts_opened = t
    end
    if not ghosts_f:seek("set", 0) then
        ghosts_f:close()
        ghosts_f = nil
        return nil
    end
    return ghosts_f:read("a")
end

local function reopen_ghosts()
    -- (nothing new for a while: the file may have been made again, an older app replaces it each time)
    if ghosts_f then ghosts_f:close() end
    ghosts_f = nil
end

local function read_ghosts(t)
    -- -> seq, the app's clock at it (or nil), {id -> {X, Y, Z, Pitch, Yaw, Roll, cls = , v = {per second} or nil}};
    -- nil when there is no whole update (being written: the next frame)
    local text = ghosts_text(t)
    if not text then return nil end
    local seq, when = text:match("^ACRDG 2 (%d+) ?([%d%.]*)")
    if not seq then return nil end
    local stop, tail = text:match("()\nend ?(%d*)")
    if not stop or (tail ~= "" and tail ~= seq) then return nil end     -- (no end yet, or another update's)
    local out, warm_now, names_now = {}, {}, {}
    for line in text:sub(1, stop):gmatch("\n([^\n]+)") do               -- (up to the end: never what lies after it)
        local w = {}
        for x in line:gmatch("%S+") do w[#w + 1] = x end
        if w[1] == "name" then                                           -- name <id> <seq> <shown> <colour> <the name>
            if w[3] ~= seq then return nil end
            local words = line:match("^name %S+ %S+ %S+ %S+ (.+)$")
            if words then names_now[w[2]] = {text = words, shown = w[4] == "1", colour = w[5]} end
        elseif w[1] == "path" and #w >= 10 then                          -- path <id> <seq> <dt ms> X Y Z P Yw R ...
            if w[3] ~= seq then return nil end
            local poses = {}
            for i = 5, #w - 5, 6 do
                local p = {}
                for k = 0, 5 do p[k + 1] = tonumber(w[i + k]) end
                if p[6] then poses[#poses + 1] = p end
            end
            if #poses >= 2 then names_now["\0path:" .. w[2]] = {dt = (tonumber(w[4]) or 100) / 1000, poses = poses} end
        elseif w[1] == "path2" and #w >= 11 then                         -- path2 <id> <seq> <dt ms> <their clock ms> X Y Z P Yw R ...
            if w[3] ~= seq then return nil end
            local poses = {}
            for i = 6, #w - 5, 6 do
                local p = {}
                for k = 0, 5 do p[k + 1] = tonumber(w[i + k]) end
                if p[6] then poses[#poses + 1] = p end
            end
            local c0 = tonumber(w[5])
            if #poses >= 2 and c0 then
                names_now["\0path:" .. w[2]] = {dt = (tonumber(w[4]) or 100) / 1000, c0 = c0 / 1000, poses = poses}
            end
        elseif w[1] == "path3" and #w >= 12 then                         -- path3 <id> <seq> <dt ms> <clock at the first pose> <clock now> X Y Z P Yw R ...
            if w[3] ~= seq then return nil end
            local poses = {}
            for i = 7, #w - 5, 6 do
                local p = {}
                for k = 0, 5 do p[k + 1] = tonumber(w[i + k]) end
                if p[6] then poses[#poses + 1] = p end
            end
            local c0, cn = tonumber(w[5]), tonumber(w[6])
            if #poses >= 2 and c0 and cn then
                names_now["\0path:" .. w[2]] = {dt = (tonumber(w[4]) or 100) / 1000, c0 = c0 / 1000, now = cn / 1000,
                                                poses = poses}
            end
        elseif w[1] == "wlivery" then                                   -- wlivery <seq> <livery name...> (WATCH)
            if w[2] ~= seq then return nil end
            names_now["\0wlivery"] = line:match("^wlivery %S+ (.+)$")
        elseif w[1] == "wdash" and #w >= 5 then                        -- wdash <rpm> <throttle> <gear> <seq> (WATCH: its sound)
            if w[5] ~= seq then return nil end
            names_now["\0wdash"] = {rpm = tonumber(w[2]) or 0, load = tonumber(w[3]) or 0, gear = tonumber(w[4]) or 1}
        elseif w[1] == "route" then                                      -- route <seq> <X> <Y>... (WATCH: the road ahead)
            if w[2] ~= seq then return nil end
            local pts = {}
            for i = 3, #w - 1, 2 do
                local x, y = tonumber(w[i]), tonumber(w[i + 1])
                if x and y then pts[#pts + 1] = {x, y} end
            end
            names_now["\0route"] = pts
        elseif #w >= 15 and w[15] ~= seq then return nil                 -- (a line of another update)
        elseif w[1] == "warm" and #w >= 4 then                           -- warm <class> <how many> <seq>
            if w[4] ~= seq then return nil end
            warm_now[w[2]] = tonumber(w[3]) or 0
        elseif w[1] == "watch" and #w >= 4 then                          -- watch <id> <camera> <seq> (WATCH)
            if w[4] ~= seq then return nil end
            names_now["\0watch"] = {id = w[2], cam = w[3]}
        elseif #w >= 8 then
            local g = {cls = w[2]}
            for i = 1, 6 do g[i] = tonumber(w[i + 2]) end
            if #w >= 14 then
                g.v = {}
                for i = 1, 6 do g.v[i] = tonumber(w[i + 8]) or 0 end
            end
            if g[1] and g[2] and g[3] and g[4] and g[5] and g[6] then out[w[1]] = g end
        end
    end
    for id, g in pairs(out) do                         -- (each car's path ahead on it, WATCH: on_path)
        local key = "\0path:" .. id
        if names_now[key] then g.path = names_now[key] end
    end
    for k in pairs(names_now) do
        if type(k) == "string" and k:sub(1, 6) == "\0path:" then names_now[k] = nil end
    end
    return seq, tonumber(when), out, warm_now, names_now
end

local function angle(a)            -- degrees, to -180..180
    return (a + 180) % 360 - 180
end

local function carried_raw(c, t)
    -- where car c is at this mod's clock t: the app's last pose, moved on at its speed (at most AHEAD_S)
    local b, v = c.base, c.vel
    local dt = math.max(0, math.min(AHEAD_S, t - c.t))
    local p = {}
    for i = 1, 6 do p[i] = b[i] + (v and v[i] or 0) * dt end
    return p
end

-- WATCH: the path ahead of a car (the app's "path" line: its poses every dt from t0 on, as it will be drawn: the
-- drivers are played back 1.5 s late, so the app knows where they go next). Drawn from it, on the mod's own clock,
-- through a smooth curve (Catmull-Rom): the app's updates may come late (its thread busy 25 ms at a time, once 150 ms+:
-- a stop-and-jump, the user's "laggy", 22 Nov 2026) without the car feeling it. nil past its end: carried as before.
-- Their stage clock is kept here too ("path2": each path says the clock at its first pose): it runs at the frame's
-- pace, nudged at most PLAY_WARP towards where the app says it is, so the app's updates (each placed by when it wrote
-- them, a millisecond or two either way, and its own clock eased 5 % at most) never step the car back or on.
local PLAY_WARP, PLAY_SNAP = 0.06, 0.5           -- (a little over the app's own 5 %: it always keeps up)
local function play_clock(c, t)
    local P = c.path
    -- (the app sends one pose before now: their clock now is the second pose's. Taken as the first, the car was
    -- drawn a pose early, where the curve has no pose behind it, its speed swinging: the shake left, seen live on
    -- Bughuul 23 Nov 2026)
    -- (path3: the app says their clock now outright; its poses on a fixed grid of their clock, the same in every path)
    local target = (P.now or (P.c0 + P.dt)) + (t - P.t0)
    if not c.pc or not c.pc_t or math.abs(target - (c.pc + (t - c.pc_t))) > PLAY_SNAP then
        c.pc, c.pc_t = target, t
        return target
    end
    local dt = t - c.pc_t
    if dt > 0 then
        local err = target - (c.pc + dt)
        c.pc = c.pc + dt * (1 + math.max(-PLAY_WARP, math.min(PLAY_WARP, err)))
        c.pc_t = t
    end
    return c.pc
end

local function on_path(c, t)
    local P = c.path
    if not P or not P.t0 then return nil end
    local u
    if P.c0 then
        -- (drawn where the curve has a pose on each side: its first segment, with none before it, sped up and slowed
        -- down within every update, a judder; the app sends one pose before now for it, and a moment behind it the
        -- path before is used)
        local clock = play_clock(c, t)
        u = (clock - P.c0) / P.dt
        local Q = c.prev_path
        if u < 1 and Q and Q.c0 then
            local uq = (clock - Q.c0) / Q.dt
            if (uq >= 1 and uq <= #Q.poses - 3) or u < 0 then P, u = Q, uq end
        end
    else
        u = (t - P.t0) / P.dt
    end
    local n = #P.poses
    if u < 0 or u > n - 1 then return nil end
    local i = math.floor(u)
    local f = u - i
    local function at(k) return P.poses[math.max(1, math.min(n, k + 1))] end
    local p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
    local f2, f3 = f * f, f * f * f
    local out, vel = {}, {}
    for k = 1, 6 do
        local a0, a1, a2, a3 = p0[k], p1[k], p2[k], p3[k]
        if k >= 4 then                                 -- (angles: unwrapped round the second)
            a0 = a1 + angle(a0 - a1); a2 = a1 + angle(a2 - a1); a3 = a2 + angle(a3 - a2)
        end
        out[k] = 0.5 * ((2 * a1) + (-a0 + a2) * f + (2 * a0 - 5 * a1 + 4 * a2 - a3) * f2 + (-a0 + 3 * a1 - 3 * a2 + a3) * f3)
        vel[k] = 0.5 * ((-a0 + a2) + 2 * (2 * a0 - 5 * a1 + 4 * a2 - a3) * f + 3 * (-a0 + 3 * a1 - 3 * a2 + a3) * f2) / P.dt
    end
    return out, vel
end

local function carried(c, t)
    -- ... plus what is left of the difference being eased out (on a path: from it, the app's word only its fallback)
    local pp, pv = on_path(c, t)
    if pp then
        c.vel = pv
        c.base, c.t, c.err = pp, t, nil                -- (off its end: carried on from here, no jump)
        return pp
    end
    local p = carried_raw(c, t)
    if c.err then
        local k = math.exp(-(t - c.err_t) / EASE_S)
        if k < 0.005 then
            c.err = nil
        else
            for i = 1, 6 do p[i] = p[i] + c.err[i] * k end
        end
    end
    return p
end

local function took(c, g, t_pose, t)
    -- the app's new word on car c (pose g at this mod's clock t_pose), seen at t: from it on, the difference from
    -- where the car was being carried eased out (a reset: jumped)
    if g.path then                                     -- (WATCH: its path ahead, from now on: on_path)
        c.prev_path = c.path
        c.path = {t0 = t_pose, c0 = g.path.c0, now = g.path.now, dt = g.path.dt, poses = g.path.poses}
        if on_path(c, t) then
            -- (a car made while its paths were already coming had no base pose: never drawn, so WATCH went off and
            -- never came back on it; seen live, VBR_PAUL_MARTIN starting a new run, 24 Nov 2026)
            if not c.base then c.base, c.vel, c.t = g, g.v, t_pose end
            return
        end
    else
        c.path, c.prev_path, c.pc = nil, nil, nil
    end
    local before = c.base and carried(c, t)
    c.base, c.vel, c.t = g, g.v, t_pose
    if before then
        local after = carried_raw(c, t)
        local e = {before[1] - after[1], before[2] - after[2], before[3] - after[3],
                   angle(before[4] - after[4]), angle(before[5] - after[5]), angle(before[6] - after[6])}
        if math.abs(e[1]) + math.abs(e[2]) + math.abs(e[3]) < SNAP_CM then
            c.err, c.err_t = e, t
        else
            c.err = nil
        end
    end
end

local classes = {}               -- class path -> UClass (or false: could not load it)

local function class_for(path, me)
    if path == "-" then return me:GetClass() end
    local c = classes[path]
    -- (a class only the mod loaded is the game's to free once no car of it is left: the pool emptied after 2 min, or
    -- the level gone. Kept here unchecked, the next car spawned from it would come from freed memory, a crash pcall
    -- can't catch; no ghost was made on the next stage, 21 Nov 2026. classes is also emptied in the menus: tick)
    if c and not c:IsValid() then c = nil end
    if c == nil then
        c = StaticFindObject(path)
        if not (c and c:IsValid()) then
            local ok, got = pcall(LoadAsset, path)
            c = StaticFindObject(path)
            if not (c and c:IsValid()) and ok and got and got.IsValid and got:IsValid() then c = got end
        end
        if not (c and c:IsValid()) then
            log("can't load %s: your car instead", path)
            c = false
        end
        classes[path] = c
    end
    return c or me:GetClass()
end

local function skinned(actor)
    local out = {}
    local cls = StaticFindObject("/Script/Engine.SkinnedMeshComponent")
    local comps = actor:K2_GetComponentsByClass(cls)
    local function add(c)
        if c and c.IsValid and c:IsValid() then out[c:GetFName():ToString()] = c end
    end
    if type(comps) == "table" then
        for _, c in pairs(comps) do add(c.get and c:get() or c) end
    else
        comps:ForEach(function(_, e) add(e:get()) end)
    end
    return out
end

-- The body keeps its own shape: never your car's pose (another car's bones opened its doors; and the game hides parts
-- of your car in some views, the bumper camera its rear panels, which a copy of your pose hid on the ghost too). The
-- crew: the same car as yours seats it like yours; another car's is hidden (seated like yours, their heads came
-- through a low roof: Stratos, Alpine, Fiat 124). The suspension never follows yours either (your car's wheels would
-- stick out of a narrower car): place_wheels() sets it.
local function crew(name)   -- Driver, CoDriver, HelmetCoDriver, SuitCodriver, ..., Pacenotes (the co-driver's book)
    return name:find("[Dd]river") ~= nil or name:find("Pacenote") ~= nil
end

local function follow_pose(ghost, me)
    local same = ghost:GetClass():GetFullName() == me:GetClass():GetFullName()
    local mine = skinned(me)
    for name, c in pairs(skinned(ghost)) do
        if crew(name) then
            if same and mine[name] then
                c:SetLeaderPoseComponent(mine[name], true, false)
            else
                c:SetVisibility(false, true)
            end
        end
    end
end

-- The wheels. A car without physics never moves its wheels itself: the game's suspension animation keeps the four
-- wheel positions (world, from when the car appeared) until something sets them, so a moving ghost left its wheels
-- behind. Each frame they are set from where the car is, at the car's resting wheel positions (wheels.lua: measured
-- in the game with each car as your own); a car not measured keeps where its model has them.
local BONES = {"EXT_FL_Tire", "EXT_FR_Tire", "EXT_RL_Tire", "EXT_RR_Tire"}   -- (the animation's wheel order)
local ok_rest, REST = pcall(require, "wheels")
if not ok_rest or type(REST) ~= "table" then
    log("no wheels.lua (%s): wheels where the models have them", tostring(REST))
    REST = {}
end

local function wheels_of(a)
    local r = REST[a:GetClass():GetFName():ToString()]
    if r then return r end
    local sm, out, size = a.SuspensionsMesh, {}, 0
    for i, b in ipairs(BONES) do
        local t = sm:GetSocketTransform(FName(b), 2)            -- (the car's own space, cm)
        out[i] = {t.Translation.X, t.Translation.Y, t.Translation.Z}
        size = size + math.abs(t.Translation.X) + math.abs(t.Translation.Y)
    end
    if size < 100 then return nil end                          -- (no pose yet: left as the game has them)
    return out
end

local function rotation(p, y, r)
    -- Unreal's rotator -> its axes (X, Y, Z in the world) and quaternion
    local sp, cp = math.sin(math.rad(p)), math.cos(math.rad(p))
    local sy, cy = math.sin(math.rad(y)), math.cos(math.rad(y))
    local sr, cr = math.sin(math.rad(r)), math.cos(math.rad(r))
    local ax = {cp * cy, cp * sy, sp}
    local ay = {sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp}
    local az = {-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp}
    local hsp, hcp = math.sin(math.rad(p) / 2), math.cos(math.rad(p) / 2)
    local hsy, hcy = math.sin(math.rad(y) / 2), math.cos(math.rad(y) / 2)
    local hsr, hcr = math.sin(math.rad(r) / 2), math.cos(math.rad(r) / 2)
    local q = {X = hcr * hsp * hsy - hsr * hcp * hcy, Y = -hcr * hsp * hcy - hsr * hcp * hsy,
               Z = hcr * hcp * hsy - hsr * hsp * hcy, W = hcr * hcp * hcy + hsr * hsp * hsy}
    return ax, ay, az, q
end

-- quaternions (X, Y, Z, W): a * b (b turned first, in a's own axes), and a turn of `rad` about the car's own axis
local function qmul(a, b)
    return {X = a.W * b.X + a.X * b.W + a.Y * b.Z - a.Z * b.Y, Y = a.W * b.Y - a.X * b.Z + a.Y * b.W + a.Z * b.X,
            Z = a.W * b.Z + a.X * b.Y - a.Y * b.X + a.Z * b.W, W = a.W * b.W - a.X * b.X - a.Y * b.Y - a.Z * b.Z}
end
local function qaxis(x, y, z, rad)
    local s = math.sin(rad / 2)
    return {X = x * s, Y = y * s, Z = z * s, W = math.cos(rad / 2)}
end

-- The ground under each wheel (0.2, the user, 21 Nov 2026: "sometimes cars are levitating", "wheels are not moving"):
-- a ray straight down at each wheel, for the cars near the camera (c.close: detail()), a few times... every frame.
-- Each wheel then sits on it (within SUSP_CM of where it rests), the body follows the ground under its four wheels
-- (c.lift: eased, while the car is near the ground; in the air, the driver's own height), the wheels roll with the
-- car's speed and the front ones steer with how it turns.
local KSL = nil
local SUSP_CM = 14                 -- a wheel up or down this far from where it rests, at most
local LIFT_MAX = 45                -- the body moved this far at most to sit on the ground (more: in the air, left be)
local HIT = nil
local function ground(world, x, y, z, ignore)
    if not (KSL and KSL:IsValid()) then KSL = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary") end
    local out = {}
    local ok, got = pcall(function()
        return KSL:LineTraceSingle(world, {X = x, Y = y, Z = z + 90.0}, {X = x, Y = y, Z = z - 160.0}, 0, false,
                                   ignore, 0, out, true, {R = 0, G = 0, B = 0, A = 0}, {R = 0, G = 0, B = 0, A = 0}, 0.0)
    end)
    if HIT == nil then                                  -- (once: how the game answers, in UE4SS.log)
        HIT = ok
        log("ground under the ghosts: %s %s", tostring(ok), ok and tostring(got) or tostring(got))
    end
    if not (ok and got) then return nil end
    local hz = nil
    pcall(function() hz = out.OutHit.ImpactPoint.Z end)
    if hz == nil then pcall(function() hz = out.ImpactPoint.Z end) end
    if hz == nil then pcall(function() hz = out.OutHit.Location.Z end) end
    return hz
end

local function place_wheels(c, g, t)
    if not c.wheels then return g end
    local ai = c.anim
    if not (ai and ai:IsValid()) then
        ai = c.actor.SuspensionsMesh:GetAnimInstance()
        if not (ai and ai:IsValid()) then return g end
        c.anim = ai
    end
    local ax, ay, az, q = rotation(g[4], g[5], g[6])
    local dt = c.wt and math.min(0.1, math.max(0, t - c.wt)) or 0
    c.wt = t
    -- how fast it goes along its own forward (the car's +Y), how fast it turns: from how the app says it moves
    local v = c.vel or {0, 0, 0, 0, 0, 0}
    local fwd = v[1] * ay[1] + v[2] * ay[2] + v[3] * ay[3]                          -- cm/s
    local radius = math.max(20, c.wheels[1][3])
    -- (about +X, the car's left: a positive turn takes the wheel's top backwards, so rolling forward is negative)
    c.spin = ((c.spin or 0) - fwd * dt / radius) % (2 * math.pi)
    local base = c.wheels[1][2] - c.wheels[3][2]
    local want = 0
    if math.abs(fwd) > 300 then
        want = math.atan(base * math.rad(v[5] or 0) / fwd)
        want = math.max(-0.55, math.min(0.55, want))
    end
    c.steer = (c.steer or 0) + (want - (c.steer or 0)) * math.min(1, dt * 8)
    -- the ground under each wheel (near the camera only)
    local world = c.close and UEHelpers.GetWorld() or nil
    local at, offs, n, sum = {}, {}, 0, 0
    for i = 1, 4 do
        local l = c.wheels[i]
        at[i] = {X = g[1] + ax[1] * l[1] + ay[1] * l[2] + az[1] * l[3],
                 Y = g[2] + ax[2] * l[1] + ay[2] * l[2] + az[2] * l[3],
                 Z = g[3] + ax[3] * l[1] + ay[3] * l[2] + az[3] * l[3]}
        if world then
            local gz = ground(world, at[i].X, at[i].Y, at[i].Z, {c.actor})
            if gz then
                offs[i] = gz + l[3] - at[i].Z                -- (+: the wheel should be higher: in the ground now)
                n, sum = n + 1, sum + offs[i]
            end
        end
    end
    local target = 0
    if n >= 3 and math.abs(sum / n) < LIFT_MAX then target = sum / n end
    c.lift = (c.lift or 0) + (target - (c.lift or 0)) * math.min(1, dt * 6)
    local wt, st = ai.WheelTransforms, ai.SuspensionTransforms
    local qs = qmul(q, qaxis(0, 0, 1, c.steer))                -- (front: turned about the car's up)
    for i = 1, 4 do
        local p = at[i]
        local d = offs[i] and math.max(-SUSP_CM, math.min(SUSP_CM, offs[i] - c.lift)) or 0
        p = {X = p.X, Y = p.Y, Z = p.Z + c.lift + d}
        local turn = i <= 2 and qs or q
        local w, s = wt[i], st[i]
        w.Translation, w.Rotation = p, qmul(turn, qaxis(1, 0, 0, c.spin))   -- (rolling about its axle: the car's X)
        s.Translation, s.Rotation = p, turn
    end
    if c.lift ~= 0 then return {g[1], g[2], g[3] + c.lift, g[4], g[5], g[6]} end
    return g
end

local function transform(g)
    local half = math.rad(g[5]) / 2
    return {Rotation = {X = 0.0, Y = 0.0, Z = math.sin(half), W = math.cos(half)},
            Translation = {X = g[1], Y = g[2], Z = g[3]}, Scale3D = {X = 1.0, Y = 1.0, Z = 1.0}}
end

-- The ghost's dash screens (GaugeComponent: the gear screen on the dash) are stopped: while a ghost's one ticked,
-- YOUR car's went black (the same car as yours, the Skoda's gear screen, seen in the game 2026-11-10; it came back as
-- soon as the ghost's stopped ticking). Checked again now and then (quiet_gauges), in case the game starts it again.
local function gauges(a)
    local out = {}
    local comps = a:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.ActorComponent"))
    local function add(c)
        if c and c.IsValid and c:IsValid() and c:GetClass():GetFName():ToString():find("Gauge") then
            out[#out + 1] = c
        end
    end
    if type(comps) == "table" then
        for _, c in pairs(comps) do add(c.get and c:get() or c) end
    else
        comps:ForEach(function(_, e) add(e:get()) end)
    end
    return out
end

local function quiet_gauges(c)
    for _, g in ipairs(c.gauges or {}) do
        if g:IsValid() and g:IsComponentTickEnabled() then g:SetComponentTickEnabled(false) end
    end
end

-- A ghost is a picture of a car: all that makes a car a car is stopped on it (its own update, its sound, dust and
-- smoke, damage, crew animations, the dash screens, and the update of each of its ~40 models); only its lights (night
-- stages) and its suspension (it places the wheels) go on. Its crew and its inside are drawn only when it is near
-- (NEAR_M, hidden again past FAR_M). Measured with 10 ghosts moving round in front of you (2026-11-10): the game
-- thread's time a frame went from 23 ms (5 without them) to about 9, the draw calls from 8600 to about 5000.
local KEEP_TICK = {SuspensionsMesh = true}
local KEEP_TICK_CLASS = {CarLightsComponent = true}
local NEAR_M, FAR_M = 40, 50
local GROUND_M = 150             -- the cars this near the camera sit on the ground (four rays down each, place_wheels)

local function trim(a)
    a:SetActorTickEnabled(false)
    local scene = StaticFindObject("/Script/Engine.SceneComponent")
    local crew_parts, inside = {}, {}
    local comps = a:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.ActorComponent"))
    local list = {}
    if type(comps) == "table" then
        for _, c in pairs(comps) do list[#list + 1] = c.get and c:get() or c end
    else
        comps:ForEach(function(_, e) list[#list + 1] = e:get() end)
    end
    for _, c in ipairs(list) do
        if c and c.IsValid and c:IsValid() then
            local cls, name = c:GetClass():GetFName():ToString(), c:GetFName():ToString()
            if not KEEP_TICK[name] and not KEEP_TICK_CLASS[cls] and c:IsComponentTickEnabled() then
                c:SetComponentTickEnabled(false)
                if cls == "NiagaraComponent" or cls == "CarAudioComponent" then c:Deactivate() end
            end
            if c:IsA(scene) then
                if crew(name) then
                    crew_parts[#crew_parts + 1] = c
                elseif name:find("^Internal") then
                    inside[#inside + 1] = c
                end
            end
        end
    end
    return crew_parts, inside
end

local function detail(c, me_loc)
    -- the crew (if it is shown at all: the same car as yours) and the inside, near only
    local p = c.shown
    local d = math.sqrt((p[1] - me_loc.X) ^ 2 + (p[2] - me_loc.Y) ^ 2 + (p[3] - me_loc.Z) ^ 2) / 100
    c.close = d < GROUND_M                                    -- (its wheels on the ground: place_wheels)
    local want = d < NEAR_M or (c.detail and d < FAR_M)
    if want == c.detail then return end
    c.detail = want
    for _, part in ipairs(c.inside) do
        if part:IsValid() then part:SetVisibility(want, false) end
    end
    if c.crew_shown then
        for _, part in ipairs(c.crew) do
            if part:IsValid() then part:SetVisibility(want, true) end
        end
        -- (WATCH's cockpit shot keeps its driver away: shown again here, the camera was inside their head, 22 Nov 2026)
        if c.driver_hidden and driver_visible then pcall(driver_visible, c, false) end
        if c.codriver_hidden and driver_visible then pcall(driver_visible, c, false, true) end   -- (the passenger-seat shot's)
    end
end

-- A ghost is hidden only while it is IN your car (its name stays: the app draws it): one driving through you filled the
-- screen. Close racing stays: a car side by side with you, or a few metres ahead or behind, is shown. "In your car":
-- its middle within OVERLAP_FWD of yours lengthways and OVERLAP_SIDE sideways (cars are 4.1-4.3 m long, 1.8 m wide:
-- wheels.lua), in your car's own axes (x = left, y = forward). In a chase view also within CAM_M of the camera (behind
-- your car: one passing through it). Shown again only a little further out (no blinking at the edge).
local OVERLAP_FWD, OVERLAP_SIDE, OVERLAP_UP = 400, 170, 300      -- cm
local CAM_M = 250
local CAM_OUT = 300                                              -- cm: the camera further from your car's middle: a chase view
local OUT = 60                                                   -- cm more to be shown again

local function near_hide(c, cam, me)
    local p = c.shown
    local was = c.near == true
    local m = was and OUT or 0
    local dx, dy, dz = p[1] - me.X, p[2] - me.Y, p[3] - me.Z
    local fwd = math.abs(-dx * me.sy + dy * me.cy)
    local side = math.abs(dx * me.cy + dy * me.sy)
    local inside = fwd < OVERLAP_FWD + m and side < OVERLAP_SIDE + m and math.abs(dz) < OVERLAP_UP + m
    local at_cam = me.cam_out and ((p[1] - cam.X) ^ 2 + (p[2] - cam.Y) ^ 2 + (p[3] - cam.Z) ^ 2) < (CAM_M + m) ^ 2
    local want = inside or at_cam == true                        -- (always true or false, never nil)
    if want == was then return end
    c.near = want
    c.actor:SetActorHiddenInGame(want)
end

local function spawn(me, g)
    local gs = UEHelpers.GetGameplayStatics()
    local t = transform(g)
    local a = gs:BeginDeferredActorSpawnFromClass(UEHelpers.GetWorld(), class_for(g.cls, me), t, 1, nil, 0)
    if not a or not a:IsValid() then return nil end
    a.bInitializePhysics = false                      -- a picture of a car: no physics, nothing to drive
    gs:FinishSpawningActor(a, t, 0)
    a:SetActorEnableCollision(false)
    -- (never SetInputEnabled(false) on it: the cars share one input set-up, and that switched off YOUR car's
    -- throttle and steering, for good, the first time a ghost came: seen in the game 2026-11-05)
    follow_pose(a, me)
    return a
end

-- Kept cars. Making a ghost costs the game about 45 ms (a hitch of a frame and a half at 30 frames a second, measured
-- 2026-11-11); hiding one and showing it again, under 1 ms. So a ghost that goes (out of range, or the app stops
-- telling) is hidden and kept for the next car of its model (POOL_MAX at most, POOL_KEEP_S each); and while your car
-- stands still (waiting at the start), the cars the app says are on the stage ("warm" lines) are made ahead of time,
-- one every WARM_S, so that none is made while you drive. 30 drivers setting off past you, 2 s apart: 30 frames of
-- 66-75 ms before, 0 after (all made while waiting).
local POOL_MAX = 10
local POOL_KEEP_S = 120
local WARM_S = 0.5
local pool = {}                  -- class path -> {car, ...}: hidden, trimmed, ready
local pooled = 0
local pool_leader = nil          -- (whose crew they follow: your car; another car of yours: they go)
local warm, warm_t = {}, -1e9

local function make(me, g, me_at)
    local a = spawn(me, g)
    if not a then return nil end
    local c = {actor = a, leader = me_at, cls = g.cls, wheels = wheels_of(a), gauges = gauges(a), detail = true,
               crew_shown = a:GetClass():GetFullName() == me:GetClass():GetFullName()}
    c.crew, c.inside = trim(a)
    quiet_gauges(c)
    if trace then trace:write(string.format("# spawn %d %s\n", frame, g.cls)) end
    return c
end

local function destroy(c)
    if c.actor and c.actor:IsValid() then c.actor:K2_DestroyActor() end
end

local function park(c, t)
    if pooled >= POOL_MAX or c.painted or not c.actor:IsValid() then
        destroy(c)
        return
    end
    c.actor:SetActorHiddenInGame(true)
    c.base, c.vel, c.err, c.shown, c.parked_t = nil, nil, nil, nil, t
    pool[c.cls] = pool[c.cls] or {}
    table.insert(pool[c.cls], c)
    pooled = pooled + 1
end

local function take(cls, me_at)
    local list = pool[cls]
    while list and #list > 0 do
        local c = table.remove(list)
        pooled = pooled - 1
        if c.actor:IsValid() and c.leader == me_at then
            c.actor:SetActorHiddenInGame(false)
            c.near = false                             -- (shown: near_hide hides it again if it comes back close)
            return c
        end
        destroy(c)
    end
    return nil
end

local function empty_pool(keep_s, t)
    -- the kept cars removed: all (keep_s nil), or those unused for longer than keep_s
    for _, list in pairs(pool) do
        for i = #list, 1, -1 do
            local c = list[i]
            if not keep_s or t - c.parked_t > keep_s or not c.actor:IsValid() then
                table.remove(list, i)
                pooled = pooled - 1
                destroy(c)
            end
        end
    end
end

local function remove(id, t, gone)
    -- a ghost goes: kept for the next of its model (gone: removed for good)
    local c = cars[id]
    cars[id] = nil
    if not c then return end
    if gone then destroy(c) else park(c, t) end
end

local function warm_up(me, me_at, t)
    -- (while you stand still) one more car made ahead of time, of a model the app says may come and short of
    if spawned_this_frame or t - warm_t < WARM_S or pooled >= POOL_MAX then return end
    local ok, v = pcall(function() return me:GetVelocity() end)
    if not ok or not v or math.sqrt(v.X * v.X + v.Y * v.Y + v.Z * v.Z) > 200 then return end
    for cls, want in pairs(warm) do
        local have = #(pool[cls] or {})
        for _, c in pairs(cars) do
            if c.cls == cls then have = have + 1 end
        end
        if have < want then
            local l, r = me:K2_GetActorLocation(), me:K2_GetActorRotation()
            local c = make(me, {l.X, l.Y, l.Z - 2000, 0, r.Yaw, 0, cls = cls}, me_at)   -- (made out of sight)
            spawned_this_frame, warm_t = true, t
            if c then park(c, t) end
            return
        end
    end
end

local cam_f = nil                              -- (the camera file, kept open)

-- The game's mode on the loaded stage: the race event the game made for it (its game state's RaceEventManagerComponent
-- .RaceEvent; checked in the game 2026-11-19): a Rally Weekend's (BC_RaceEventRally_C) has a
-- RaceEventRaceSettingsRallyWeekendComponent, a Single Rally Stage's is BC_RaceEventSingleEvent_C, Free Practice's
-- BC_RaceEventFreePractice_C, Time Attack's BC_RaceEventTimeAttack_C. -> 'weekend', 'single', 'practice', 'timeattack',
-- 'championship', 'other' (a race event, none of those), 'none' (no race event: the menus), 'unknown' (can't be told:
-- the game changed). The app counts a daily's or a time trial's run only in 'weekend' (app.py game_mode); the
-- game's save can't tell it before the finish (it writes the Rally Weekend once the stage is over).
local RW_SETTINGS = nil
local mode_now, mode_event, mode_frame = "none", nil, -1000

-- The race's settings on the loaded stage, as the game runs it (its race event's settings component: the fields of
-- RaceEventRaceSettingsComponent, probed in the game 2026-11-19, docs/hardcore-and-assists.md): manual respawn (0 off,
-- 1 full, 2 realistic), damage on (0 / 1), collisions, wear, mechanical failures (0 off, 1 light, 2 severe, 3
-- realistic), penalties (0 off, 1 light, 2 realistic), Hardcore (0 / 1), tyre damage (0 off, 1 light, 2 realistic, 3
-- severe) -> "rdcwfpht", one digit each, for the camera line (one word: a value can't be taken for the line's <seq>,
-- which ends each group); nil without a race event. The app checks them against the event's
-- rules on the start line (app.py settings_changed): a change in the game's menus is told before the run, not after.
-- (Only plain fields are read: reading every kind of field of the race event crashed the game in the probe.)
local settings_comp, settings_event, settings_now = nil, nil, nil
-- A search through every object of the engine (FindAllOf) that found nothing is not made again for MISS_S: such
-- searches, two to four times a second on the game's thread while a level loads (the race event there, the things
-- searched for not yet), slowed its loading screens to minutes (seen 24 Nov 2026).
local MISS_S = 5.0
local missed_at = {}
local function may_search(what)
    local t = os.clock()
    local at = missed_at[what]
    if at and t - at < MISS_S then return false end
    missed_at[what] = nil
    return true
end
local function search_missed(what) missed_at[what] = os.clock() end
local SETTINGS_LIB = nil
local function game_settings_comp(ev)
    -- the race's settings component as the game itself gets it (what DRIVE writes, drive.lua), if it is this race
    -- event's. A search by owner alone can find another settings component of the same race event (a stage restarted,
    -- 25 Nov 2026: read as all Off, a DNF the stewards cancelled)
    if not (SETTINGS_LIB and SETTINGS_LIB:IsValid()) then
        SETTINGS_LIB = StaticFindObject("/Script/acr.Default__RaceEventUtilsFunctionLibrary")
    end
    local c = SETTINGS_LIB:GetRaceEventRaceSettingsComponent(UEHelpers.GetPlayerController())
    if c and c:IsValid() and c:GetOuter():GetAddress() == ev:GetAddress() then return c end
    return nil
end
local rules_comp, rules_event = nil, nil         -- (game_settings_comp's, for the values; settings_comp: the calendar too)
local function read_settings(ev)
    local at = ev:GetAddress()
    if rules_event ~= at or not (rules_comp and rules_comp:IsValid()) then
        local ok, c = pcall(game_settings_comp, ev)
        rules_comp, rules_event = ok and c or nil, at
    end
    if (settings_event ~= at or not (settings_comp and settings_comp:IsValid())) and
            (settings_event ~= at or may_search("settings")) then
        settings_comp, settings_event = nil, at
        for _, o in ipairs(FindAllOf("RaceEventRaceSettingsComponent") or {}) do
            local ok, mine = pcall(function()
                local outer = o:GetOuter()
                return outer and outer:IsValid() and outer:GetAddress() == at
            end)
            if ok and mine then settings_comp = o end
        end
        if not settings_comp then search_missed("settings") end
    end
    local s = (rules_comp and rules_comp:IsValid()) and rules_comp or settings_comp
    if not s then return nil end
    local o = s.RaceOptions
    local d = o.CarDamage
    local function b(x) return x and 1 or 0 end
    return string.format("%d%d%d%d%d%d%d%d", o.Respawn.ManualRespawn, b(d.bDamagesEnabled), d.Collisions, d.Wear,
        d.MechanicalFailures, s.RacePenaltyOptions.RacePenalty, b(s.HardCoreOptions.bHardCore),
        o.TyreManagement.TyresDamage)
end

-- The player's driving aids (probed 2026-11-19, docs/hardcore-and-assists.md): their race participant (the
-- BC_RaceParticipant_C whose ID is the player state's ParticipantId, LOCAL_PLAYER; in this level), its
-- RaceParticipantData.DrivingAids as the race applies them: gearbox (0 manual, 1 automatic), ABS, TC, starting handbrake
-- assist, clutch (0 manual, 1 automatic) -> "gatbc"; and the game's race viewmodel (the UI's own, UIViewmodelManager:
-- what the car's dash shows, aids switched in the car too): ABS, TC, gearbox, clutch -> "atgc". The app checks them
-- against an event without aids on the start line, and any change during a stage is a DNF (app.py _watch_run).
local aid_part, aid_event, aid_vm = nil, nil, nil
local function bit(x) return x and 1 or 0 end
local function read_aids(ev)
    local at = ev:GetAddress()
    if (aid_event ~= at or not (aid_part and aid_part:IsValid())) and (aid_event ~= at or may_search("aids")) then
        aid_part, aid_event = nil, at
        local want = UEHelpers.GetPlayerController().PlayerState.ParticipantId:ToString()
        local level = ev:GetOuter():GetAddress()
        for _, o in ipairs(FindAllOf("BC_RaceParticipant_C") or {}) do
            local ok, mine = pcall(function()
                return o.ID:ToString() == want and o:GetOuter():GetAddress() == level
            end)
            if ok and mine then aid_part = o.RaceParticipantData end
        end
        if not aid_part then search_missed("aids") end
    end
    if not (aid_vm and aid_vm:IsValid()) and may_search("viewmodel") then
        aid_vm = nil
        for _, o in ipairs(FindAllOf("ViewmodelRace") or {}) do
            local ok, n = pcall(function() return o:GetFullName() end)
            if ok and n:find("UIViewmodelManager", 1, true) then aid_vm = o end
        end
        if not aid_vm then search_missed("viewmodel") end
    elseif not (aid_vm and aid_vm:IsValid()) then
        aid_vm = nil
    end
    local a, v = nil, nil
    if aid_part and aid_part:IsValid() then
        local d = aid_part.DrivingAids
        a = string.format("%d%d%d%d%d", d.Transmission, bit(d.bABSEnabled), bit(d.bTCSEnabled),
            bit(d.bHandbrakeStartingHelp), bit(d.bAutomaticClutch))
    end
    if aid_vm then
        local ok, s = pcall(function()
            return string.format("%d%d%d%d", bit(aid_vm.ABSEnabled), bit(aid_vm.TCSEnabled), aid_vm.Transmission,
                bit(aid_vm.bAutoClutch))
        end)
        v = ok and s or nil
    end
    return a, v
end
local aids_now, dash_now = nil, nil

-- An event without driving aids (the app's aidsOff, appui.lua -> _G.ACRDAILY_AIDS_OFF: only while its run waits on the
-- start line, never once its clock runs): ABS, traction control and the starting handbrake assist switched off for the
-- player, the game's own way (the participant's DrivingAids, then OnRep_DrivingAids: probed 19 Nov 2026,
-- docs/hardcore-and-assists.md), so DRIVE is never what makes the run not count (the user, 25 Nov 2026). The player's
-- own settings (Driving Assists) are left as they are: the next race takes them again. a / v: read_aids'.
local aids_forced_at = -10
local function force_aids_off(a, v)
    local on = (a and (a:sub(2, 2) == "1" or a:sub(3, 3) == "1" or a:sub(4, 4) == "1")) or
               (v and (v:sub(1, 1) == "1" or v:sub(2, 2) == "1"))
    if not on or not (aid_part and aid_part:IsValid()) then return end
    local now = os.clock()
    if now - aids_forced_at < 1.0 then return end         -- (once a second at most: the game applies it at once)
    aids_forced_at = now
    local d = aid_part.DrivingAids
    d.bABSEnabled = false
    d.bTCSEnabled = false
    d.bHandbrakeStartingHelp = false
    aid_part:OnRep_DrivingAids()
    log("aids: ABS, TC and the starting handbrake assist switched off (the event has none; were %s %s)",
        tostring(a), tostring(v))
end

-- The Rally Weekend's stage being driven as the game runs it (0.2): its track, weather, start time, time speed,
-- wetness, grip, random / dynamic weather, and its place in the calendar, to %APPDATA%\ACR Daily\ingame-setup.txt
-- ("ACRSETUP <n> <track> <weather> <seconds> <speed> <wet %> <grip> <random> <dynamic> <index> <ours>" / "ACRSETUP <n> none",
-- then "end <n>"), written when it changes. A run set up in the running game (drive.lua) is checked against it: the
-- game's save holds the set-up only once its results screen is left (it showed the one before as the screen came up,
-- 20 Nov 2026), so the app can't judge such a run from the save's first write (ingamedrive.py setup_changed).
local SETUP_FILE = DIR .. "ingame-setup.txt"
local UTIL = nil
local setup_now, setup_written, setup_f, setup_n = nil, false, nil, 0
local function read_setup(ev)
    local s = settings_comp                              -- (read_settings': this race event's settings)
    if not (s and s:IsValid()) then return nil end
    if not (UTIL and UTIL:IsValid()) then UTIL = StaticFindObject("/Script/acr.Default__RaceEventUtilsFunctionLibrary") end
    local i = UTIL:GetRallyWeekendSubEventIndex(UEHelpers.GetPlayerController())
    local sub = s.RallyWeekendCalendar.RallyWeekendSubEvents[i + 1]
    if not sub then return nil end
    local w = sub.WeatherOptions
    -- (last: did ACR DAILY take the game here? appui.lua's _G.ACRDAILY_OURS: 1 / 0, "-" with no appui)
    local o = rawget(_G, "ACRDAILY_OURS")
    return string.format("%s %d %d %d %d %d %d %d %d %s", sub.TrackId:ToString(), w.Preset.WeatherType,
        math.floor(w.StartingTime.TimeSeconds + 0.5), w.TimeSpeed, math.floor(w.StartingWetness * 100 + 0.5),
        w.StartingGripLevel, w.Preset.bRandom and 1 or 0, w.bDynamicWeather and 1 or 0, i,
        o == nil and "-" or (o and "1" or "0"))
end
local function write_setup()
    local line = setup_now or "none"
    if line == setup_written then return end
    if not setup_f then setup_f = io.open(SETUP_FILE, "w") end
    if not setup_f then return end
    setup_n = setup_n + 1
    local body = string.format("ACRSETUP %d %s\nend %d\n", setup_n, line, setup_n)
    setup_f:seek("set", 0)
    setup_f:write(body .. string.rep(" ", 120 - #body))
    setup_f:flush()
    setup_written = line
end

local function race_mode()
    if frame - mode_frame < 30 then return mode_now end   -- (twice a second is enough: it changes with a level)
    mode_frame = frame
    settings_now, aids_now, dash_now = nil, nil, nil
    setup_now = nil                                     -- (read again below for a Rally Weekend's race event)
    local ok, m = pcall(function()
        local world = UEHelpers.GetWorld()
        if not (world and world:IsValid()) then return "none" end
        local gs = world.GameState
        if not (gs and gs:IsValid()) then return "none" end
        local rem = gs.RaceEventManagerComponent
        if not (rem and rem.IsValid and rem:IsValid()) then return "none" end
        local ev = rem.RaceEvent
        if not (ev and ev.IsValid and ev:IsValid()) then return "none" end
        local sok, s = pcall(read_settings, ev)
        settings_now = sok and s or nil
        if mode_now == "weekend" and mode_event == ev:GetAddress() then
            local wok, w = pcall(read_setup, ev)
            setup_now = wok and w or nil
        end
        local aok, a, v = pcall(read_aids, ev)
        if aok then aids_now, dash_now = a, v end
        if aok and rawget(_G, "ACRDAILY_AIDS_OFF") then
            local fok, fe = pcall(force_aids_off, a, v)
            if not fok then log("aids: %s", tostring(fe)) end
        end
        local at = ev:GetAddress()
        if at == mode_event and mode_now ~= "unknown" and mode_now ~= "none" then return mode_now end
        mode_event = at
        if not (RW_SETTINGS and RW_SETTINGS:IsValid()) then
            RW_SETTINGS = StaticFindObject("/Script/acr.RaceEventRaceSettingsRallyWeekendComponent")
        end
        if not (RW_SETTINGS and RW_SETTINGS:IsValid()) then return "unknown" end
        local comps = ev:K2_GetComponentsByClass(RW_SETTINGS)
        if comps and #comps > 0 then return "weekend" end
        local cn = ev:GetClass():GetFName():ToString():lower()
        if cn:find("singleevent", 1, true) then return "single" end
        if cn:find("practice", 1, true) then return "practice" end       -- (BC_RaceEventFreePractice_C)
        if cn:find("timeattack", 1, true) then return "timeattack" end   -- (BC_RaceEventTimeAttack_C)
        if cn:find("championship", 1, true) then return "championship" end
        return "other"
    end)
    if not ok then log("mode: %s", tostring(m)) end
    pcall(write_setup)
    local was = mode_now
    mode_now = ok and m or "unknown"
    if mode_now ~= was then log("mode: %s", mode_now) end
    return mode_now
end

-- The penalties on the stage so far, as the game keeps them while it runs (RacePenaltyPlayerData: PenaltyTotalTime in
-- seconds, bDisqualify; probed 22 Nov 2026). The stage clock stops at the finish line, so the clock plus these is the
-- time with penalties there, before the results screen and the loading after it (the game hangs on that loading, often
-- on Turini, and saves nothing: the user, 22 Nov 2026). The app keeps what it read at the finish and uses it only if the
-- game never saves the run's result.
penalty_now = nil                -- {ms, disqualified 0/1}, or nil (no stage, none found)
local pen_obj, pen_name, pen_look, penalty_seen = nil, nil, -1e9, nil
local function read_penalty(t)
    if t - pen_look < 0.25 then return end
    pen_look = t
    local ok_s, same = pcall(function() return pen_obj and pen_obj:IsValid() and pen_obj:GetFullName() == pen_name end)
    if not (ok_s and same) and not may_search("penalty") then
        pen_obj, penalty_now = nil, nil
        return
    end
    if not (ok_s and same) then
        -- yours: the one on your player state (the stage's other cars, the game's AI, have their own: 22 Nov 2026)
        pen_obj, pen_name = nil, nil
        local mine = nil
        pcall(function()
            local ps = UEHelpers.GetPlayerController().PlayerState
            mine = ps:GetFullName():match("^%S+%s+(.+)$")
        end)
        if mine then
            for _, x in ipairs(FindAllOf("RacePenaltyPlayerData") or {}) do
                local okn, n = pcall(function() return x:GetFullName() end)
                if okn and x:IsValid() and n:find(mine .. ".", 1, true) then
                    pen_obj, pen_name = x, n
                    break
                end
            end
        end
        if not pen_obj then search_missed("penalty") end
        if pen_name ~= penalty_seen then
            penalty_seen = pen_name
            log("penalties read from %s", tostring(pen_name))
        end
    end
    if not pen_obj then
        penalty_now = nil
        return
    end
    local ok, ms, dq = pcall(function()
        return math.floor((pen_obj.PenaltyTotalTime or 0) * 1000 + 0.5), pen_obj.bDisqualify and 1 or 0
    end)
    penalty_now = ok and {ms, dq} or nil
end

-- Your car's livery as the game has it on now (its AcrLivery ID: the official row, or "usergen_<folder>": probed 22 Nov
-- 2026), to ingame-livery.txt when it changes: the app sends it with your car, and those watching you see it.
local LIVERY_FILE = DIR .. "ingame-livery.txt"
local livery_said, livery_look = nil, -1e9
local function tell_livery(me, t)
    if t - livery_look < 2.0 then return end
    livery_look = t
    if rawget(_G, "watching") then return end          -- (WATCH paints your car in theirs: not yours)
    local ok, id = pcall(function() return me.LiveryCustomization.CurrentLivery.ID:ToString() end)
    if not ok or not id or id == "" or id == "None" or id == livery_said then return end
    local f = io.open(LIVERY_FILE, "w")
    if f then
        f:write(id .. "\n")
        f:close()
        livery_said = id
    end
end

-- Your car's damage, to ingame-damage.txt 4 times a second while you have a car (the app keeps what it says at the
-- finish line and sends it with the stage: after a crash of the game past the line, the next stage starts with the car
-- as it finished, drive.lua; the user, 24 Nov 2026). Each damageable part's life points (100: intact), as the game keeps
-- them on the car's CarDamageComponent (NamedParts), only those below 100:
--   ACRDMG <seq> <part>=<life points> ... end <seq>      (or "ACRDMG <seq> none end <seq>": no car of yours)
-- (kept open and written over in place, padded, as the camera file: probed in the game 24 Nov 2026)
local DAMAGE_FILE = DIR .. "ingame-damage.txt"
local dmg_f, dmg_seq, dmg_comp, dmg_of, dmg_look = nil, 0, nil, nil, -1e9
local function car_damage_comp(car)
    -- the car's own CarDamage component (a property of the game's car blueprint), looked up once per car. Never by
    -- FindAllOf: walking every object of the engine 4 times a second slowed the game's loading screens from 1 minute to
    -- 6 and more (seen 24 Nov 2026, while there was no car to find)
    local at = car:GetAddress()
    if dmg_of == at then
        if dmg_comp == false then return nil end
        local ok, valid = pcall(function() return dmg_comp:IsValid() end)
        if ok and valid then return dmg_comp end
    end
    dmg_comp, dmg_of = false, at
    local ok, c = pcall(function() return car.CarDamage end)
    if ok and c and c.IsValid and c:IsValid() then dmg_comp = c end
    return dmg_comp or nil
end
function car_parts(car)
    -- {part = life points} of a car's damageable parts (every part), or nil
    local comp = car and car_damage_comp(car)
    if not comp then return nil end
    local out = {}
    comp.NamedParts:ForEach(function(k, v)
        local p = v:get()
        out[k:get():ToString()] = p.LifePoints
    end)
    return out
end
local function write_damage(me, t)
    if t - dmg_look < 0.25 then return end
    dmg_look = t
    if not dmg_f then
        dmg_f = io.open(DAMAGE_FILE, "w")
        if not dmg_f then return end
    end
    dmg_seq = dmg_seq + 1
    local words = {}
    -- past the finish line: the car as it crossed it (drive.lua keeps it, ACRDAILY_FINISH), not what came after
    local fin = rawget(_G, "ACRDAILY_FINISH")
    local parts = fin and fin.parts or (me and car_parts(me))
    if parts then
        for k, lp in pairs(parts) do
            if type(lp) == "number" and lp < 99.95 then words[#words + 1] = string.format("%s=%.1f", k, lp) end
        end
        table.sort(words)
    else
        words[1] = "none"
    end
    local line = string.format("ACRDMG %d %s end %d", dmg_seq, table.concat(words, " "), dmg_seq)
    dmg_f:seek("set", 0)
    dmg_f:write(line .. string.rep(" ", math.max(0, 1500 - #line)) .. "\n")
    dmg_f:flush()
end

local function write_camera(pc)
    local cm = pc and pc.PlayerCameraManager
    if not (cm and cm:IsValid()) then return end
    if not cam_f then
        cam_f = io.open(CAMERA_FILE, "w")          -- (made once; then overwritten in place)
        if not cam_f then return end
    end
    local l, r = cm:GetCameraLocation(), cm:GetCameraRotation()
    cam_seq = cam_seq + 1
    local line = string.format("CAM %d %.2f %.2f %.2f %.4f %.4f %.4f %.4f %d", cam_seq, l.X, l.Y, l.Z, r.Pitch, r.Yaw,
        r.Roll, cm:GetFOVAngle(), cam_seq)
    -- the game's mode (race_mode): "M <mode> <seq>"; the race's settings (read_settings): "S <rdcwfpht> <seq>"
    line = line .. string.format(" M %s %d", race_mode(), cam_seq)
    if names_by_game then line = line .. string.format(" N 1 %d", cam_seq) end
    if settings_now then line = line .. string.format(" S %s %d", settings_now, cam_seq) end
    -- the player's driving aids (read_aids): "A <gatbc> <seq>", the car's as its dash shows them: "V <atgc> <seq>"
    if aids_now then line = line .. string.format(" A %s %d", aids_now, cam_seq) end
    if dash_now then line = line .. string.format(" V %s %d", dash_now, cam_seq) end
    -- WATCH: the camera shot on now (tv, onboard, heli...): "W <shot> <seq>" (the app's broadcast shows it)
    -- the penalties the game has given on this stage so far: "P <ms> <disqualified 0/1> <seq>" (read_penalty)
    if penalty_now then line = line .. string.format(" P %d %d %d", penalty_now[1], penalty_now[2], cam_seq) end
    -- COPILOT: the game's own co-driver off (codriver_off): "C <1/0> <seq>"
    if codriver_now then line = line .. string.format(" C %d %d", codriver_now, cam_seq) end
    local shot = rawget(_G, "ACRDAILY_SHOT")
    if shot then line = line .. string.format(" W %s %d", shot, cam_seq) end
    -- the cars hidden in your car (near_hide, last frame): "H <id>... <seq>", so the app draws no name over them either
    -- (an older app reads the line up to the first <seq> only)
    local hidden = {}
    for id, c in pairs(cars) do
        if c.near then hidden[#hidden + 1] = id end
    end
    if #hidden > 0 then
        local tail = string.format(" %d", cam_seq)
        local add = " H"
        for _, id in ipairs(hidden) do
            if #line + #add + #id + 1 + #tail > 159 then break end   -- (the line stays 160 characters at most)
            add = add .. " " .. id
        end
        line = line .. add .. tail
    end
    cam_f:seek("set", 0)                            -- (always 160 characters: a shorter line leaves nothing of the last)
    cam_f:write(line .. string.rep(" ", math.max(0, 159 - #line)) .. "\n")
    cam_f:flush()
    -- (where the camera is: near_hide; and which way it looks: the names over the cars, hud.lua)
    return {X = l.X, Y = l.Y, Z = l.Z, P = r.Pitch, Yw = r.Yaw, R = r.Roll, fov = cm:GetFOVAngle()}
end

local trace_check = -1

local function trace_frame(t)
    if frame - trace_check >= 120 then              -- (looked for every 120 frames)
        trace_check = frame
        local on = io.open(TRACE_FLAG, "r")
        if on then on:close() end
        if on and not trace then
            trace = io.open(DIR .. "ghost-trace.txt", "w")
        elseif not on and trace then
            trace:close()
            trace = nil
        end
    end
    if not trace then return end
    if frame % 120 == 0 and offset then trace:write(string.format("# offset %.4f\n", offset)) end
    for id, c in pairs(cars) do
        if c.shown then
            local p = c.shown
            -- (then the game's own frame length and, on a path, the driver's clock it is drawn at: testing)
            trace:write(string.format("%d %.4f %s %.1f %.1f %.1f %.3f %.4f %.4f\n", frame, t, id, p[1], p[2], p[3], p[5],
                                      last_delta or 0, c.pc or 0))
        end
    end
end

-- WATCH (0.2, the app's watch.py): the game's camera on another driver's car, the one the app names in ingame-ghosts.txt
-- ("watch <id> <camera>"): a camera of our own (a CameraActor), placed every frame round that car, the player's view
-- set to it (SetViewTargetWithBlend); back on the player's car when the app stops naming one.
-- As a rally's TV broadcast (the user, 21 Nov 2026: "the camera should be like TV, sometimes TV sometimes cockpit"):
--   tv       a camera by the road ahead of the car (the app's "route" line: the road's next few hundred metres), still,
--            turning and zooming to keep the car framed as it comes and goes past; the next one when it has gone
--   onboard  on the roof, looking down the road; bonnet: on the bonnet; wheel: on its right flank, by the rear wheel
--   heli     high and far, drifting after it; chase / far / high / side / front: round it, following its heading
--   auto     the director: cuts between them (a TV camera most, onboards, the helicopter...), each held a few seconds
watching = nil                   -- {id, cam} from the app's file, or nil
watch_route = nil                -- the road ahead of the followed car: {{X, Y}...} (the app's "route" line), or nil
local W = {cam = nil, world = nil, on = false, yaw = nil, t = nil, loc = nil, set_t = -1e9, shot = nil, last = nil,
           aim = nil, fov = nil, heli = nil}
local VIEWS = {chase = {-650, 0, 210, 70}, far = {-1250, 0, 420, 60}, high = {-700, 0, 1250, 60},
               side = {80, 620, 140, 55}, front = {760, 0, 150, 55}}       -- along, across, up (cm), field of view
-- on the car (cm from its root, on the ground under its middle): forward, left, up; pitch (down -), yaw (degrees), fov
local MOUNTS = {onboard = {35, 0, 152, -7, 0, 80}, bonnet = {170, 0, 98, -3, 0, 84}, wheel = {-60, -112, 52, -2, -5, 86}}
-- the director's choices: how often, how long (s)
local AUTO = {{"tv", 5}, {"incar", 2.0}, {"onboard", 1.6}, {"chase", 1.6}, {"cockpit", 1.0}, {"heli", 0.8},
              {"wheel", 1.0}, {"bonnet", 0.8}, {"side", 0.6}}
local HOLD = {onboard = {7, 11}, bonnet = {5, 8}, wheel = {4, 6}, chase = {5, 8}, heli = {6, 9}, side = {4, 6},
              far = {5, 8}, high = {5, 8}, front = {4, 6}, incar = {6, 10}, cockpit = {6, 10}, seat = {6, 10}}
-- inside the car: the game's own camera points on it (AcrCameraComponents: the driver's eyes, between the two
-- crew's heads as the TV's in-car shot; 22 Nov 2026: "is there no cockpit view?")
-- seat: the passenger seat (the user, 25 Nov 2026: the co-driver "is basically in the backseat", next to the driver):
-- the driver's eye point mirrored across the car's centre line, looking where it looks
local CAR_CAMS = {cockpit = "FirstPerson", incar = "BetweenHeads", seat = "FirstPerson"}

local function watch_camera()
    local world = UEHelpers.GetWorld()
    if W.cam and W.cam:IsValid() and W.world == world:GetAddress() then return W.cam end
    local gs = UEHelpers.GetGameplayStatics()
    local tr = {Rotation = {X = 0.0, Y = 0.0, Z = 0.0, W = 1.0}, Translation = {X = 0.0, Y = 0.0, Z = 0.0},
                Scale3D = {X = 1.0, Y = 1.0, Z = 1.0}}
    local a = gs:BeginDeferredActorSpawnFromClass(world, StaticFindObject("/Script/Engine.CameraActor"), tr, 1, nil, 0)
    if not (a and a:IsValid()) then return nil end
    gs:FinishSpawningActor(a, tr, 0)
    -- (the whole screen, not 16:9 with black bars at its sides on a wider one)
    pcall(function() a.CameraComponent:SetConstraintAspectRatio(false) end)
    pcall(function() a.CameraComponent.bConstrainAspectRatio = false end)
    W.cam, W.world = a, world:GetAddress()
    return a
end

-- the game's race display (its timer, gaps, speedometer: the player's car's) put away while watching, and back
local hud_was = nil
function game_hud(on)
    for _, w in ipairs(FindAllOf("WB_MainGameHUD_C") or {}) do
        local ok, n = pcall(function() return w:GetFullName() end)
        if ok and w:IsValid() and n:find("/Engine/Transient", 1, true) then
            if not on then
                if hud_was == nil then hud_was = w:GetVisibility() end
                if w:GetVisibility() ~= 1 then w:SetVisibility(1) end      -- (ESlateVisibility::Collapsed)
            elseif hud_was ~= nil then
                w:SetVisibility(hud_was)
            end
        end
    end
    if on then hud_was = nil end
end

-- The car followed heard (the user, 22 Nov 2026: "Do ghosts support sound? It's pretty quiet"): a ghost's own sound is
-- off (trim: it follows the car's physics, which a ghost has none of), so its engine and exhaust (the game's FMOD
-- events, CarAudio.EngineEvent / ExhaustEvent, its bank loaded) are played on it by the mod, fed the revs and throttle
-- the app sends (wdash: their dash, or worked out from how the car moves). The event parameters are the game's own
-- (in acr.exe: "Engine.rpmEngine", "Exhaust.loadEngine", ...). Heard from where the camera is: near on an onboard, far
-- on a TV camera.
watch_dash = nil                 -- {rpm, load, gear} from the app's file, or nil
local SND = {car = nil, parts = {}, rpm = nil, gear = nil, shift_t = nil}
local FMODS = nil
local function sound_off()
    for _, s in ipairs(SND.parts) do
        if s and s:IsValid() then
            pcall(function() s:Stop() end)
            pcall(function() s:K2_DestroyComponent(s) end)
        end
    end
    SND.parts, SND.car, SND.rpm, SND.gear = {}, nil, nil, nil
    if SND.cabin then                                  -- (the game's own camera sets it again from here)
        SND.cabin = nil
        pcall(function() FMODS:SetGlobalParameterByName(FName("cabinFilter"), 0.0, false) end)
    end
end
local function sound_on(c)
    if not (FMODS and FMODS:IsValid()) then FMODS = StaticFindObject("/Script/FMODStudio.Default__FMODBlueprintStatics") end
    if not (FMODS and FMODS:IsValid()) then return end
    local ca = c.actor.CarAudio
    if not (ca and ca:IsValid()) then return end
    pcall(function() if ca.CarBank and ca.CarBank:IsValid() then FMODS:LoadBank(ca.CarBank, true, true) end end)
    for _, ev in ipairs({ca.EngineEvent, ca.ExhaustEvent}) do
        if ev and ev:IsValid() then
            local ok, s = pcall(function()
                return FMODS:PlayEventAttached(ev, c.actor.RootComponent, FName("None"), {X = 0.0, Y = 0.0, Z = 0.0}, 0,
                                               true, true, false)
            end)
            if ok and s and s:IsValid() then
                pcall(function() s:SetParameter(FName("engineTurnOn"), 1.0) end)
                SND.parts[#SND.parts + 1] = s
            end
        end
    end
    log("watch: sound on (%d parts)", #SND.parts)
end
local function sound_tick(c, id, t, dt)
    local d = watch_dash
    if not d then
        if SND.car then sound_off() end
        return
    end
    if SND.car ~= id or (SND.parts[1] and not SND.parts[1]:IsValid()) then
        sound_off()
        SND.car = id
        pcall(sound_on, c)
    end
    -- (the revs eased between the app's updates: no steps in the engine's note)
    SND.rpm = SND.rpm and SND.rpm + (d.rpm - SND.rpm) * math.min(1, dt * 10) or d.rpm
    SND.load = SND.load and SND.load + (d.load - SND.load) * math.min(1, dt * 8) or d.load
    local up = SND.gear and d.gear > SND.gear
    SND.gear = d.gear
    for _, s in ipairs(SND.parts) do
        if s:IsValid() then
            pcall(function()
                s:SetParameter(FName("rpmEngine"), SND.rpm + 0.0)
                s:SetParameter(FName("loadEngine"), SND.load + 0.0)
                if up then s:SetParameter(FName("triggerGearUp"), 1.0) SND.shift_t = t end
                if SND.shift_t and t - SND.shift_t > 0.1 then s:SetParameter(FName("triggerGearUp"), 0.0) end
            end)
        end
    end
    if SND.shift_t and t - SND.shift_t > 0.1 then SND.shift_t = nil end
    -- heard as from where the camera is: the sound's place and distance follow the camera by themselves (it is the
    -- player's view: the listener); inside the car the game muffles the engine with its global "cabinFilter" (in its
    -- sound banks: camera/cabinFilter), set by its own camera, not WATCH's: set here by the shot (the user, 22 Nov 2026:
    -- "the sound of the car changes according to the camera's view?")
    local inside = (W.shot and (W.shot.name == "cockpit" or W.shot.name == "incar" or W.shot.name == "seat")) and 1.0 or 0.0
    if inside ~= SND.cabin or frame % 30 == 0 then
        SND.cabin = inside
        pcall(function() FMODS:SetGlobalParameterByName(FName("cabinFilter"), inside, false) end)
    end
end

-- The co-driver calling the followed car's notes on in-car and cockpit shots (the user, 22 Nov 2026: "when in cockpit or
-- in car we should be able to hear the copilot giving out notes"): the game's pacenotes follow the pawn its
-- PacenoteStateComponent names (OnPossessedPawnChanged: probed 22 Nov 2026), pointed at the ghost meanwhile, back at
-- your car otherwise.
-- The car followed in its driver's own livery (the user, 22 Nov 2026: "we should be able to see THEIR LIVERY"). The game
-- paints only the player's car (PlayerCustomization:ApplyLivery; aimed at a ghost it did nothing: probed 22 Nov 2026), so
-- your car, out of sight while watching, is painted in it, and its finished paint (its meshes' materials) put on the
-- ghost; the ghost's own put back when another car is followed or WATCH ends. One at a time: the paint is shared, your
-- car's next painting repaints the ghost too (seen 22 Nov 2026).
watch_livery = nil               -- the livery name the app gives for the car followed ("usergen_<folder>" or a row)
local LIV = {car = nil, name = nil, saved = nil, copy_at = nil, ghost = nil}
local LIVERY_BAKE_S = 3.0
local function mesh_comps(a)
    local out = {}
    local list = a:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.MeshComponent"))
    local function add(c) if c and c.IsValid and c:IsValid() then out[c:GetFName():ToString()] = c end end
    if type(list) == "table" then for _, c in pairs(list) do add(c.get and c:get() or c) end
    else list:ForEach(function(_, e) add(e:get()) end) end
    return out
end
-- The ghost's own paint is NOT put back: once swapped for yours nothing in the game holds its old materials (a Lua
-- reference doesn't keep a UObject alive), the game frees them, and SetMaterial with one CRASHED the game (null + 0x38
-- in SetMaterial, the user's game 22 Nov 22:28 and 24 Nov 08:47, both as the car followed finished: WATCH off put the
-- paint back). A painted ghost keeps that paint and is never kept for another driver (park: removed when it goes);
-- not removed here either: the game's pace notes may still point at it (notes_follow), and a removed car there is the
-- same kind of crash.
local function livery_restore()
    LIV.ghost, LIV.saved, LIV.copy_at = nil, nil, nil
end
local function livery_tick(c, me, t)
    local name = watch_livery
    if name == "-" then name = nil end
    if LIV.ghost ~= c or LIV.name ~= name then
        livery_restore()
        LIV.ghost, LIV.name = c, name
        if not name or not (me and me:IsValid()) then return end
        local pcc = nil
        for _, x in ipairs(FindAllOf("PlayerCustomizationComponent") or {}) do
            local n = x:GetFullName()
            if n:find("PersistentLevel", 1, true) and n:find("RacePlayerController", 1, true) then pcc = x end
        end
        if not pcc then return end
        if name:sub(1, 8) == "usergen_" then pcall(function() FindFirstOf("LiveryCustomizationSubsystem"):OnDbInited() end) end
        local ok = pcall(function() pcc:ApplyLivery(FName(name)) end)
        LIV.copy_at = ok and t + LIVERY_BAKE_S or nil
        log("watch: livery %s for the car followed: %s", name, ok and "painting" or "failed")
        return
    end
    if LIV.copy_at and t >= LIV.copy_at and c.actor:IsValid() and me and me:IsValid() then
        LIV.copy_at = nil
        local mine, theirs, saved, n = mesh_comps(me), mesh_comps(c.actor), {}, 0
        for cname, mc in pairs(mine) do
            local gc = theirs[cname]
            if gc then
                local k = 0
                pcall(function() k = mc:GetNumMaterials() end)
                for i = 0, k - 1 do
                    pcall(function()
                        local m = mc:GetMaterial(i)
                        if m and m:IsValid() then
                            saved[cname] = true          -- (painted: never pooled, park)
                            gc:SetMaterial(i, m)
                            n = n + 1
                        end
                    end)
                end
            end
        end
        LIV.saved = n > 0 and saved or nil
        if n > 0 then c.painted = true end                -- (never kept for another driver: park)
        log("watch: livery on the car followed (%d paints)", n)
    end
end

-- the driver's parts of a ghost (not the co-driver's): Driver, HelmetDriver, HansDriver, SuitDriver, GlovesDriver...
function driver_visible(c, on, co)       -- (co: the co-driver's figure instead: hidden on the passenger-seat shot)
    for _, part in ipairs(c.crew or {}) do
        local ok, n = pcall(function() return part:GetFName():ToString() end)
        local is_co = ok and n:lower():find("codriver", 1, true) ~= nil
        if ok and part:IsValid() and n:find("river", 1, true) and (co and is_co or (not co and not is_co and n:find("Driver", 1, true))) then
            part:SetVisibility(on and c.crew_shown and c.detail ~= false, false)
        end
    end
end

-- COPILOT (the app's copilot.py; appui.lua sets _G.ACRDAILY_COPILOT while a COPILOT stage is on): the game's own co-driver
-- off, for the crew's driver (their co-driver reads the notes over voice) and for their co-driver (watching the driver's
-- car: no game voice to repeat). Its notes stop moving on (PacenoteStateComponent and PacenoteAudioComponent: their tick
-- off, the voice's component deactivated) and its notes on screen are collapsed (the pacenote widgets). On the camera
-- line: "C <1/0> <seq>": 1 = its components found and every one off, 0 = not (copilot.py: the driver's run then doesn't
-- count). Looked for again every 2 s (FindAllOf costs: never more often), kept off every 0.25 s. (Classes from the game's
-- .usmap, 24 Nov 2026; not yet seen in the game.)
local CODRIVER = {look = -1e9, found_t = -1e9, world = nil, objs = {}, said = nil}
codriver_now = nil
local function codriver_off(t)
    if not rawget(_G, "ACRDAILY_COPILOT") then
        codriver_now = nil
        if CODRIVER.said ~= nil then CODRIVER.said = nil log("copilot: the game's co-driver left as it is") end
        return
    end
    if t - CODRIVER.look < 0.25 then return end
    CODRIVER.look = t
    local world = UEHelpers.GetWorld()
    local wa = world and world:IsValid() and world:GetAddress() or nil
    if CODRIVER.world ~= wa then CODRIVER.objs, CODRIVER.world, CODRIVER.found_t = {}, wa, -1e9 end
    if t - CODRIVER.found_t > 2.0 then
        CODRIVER.found_t = t
        local list = {}
        for _, cls in ipairs({"PacenoteStateComponent", "PacenoteAudioComponent", "PacenoteCanvasWidget", "PacenoteMainWidget"}) do
            for _, x in ipairs(FindAllOf(cls) or {}) do
                local okn, n = pcall(function() return x:GetFullName() end)
                if okn and not n:find("Default__", 1, true) then
                    list[#list + 1] = {o = x, widget = cls:find("Widget", 1, true) ~= nil, audio = cls == "PacenoteAudioComponent"}
                end
            end
        end
        CODRIVER.objs = list
    end
    local comps, off = 0, 0
    for _, e in ipairs(CODRIVER.objs) do
        pcall(function()
            if not e.o:IsValid() then return end
            if e.widget then
                if e.o:GetVisibility() ~= 1 then e.o:SetVisibility(1) end      -- (ESlateVisibility::Collapsed)
                return
            end
            comps = comps + 1
            if e.o:IsComponentTickEnabled() then e.o:SetComponentTickEnabled(false) end
            if e.audio and not e.deactivated then
                e.o:Deactivate()
                e.deactivated = true
            end
            if not e.o:IsComponentTickEnabled() then off = off + 1 end
        end)
    end
    codriver_now = (comps > 0 and off == comps) and 1 or 0
    local said = string.format("%d of %d off", off, comps)
    if said ~= CODRIVER.said then
        CODRIVER.said = said
        log("copilot: the game's co-driver: %s", said)
    end
end

local NOTES = {on = nil}
local function notes_follow(pc, me, actor)
    local st = nil
    pcall(function()
        for _, x in ipairs(FindAllOf("PacenoteStateComponent") or {}) do
            local n = x:GetFullName()
            if n:find("PersistentLevel", 1, true) and not n:find("Default__", 1, true) then st = x end
        end
    end)
    if not st then return end
    local want = actor or me
    local okc, cur = pcall(function() return st.Pawn end)
    local same = okc and cur and cur:IsValid() and want and want:IsValid() and cur:GetAddress() == want:GetAddress()
    if same then return end
    local ok, e = pcall(function()
        st:OnPossessedPawnChanged((okc and cur and cur:IsValid()) and cur or me, want)
        st.Pawn = want
    end)
    if NOTES.on ~= (actor ~= nil) then
        NOTES.on = actor ~= nil
        log("watch: pace notes for %s: %s %s", actor and "the car followed" or "your car", ok and "ok" or "failed",
            ok and "" or tostring(e))
    end
end

function watch_off(pc, me)
    if NOTES.on then pcall(notes_follow, pc, me, nil) end
    if W.drv_car and W.drv_car.driver_hidden then
        pcall(driver_visible, W.drv_car, true)
        W.drv_car.driver_hidden = false
    end
    if W.drv_car and W.drv_car.codriver_hidden then          -- (the passenger-seat shot hid the co-driver's figure)
        pcall(driver_visible, W.drv_car, true, true)
        W.drv_car.codriver_hidden = false
    end
    W.drv_car = nil
    pcall(livery_restore)
    LIV.name = nil
    sound_off()
    if not W.on then return end
    W.on, W.yaw, W.loc, W.shot, W.aim, W.fov, W.heli, W.fp = false, nil, nil, nil, nil, nil, nil, nil
    _G.ACRDAILY_SHOT = nil
    if pc and pc:IsValid() and me and me:IsValid() then
        pcall(function() pc:SetViewTargetWithBlend(me, 0.5, 0, 0.0, false) end)   -- (5 parameters, not 6)
    end
    if not watching then game_hud(true) end              -- (WATCH still on, nobody to follow: kept away)
    log("watch: off")
end

-- ---- a few sums (vectors as {x, y, z})
local function vadd(a, b, k) k = k or 1 return {a[1] + b[1] * k, a[2] + b[2] * k, a[3] + b[3] * k} end
local function vlen(a) return math.sqrt(a[1] * a[1] + a[2] * a[2] + a[3] * a[3]) end
local function vnorm(a) local l = vlen(a) if l < 1e-6 then return {1, 0, 0} end return {a[1] / l, a[2] / l, a[3] / l} end
local function look_rot(from, to)
    local dx, dy, dz = to[1] - from[1], to[2] - from[2], to[3] - from[3]
    return {Pitch = math.deg(math.atan(dz, math.sqrt(dx * dx + dy * dy))), Yaw = math.deg(math.atan(dy, dx)), Roll = 0.0}
end
local function axes_rot(f, u)
    -- the rotator whose forward is f and whose up is u (as near as it can be)
    local yaw = math.atan(f[2], f[1])
    local pitch = math.asin(math.max(-1, math.min(1, f[3])))
    local sy, cy, sp, cp = math.sin(yaw), math.cos(yaw), math.sin(pitch), math.cos(pitch)
    local y0 = {-sy, cy, 0}
    local z0 = {-sp * cy, -sp * sy, cp}
    local roll = math.atan(u[1] * y0[1] + u[2] * y0[2] + u[3] * y0[3], u[1] * z0[1] + u[2] * z0[2] + u[3] * z0[3])
    return {Pitch = math.deg(pitch), Yaw = math.deg(yaw), Roll = math.deg(roll)}
end

-- the ground at (x, y), looked for from well above to well below z (a TV camera's foot, the road under it)
local function ground_far(world, x, y, z, ignore)
    if not (KSL and KSL:IsValid()) then KSL = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary") end
    local out = {}
    local ok, got = pcall(function()
        return KSL:LineTraceSingle(world, {X = x, Y = y, Z = z + 6000.0}, {X = x, Y = y, Z = z - 8000.0}, 0, false,
                                   ignore, 0, out, true, {R = 0, G = 0, B = 0, A = 0}, {R = 0, G = 0, B = 0, A = 0}, 0.0)
    end)
    if not (ok and got) then return nil end
    local hz = nil
    pcall(function() hz = out.OutHit.ImpactPoint.Z end)
    if hz == nil then pcall(function() hz = out.ImpactPoint.Z end) end
    return hz
end

-- can a camera at a see b? (nothing in the way but within `near` cm of b)
local function clear(world, a, b, ignore, near)
    if not (KSL and KSL:IsValid()) then KSL = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary") end
    local out = {}
    local ok, got = pcall(function()
        return KSL:LineTraceSingle(world, {X = a[1], Y = a[2], Z = a[3]}, {X = b[1], Y = b[2], Z = b[3]}, 0, false,
                                   ignore, 0, out, true, {R = 0, G = 0, B = 0, A = 0}, {R = 0, G = 0, B = 0, A = 0}, 0.0)
    end)
    local function blocked(okk, gott, o)
        if not okk or not gott then return false end
        local hit = nil
        pcall(function() local q = o.OutHit.ImpactPoint hit = {q.X, q.Y, q.Z} end)
        if hit == nil then pcall(function() local q = o.ImpactPoint hit = {q.X, q.Y, q.Z} end) end
        if hit == nil then return true end
        return vlen({b[1] - hit[1], b[2] - hit[2], b[3] - hit[3]}) >= (near or 300)
    end
    if blocked(ok, got, out) then return false end
    -- (and the solid things in the world: trees' trunks have collision for the cars but not for sight, 22 Nov 2026:
    -- "for many cameras you just see trees")
    local out2 = {}
    local ok2, got2 = pcall(function()
        return KSL:LineTraceSingleForObjects(world, {X = a[1], Y = a[2], Z = a[3]}, {X = b[1], Y = b[2], Z = b[3]},
                                            {0, 1}, false, ignore, 0, out2, true, {R = 0, G = 0, B = 0, A = 0},
                                            {R = 0, G = 0, B = 0, A = 0}, 0.0)
    end)
    return not blocked(ok2, got2, out2)
end

-- a TV camera by the road ahead of the car, or nil (no road known, nowhere it sees the road from)
local function tv_place(c, world)
    local R = watch_route
    if not R or #R < 6 then return nil end
    local p = c.shown
    local bi, best = 1, 1e18
    for i, q in ipairs(R) do
        local d = (q[1] - p[1]) ^ 2 + (q[2] - p[2]) ^ 2
        if d < best then bi, best = i, d end
    end
    local function along_to(i)                            -- route index i: how far ahead of the car (cm)
        local s = 0
        for k = bi + 1, i do s = s + math.sqrt((R[k][1] - R[k - 1][1]) ^ 2 + (R[k][2] - R[k - 1][2]) ^ 2) end
        return s
    end
    local wants = {math.random(140, 230) * 100, math.random(90, 140) * 100, math.random(230, 320) * 100}
    for _, want in ipairs(wants) do
        local ai = nil
        for i = bi + 1, #R - 1 do
            if along_to(i) >= want then ai = i break end
        end
        if ai and ai > 1 then
            local dir = vnorm({R[ai + 1][1] - R[ai - 1][1], R[ai + 1][2] - R[ai - 1][2], 0})
            local perp = {-dir[2], dir[1], 0}
            local gz_a = ground_far(world, R[ai][1], R[ai][2], p[3], {c.actor}) or p[3]
            local road = {R[ai][1], R[ai][2], gz_a + 110}
            local sides = math.random() < 0.5 and {1, -1} or {-1, 1}
            for _, s in ipairs(sides) do
                -- (at the road's edge: the road itself is clear; further out it stood in trees and bushes, which the
                -- sight checks don't all see, 21-22 Nov 2026)
                local off = math.random(300, 420)
                local back = math.random(-300, 900)          -- (a little past the bend, or before it)
                local x = R[ai][1] + perp[1] * s * off + dir[1] * back
                local y = R[ai][2] + perp[2] * s * off + dir[2] * back
                local gz = ground_far(world, x, y, gz_a, {c.actor})
                if gz and math.abs(gz - gz_a) < 2500 then
                    local cam = {x, y, gz + math.random(130, 230)}
                    -- it sees the road there, and three places on the road the car comes along
                    local sees = clear(world, cam, road, {c.actor})
                    for _, back_i in ipairs({2, 4, 7}) do
                        if not sees then break end
                        local q = R[math.max(bi + 1, ai - back_i)]
                        local gz_q = ground_far(world, q[1], q[2], gz_a, {c.actor}) or gz_a
                        sees = clear(world, cam, {q[1], q[2], gz_q + 110}, {c.actor}, 500)
                    end
                    if sees then return {pos = cam, road = road} end
                end
            end
        end
    end
    return nil
end

local function pick_shot(mode, t)
    if mode ~= "auto" then return mode end
    local total = 0
    for _, s in ipairs(AUTO) do
        if s[1] ~= W.last and (s[1] ~= "tv" or (watch_route and #watch_route >= 6)) then total = total + s[2] end
    end
    local r = math.random() * total
    for _, s in ipairs(AUTO) do
        if s[1] ~= W.last and (s[1] ~= "tv" or (watch_route and #watch_route >= 6)) then
            r = r - s[2]
            if r <= 0 then return s[1] end
        end
    end
    return "chase"
end

local function new_shot(name, t, c, world)
    local s = {name = name, t0 = t}
    if name == "tv" then
        local at = tv_place(c, world)
        if not at then return nil end
        s.pos, s.min_d, s.blocked = at.pos, 1e18, nil
        s.ends = t + 18
    else
        local h = HOLD[name] or {5, 8}
        s.ends = t + h[1] + math.random() * (h[2] - h[1])
    end
    W.aim, W.fov, W.heli = nil, nil, nil
    return s
end

function watch_tick(pc, me, t)
    if not watching then                                 -- (no WATCH: the race display back, if it was put away)
        watch_off(pc, me)
        if hud_was ~= nil then game_hud(true) end
        return
    end
    local c = watching and cars[watching.id]
    if not (c and c.shown and c.actor:IsValid() and pc and pc:IsValid()) then
        watch_off(pc, me)
        if watching and last_new_t and t - last_new_t < STALE_S then game_hud(false) end   -- (WATCH, nobody yet)
        return
    end
    local cam = watch_camera()
    if not cam then return end
    local world = UEHelpers.GetWorld()
    local dt = W.t and math.min(0.1, math.max(0, t - W.t)) or 0
    W.t = t
    -- The cameras follow a steadied copy of the car (the user, 21 Nov 2026: "it is still laggy"): carried on at the
    -- car's own speed every frame, then drawn a little towards where it is drawn; the small jumps between the app's
    -- updates are ironed out, a real change of course followed within a fraction of a second. A jump (a reset, another
    -- car): taken at once.
    local raw = c.shown
    local fp = W.fp
    if not fp or W.fp_car ~= watching.id or (raw[1] - fp[1]) ^ 2 + (raw[2] - fp[2]) ^ 2 + (raw[3] - fp[3]) ^ 2 > 400 ^ 2 then
        fp = {raw[1], raw[2], raw[3], raw[4], raw[5], raw[6]}
    else
        local v = c.vel or {0, 0, 0, 0, 0, 0}
        local k, ka = math.min(1, dt * 9), math.min(1, dt * 7)
        for i = 1, 3 do fp[i] = fp[i] + v[i] * dt fp[i] = fp[i] + (raw[i] - fp[i]) * k end
        for i = 4, 6 do fp[i] = fp[i] + (v[i] or 0) * dt fp[i] = fp[i] + angle(raw[i] - fp[i]) * ka end
    end
    W.fp, W.fp_car = fp, watching.id
    local p = fp
    -- (which way it goes: from how it moves, not its yaw, whose 0 isn't the model's front on every car: the camera sat
    -- beside the car, 21 Nov 2026; standing still: the last way kept)
    local v = c.vel
    local want = W.yaw
    if v and (v[1] * v[1] + v[2] * v[2]) > 300 * 300 then want = math.deg(math.atan(v[2], v[1])) end
    want = want or p[5]
    W.yaw = W.yaw and W.yaw + angle(want - W.yaw) * math.min(1, dt * 2.5) or want
    -- the shot: kept until its time is up (a TV camera: until the car has gone past), then the director's next
    local mode = watching.cam or "auto"
    local s = W.shot
    if s and (s.mode ~= mode or s.car ~= watching.id) then s = nil end
    if s and t >= s.ends then s = nil end
    if not s then
        for _ = 1, 3 do
            local name = pick_shot(mode, t)
            s = new_shot(name, t, c, world)
            if s then break end
            if mode ~= "auto" then break end
        end
        s = s or new_shot("chase", t, c, world)
        s.mode, s.car = mode, watching.id
        W.last, W.shot = s.name, s
    end
    local loc, rot, fov
    local target = {p[1], p[2], p[3] + 80}
    if s.name == "tv" then
        loc = s.pos
        local d = vlen({target[1] - loc[1], target[2] - loc[2], target[3] - loc[3]})
        if d < s.min_d then s.min_d = d end
        -- gone past (further than its nearest by 30 m), or hidden from it a while: the next shot
        if d > s.min_d + 3000 and s.min_d < 8000 then s.ends = math.min(s.ends, t + 0.2) end
        if frame % 5 == 0 and d < 16000 then
            if clear(world, loc, target, {c.actor}, 350) then s.blocked = nil
            elseif not s.blocked then s.blocked = t
            elseif t - s.blocked > 1.4 and t - s.t0 > 2.5 then s.ends = t end
        end
        if t - s.t0 > 9 and s.min_d > 9000 then s.ends = t end       -- (it isn't coming: the road went elsewhere)
        -- the camera turns after the car a little late, and zooms to keep it about the same size
        W.aim = W.aim and vadd(W.aim, {target[1] - W.aim[1], target[2] - W.aim[2], target[3] - W.aim[3]}, math.min(1, dt * 7)) or target
        rot = look_rot(loc, W.aim)
        local f = math.max(7, math.min(62, math.deg(2 * math.atan(1150 / math.max(1, d)))))
        W.fov = W.fov and W.fov + (f - W.fov) * math.min(1, dt * 3) or f
        fov = W.fov
    elseif CAR_CAMS[s.name] and (function()
        local okc, comp = pcall(function() return c.actor[CAR_CAMS[s.name]] end)
        if not (okc and comp and comp:IsValid()) then return false end
        local l, r = comp:K2_GetComponentLocation(), comp:K2_GetComponentRotation()
        loc, rot = {l.X, l.Y, l.Z}, {Pitch = r.Pitch, Yaw = r.Yaw, Roll = r.Roll}
        if s.name == "seat" then
            local ax = rotation(p[4], p[5], p[6])                -- (the car's left)
            local d = (l.X - p[1]) * ax[1] + (l.Y - p[2]) * ax[2] + (l.Z - p[3]) * ax[3]
            loc = {l.X - 2 * d * ax[1], l.Y - 2 * d * ax[2], l.Z - 2 * d * ax[3]}
        end
        local okf, f = pcall(function() return comp.FieldOfView end)
        fov = (okf and type(f) == "number" and f > 20 and f < 120) and f or 75
        return true
    end)() then
        -- (placed above: the car's own camera point, moving with the car as drawn)
    elseif MOUNTS[s.name] or CAR_CAMS[s.name] then
        local m = MOUNTS[s.name] or MOUNTS.onboard
        local ax, ay, az = rotation(p[4], p[5], p[6])          -- (the car's left, forward, up)
        loc = {p[1] + ay[1] * m[1] + ax[1] * m[2] + az[1] * m[3],
               p[2] + ay[2] * m[1] + ax[2] * m[2] + az[2] * m[3],
               p[3] + ay[3] * m[1] + ax[3] * m[2] + az[3] * m[3]}
        local pt, yw = math.rad(m[4]), math.rad(m[5])
        local f = vadd({ay[1] * math.cos(pt), ay[2] * math.cos(pt), ay[3] * math.cos(pt)}, az, math.sin(pt))
        f = vnorm(vadd({f[1] * math.cos(yw), f[2] * math.cos(yw), f[3] * math.cos(yw)}, ax, math.sin(yw)))
        local u = vnorm(vadd({az[1] * math.cos(pt), az[2] * math.cos(pt), az[3] * math.cos(pt)}, ay, -math.sin(pt)))
        rot = axes_rot(f, u)
        fov = m[6]
    elseif s.name == "heli" then
        -- high and far behind to one side, drifting after the car (a helicopter can't keep up exactly)
        local yr = math.rad(W.yaw)
        local fx, fy = math.cos(yr), math.sin(yr)
        s.side = s.side or (math.random() < 0.5 and 1 or -1)
        local want_at = {p[1] - fx * 2600 - fy * 1500 * s.side, p[2] - fy * 2600 + fx * 1500 * s.side, p[3] + 2300}
        W.heli = W.heli and vadd(W.heli, {want_at[1] - W.heli[1], want_at[2] - W.heli[2], want_at[3] - W.heli[3]},
                                 math.min(1, dt * 0.9)) or want_at
        loc = W.heli
        rot = look_rot(loc, target)
        fov = 38
    else
        local vw = VIEWS[s.name] or VIEWS.chase
        local yr = math.rad(W.yaw)
        local fx, fy = math.cos(yr), math.sin(yr)                 -- (the car's forward, in the game's X / Y)
        loc = {p[1] + fx * vw[1] - fy * vw[2], p[2] + fy * vw[1] + fx * vw[2], p[3] + vw[3]}
        rot = look_rot(loc, {p[1], p[2], p[3] + 90})              -- (looking at the car, a little above its root)
        fov = vw[4]
    end
    crumb("watch: camera " .. tostring(s.name))
    cam:K2_SetActorLocationAndRotation({X = loc[1], Y = loc[2], Z = loc[3]}, rot, false, {}, false)
    pcall(function() cam.CameraComponent:SetFieldOfView(fov + 0.0) end)
    W.loc = {X = loc[1], Y = loc[2], Z = loc[3]}
    _G.ACRDAILY_SHOT = s.name                                  -- (the camera on: the app's broadcast shows it)
    crumb("watch: sound")
    sound_tick(c, watching.id, t, dt)
    -- (its speed, as the game reads a car's: a ghost moved without physics says 0, and the pace notes' look-ahead
    -- goes by the speed along the stage)
    pcall(function()
        local v = c.vel or {0, 0, 0}
        c.actor.RootComponent.ComponentVelocity = {X = v[1] + 0.0, Y = v[2] + 0.0, Z = v[3] + 0.0}
    end)
    crumb("watch: livery")
    pcall(livery_tick, c, me, t)
    if frame % 15 == 0 then
        local inside = s.name == "cockpit" or s.name == "incar" or s.name == "seat"
        crumb("watch: pace notes")
        if not rawget(_G, "ACRDAILY_COPILOT") then          -- (COPILOT: the crew's co-driver reads them, not the game)
            pcall(notes_follow, pc, me, inside and c.actor or nil)
        end
    end
    -- the driver's own figure away on the cockpit shot (the camera is at their eyes: it showed the inside of their
    -- helmet, 22 Nov 2026); back on any other
    local no_driver = s.name == "cockpit"
    -- the steering wheel shown in their car (the interior's bones: hidden on the stage when you drive without the
    -- game's wheel, which took it off the car watched too: "there is no wheel in the broadcast", 22 Nov 2026)
    if not c.wheel_shown and frame % 30 == 0 then
        crumb("watch: steering wheel")
        c.wheel_shown = true
        for _, part in ipairs(c.inside or {}) do
            local okn, n = pcall(function() return part:GetFName():ToString() end)
            if okn and n == "InternalMesh" and part:IsValid() then
                for _, b in ipairs({"ROOT_SteeringWheel", "SM_IntSteeringWheel", "SM_IntSteeringWheelDecals",
                                    "Bone_SteeringColumn", "Bone_SteeringShaft01", "Bone_SteeringShaft02"}) do
                    pcall(function()
                        if part:IsBoneHiddenByName(FName(b)) then
                            part:UnHideBoneByName(FName(b))
                            log("watch: steering wheel part shown: %s", b)
                        end
                    end)
                end
            end
        end
    end
    local no_co = s.name == "seat"
    if c.codriver_hidden ~= no_co then
        pcall(driver_visible, c, not no_co, true)
        c.codriver_hidden = no_co
    end
    if c.driver_hidden ~= no_driver or W.drv_car ~= c then
        if W.drv_car and W.drv_car ~= c and W.drv_car.driver_hidden then pcall(driver_visible, W.drv_car, true) end
        if W.drv_car and W.drv_car ~= c and W.drv_car.codriver_hidden then
            pcall(driver_visible, W.drv_car, true, true)
            W.drv_car.codriver_hidden = false
        end
        crumb("watch: driver figure")
        pcall(driver_visible, c, not no_driver)
        c.driver_hidden, W.drv_car = no_driver, c
    end
    -- the view on it: once, and again now and then (a game's own camera change may take it back)
    if not W.on or t - W.set_t > 1.0 then
        local ok, vt = pcall(function() return pc:GetViewTarget() end)
        if not W.on or not (ok and vt and vt:IsValid() and vt:GetAddress() == cam:GetAddress()) then
            crumb("watch: view target")
            local ok_set, why = pcall(function() pc:SetViewTargetWithBlend(cam, W.on and 0.0 or 0.6, 0, 0.0, false) end)
            if not ok_set then log("watch: view not set: %s", tostring(why)) end
            if not W.on then log("watch: on %s (%s)", watching.id, watching.cam) end
        end
        game_hud(false)                                       -- (its race display: your car's, not theirs)
        W.on, W.set_t = true, t
    end
end

local function tick()
    frame = frame + 1
    spawned_this_frame = false
    local me, pc = pawn()
    local t = frame_clock(me or pc)
    if me then
        pcall(read_penalty, t)
        pcall(tell_livery, me, t)
        pcall(codriver_off, t)                         -- (COPILOT: the game's co-driver kept off)
    else
        penalty_now = nil
        codriver_now = nil
    end
    pcall(write_damage, me, t)
    local cam = write_camera(pc)
    _G.ACRDAILY_NAMES = nil                            -- (the names over the cars, for hud.lua: set again below)
    local seq, when, ghosts, warm_now, names_now = read_ghosts(t)
    local fresh = seq and seq ~= last_seq
    if fresh then
        last_seq, last_new_t, warm, ghost_names = seq, t, warm_now, names_now or {}
        watching = ghost_names["\0watch"]
        ghost_names["\0watch"] = nil
        if ghost_names["\0route"] then watch_route = ghost_names["\0route"] end   -- (kept between the app's updates)
        ghost_names["\0route"] = nil
        watch_dash = ghost_names["\0wdash"]
        ghost_names["\0wdash"] = nil
        watch_livery = ghost_names["\0wlivery"]
        ghost_names["\0wlivery"] = nil
        if not watching then watch_route = nil end
    end
    if ghosts_f and t - math.max(last_new_t or 0, ghosts_opened or 0) > 2.0 then reopen_ghosts() end
    if not me then                                     -- (no car of yours: a menu, another stage loading)
        watch_off(nil, nil)
        hud_was = nil                                  -- (a new level: its own race display)
        for k in pairs(classes) do classes[k] = nil end   -- (the cars' classes: looked up again on the next stage)
        for id in pairs(cars) do remove(id, t, true) end
        empty_pool()
        pool_leader = nil
        return
    end
    local me_at = me:GetAddress()                      -- (Lua wrappers differ each time: compare the objects)
    if pool_leader ~= me_at then                       -- (another car of yours, a restart: the kept ones follow the old)
        empty_pool()
        pool_leader = me_at
    end
    if last_new_t and t - last_new_t > STALE_S then
        watch_off(pc, me)
        for id in pairs(cars) do remove(id, t) end     -- (the app stopped telling: kept for when it tells again)
        return
    end
    if fresh then
        local t_pose = when and app_to_here(when, t) or t
        for id, g in pairs(ghosts) do
            local c = cars[id]
            if c and (not c.actor:IsValid() or c.leader ~= me_at or c.cls ~= g.cls) then
                remove(id, t, c.leader ~= me_at)       -- (your car was replaced: a restart; or they changed car)
                c = nil
            end
            if not c then
                c = take(g.cls, me_at)                 -- (one kept: at once, no hitch)
                if not c and not spawned_this_frame then
                    c = make(me, g, me_at)             -- (else one new car a frame at most: the next file brings it)
                    spawned_this_frame = true
                end
                if c then cars[id] = c end
            end
            if c then
                c.seen_t = t
                took(c, g, t_pose, t)
            end
        end
    end
    warm_up(me, me_at, t)
    if frame % 60 == 0 then empty_pool(POOL_KEEP_S, t) end
    local me_loc = frame % 15 == 0 and (W.on and W.loc or me:K2_GetActorLocation()) or nil   -- (near or far: a few
    -- times a second; WATCH: from its camera)
    local here = nil                                   -- (where your car is and which way it faces: near_hide)
    if next(cars) then
        local l, r = me:K2_GetActorLocation(), me:K2_GetActorRotation()
        local yaw = math.rad(r.Yaw)
        here = {X = l.X, Y = l.Y, Z = l.Z, cy = math.cos(yaw), sy = math.sin(yaw)}
        -- (the camera behind your car, a chase view: checked there too; bonnet, dash, helmet, bumper: it is in your car)
        here.cam_out = cam ~= nil and ((cam.X - l.X) ^ 2 + (cam.Y - l.Y) ^ 2 + (cam.Z - l.Z) ^ 2) > CAM_OUT ^ 2
    end
    for id, c in pairs(cars) do
        if t - (c.seen_t or t) > GONE_S then
            remove(id, t)
        elseif c.base and c.actor:IsValid() then       -- every frame: where it is now
            -- (moved, not teleported: the picture then knows how it moves, like every other car, for the motion
            -- blur and for DLSS / TAA and frame generation, which smeared or stuttered a car that teleported each
            -- frame; it has no physics and no collision, so nothing else changes)
            local p = place_wheels(c, carried(c, t), t)      -- (the wheels first: the body lifted onto them)
            c.actor:K2_SetActorLocationAndRotation({X = p[1], Y = p[2], Z = p[3]},
                {Pitch = p[4], Yaw = p[5], Roll = p[6]}, false, {}, false)
            c.shown = p
            if W.on and watching and watching.id == id then
                -- (WATCH: the car followed is never hidden, the camera being on it: its onboard showed no bonnet)
                if c.near then
                    c.near = false
                    c.actor:SetActorHiddenInGame(false)
                end
            elseif here then
                near_hide(c, cam, here)
            end
            if frame % 60 == 0 then quiet_gauges(c) end
            if me_loc then detail(c, me_loc) end
        end
    end
    watch_tick(pc, me, t)
    -- the drivers' names over their cars, drawn by hud.lua with the game's camera (not over one hidden in your car,
    -- nor one out of sight, as the app says)
    if cam and names_by_game then
        local list = {}
        for id, c in pairs(cars) do
            local n = ghost_names[id]
            if n and n.shown and c.shown and not c.near then
                list[#list + 1] = {x = c.shown[1], y = c.shown[2], z = c.shown[3] + NAME_UP, text = n.text,
                                   colour = n.colour}
            end
        end
        _G.ACRDAILY_NAMES = {cam = cam, list = list, t = t}
    end
    trace_frame(t)
end

-- The app's timer drawn in the game, for VR (hud.lua): when the app writes ingame-hud.txt.
local ok_hud, hud = pcall(require, "hud")
if not ok_hud or type(hud) ~= "table" then
    log("no hud.lua (%s): no timer in the game", tostring(hud))
    hud = nil
end
names_by_game = hud ~= nil                             -- (it draws the drivers' names over their cars too)

-- ACR DAILY inside the game (appui.lua, 0.2): MULTIPLAYER's ACR DAILY tile and the app's pages, while the app writes
-- ingame-app.txt. While %APPDATA%\ACR Daily\app-dev.on exists, appui.lua is loaded again when it changes on disk.
local ok_app, appui = pcall(require, "appui")
if not ok_app or type(appui) ~= "table" then
    log("no appui.lua (%s): no ACR DAILY in the game's menu", tostring(appui))
    appui = nil
end
local APP_DEV = DIR .. "app-dev.on"
local APP_HERE = (debug.getinfo(1, "S").source or ""):match("^@(.*[/\\])") or ""
local app_dev_size = nil
local function app_dev_reload()
    local flag = io.open(APP_DEV, "r")
    if not flag then return end
    flag:close()
    local size = ""
    for _, n in ipairs({"appui.lua", "drive.lua"}) do
        local h = io.open(APP_HERE .. n, "rb")
        if h then
            size = size .. tostring(h:seek("end")) .. "/"
            h:close()
        end
    end
    if app_dev_size == nil then app_dev_size = size end
    if size == app_dev_size then return end
    app_dev_size = size
    if appui and appui.unload then pcall(appui.unload) end
    package.loaded["drive"] = nil
    package.loaded["hudkit"] = nil                       -- (the pages' own copy made again: the HUD keeps its own)
    local ok, fresh = pcall(dofile, APP_HERE .. "appui.lua")
    log("dev: appui.lua loaded again: %s", ok and "ok" or tostring(fresh))
    if ok and type(fresh) == "table" then appui = fresh end
end

-- On the game thread, every frame (one loop for the mod's whole life: no callback made per frame). A UE4SS without
-- frame loops: as often as it runs delayed ones (each game frame, at most).
local errors, hud_errors, app_errors = 0, 0, 0
local function step()
    local crumbs = W.on                               -- (WATCH: each step on disk, ghost-crumbs.txt)
    if crumbs then crumb("ghost cars") end
    local ok, err = pcall(tick)
    if crumbs then crumb("hud and pages") end
    if not ok then
        errors = errors + 1
        if errors <= 3 or errors % 300 == 0 then log("error (%d): %s", errors, tostring(err)) end
    end
    if hud then
        local ok2, err2 = pcall(hud.tick, now())
        if not ok2 then
            hud_errors = hud_errors + 1
            if hud_errors <= 3 or hud_errors % 300 == 0 then log("timer error (%d): %s", hud_errors, tostring(err2)) end
        end
    end
    if frame % 60 == 0 then pcall(app_dev_reload) end
    if appui then
        local ok3, err3 = pcall(appui.tick, now())
        if not ok3 then
            app_errors = app_errors + 1
            if app_errors <= 3 or app_errors % 300 == 0 then log("ACR DAILY pages error (%d): %s", app_errors, tostring(err3)) end
        end
    end
    return false
end
if type(LoopInGameThreadAfterFrames) == "function" then
    LoopInGameThreadAfterFrames(1, step)
    log("moving the cars every frame")
else
    LoopInGameThreadWithDelay(1, step)
    log("moving the cars every 1 ms at most (no frame loop in this UE4SS)")
end
