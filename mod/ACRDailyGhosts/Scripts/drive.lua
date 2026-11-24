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
--   rules = {respawn, damage, collisions, wear, failures, penalty, hardcore}, opponents, order,
--   tyres = {<compound row>: count} (optional: the game's own otherwise), livery = <livery name> (optional)}
-- Answers through tell("drive", "<n> ok" | "<n> error <why>" | "<n> step <what>").
local UEHelpers = require("UEHelpers")

local D = {}
local TAG = "[ACRDailyDrive] "
local function log(fmt, ...) print(TAG .. string.format(fmt, ...) .. "\n") end

local LIB = "/Script/acr.Default__RaceEventUtilsFunctionLibrary"
local WAIT_EVENT_S = 6.0          -- the Rally Weekend's race event made, at most this long after SetupRaceEvent
local WAIT_DIALOG_S = 15.0        -- the game's CONTINUE RALLY WEEKEND question up, at most this long (it loads the rally first)

local job = nil                   -- {n, setup, tell, step, at, t0}
local livery, livery_world, livery_at, livery_done = nil, nil, 0, 0   -- (dress(): the livery for the rally's stages)

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
    -- (the livery picked, setup.livery: the car's official one's name, or "usergen_<folder>" for one in
    -- Documents\My Games\acr\Liveries\<car>: put on the car in each stage's level, dress() below. The garage's own
    -- pick for the car is left as it is)
    return true
end

-- The tyres: the game's own allocation first (J on its tyre screen: every compound the rally allows, its total), then
-- the player's counts (setup.tyres = {<compound row>: n}) written over it in place when they fit: only compounds the
-- game offers, adding up to its total (the map can't be passed from Lua: probed 21 Nov 2026). Otherwise the game's own
-- stays, and the answer says so.
local function own_participant_data()
    local want = UEHelpers.GetPlayerController().PlayerState.ParticipantId:ToString()
    for _, o in ipairs(FindAllOf("BC_RaceParticipant_C") or {}) do
        local ok, id = pcall(function() return o.ID:ToString() end)
        if ok and id == want then return o.RaceParticipantData end
    end
    return nil
end

local function chosen_tyres(wanted)
    local d = own_participant_data()
    if not d then return "no participant" end
    local ta = d.TiresAllocation
    local m = ta.Compounds
    local have, total = {}, 0
    m:ForEach(function(k, v) have[k:get().Row:ToString()] = true end)
    for row, n in pairs(wanted) do
        if not have[row] then return "not in this rally: " .. row end
        total = total + n
    end
    if total <= 0 then return "no tyres" end
    -- (the app counts out of 16, the game's tyre screen for a short rally; a rally that takes another number gets the
    -- same shares of it, the largest remainders rounded up)
    local scaled, given, rest = {}, 0, {}
    for row, n in pairs(wanted) do
        local x = n * ta.Count / total
        scaled[row] = math.floor(x)
        given = given + scaled[row]
        rest[#rest + 1] = {row = row, r = x - scaled[row]}
    end
    table.sort(rest, function(a, b) return a.r > b.r end)
    for i = 1, ta.Count - given do scaled[rest[(i - 1) % #rest + 1].row] = scaled[rest[(i - 1) % #rest + 1].row] + 1 end
    m:ForEach(function(k, v) v:set(scaled[k:get().Row:ToString()] or 0) end)
    live("PlayerRaceConfigurationComponent"):ServerSetTiresAllocation(ta)
    return nil
end

steps[6] = function(t)
    local L = lib()
    local pc = UEHelpers.GetPlayerController()
    L:AutoSetTiresAllocationForLocalPlayerParticipant(pc)
    if not L:HasTiresAllocatedForLocalPlayerParticipant(pc) then error("no tyres allocated") end
    if type(job.setup.tyres) == "table" and next(job.setup.tyres) then
        local ok, why = pcall(chosen_tyres, job.setup.tyres)
        if ok and why == nil then
            step_said("tyres chosen")
        else
            L:AutoSetTiresAllocationForLocalPlayerParticipant(pc)      -- (the game's own again: whatever was half done)
            step_said("tyres auto " .. tostring(why))
        end
    end
    if not L:IsRaceEventConsistent(pc) then error("the game says the rally isn't consistent") end
    step_said("tyres")
    return true
end

steps[7] = function(t)
    live("PlayerFlowComponent"):ServerExecuteFlow(FName("FSM.Flow.StartRaceEvent"))
    log("DRIVE %s: started (%s, %s, %d stages)", tostring(job.n), job.setup.preset, job.setup.car, #job.setup.stages)
    if type(job.setup.damage) == "table" then            -- (the car as it finished the stage before: restore below)
        car_damage = {parts = job.setup.damage, n = job.n, tell = job.tell, at = t, index = 0}
    end
    job.tell("drive", string.format("%s ok", job.n))
    job = nil
    return true
end

-- After a crash of the game past a finish line (the stage counted from its finish-line time, the rally set up again
-- from the next stage: setup.damage), the car as it was at that line put on the next stage's car before it starts (the
-- user, 24 Nov 2026; a NEXT STAGE in the running game needs none of this: the game carries the car itself, given the
-- car at the line: "the whole car at the finish line" below). parts = {<part> = <life points>} as the app read them at
-- that finish (main.lua write_damage): every other part is put back to 100. The tyres come new (not kept by the server).
-- How (probed in the game 24 Nov 2026): each part's LifePoints written, then the player's repairs component makes its
-- plans again and applies the selected one, empty (nothing repaired, no time, no penalty): the game sets every part's
-- state from its life points, as it does at a Service Park (engine 35 -> state 3, radiator 25 -> 3, suspension 50 -> 2;
-- back to 100 -> 0). Written alone, the life points stay but the states don't. It works on the start line (no Service
-- Park needed) and at a Service Park (before the player repairs anything: their repairs then go on top).
car_damage = nil                 -- {parts, n, tell, at, index (the calendar's stage it is for, or nil)}
local DAMAGE_WAIT_S = 2.0        -- the new car this long before it is touched (it is being made)
local DAMAGE_GIVE_UP_S = 1800    -- no next stage by then: not done
local CAR_STILL_KMH = 2.0        -- on the start line, the car still standing (before it drives to the start)

local UTIL_ = nil
local function sub_index()
    local ok, i = pcall(function()
        UTIL_ = (UTIL_ and UTIL_:IsValid()) and UTIL_ or StaticFindObject(LIB)
        return UTIL_:GetRallyWeekendSubEventIndex(UEHelpers.GetPlayerController())
    end)
    return ok and i or nil
end

local function restore_damage(t)
    local d = car_damage
    if not d then return end
    if t - d.at > DAMAGE_GIVE_UP_S then
        car_damage = nil
        d.tell("drive", string.format("%s damage none: no next stage came", d.n))
        return
    end
    local okw, w = pcall(UEHelpers.GetWorld)
    local name = okw and w and w:IsValid() and w:GetFullName() or ""
    if name == "" or name:find("MainMenu", 1, true) then
        d.seen = nil
        return
    end
    local pc = UEHelpers.GetPlayerController()
    local pawn = pc and pc.Pawn
    if not (pawn and pawn:IsValid()) then return end
    local at = pawn:GetAddress()
    local at_park = pawn:GetClass():GetFName():ToString():find("ServicePark", 1, true) ~= nil
    local comp = nil
    if at_park then                                      -- (the Service Park: its car isn't the player's pawn)
        for _, c in ipairs(FindAllOf("CarDamageComponent") or {}) do
            local ok, n = pcall(function() return c:GetFullName() end)
            if ok and n:find("PersistentLevel", 1, true) and not n:find("Default__", 1, true) then comp = comp or c end
        end
    else
        local ok, c = pcall(function() return pawn.CarDamage end)
        comp = ok and c and c.IsValid and c:IsValid() and c or nil
        if not comp then return end                      -- (not a car: a camera, a menu)
        local okv, v = pcall(function() return pawn:GetVelocity() end)
        if okv and v and math.sqrt(v.X * v.X + v.Y * v.Y) * 0.036 > CAR_STILL_KMH then
            if not d.moving then
                d.moving = true
                log("DRIVE %s: the car moved before its damage was put on", tostring(d.n))
            end
            return
        end
    end
    if not comp then return end
    if d.index ~= nil then                               -- (only the stage it is for)
        local i = sub_index()
        if i ~= nil and i ~= d.index then return end
    end
    if d.seen ~= at then
        d.seen, d.seen_t = at, t
        return
    end
    if t - d.seen_t < DAMAGE_WAIT_S then return end
    local count = 0
    pcall(function() comp.NamedParts:ForEach(function() count = count + 1 end) end)
    if count < 5 then return end
    local want = {}
    for k, v in pairs(d.parts or {}) do
        if type(k) == "string" and type(v) == "number" then want[k:lower()] = math.max(0, math.min(100, v)) end
    end
    local set, missed = 0, 0
    comp.NamedParts:ForEach(function(k, v)
        local id = k:get():ToString():lower()            -- (the same part's name differs in case between levels)
        local lp = want[id] or 100
        local p = v:get()
        local ok = pcall(function() p.LifePoints = lp + 0.0 end)
        if ok and math.abs(p.LifePoints - lp) < 0.05 then set = set + 1 else missed = missed + 1 end
        want[id] = nil
    end)
    for _ in pairs(want) do missed = missed + 1 end
    -- the states, from the life points: the repairs plans made again, the selected one applied if empty
    local repaired, states = 0, "set"
    local okr = pcall(function()
        local r = pc.PlayerCarRepairs
        r:GenerateRepairsPlans()
        pcall(function() r.SelectedRepairsPlan.SelectedRepairs:ForEach(function() repaired = repaired + 1 end) end)
        if repaired == 0 then r:ApplySelectedRepairsPlan() else states = "kept" end
    end)
    if not okr then states = "failed" end
    car_damage = nil
    log("DRIVE %s: the car as it finished put on (%s): %d parts%s; states %s", tostring(d.n), at_park and "Service Park" or "start line",
        set, missed > 0 and (", " .. missed .. " not") or "", states)
    d.tell("drive", string.format("%s damage %d %d %s %s", d.n, set, missed, at_park and "park" or "line", states))
end

-- CONTINUE (a rally of the player's in progress in the game: an event's, set up before): the game's own way back into
-- it, its buttons pressed from here as the player would (probed 21 Nov 2026). The flow "ResumeRaceEvent" alone, sent
-- with no menu screen, started the default calendar instead (Wales, not the rally in progress: the menu loads the rally
-- from the save as its RALLY WEEKEND screen opens). So: the RACING page's RALLY tile, the RALLY page's RALLY WEEKEND
-- tile (its second), and the game's own question CONTINUE RALLY WEEKEND: RESUME (its first button). Buttons found by
-- their class and place, never their words (the game's language). Each pressed with HandleButtonClicked, as a click.
local function transient(class)
    local out = {}
    for _, x in ipairs(FindAllOf(class) or {}) do
        local ok, n = pcall(function() return x:GetFullName() end)
        if ok and x:IsValid() and n:find("/Engine/Transient", 1, true) and not n:find("Default__", 1, true) then
            out[#out + 1] = x
        end
    end
    return out
end

local function visible(list)
    local out = {}
    for _, b in ipairs(list) do
        local ok, v = pcall(function() return b:IsVisible() end)
        if ok and v then out[#out + 1] = b end
    end
    return out
end

local function press(b, what)
    b:HandleButtonClicked()
    step_said(what)
    return true
end

local PANEL_, CONTENT_ = nil, nil
local function find(root, name)
    PANEL_ = PANEL_ or StaticFindObject("/Script/UMG.PanelWidget")
    CONTENT_ = CONTENT_ or StaticFindObject("/Script/UMG.ContentWidget")
    local hit
    local function walk(w, d)
        if hit or d > 12 or not (w and w:IsValid()) then return end
        if w:GetFName():ToString() == name then hit = w return end
        if w:IsA(PANEL_) then
            for i = 0, w:GetChildrenCount() - 1 do walk(w:GetChildAt(i), d + 1) end
        elseif w:IsA(CONTENT_) then
            local ok, ch = pcall(function() return w:GetContent() end)
            if ok then walk(ch, d + 1) end
        end
    end
    walk(root, 0)
    return hit
end

local resume_steps = {
    function(t)                                  -- RACING's RALLY tile (the switcher's second page)
        if not in_main_menu() then error("not in the game's main menu") end
        local sel = transient("WB_SelectWidget_C")[1]
        if not sel then error("the game's menu isn't ready") end
        local sw = find(sel.WidgetTree.RootWidget, "OptionSwitcher")
        local racing = sw and sw:GetChildAt(1)
        local slot = racing and find(racing.WidgetTree.RootWidget, "RallyContainer")
        local tile = slot and slot:GetContent() and slot:GetContent():GetContent()
        if not (tile and tile:IsValid()) then error("no RALLY tile in the game's menu") end
        return press(tile, "rally")
    end,
    function(t)                                  -- the RALLY page's second tile: RALLY WEEKEND
        local subs = visible(transient("WB_SubSelectionButton_C"))
        if #subs < 2 then
            if t - job.at > WAIT_EVENT_S then error("the game's RALLY page didn't come up") end
            return false
        end
        return press(subs[2], "rally weekend")
    end,
    function(t)                                  -- its question CONTINUE RALLY WEEKEND: RESUME (its confirm button; CREATE
        local btns = visible(transient("WB_ConfirmationButton_C"))   -- NEW is another kind), or none: no rally
        local asked = #visible(transient("WB_DialogConfirm_C")) > 0
        if #btns < 1 or not asked then
            if t - job.at > WAIT_DIALOG_S then error("no rally in progress in the game") end
            return false
        end
        press(btns[1], "resume")
        log("CONTINUE %s: resumed", tostring(job.n))
        job.tell("drive", string.format("%s ok", job.n))
        job = nil
        return true
    end,
}
--- The app's DRIVE: n (its number), setup (above), tell (appui's). -> false when one is already being done.
function D.start(n, setup, tell, t)
    if job then
        tell("drive", string.format("%s error busy", n))
        return false
    end
    local resume = type(setup) == "table" and setup.resume == true
    if not resume and (type(setup) ~= "table" or type(setup.stages) ~= "table" or #setup.stages == 0 or not setup.car
                       or not setup.preset) then
        tell("drive", string.format("%s error bad set-up", n))
        return false
    end
    job = {n = n, setup = setup, tell = tell, step = 1, at = t, wait = 2, steps = resume and resume_steps or steps}
    -- the livery for the stages to come (or none: the game's own pick)
    livery = (type(setup.livery) == "string" and setup.livery ~= "") and setup.livery or nil
    livery_world = nil
    log("DRIVE %s: %s, %s", tostring(n), setup.preset, setup.car)
    return true
end

function D.busy() return job ~= nil end

-- The game's list of the player's own liveries read again from Documents\My Games\acr\Liveries: one installed while it
-- runs is there at once, no restart (probed 21 Nov 2026: LiveryCustomizationSubsystem:OnDbInited, then the new
-- folder's "usergen_<name>" took on the car; without it, nothing).
function D.rescan_liveries()
    local sub = FindFirstOf("LiveryCustomizationSubsystem")
    local ok = sub and sub:IsValid() and pcall(function() sub:OnDbInited() end)
    log("liveries read again: %s", ok and "ok" or "failed")
    return ok
end

-- The livery picked, put on the car in each stage's level (the game dresses the car from its own per-car pick as a
-- level loads: the menu's OnLiveryChanged didn't reach the stage, PlayerCustomization:ApplyLivery on the stage's own
-- player did, probed 21 Nov 2026). A few times after the level came: the game dresses the car from its own pick later
-- than 6 s (it was its livery again then), and one put on at the Service Park stays to the start line and on.
local LIVERY_AT = {2.0, 6.0, 12.0, 20.0, 35.0}
local function dress(t)
    if not livery then return end
    local okw, w = pcall(UEHelpers.GetWorld)
    local name = okw and w and w:IsValid() and w:GetFullName() or ""
    if name == "" or name:find("MainMenu", 1, true) then
        livery_world = nil
        return
    end
    if livery_world ~= name then
        livery_world, livery_at, livery_done = name, t, 0
    end
    local due = LIVERY_AT[livery_done + 1]
    if not due or t - livery_at < due then return end
    livery_done = livery_done + 1
    local c = nil
    for _, x in ipairs(FindAllOf("PlayerCustomizationComponent") or {}) do
        local ok, n = pcall(function() return x:GetFullName() end)
        if ok and n:find("PersistentLevel", 1, true) and n:find("RacePlayerController", 1, true) then c = x end
    end
    if c then
        if livery_done == 1 and livery:sub(1, 8) == "usergen_" then D.rescan_liveries() end   -- (one installed since)
        local ok = pcall(function() c:ApplyLivery(FName(livery)) end)
        log("livery %s on the stage's car: %s", livery, ok and "ok" or "failed")
    end
end

-- ---------------------------------------------------------------------- the whole car at the finish line
-- The car as it crossed the finish line goes on to the next stage, whatever happened past it (the user, 24 Nov 2026:
-- "the whole state of a car - including tyres"; fair for everyone, a crash after the line or not). The game carries the
-- car between a Rally Weekend's stages itself: NEXT STAGE stores a snapshot of it (FSM_NextGamePostGameGM:
-- CarRaceComponent and PlayerTiresSetupComponent ClientStoreSnapshot -> ServerSnapshotStored(struct)) and the next
-- stage loads it (ClientLoadSnapshot). Probed in the game 24 Nov 2026: the same two calls made by hand on the stage give
-- the same structs there and then, nothing else happens. So: at the finish line (PlayerRaceSectorsTracker:
-- MulticastOnLastSectorPassed) the car's and the tyres' snapshots are taken that way and kept (every field the game's
-- reflection shows); when the game stores its own after the finish, those fields are written into it. Kept: the parts'
-- life (0-1 in the snapshot), brakes' / clutch's / differentials' wear, the body's deformation and parts come off, the
-- lights' damage, dirt and body damage zones, the windscreens' cracks (their baked intensities), each tyre (tread,
-- wear: grain, blisters, marbles, flat spots; damage, deflation, puncture). Not kept (no fields the game shows): each
-- part's property bag, the windscreens' crack history. Only for a stage ACR DAILY took the game to (ACRDAILY_OURS).
local V = "v"
-- an array of the snapshot (by place, or by its entries' `key` name); `fill`: what an entry the car at the finish didn't
-- have gets (the game lists only what isn't as new: a part, a bent bone, a panel come off after the line put back as
-- new: seen 24 Nov 2026, the front lights broken past the line came along until this)
local function A(s, key, fill) return {arr = s, key = key, fill = fill} end
local WEAR = {Wear = {Value = V}}
local ATTACHED = {State = {bDetached = false, bPartiallyDetached = false}}
local SNAP_CAR = {
    CarState = {BrakesDiscsStatus = A(WEAR), BrakesPadsStatus = A(WEAR), ClutchStatus = WEAR, DifferentialsStatus = A(WEAR)},
    CarDestruction = {
        CarDeformer = {DeformableBones = A({State = {CurrentDeformation = V, DeformationRand = V}}, "Name",
            {State = {CurrentDeformation = 0.0}})},
        ConstrainedComponents = {
            ksState = {
                Components = A({State = {Constraints = A({State = {bDetached = V, bPartiallyDetached = V}}, "Name", ATTACHED)}},
                    "Name", {State = {Constraints = {all = ATTACHED}}}),
                ComponentsConstraints = A({State = {Constraint = {bDetached = V, bPartiallyDetached = V}}}, "Name",
                    {State = {Constraint = {bDetached = false, bPartiallyDetached = false}}})},
            ConstrainedComponentsState = A({State = {bPartialBreakEnabled = V, bBreakEnabled = V, bExternalReset = V}}, "Name")}},
    CarDamage = {PartsStates = A({LifePoints = V, bRepaired = V}, "ID", {LifePoints = 1.0})},
    LightsDamage = {ZoneDamages = A(V)},                 -- (by place: ZoneNames is the same list, checked below)
    CarFX = {ZonesData = A({Values = A(V), Damages = V}), GenericDirt = V},
    Windshields = {Windshields = A({BakedCracksIntensities = {X = V, Y = V, Z = V, W = V}}, "ComponentName")},
}
local SNAP_TYRES = {ProviderState = {Tires = A({MaxTread = A(V), PreviousEquippedIndex = V,
    Damage = {Wear = {Tread = A(V), Grain = V, Blister = V, Marbles = V, FlatSpot = V, Normalized = V},
              Value = V, Deflation = V, bPunctured = V}}, "ID")}}

local function snap_read(x, sch)
    if sch == V then return x end
    if sch.arr then
        local out = {n = #x, by = sch.key and {} or nil}
        for i = 1, #x do
            local e = x[i]
            local ok, v = pcall(snap_read, e, sch.arr)
            if ok then
                if sch.key then out.by[e[sch.key]:ToString()] = v else out[i] = v end
            end
        end
        return out
    end
    local out = {}
    for k, s in pairs(sch) do
        local ok, v = pcall(function() return snap_read(x[k], s) end)
        if ok then out[k] = v end
    end
    return out
end

local function snap_write(x, sch, d, st)
    -- d (snap_read's) written into x; st: {set, skipped} counts
    if sch.arr then
        if not sch.key and d.n ~= #x then st.skipped = st.skipped + 1 return end   -- (another list: left)
        for i = 1, #x do
            local e = x[i]
            local v = nil
            if sch.key then
                local okk, k = pcall(function() return e[sch.key]:ToString() end)
                v = okk and d.by and d.by[k] or nil
                if v == nil then v = d.all or sch.fill end       -- (not at the finish: as new)
            else
                v = d[i]
            end
            if v == nil then
                st.skipped = st.skipped + 1
            elseif sch.arr == V then
                if pcall(function() x[i] = v end) then st.set = st.set + 1 else st.skipped = st.skipped + 1 end
            else
                snap_write(e, sch.arr, v, st)
            end
        end
        return
    end
    for k, s in pairs(sch) do
        local v = d[k]
        if v ~= nil then
            if s == V then
                if pcall(function() x[k] = v end) then st.set = st.set + 1 else st.skipped = st.skipped + 1 end
            else
                local ok = pcall(function() snap_write(x[k], s, v, st) end)
                if not ok then st.skipped = st.skipped + 1 end
            end
        end
    end
end

D._snap = {read = snap_read, write = snap_write, CAR = SNAP_CAR, TYRES = SNAP_TYRES}   -- (tests: client/tests/test_mod_snapshot.py)

-- _G.ACRDAILY_FINISH: {world, at, pending, car (snap_read of the car's), tyres (of the tyres'), lights (zone names),
-- parts {<part> = life points 0-100} (main.lua writes these to ingame-damage.txt while it is kept), stored}
local function world_name_now()
    local ok, n = pcall(function() return UEHelpers.GetWorld():GetFullName() end)
    return ok and n or ""
end

local function on_finish(self)
    if not rawget(_G, "ACRDAILY_OURS") or rawget(_G, "watching") then return end
    local pc = UEHelpers.GetPlayerController()
    local mine = pcall(function()
        if self:get():GetOwner():GetAddress() ~= pc:GetAddress() then error("not mine") end
    end)
    if not mine then return end
    _G.ACRDAILY_FINISH = {world = world_name_now(), at = os.clock(), pending = true}
end

local function capture(f)
    -- the game's own snapshot calls, made at the finish line (the frame after it): ServerSnapshotStored is called from
    -- inside each, and on_stored keeps what it gets
    f.pending = false
    local pc = UEHelpers.GetPlayerController()
    f.capturing = true
    pcall(function() pc.CarRace:ClientStoreSnapshot() end)
    pcall(function() pc.PlayerTiresSetup:ClientStoreSnapshot() end)
    f.capturing = false
    local parts = {}
    for k, v in pairs(f.car and f.car.CarDamage and f.car.CarDamage.PartsStates and f.car.CarDamage.PartsStates.by or {}) do
        if type(v.LifePoints) == "number" then parts[k] = v.LifePoints * 100.0 end
    end
    f.parts = next(parts) and parts or nil
    local nt = 0
    for _ in pairs(f.tyres and f.tyres.ProviderState and f.tyres.ProviderState.Tires and f.tyres.ProviderState.Tires.by or {}) do
        nt = nt + 1
    end
    log("finish: the car kept as it crossed the line (%s, %d tyres)", f.car and "car" or "NO car", nt)
end

local function on_stored(which, self, param)
    local f = rawget(_G, "ACRDAILY_FINISH")
    if not f then return end
    local pc = UEHelpers.GetPlayerController()
    local comp = which == "car" and pc.CarRace or pc.PlayerTiresSetup
    if self:get():GetAddress() ~= comp:GetAddress() then return end
    local s = param:get()
    if f.capturing then
        if which == "car" then
            f.car = snap_read(s, SNAP_CAR)
            local names = {}
            pcall(function()
                local zn = s.LightsDamage.ZoneNames
                for i = 1, #zn do names[i] = zn[i]:ToString() end
            end)
            f.lights = table.concat(names, ",")
        else
            f.tyres = snap_read(s, SNAP_TYRES)
        end
        return
    end
    -- the game's own store (NEXT STAGE, or a restart): the car as it crossed the line written into it
    if f.world ~= world_name_now() then return end
    local data = which == "car" and f.car or f.tyres
    if not data then return end
    local st = {set = 0, skipped = 0}
    if which == "car" then
        local names = {}
        pcall(function()
            local zn = s.LightsDamage.ZoneNames
            for i = 1, #zn do names[i] = zn[i]:ToString() end
        end)
        local d = data
        if table.concat(names, ",") ~= f.lights then              -- (other light zones: their damage left as it is)
            d = {}
            for k, v in pairs(data) do d[k] = v end
            d.LightsDamage = nil
        end
        snap_write(s, SNAP_CAR, d, st)
    else
        snap_write(s, SNAP_TYRES, data, st)
    end
    f.stored = (f.stored or 0) + 1
    log("finish: the game's store of the %s given the car at the finish line: %d fields, %d left", which, st.set, st.skipped)
end

_G.ACRDAILY_SNAP_ON = function(kind, self, param)
    local ok, e = pcall(function()
        if kind == "finish" then on_finish(self) else on_stored(kind, self, param) end
    end)
    if not ok then log("finish (%s): %s", kind, tostring(e)) end
end
if not rawget(_G, "ACRDAILY_SNAP_HOOKED") then              -- (once a game: the hooks call the latest module's code)
    _G.ACRDAILY_SNAP_HOOKED = true
    for _, h in ipairs({{"/Script/acr.PlayerRaceSectorsTracker:MulticastOnLastSectorPassed", "finish"},
            {"/Script/acr.CarRaceComponent:ServerSnapshotStored", "car"},
            {"/Script/acr.PlayerTiresSetupComponent:ServerSnapshotStored", "tyres"}}) do
        local kind = h[2]
        local ok, e = pcall(RegisterHook, h[1], function(self, param)
            local fn = rawget(_G, "ACRDAILY_SNAP_ON")
            if fn then fn(kind, self, param) end
        end)
        if not ok then log("finish: no hook on %s: %s", h[1], tostring(e)) end
    end
end

--- every frame (appui.lua, before anything else: the app may be gone)
function D.finish_tick()
    local f = rawget(_G, "ACRDAILY_FINISH")
    if not f then return end
    if f.pending then
        capture(f)
    elseif f.world ~= world_name_now() then                  -- (another level: the next stage, the menu)
        _G.ACRDAILY_FINISH = nil
    end
end

--- every frame (appui.lua)
function D.tick(t)
    pcall(dress, t)
    local okd, ed = pcall(restore_damage, t)
    if not okd then
        log("damage: %s", tostring(ed))
        car_damage = nil
    end
    if not job then return end
    if job.wait > 0 then
        job.wait = job.wait - 1
        return
    end
    local f = job.steps[job.step]
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
