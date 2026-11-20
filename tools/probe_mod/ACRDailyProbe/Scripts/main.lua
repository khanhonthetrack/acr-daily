-- ACR Daily probe (testing only, never shipped): runs %APPDATA%\ACR Daily\probe\probe.lua on the game thread when it
-- appears, writes what it returns / prints to probe\out.txt, then renames it to probe.done.lua.
local DIR = (os.getenv("APPDATA") or ".") .. "\\ACR Daily\\probe\\"
local IN, OUT, DONE = DIR .. "probe.lua", DIR .. "out.txt", DIR .. "probe.done.lua"
print("[ACRDailyProbe] loaded\n")

_G.PROBE = _G.PROBE or {}            -- state kept between probes
local function run()
    local f = io.open(IN, "r")
    if not f then return end
    local src = f:read("a")
    f:close()
    os.remove(DONE)
    os.rename(IN, DONE)
    local lines = {}
    local function out(...)
        local t = {}
        for i = 1, select("#", ...) do t[#t + 1] = tostring(select(i, ...)) end
        lines[#lines + 1] = table.concat(t, "\t")
    end
    local env = setmetatable({out = out}, {__index = _G})
    local chunk, err = load(src, "probe", "t", env)
    if not chunk then
        out("LOAD ERROR", err)
    else
        local ok, e = xpcall(chunk, debug.traceback)
        if not ok then out("ERROR", e) end
    end
    local o = io.open(OUT .. ".tmp", "w")
    o:write(table.concat(lines, "\n") .. "\n")
    o:close()
    os.remove(OUT)
    os.rename(OUT .. ".tmp", OUT)
end

local n = 0
LoopInGameThreadAfterFrames(1, function()
    n = n + 1
    if n % 20 == 0 then
        local ok, e = pcall(run)
        if not ok then print("[ACRDailyProbe] " .. tostring(e) .. "\n") end
    end
    local hook = rawget(_G, "PROBE_TICK")
    if hook then pcall(hook, n) end
    return false
end)
