-- ACR Daily ghost cars, in the game (a UE4SS Lua mod).
--
-- The ACR Daily app writes where the other drivers' cars are (live) to %APPDATA%\ACR Daily\ingame-ghosts.txt about
-- 60 times a second; this mod puts a real car there for each: the driver's own car model (its physics off, nothing
-- to hit), moved every frame, its wheels set where that car's wheels sit at rest (wheels.lua). It also writes the
-- game's camera to %APPDATA%\ACR Daily\ingame-camera.txt, so the app can put the names above the cars exactly.
--
-- ingame-ghosts.txt:   ACRDG 2 <seq>
--                      <id> <class> <X> <Y> <Z> <Pitch> <Yaw> <Roll>   (the game's units: cm, degrees; one per car)
--                      end
--   <class>: the driver's own car ('/Game/Data/Vehicles/.../BC_X.BC_X_C'), or '-' (unknown: your car's)
-- ingame-camera.txt:   CAM <seq> <X> <Y> <Z> <Pitch> <Yaw> <Roll> <horizontal fov>
local UEHelpers = require("UEHelpers")

local TAG = "[ACRDailyGhosts] "
local DIR = (os.getenv("APPDATA") or ".") .. "\\ACR Daily\\"
local GHOSTS_FILE = DIR .. "ingame-ghosts.txt"
local CAMERA_FILE = DIR .. "ingame-camera.txt"
local STALE_FRAMES = 90          -- the app's file not changing for this many frames (~1.5 s): ghosts hidden
local GONE_FRAMES = 30           -- a ghost missing from the file this long: removed

local cars = {}                  -- id -> {actor, seen, leader}
local last_seq, same_for = nil, 0
local frame = 0
local cam_seq = 0
local spawned_this_frame = false

local function log(fmt, ...) print(TAG .. string.format(fmt, ...) .. "\n") end
log("loaded")

local function pawn()
    local pc = UEHelpers.GetPlayerController()
    if pc and pc:IsValid() then
        local p = pc.Pawn
        if p and p:IsValid() and p.SetInputEnabled then return p, pc end
        return nil, pc
    end
end

local function read_ghosts()
    local f = io.open(GHOSTS_FILE, "r")
    if not f then return nil end
    local text = f:read("a")
    f:close()
    if not text or not text:find("\nend") then return nil end   -- (being written: next frame)
    local seq = text:match("^ACRDG 2 (%d+)")
    if not seq then return nil end
    local out = {}
    for id, cls, x, y, z, p, yaw, r in text:gmatch("\n(%S+) (%S+) (%S+) (%S+) (%S+) (%S+) (%S+) (%S+)") do
        out[id] = {tonumber(x), tonumber(y), tonumber(z), tonumber(p), tonumber(yaw), tonumber(r), cls = cls}
    end
    return seq, out
end

local classes = {}               -- class path -> UClass (or false: could not load it)

local function class_for(path, me)
    if path == "-" then return me:GetClass() end
    local c = classes[path]
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

local function place_wheels(c, g)
    if not c.wheels then return end
    local ai = c.anim
    if not (ai and ai:IsValid()) then
        ai = c.actor.SuspensionsMesh:GetAnimInstance()
        if not (ai and ai:IsValid()) then return end
        c.anim = ai
    end
    local ax, ay, az, q = rotation(g[4], g[5], g[6])
    local wt, st = ai.WheelTransforms, ai.SuspensionTransforms
    for i = 1, 4 do
        local l = c.wheels[i]
        local p = {X = g[1] + ax[1] * l[1] + ay[1] * l[2] + az[1] * l[3],
                   Y = g[2] + ax[2] * l[1] + ay[2] * l[2] + az[2] * l[3],
                   Z = g[3] + ax[3] * l[1] + ay[3] * l[2] + az[3] * l[3]}
        local w, s = wt[i], st[i]
        w.Translation, w.Rotation = p, q
        s.Translation, s.Rotation = p, q
    end
end

local function transform(g)
    local half = math.rad(g[5]) / 2
    return {Rotation = {X = 0.0, Y = 0.0, Z = math.sin(half), W = math.cos(half)},
            Translation = {X = g[1], Y = g[2], Z = g[3]}, Scale3D = {X = 1.0, Y = 1.0, Z = 1.0}}
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

local function remove(id)
    local c = cars[id]
    if c and c.actor and c.actor:IsValid() then c.actor:K2_DestroyActor() end
    cars[id] = nil
end

local function write_camera(pc)
    local cm = pc and pc.PlayerCameraManager
    if not (cm and cm:IsValid()) then return end
    local l, r = cm:GetCameraLocation(), cm:GetCameraRotation()
    cam_seq = cam_seq + 1
    local f = io.open(CAMERA_FILE .. ".tmp", "w")
    if not f then return end
    f:write(string.format("CAM %d %.2f %.2f %.2f %.4f %.4f %.4f %.4f\n", cam_seq, l.X, l.Y, l.Z, r.Pitch, r.Yaw, r.Roll,
        cm:GetFOVAngle()))
    f:close()
    os.remove(CAMERA_FILE)
    os.rename(CAMERA_FILE .. ".tmp", CAMERA_FILE)
end

local function tick()
    frame = frame + 1
    spawned_this_frame = false
    local me, pc = pawn()
    write_camera(pc)
    local seq, ghosts = read_ghosts()
    if seq then
        if seq == last_seq then same_for = same_for + 1 else same_for, last_seq = 0, seq end
    end
    if not me or same_for > STALE_FRAMES or not ghosts then
        if not me or same_for > STALE_FRAMES then
            for id in pairs(cars) do remove(id) end
        end
        return
    end
    local me_at = me:GetAddress()                      -- (Lua wrappers differ each time: compare the objects)
    for id, g in pairs(ghosts) do
        local c = cars[id]
        if c and (not c.actor:IsValid() or c.leader ~= me_at or c.cls ~= g.cls) then
            remove(id)                                 -- (your car was replaced: a restart; or they changed car)
            c = nil
        end
        if not c and spawned_this_frame then
            -- one new car a frame at most
        elseif not c then
            local a = spawn(me, g)
            spawned_this_frame = true
            if a then
                c = {actor = a, leader = me_at, cls = g.cls, wheels = wheels_of(a)}
                cars[id] = c
            end
        end
        if c then
            c.seen = frame
            c.actor:K2_SetActorLocationAndRotation({X = g[1], Y = g[2], Z = g[3]},
                {Pitch = g[4], Yaw = g[5], Roll = g[6]}, false, {}, true)
            place_wheels(c, g)
        end
    end
    for id, c in pairs(cars) do
        if frame - (c.seen or 0) > GONE_FRAMES then remove(id) end
    end
end

-- on the game thread, every 16 ms (one loop for the mod's whole life: no callback made per frame)
LoopInGameThreadWithDelay(16, function()
    local ok, err = pcall(tick)
    if not ok and frame % 300 == 1 then log("error: %s", tostring(err)) end
    return false
end)
