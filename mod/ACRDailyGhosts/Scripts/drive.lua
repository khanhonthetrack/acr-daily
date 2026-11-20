-- DRIVE inside the game (0.2): the app's set-up (a daily, a time trial, an event's rally) made in the running game
-- through the game's own calls, then the game goes to the Service Park: no save written, no restart, no key presses.
-- (Part of the ACR Daily mod: appui.lua starts it on the app's command and ticks it every frame.)
--
-- Probed in the game 20 Nov 2026 (docs/ingame-app.md, "DRIVE without restarting the game"):
--   PlayerRaceConfiguration:ServerSetRaceEventConfigurationId({DefaultRaceEventConfigurations, DefaultRally}) and
--   PlayerFlow:ServerExecuteFlow("FSM.Flow.SetupRaceEvent")      = RACING > RALLY > RALLY WEEKEND (its race event made)
--   RaceEventUtilsFunctionLibrary: SetRaceEventRallyWeekendCalendarPreset, AddDefaultedRallyWeekendSubEvent   calendar
--   the sub-event's own fields (Day, PreRaceZoneConfigurationId, WeatherOptions...)        written directly, read back
--   SelectRallyWeekendSubEvent(0)                                  the first stage's weather taken as the event's own
--   PlayerRaceConfiguration:ServerSetCar(id)                       the car, as the game's car pick does it
--   AutoSetTiresAllocationForLocalPlayerParticipant                J on the tyre screen
--   PlayerFlow:ServerExecuteFlow("FSM.Flow.StartRaceEvent")        CONFIRM AND START RALLY: to the Service Park
-- Never: a car id that isn't the game's (the game crashed loading the stage: 'eligible' says yes to anything), the
-- event's own WeatherOptions written (crashed once: the game copies the stage's with SelectRallyWeekendSubEvent).
--
-- setup (from the app, ingamedrive.py): {preset, car, stages = [{track, day, service, weather, start, wet}],
--   rules = {respawn, damage, collisions, wear, failures, penalty, hardcore}, opponents, order}
-- Answers through tell("drive", "<n> ok" | "<n> error <why>" | "<n> step <what>").
local UEHelpers = require("UEHelpers")

local D = {}
local TAG = "[ACRDailyDrive] "
local function log(fmt, ...) print(TAG .. string.format(fmt, ...) .. "\n") end

local LIB = "/Script/acr.Default__RaceEventUtilsFunctionLibrary"
local WAIT_EVENT_S = 6.0          -- the Rally Weekend's race event made, at most this long after SetupRaceEvent

local job = nil                   -- {n, setup, tell, step, at, t0}

local function lib()
    local l = StaticFindObject(LIB)
    if not (l and l:IsValid()) then error("no RaceEventUtilsFunctionLibrary") end
    return l
end

local function live(class)
    -- the live one: in a level or the engine's own objects (not a class default, not a blueprint's template)
    for _, x in ipairs(FindAllOf(class) or {}) do
        local ok, n = pcall(function() return x:GetFullName() end)
        if ok and x:IsValid() and not n:find("Default__", 1, true) and
           (n:find("PersistentLevel", 1, true) or n:find("/Engine/Transient", 1, true)) then
            return x
        end
    end
    return nil
end

local function in_main_menu()
    -- the game's main menu up (the live WB_MainMenu, in the menu's level)
    local ok, world = pcall(UEHelpers.GetWorld)
    local level = ok and world and world:IsValid() and world:GetFullName() or ""
    return live("WB_MainMenu_C") ~= nil and level:find("MainMenu", 1, true) ~= nil
end

local function fail(why)
    log("DRIVE %s: %s", tostring(job and job.n), why)
    if job then job.tell("drive", string.format("%s error %s", job.n, why)) end
    job = nil
end

local function step_said(what)
    if job then job.tell("drive", string.format("%s step %s", job.n, what)) end
end

-- the steps, each run once on its own frame; one returns true when done, false to be run again next frame (waiting)
local steps = {}

steps[1] = function(t)
    if not in_main_menu() then error("not in the game's main menu") end
    local cfg = live("PlayerRaceConfigurationComponent")
    local flow = live("PlayerFlowComponent")
    if not (cfg and flow) then error("the game's menu isn't ready") end
    cfg:ServerSetRaceEventConfigurationId({Table = FName("DefaultRaceEventConfigurations"), Row = FName("DefaultRally")})
    flow:ServerExecuteFlow(FName("FSM.Flow.SetupRaceEvent"))
    step_said("rally weekend")
    return true
end

steps[2] = function(t)
    -- wait for the Rally Weekend's race event and its settings
    local L = lib()
    local pc = UEHelpers.GetPlayerController()
    local ev = L:GetRaceEvent(pc)
    local ok = ev and ev:IsValid() and L:GetRaceEventConfigurationId(pc):ToString() == "DefaultRally"
    local c = ok and L:GetRaceEventRaceSettingsRallyWeekendComponent(pc)
    if not (c and c:IsValid()) then
        if t - job.at > WAIT_EVENT_S then error("the game's Rally Weekend didn't come up") end
        return false
    end
    -- (not IsRallyInProgress: it is true for any Rally Weekend set up in the menu, a save with none in progress too,
    -- seen 20 Nov 2026. A rally of the player's in progress is the app's to see, in the save: ingamedrive.ready)
    return true
end

steps[3] = function(t)
    local s = job.setup
    local L = lib()
    local pc = UEHelpers.GetPlayerController()
    L:SetRaceEventRallyWeekendCalendarPreset(pc, FName(s.preset))
    for k, st in ipairs(s.stages) do
        L:AddDefaultedRallyWeekendSubEvent(pc, FName(st.track), k == 1, not st.service, k - 1, false)
    end
    local c = L:GetRaceEventRaceSettingsRallyWeekendComponent(pc)
    local subs = c.RallyWeekendCalendar.RallyWeekendSubEvents
    if #subs ~= #s.stages then error(string.format("the calendar holds %d stages, not %d", #subs, #s.stages)) end
    for k, st in ipairs(s.stages) do
        local sub = subs[k]
        if sub.TrackId:ToString():lower() ~= st.track:lower() then
            error(string.format("stage %d is %s, not %s", k, sub.TrackId:ToString(), st.track))
        end
        sub.Day = st.day
        sub.PreRaceZoneConfigurationId = FName(st.service and "ServiceParkDefault" or "NoZone")
        local w = sub.WeatherOptions
        w.Preset.WeatherType = st.weather
        w.Preset.bRandom = false
        w.TargetPreset.WeatherType = st.weather
        w.TargetPreset.bRandom = false
        w.bDynamicWeather = false
        w.StartingTime.TimeSeconds = st.start + 0.0
        w.TimeSpeed = 0                      -- time stands still: the same light for everyone
        w.StartingWetness = (st.wet or 0) + 0.0
        w.StartingAccumulatedSnow = 0.0
        w.StartingGripLevel = 4              -- optimal
    end
    local cal = c.RallyWeekendCalendar
    cal.bIsCustomPreset = true
    -- read back
    for k, st in ipairs(s.stages) do
        local sub = c.RallyWeekendCalendar.RallyWeekendSubEvents[k]
        local w = sub.WeatherOptions
        if sub.Day ~= st.day or w.Preset.WeatherType ~= st.weather or math.abs(w.StartingTime.TimeSeconds - st.start) > 1 then
            error(string.format("stage %d didn't take its day / weather / time", k))
        end
    end
    L:SelectRallyWeekendSubEvent(pc, 0)
    if not L:IsRaceEventConsistent(pc) then error("the game says the calendar isn't consistent") end
    step_said("calendar")
    return true
end

steps[4] = function(t)
    -- the rules (the daily's / the event's), on the event's settings; read back
    local r, s = job.setup.rules or {}, job.setup
    local L = lib()
    local pc = UEHelpers.GetPlayerController()
    local set = L:GetRaceEventRaceSettingsComponent(pc)
    local o = set.RaceOptions
    o.Respawn.ManualRespawn = r.respawn
    o.CarDamage.bDamagesEnabled = r.damage == 1
    o.CarDamage.Collisions = r.collisions
    o.CarDamage.Wear = r.wear
    o.CarDamage.MechanicalFailures = r.failures
    set.RacePenaltyOptions.RacePenalty = r.penalty
    set.HardCoreOptions.bHardCore = r.hardcore == 1
    set.AIOptions.NumOfOpponents = s.opponents or 1
    local rally = L:GetRaceEventRaceSettingsRallyComponent(pc)
    rally.RunningOrderOptions.RunningOrderType = s.order_type or 1   -- custom
    rally.RunningOrderOptions.RunningOrder = s.order or 1             -- first on the road
    local o2 = L:GetRaceEventRaceSettingsComponent(pc).RaceOptions
    local d = o2.CarDamage
    local got = string.format("%d%d%d%d%d%d", o2.Respawn.ManualRespawn, d.bDamagesEnabled and 1 or 0, d.Collisions, d.Wear,
                              d.MechanicalFailures, L:GetRaceEventRaceSettingsComponent(pc).RacePenaltyOptions.RacePenalty)
    local want = string.format("%d%d%d%d%d%d", r.respawn, r.damage, r.collisions, r.wear, r.failures, r.penalty)
    if got ~= want then error("the rules didn't take: " .. got .. " not " .. want) end
    step_said("rules")
    return true
end

steps[5] = function(t)
    live("PlayerRaceConfigurationComponent"):ServerSetCar(FName(job.setup.car))
    step_said("car")
    return true
end

steps[6] = function(t)
    local L = lib()
    local pc = UEHelpers.GetPlayerController()
    L:AutoSetTiresAllocationForLocalPlayerParticipant(pc)
    if not L:HasTiresAllocatedForLocalPlayerParticipant(pc) then error("no tyres allocated") end
    if not L:IsRaceEventConsistent(pc) then error("the game says the rally isn't consistent") end
    step_said("tyres")
    return true
end

steps[7] = function(t)
    live("PlayerFlowComponent"):ServerExecuteFlow(FName("FSM.Flow.StartRaceEvent"))
    log("DRIVE %s: started (%s, %s, %d stages)", tostring(job.n), job.setup.preset, job.setup.car, #job.setup.stages)
    job.tell("drive", string.format("%s ok", job.n))
    job = nil
    return true
end

--- The app's DRIVE: n (its number), setup (above), tell (appui's). -> false when one is already being done.
function D.start(n, setup, tell, t)
    if job then
        tell("drive", string.format("%s error busy", n))
        return false
    end
    if type(setup) ~= "table" or type(setup.stages) ~= "table" or #setup.stages == 0 or not setup.car or not setup.preset then
        tell("drive", string.format("%s error bad set-up", n))
        return false
    end
    job = {n = n, setup = setup, tell = tell, step = 1, at = t, wait = 2}
    log("DRIVE %s: %s, %s", tostring(n), setup.preset, setup.car)
    return true
end

function D.busy() return job ~= nil end

--- every frame (appui.lua)
function D.tick(t)
    if not job then return end
    if job.wait > 0 then
        job.wait = job.wait - 1
        return
    end
    local f = steps[job.step]
    if not f then job = nil return end
    local ok, done = pcall(f, t)
    if not ok then
        fail(tostring(done):gsub("^.-:%d+: ", ""))
        return
    end
    if done and job then
        job.step = job.step + 1
        job.at = t
        job.wait = 6                     -- (a few frames between steps: the game's own calls settle)
    end
end

return D
