-- REAPER MCP Server - Lua ReaScript
-- File-based IPC: polls for command.json, writes response.json
-- Install: Actions > Show action list > Load ReaScript > select this file
-- Then run it. It will keep running via defer() loop.

local json = {}
local ipc_dir
local command_file
local response_file
local command_tmp
local response_tmp
local lock_file
local running = true
local last_heartbeat = 0
local HEARTBEAT_INTERVAL = 10 -- seconds

-- ============================================================
-- Setup IPC directory
-- ============================================================

local function setup_ipc()
  local sep = package.config:sub(1,1)
  if sep == "\\" then
    -- Windows: %TEMP% (same thing Python's tempfile.gettempdir() returns)
    ipc_dir = os.getenv("TEMP") .. "\\reaper_mcp"
  else
    -- macOS + Linux: prefer $TMPDIR if set (macOS sets it to /var/folders/.../T/),
    -- otherwise fall back to /tmp. This MUST match Python's tempfile.gettempdir()
    -- or the Python MCP client and this Lua server write to different folders
    -- and never see each other's files.
    local tmpdir = os.getenv("TMPDIR")
    if tmpdir and tmpdir ~= "" then
      if tmpdir:sub(-1) == "/" then tmpdir = tmpdir:sub(1, -2) end
      ipc_dir = tmpdir .. "/reaper_mcp"
    else
      ipc_dir = "/tmp/reaper_mcp"
    end
  end
  -- Use REAPER's native directory API instead of os.execute so an
  -- adversarial TMPDIR value can't inject shell commands.
  if reaper.RecursiveCreateDirectory then
    reaper.RecursiveCreateDirectory(ipc_dir, 0)
  else
    -- Very old REAPER fallback: shell mkdir with defensive quoting.
    -- Replace any embedded quote in the path with underscore.
    local safe_dir = ipc_dir:gsub('"', "_")
    if sep == "\\" then
      os.execute('mkdir "' .. safe_dir .. '" 2>nul')
    else
      os.execute('mkdir -p "' .. safe_dir .. '" 2>/dev/null')
    end
  end
  command_file = ipc_dir .. sep .. "command.json"
  response_file = ipc_dir .. sep .. "response.json"
  command_tmp = ipc_dir .. sep .. "command.tmp"
  response_tmp = ipc_dir .. sep .. "response.tmp"
  lock_file = ipc_dir .. sep .. "server.lock"

  -- Write lock file so client knows we're alive
  local f = io.open(lock_file, "w")
  if f then f:write(tostring(os.time())); f:close() end
  last_heartbeat = os.time()

  reaper.ShowConsoleMsg("ReaperMCP: Server started. IPC dir: " .. ipc_dir .. "\n")
end

-- ============================================================
-- Heartbeat — update lock file periodically so client
-- can detect if we've crashed
-- ============================================================

local function update_heartbeat()
  local now = os.time()
  if now - last_heartbeat >= HEARTBEAT_INTERVAL then
    local f = io.open(lock_file, "w")
    if f then f:write(tostring(now)); f:close() end
    last_heartbeat = now
  end
end

-- ============================================================
-- Minimal JSON encoder/decoder
-- ============================================================

local MAX_DEPTH = 50
local MAX_JSON_LENGTH = 20 * 1024 * 1024 -- 20MB (headroom for 50k-note batches)

local function json_encode(val, depth, visited)
  depth = depth or 0
  if depth > MAX_DEPTH then return '"<max depth>"' end

  local t = type(val)
  if t == "nil" then return "null"
  elseif t == "boolean" then return val and "true" or "false"
  elseif t == "number" then
    if val ~= val then return "null" end -- NaN
    if val == math.huge or val == -math.huge then return "null" end
    -- Use integer format when possible
    if val == math.floor(val) and val >= -2147483648 and val <= 2147483647 then
      return string.format("%d", val)
    end
    -- %.17g preserves full IEEE-754 double precision on the round-trip
    -- Lua → JSON → Python. The old "%.6f" truncated MIDI positions to
    -- microsecond granularity, which quietly drifted notes off-grid on
    -- sub-sample batch inserts. %.17g gives ~15 decimal digits — enough
    -- to keep every float we actually handle bit-exact.
    return string.format("%.17g", val)
  elseif t == "string" then
    val = val:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t'):gsub('%z', '')
    return '"' .. val .. '"'
  elseif t == "table" then
    visited = visited or {}
    if visited[val] then return '"<circular>"' end
    visited[val] = true
    -- Check if pure array: only consecutive integer keys 1..n, no string keys
    local n = #val
    local is_array = true
    if n == 0 and next(val) ~= nil then
      is_array = false  -- has keys but no numeric ones
    else
      -- Verify no extra keys beyond 1..n
      local count = 0
      for _ in pairs(val) do count = count + 1 end
      if count ~= n then is_array = false end
    end
    if is_array then
      local parts = {}
      for i = 1, n do
        parts[i] = json_encode(val[i], depth + 1, visited)
      end
      visited[val] = nil
      return "[" .. table.concat(parts, ",") .. "]"
    else
      local parts = {}
      for k, v in pairs(val) do
        parts[#parts+1] = json_encode(tostring(k), depth + 1, visited) .. ":" .. json_encode(v, depth + 1, visited)
      end
      visited[val] = nil
      return "{" .. table.concat(parts, ",") .. "}"
    end
  end
  return "null"
end

local function json_decode(str)
  if not str or str == "" then return nil end
  if #str > MAX_JSON_LENGTH then return nil end
  local len = #str
  local pos = 1
  local depth = 0
  local byte = string.byte
  local sub = string.sub
  local find = string.find

  -- ASCII codes for fast comparison
  local B_SPACE = 32  -- ' '
  local B_TAB = 9     -- '\t'
  local B_NL = 10     -- '\n'
  local B_CR = 13     -- '\r'
  local B_QUOTE = 34  -- '"'
  local B_BSLASH = 92 -- '\\'
  local B_LBRACE = 123 -- '{'
  local B_RBRACE = 125 -- '}'
  local B_LBRACK = 91  -- '['
  local B_RBRACK = 93  -- ']'
  local B_COLON = 58   -- ':'
  local B_COMMA = 44   -- ','
  local B_t = 116
  local B_f = 102
  local B_n = 110
  local B_MINUS = 45

  local function skip_ws()
    while pos <= len do
      local b = byte(str, pos)
      if b == B_SPACE or b == B_TAB or b == B_NL or b == B_CR then
        pos = pos + 1
      else
        return
      end
    end
  end

  local parse_value -- forward declaration

  local esc_map = {n = '\n', r = '\r', t = '\t', ['"'] = '"', ['\\'] = '\\', ['/'] = '/'}

  local function parse_string()
    pos = pos + 1 -- skip opening "
    local result = {}
    local chunk_start = pos
    while pos <= len do
      -- Find the next " or \ using string.find (bulk scan)
      local special = find(str, '["\\]', pos)
      if not special then
        -- unterminated string
        pos = len + 1
        return table.concat(result)
      end
      -- Grab the chunk of plain characters before the special char
      if special > chunk_start then
        result[#result+1] = sub(str, chunk_start, special - 1)
      end
      local b = byte(str, special)
      if b == B_QUOTE then
        pos = special + 1
        return table.concat(result)
      else
        -- backslash escape
        local esc_char = sub(str, special + 1, special + 1)
        local mapped = esc_map[esc_char]
        if mapped then
          result[#result+1] = mapped
        elseif esc_char == 'u' then
          -- Unicode escape \uXXXX — decode to UTF-8. Surrogate pairs are
          -- collapsed to '?' (rare in practice for track / plugin names).
          local hex = sub(str, special + 2, special + 5)
          local cp = tonumber(hex, 16)
          if cp then
            if cp < 0x80 then
              result[#result+1] = string.char(cp)
            elseif cp < 0x800 then
              result[#result+1] = string.char(
                0xC0 + math.floor(cp / 0x40),
                0x80 + (cp % 0x40)
              )
            elseif cp >= 0xD800 and cp <= 0xDFFF then
              result[#result+1] = '?'  -- surrogate half
            elseif cp < 0x10000 then
              result[#result+1] = string.char(
                0xE0 + math.floor(cp / 0x1000),
                0x80 + math.floor((cp % 0x1000) / 0x40),
                0x80 + (cp % 0x40)
              )
            else
              result[#result+1] = '?'
            end
          else
            result[#result+1] = '?'
          end
          pos = special + 6
          chunk_start = pos
          goto continue
        else
          result[#result+1] = esc_char
        end
        pos = special + 2
        chunk_start = pos
      end
      ::continue::
    end
    return table.concat(result)
  end

  local function parse_number()
    -- Use string.find to grab the full number token
    local _, num_end = find(str, '^%-?%d+%.?%d*[eE]?[%+%-]?%d*', pos)
    if not num_end then return 0 end
    local n = tonumber(sub(str, pos, num_end))
    pos = num_end + 1
    return n
  end

  local function parse_object()
    depth = depth + 1
    if depth > MAX_DEPTH then error("JSON nesting too deep") end
    pos = pos + 1 -- skip {
    local obj = {}
    skip_ws()
    if byte(str, pos) == B_RBRACE then pos = pos + 1; depth = depth - 1; return obj end
    while true do
      skip_ws()
      local key = parse_string()
      skip_ws()
      pos = pos + 1 -- skip :
      skip_ws()
      obj[key] = parse_value()
      skip_ws()
      if byte(str, pos) == B_RBRACE then pos = pos + 1; depth = depth - 1; return obj end
      pos = pos + 1 -- skip ,
    end
  end

  local function parse_array()
    depth = depth + 1
    if depth > MAX_DEPTH then error("JSON nesting too deep") end
    pos = pos + 1 -- skip [
    local arr = {}
    skip_ws()
    if byte(str, pos) == B_RBRACK then pos = pos + 1; depth = depth - 1; return arr end
    while true do
      skip_ws()
      arr[#arr+1] = parse_value()
      skip_ws()
      if byte(str, pos) == B_RBRACK then pos = pos + 1; depth = depth - 1; return arr end
      pos = pos + 1 -- skip ,
    end
  end

  parse_value = function()
    skip_ws()
    local b = byte(str, pos)
    if b == B_QUOTE then return parse_string()
    elseif b == B_LBRACE then return parse_object()
    elseif b == B_LBRACK then return parse_array()
    elseif b == B_t then pos = pos + 4; return true
    elseif b == B_f then pos = pos + 5; return false
    elseif b == B_n then pos = pos + 4; return nil
    else return parse_number() end
  end

  local ok, result = pcall(parse_value)
  if ok then return result else return nil end
end

-- ============================================================
-- Response helpers (with error checking on file I/O)
-- ============================================================

local function send_success(data)
  local resp = json_encode(data and {success = true, data = data} or {success = true})
  local f, err = io.open(response_tmp, "w")
  if not f then
    reaper.ShowConsoleMsg("ReaperMCP: Failed to write response: " .. tostring(err) .. "\n")
    return
  end
  local ok, werr = f:write(resp)
  f:close()
  if not ok then
    reaper.ShowConsoleMsg("ReaperMCP: Write failed: " .. tostring(werr) .. "\n")
    return
  end
  -- On Windows os.rename fails if dest exists; remove first
  os.remove(response_file)
  local rok, rerr = os.rename(response_tmp, response_file)
  if not rok then
    reaper.ShowConsoleMsg("ReaperMCP: Rename failed: " .. tostring(rerr) .. "\n")
  end
end

local function send_error(msg)
  local resp = json_encode({success = false, error = msg})
  local f, err = io.open(response_tmp, "w")
  if not f then
    reaper.ShowConsoleMsg("ReaperMCP: Failed to write error response: " .. tostring(err) .. "\n")
    return
  end
  local ok, werr = f:write(resp)
  f:close()
  if not ok then
    reaper.ShowConsoleMsg("ReaperMCP: Write failed: " .. tostring(werr) .. "\n")
    return
  end
  -- On Windows os.rename fails if dest exists; remove first
  os.remove(response_file)
  local rok, rerr = os.rename(response_tmp, response_file)
  if not rok then
    reaper.ShowConsoleMsg("ReaperMCP: Rename failed: " .. tostring(rerr) .. "\n")
  end
end

-- ============================================================
-- Validation helpers
-- ============================================================

local function require_int(p, name)
  local v = p[name]
  if v == nil then error("Missing required parameter: " .. name, 0) end
  local n = tonumber(v)
  if not n then error("Parameter '" .. name .. "' must be a number, got: " .. tostring(v), 0) end
  return math.floor(n)
end

local function require_num(p, name)
  local v = p[name]
  if v == nil then error("Missing required parameter: " .. name, 0) end
  local n = tonumber(v)
  if not n then error("Parameter '" .. name .. "' must be a number, got: " .. tostring(v), 0) end
  return n
end

local function clamp(val, lo, hi)
  val = tonumber(val) or lo
  if val < lo then return lo end
  if val > hi then return hi end
  return val
end

local function clamp_color(val)
  return clamp(tonumber(val) or 0, 0, 255)
end

-- Build a REAPER "custom color" native int (with the 0x1000000 flag) from
-- r,g,b, clamping each to 0-255.
local function native_color(r, g, b)
  r, g, b = clamp_color(r), clamp_color(g), clamp_color(b)
  return reaper.ColorToNative(r, g, b) | 0x1000000
end

-- Same, but (0,0,0) means "no color" (returns REAPER's own 0 sentinel)
-- instead of actual black — for call sites where color_r/g/b default to 0
-- when the caller didn't pass a color at all, so there's no way to tell
-- "wants black" from "didn't ask for a color" apart from this convention.
local function native_color_or_none(r, g, b)
  r, g, b = clamp_color(r), clamp_color(g), clamp_color(b)
  if r == 0 and g == 0 and b == 0 then return 0 end
  return reaper.ColorToNative(r, g, b) | 0x1000000
end

-- Build a native color from a [r,g,b] array (or a JSON string of one) —
-- the shape configure_tracks/add_markers_batch/setup_effect_bus's bus_color
-- all accept. Validates the shape instead of silently defaulting missing/
-- malformed components to 0, which used to mean any wrong shape (an
-- {r=,g=,b=} object, a hex string, out-of-range floats) silently painted
-- everything black with no error. Returns (native_color, nil) on success,
-- (nil, error_message) on a malformed array.
local function native_color_from_array(arr)
  if type(arr) == "string" then arr = json_decode(arr) end
  if type(arr) ~= "table" or #arr ~= 3 then
    return nil, "color must be a [r,g,b] array of exactly 3 numbers (0-255 each)"
  end
  for _, v in ipairs(arr) do
    if type(v) ~= "number" then
      return nil, "color must be a [r,g,b] array of exactly 3 numbers (0-255 each)"
    end
  end
  return native_color(arr[1], arr[2], arr[3]), nil
end

-- ============================================================
-- State builders (feedback loops)
-- ============================================================

local function db_from_vol(vol)
  if vol > 0 then return 20 * math.log(vol, 10) end
  return -150.0
end

local function vol_from_db(db)
  return 10 ^ (db / 20)
end

local function build_transport_state()
  local state = reaper.GetPlayState()
  local pos
  if state & 1 == 1 then pos = reaper.GetPlayPosition() else pos = reaper.GetCursorPosition() end
  local bpm, bpi = reaper.GetProjectTimeSignature2(0)
  local playrate = reaper.Master_GetPlayRate(0)
  return {
    play_state = state,
    playing = (state & 1) == 1,
    paused = (state & 2) == 2,
    recording = (state & 4) == 4,
    position = pos,
    bpm = bpm,
    time_sig_num = bpi,
    time_sig_den = 4,
    repeating = reaper.GetSetRepeat(-1) == 1,
    playrate = playrate,
    project_length = reaper.GetProjectLength(0)
  }
end

-- Resolve a take's actual source media file, walking up through SECTION /
-- reverse wrapper sources to the real root (those wrap the true file with
-- their own source object, so a direct source-filename call on an unwrapped
-- take returns nothing useful). Returns (root_source, filename) — filename
-- is "" if the take has no source (e.g. empty/offline item).
local function resolve_source(take)
  local src = reaper.GetMediaItemTake_Source(take)
  if not src then return nil, "" end
  local root = src
  for _ = 1, 8 do
    local parent = reaper.GetMediaSourceParent(root)
    if not parent then break end
    root = parent
  end
  local filename = reaper.GetMediaSourceFileName(root, "")
  if type(filename) ~= "string" or filename == "" then
    local _, fn2 = reaper.GetMediaSourceFileName(root, "")
    filename = fn2 or ""
  end
  return root, (filename or "")
end

local function basename(path)
  if path == "" then return "" end
  return path:match("([^\\/]+)$") or path
end

-- Distinct source filenames (basename only) across every audio item on a
-- track — so a track carrying a dragged-in sample (Splice, etc.) shows what
-- was actually dropped on it directly from track-level info, no separate
-- per-item lookup needed. Capped at 20 to keep track_get_all bounded for a
-- track with a huge number of chopped/spliced items.
local function track_sample_filenames(tr)
  local seen, names = {}, {}
  local n = reaper.CountTrackMediaItems(tr)
  for i = 0, n - 1 do
    if #names >= 20 then break end
    local it = reaper.GetTrackMediaItem(tr, i)
    local take = it and reaper.GetActiveTake(it)
    if take and not reaper.TakeIsMIDI(take) then
      local _, filename = resolve_source(take)
      if filename ~= "" then
        local b = basename(filename)
        if not seen[b] then
          seen[b] = true
          names[#names+1] = b
        end
      end
    end
  end
  return names
end

local function build_track_info(tr, idx)
  local _, name = reaper.GetTrackName(tr)
  local vol = reaper.GetMediaTrackInfo_Value(tr, "D_VOL")
  local pan = reaper.GetMediaTrackInfo_Value(tr, "D_PAN")
  local color = reaper.GetMediaTrackInfo_Value(tr, "I_CUSTOMCOLOR")
  local r, g, b = 0, 0, 0
  if color ~= 0 then r, g, b = reaper.ColorFromNative(color) end
  return {
    index = idx,
    name = name,
    volume = vol,
    volume_db = db_from_vol(vol),
    pan = pan,
    mute = reaper.GetMediaTrackInfo_Value(tr, "B_MUTE") == 1,
    solo = reaper.GetMediaTrackInfo_Value(tr, "I_SOLO") > 0,
    armed = reaper.GetMediaTrackInfo_Value(tr, "I_RECARM") == 1,
    selected = reaper.IsTrackSelected(tr),
    fx_count = reaper.TrackFX_GetCount(tr),
    item_count = reaper.CountTrackMediaItems(tr),
    -- Sample-pack vendors (Splice, etc.) commonly embed BPM/key in the
    -- filename itself ("Karra_Vocal_Loop_120bpm_Cmin.wav") — this is the
    -- actual dragged-in audio file names, not the track's own display name.
    sample_filenames = track_sample_filenames(tr),
    send_count = reaper.GetTrackNumSends(tr, 0),
    receive_count = reaper.GetTrackNumSends(tr, -1),
    folder_depth = reaper.GetMediaTrackInfo_Value(tr, "I_FOLDERDEPTH"),
    color_r = r, color_g = g, color_b = b,
    input_index = reaper.GetMediaTrackInfo_Value(tr, "I_RECINPUT"),
    phase_invert = reaper.GetMediaTrackInfo_Value(tr, "B_PHASE") == 1,
    automation_mode = reaper.GetTrackAutomationMode(tr)
  }
end

local function build_item_info(item, idx)
  local pos = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
  local len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
  local vol = reaper.GetMediaItemInfo_Value(item, "D_VOL")
  local take = reaper.GetActiveTake(item)
  local name = ""
  local is_midi = false
  local pitch = 0.0
  local playrate = 1.0
  local source_file = ""
  if take then
    _, name = reaper.GetTakeName(take)
    is_midi = reaper.TakeIsMIDI(take)
    pitch = reaper.GetMediaItemTakeInfo_Value(take, "D_PITCH")
    playrate = reaper.GetMediaItemTakeInfo_Value(take, "D_PLAYRATE")
    -- Audio only — MIDI takes have no media source file to name.
    if not is_midi then
      local _, filename = resolve_source(take)
      source_file = filename
    end
  end
  local tr = reaper.GetMediaItemTrack(item)
  local tr_num = reaper.GetMediaTrackInfo_Value(tr, "IP_TRACKNUMBER")
  if tr_num < 1 then tr_num = 1 end
  return {
    index = idx,
    track_index = math.floor(tr_num - 1),
    position = pos,
    length = len,
    volume = vol,
    volume_db = db_from_vol(vol),
    name = name,
    -- Full source file path and just the filename — sample-pack vendors
    -- (Splice, etc.) commonly embed BPM/key in the filename itself
    -- ("Karra_Vocal_Loop_120bpm_Cmin.wav"), which the take's editable
    -- display `name` above does NOT reliably preserve.
    source_file = source_file,
    source_filename = basename(source_file),
    selected = reaper.IsMediaItemSelected(item),
    mute = reaper.GetMediaItemInfo_Value(item, "B_MUTE") == 1,
    is_midi = is_midi,
    pitch = pitch,
    playrate = playrate,
    fade_in = reaper.GetMediaItemInfo_Value(item, "D_FADEINLEN"),
    fade_out = reaper.GetMediaItemInfo_Value(item, "D_FADEOUTLEN"),
    color = reaper.GetMediaItemInfo_Value(item, "I_CUSTOMCOLOR")
  }
end

local function build_fx_info(tr, fx_idx)
  local _, name = reaper.TrackFX_GetFXName(tr, fx_idx, "")
  local _, preset = reaper.TrackFX_GetPreset(tr, fx_idx, "")
  return {
    index = fx_idx,
    name = name,
    enabled = reaper.TrackFX_GetEnabled(tr, fx_idx),
    preset = preset,
    param_count = reaper.TrackFX_GetNumParams(tr, fx_idx)
  }
end

local function build_fx_chain(tr)
  local count = reaper.TrackFX_GetCount(tr)
  local chain = {}
  for i = 0, count - 1 do
    chain[#chain+1] = build_fx_info(tr, i)
  end
  return {
    fx_count = count,
    instrument_index = reaper.TrackFX_GetInstrument(tr),
    fx_chain = chain
  }
end

local function build_fx_params(tr, fx_idx)
  local _, fx_name = reaper.TrackFX_GetFXName(tr, fx_idx, "")
  local _, preset = reaper.TrackFX_GetPreset(tr, fx_idx, "")
  local num = reaper.TrackFX_GetNumParams(tr, fx_idx)
  local params = {}
  local skipped = 0

  -- Detect FabFilter Pro-Q (has "Band N Used" pattern with tons of unused bands)
  local is_proq = fx_name:find("Pro%-Q") ~= nil

  -- Track which FabFilter bands are actually used (Band N Used != "Unused")
  local used_bands = {}
  if is_proq then
    for i = 0, num - 1 do
      local _, pname = reaper.TrackFX_GetParamName(tr, fx_idx, i, "")
      local val = reaper.TrackFX_GetParam(tr, fx_idx, i)
      local band_num = pname:match("^Band (%d+) Used$")
      if band_num and val > 0 then
        used_bands[tonumber(band_num)] = true
      end
    end
  end

  for i = 0, num - 1 do
    local _, pname = reaper.TrackFX_GetParamName(tr, fx_idx, i, "")
    local val = reaper.TrackFX_GetParam(tr, fx_idx, i)

    -- Skip junk params
    local is_midi_cc = pname:find("MIDI CC") ~= nil
    local is_internal = pname == "Internal" or pname == "Pitch Bend" or pname == "Channel Pressure"
    local is_junk = (pname == "-" and val == 0) or pname == "Host Bypass"
    local skip = is_midi_cc or is_internal or is_junk

    -- For Pro-Q: skip params belonging to unused bands
    if not skip and is_proq then
      local band_num = pname:match("^Band (%d+) ")
      if band_num and not used_bands[tonumber(band_num)] then
        skip = true
      end
    end

    if skip then
      skipped = skipped + 1
    else
      local _, fmt = reaper.TrackFX_FormatParamValue(tr, fx_idx, i, val, "")
      params[#params+1] = {index = i, name = pname, value = val, display = fmt}
    end
  end
  return {
    fx_name = fx_name,
    preset = preset,
    enabled = reaper.TrackFX_GetEnabled(tr, fx_idx),
    param_count = num,
    params_shown = #params,
    params_skipped = skipped,
    params = params
  }
end

local function build_send_info(tr, send_idx)
  local vol = reaper.GetTrackSendInfo_Value(tr, 0, send_idx, "D_VOL")
  local pan = reaper.GetTrackSendInfo_Value(tr, 0, send_idx, "D_PAN")
  local dest_tr = reaper.GetTrackSendInfo_Value(tr, 0, send_idx, "P_DESTTRACK")
  local dest_index = -1
  local dest_name = ""
  if dest_tr then
    dest_index = math.floor(reaper.GetMediaTrackInfo_Value(dest_tr, "IP_TRACKNUMBER") - 1)
    local _, dn = reaper.GetTrackName(dest_tr)
    dest_name = dn or ""
  end
  return {
    index = send_idx,
    volume = vol,
    volume_db = db_from_vol(vol),
    pan = pan,
    mute = reaper.GetTrackSendInfo_Value(tr, 0, send_idx, "B_MUTE") == 1,
    dest_track_index = dest_index,
    dest_track_name = dest_name,
  }
end

-- ============================================================
-- Helper: get track safely
-- ============================================================

local function get_track(params, key)
  local idx = params[key or "track_index"]
  if idx == nil then return nil, nil, "Missing parameter: " .. (key or "track_index") end
  local tr = reaper.GetTrack(0, math.floor(idx))
  if not tr then return nil, nil, "Track not found (index " .. idx .. ")" end
  return tr, math.floor(idx), nil
end

-- ============================================================
-- TRANSPORT handlers
-- ============================================================

local transport = {}

function transport.transport_play(p)
  reaper.Main_OnCommand(1007, 0)
  return build_transport_state()
end

function transport.transport_stop(p)
  reaper.Main_OnCommand(1016, 0)
  return build_transport_state()
end

function transport.transport_pause(p)
  reaper.Main_OnCommand(1008, 0)
  return build_transport_state()
end

function transport.transport_record(p)
  reaper.Main_OnCommand(1013, 0)
  return build_transport_state()
end

function transport.transport_get_state(p)
  return build_transport_state()
end

function transport.transport_set_position(p)
  if p.seconds == nil then return nil, "Missing parameter: seconds" end
  reaper.SetEditCurPos(p.seconds, true, true)
  return build_transport_state()
end

function transport.transport_set_bpm(p)
  if p.bpm == nil then return nil, "Missing parameter: bpm" end
  reaper.SetCurrentBPM(0, p.bpm, true)
  return build_transport_state()
end

function transport.transport_set_time_signature(p)
  if not p.numerator or not p.denominator then return nil, "Missing parameter: numerator/denominator" end
  local bpm = reaper.Master_GetTempo()
  reaper.SetTempoTimeSigMarker(0, -1, 0, -1, -1, bpm, p.numerator, p.denominator, false)
  reaper.UpdateTimeline()
  return build_transport_state()
end

function transport.transport_toggle_repeat(p)
  reaper.Main_OnCommand(1068, 0)
  return build_transport_state()
end

function transport.transport_toggle_metronome(p)
  reaper.Main_OnCommand(40364, 0)
  local state = build_transport_state()
  -- Read metronome state: action 40364 toggles it, GetToggleCommandState returns 1 if on
  state.metronome_enabled = reaper.GetToggleCommandState(40364) == 1
  return state
end

function transport.transport_set_playrate(p)
  if p.rate == nil then return nil, "Missing parameter: rate" end
  reaper.CSurf_OnPlayRateChange(p.rate)
  return build_transport_state()
end

-- ============================================================
-- TRACK handlers
-- ============================================================

local track = {}

function track.track_get_all(p)
  local n = reaper.CountTracks(0)
  local tracks = {}
  for i = 0, n - 1 do
    tracks[#tracks+1] = build_track_info(reaper.GetTrack(0, i), i)
  end
  return {track_count = n, tracks = tracks}
end

function track.track_get_info(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local info = build_track_info(tr, idx)
  -- Add FX chain detail
  local chain = {}
  for i = 0, reaper.TrackFX_GetCount(tr) - 1 do
    chain[#chain+1] = build_fx_info(tr, i)
  end
  info.fx_chain = chain
  return info
end

function track.track_create(p)
  local idx = p.index or -1
  if idx == -1 then idx = reaper.CountTracks(0) end
  reaper.Undo_BeginBlock()
  reaper.InsertTrackAtIndex(idx, true)
  local tr = reaper.GetTrack(0, idx)
  if p.name and p.name ~= "" then
    reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", p.name, true)
  end
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("MCP: track_create " .. (p.name or ""), -1)
  return build_track_info(tr, idx)
end

function track.track_delete(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local _, name = reaper.GetTrackName(tr)
  reaper.DeleteTrack(tr)
  reaper.UpdateArrange()
  return {deleted_index = idx, deleted_name = name or "", remaining_tracks = reaper.CountTracks(0)}
end

function track.track_rename(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if not p.name then return nil, "Missing parameter: name" end
  reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", p.name, true)
  reaper.UpdateArrange()
  return build_track_info(tr, idx)
end

function track.track_set_volume(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if p.volume_db == nil then return nil, "Missing parameter: volume_db" end
  reaper.SetMediaTrackInfo_Value(tr, "D_VOL", vol_from_db(p.volume_db))
  return build_track_info(tr, idx)
end

function track.track_set_pan(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if p.pan == nil then return nil, "Missing parameter: pan" end
  local pan = clamp(p.pan, -1.0, 1.0)
  reaper.SetMediaTrackInfo_Value(tr, "D_PAN", pan)
  return build_track_info(tr, idx)
end

function track.track_set_mute(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  reaper.SetMediaTrackInfo_Value(tr, "B_MUTE", p.mute and 1 or 0)
  return build_track_info(tr, idx)
end

function track.track_set_solo(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  reaper.SetMediaTrackInfo_Value(tr, "I_SOLO", p.solo and 1 or 0)
  return build_track_info(tr, idx)
end

function track.track_set_record_arm(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  reaper.SetMediaTrackInfo_Value(tr, "I_RECARM", p.arm and 1 or 0)
  return build_track_info(tr, idx)
end

function track.track_set_color(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  reaper.SetMediaTrackInfo_Value(tr, "I_CUSTOMCOLOR", native_color(p.r, p.g, p.b))
  reaper.UpdateArrange()
  return build_track_info(tr, idx)
end

function track.track_select(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if p.exclusive then
    reaper.SetOnlyTrackSelected(tr)
  else
    local sel = p.selected
    if sel == nil then sel = true end
    reaper.SetTrackSelected(tr, sel)
  end
  return build_track_info(tr, idx)
end

function track.track_set_input(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if p.input_index == nil then return nil, "Missing parameter: input_index" end
  reaper.SetMediaTrackInfo_Value(tr, "I_RECINPUT", math.floor(p.input_index))
  return build_track_info(tr, idx)
end

function track.track_get_mixer_state(p)
  local n = reaper.CountTracks(0)
  local tracks = {}
  for i = 0, n - 1 do
    local tr = reaper.GetTrack(0, i)
    local _, name = reaper.GetTrackName(tr)
    local vol = reaper.GetMediaTrackInfo_Value(tr, "D_VOL")
    tracks[#tracks+1] = {
      i = i, name = name,
      vol_db = db_from_vol(vol),
      pan = reaper.GetMediaTrackInfo_Value(tr, "D_PAN"),
      mute = reaper.GetMediaTrackInfo_Value(tr, "B_MUTE") == 1,
      solo = reaper.GetMediaTrackInfo_Value(tr, "I_SOLO") > 0,
      fx_bypassed = reaper.GetMediaTrackInfo_Value(tr, "I_FXEN") == 0
    }
  end
  return {track_count = n, tracks = tracks}
end

function track.track_set_folder(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if p.folder_depth == nil then return nil, "Missing parameter: folder_depth" end
  reaper.SetMediaTrackInfo_Value(tr, "I_FOLDERDEPTH", math.floor(p.folder_depth))
  return build_track_info(tr, idx)
end

-- ============================================================
-- PROJECT handlers
-- ============================================================

local project = {}

function project.project_get_info(p)
  local _, name = reaper.GetProjectName(0, "")
  local path = reaper.GetProjectPath("")
  -- `path` above is the recording/media directory (exists even for a brand
  -- new, never-saved project — e.g. the default "REAPER Media" folder) —
  -- NOT the project's own .rpp file. file_path is the actual .rpp path,
  -- empty string if this project has never been saved.
  local _, file_path = reaper.EnumProjects(-1, "")
  local sr = reaper.GetSetProjectInfo(0, "PROJECT_SRATE", 0, false)
  local bpm, bpi = reaper.GetProjectTimeSignature2(0)
  return {
    name = name, path = path, file_path = file_path or "",
    sample_rate = math.floor(sr),
    bpm = bpm, time_sig_num = bpi,
    track_count = reaper.CountTracks(0),
    item_count = reaper.CountMediaItems(0),
    marker_count = reaper.CountProjectMarkers(0),
    length = reaper.GetProjectLength(0)
  }
end

function project.project_new(p)
  reaper.Main_OnCommand(40023, 0)
  local _, name = reaper.GetProjectName(0, "")
  return {name = name, track_count = reaper.CountTracks(0)}
end

function project.project_open(p)
  if not p.path then return nil, "Missing parameter: path" end
  reaper.Main_openProject(p.path)
  local _, name = reaper.GetProjectName(0, "")
  return {name = name, track_count = reaper.CountTracks(0), item_count = reaper.CountMediaItems(0), bpm = reaper.Master_GetTempo(), length = reaper.GetProjectLength(0)}
end

function project.project_save(p)
  reaper.Main_OnCommand(40026, 0)
  local _, name = reaper.GetProjectName(0, "")
  return {name = name, saved = true}
end

function project.project_save_as(p)
  if not p.path then return nil, "Missing parameter: path" end
  -- Main_SaveProject's 2nd arg is a boolean ("force the Save-As dialog"),
  -- NOT a filename — passing a string there is truthy in Lua, so this used
  -- to just pop REAPER's interactive Save-As dialog and silently ignore
  -- p.path entirely, hanging any non-interactive caller waiting on a
  -- result. Main_SaveProjectEx takes a real filename; options&8 makes this
  -- project's active file become p.path going forward, matching normal
  -- "Save As" semantics (as opposed to "Save a Copy", which doesn't).
  reaper.Main_SaveProjectEx(0, p.path, 8)
  local _, name = reaper.GetProjectName(0, "")
  return {name = name, path = p.path, saved = true}
end

-- Save a copy to `path` WITHOUT changing this project's own active file —
-- unlike project_save_as, subsequent project_save calls still target the
-- original file. Used internally as a pre-destructive-action safety net.
function project.project_backup(p)
  if not p.path then return nil, "Missing parameter: path" end
  reaper.Main_SaveProjectEx(0, p.path, 0)
  return {path = p.path, saved = true}
end

function project.project_export_audio(p)
  -- NOTE: This opens REAPER's render dialog. The path/format params from MCP
  -- are not directly usable — REAPER uses its own render settings.
  reaper.Main_OnCommand(41824, 0)
  return {rendered = true, note = "Used REAPER default render settings. Configure render settings in REAPER for specific format/path."}
end

function project.project_undo(p)
  local action = reaper.Undo_CanUndo2(0) or ""
  reaper.Main_OnCommand(40029, 0)
  local next_undo = reaper.Undo_CanUndo2(0) or ""
  local next_redo = reaper.Undo_CanRedo2(0) or ""
  return {undone = action, next_undo = next_undo, next_redo = next_redo}
end

function project.project_redo(p)
  local action = reaper.Undo_CanRedo2(0) or ""
  reaper.Main_OnCommand(40030, 0)
  local next_undo = reaper.Undo_CanUndo2(0) or ""
  local next_redo = reaper.Undo_CanRedo2(0) or ""
  return {redone = action, next_undo = next_undo, next_redo = next_redo}
end

function project.project_get_notes(p)
  local notes = reaper.GetSetProjectNotes(0, false, "")
  return {notes = notes}
end

function project.project_set_notes(p)
  if not p.notes then return nil, "Missing parameter: notes" end
  reaper.GetSetProjectNotes(0, true, p.notes)
  local stored = reaper.GetSetProjectNotes(0, false, "")
  return {notes = stored}
end

function project.project_main_action(p)
  -- Run a REAPER Main action by command_id. Used by high-level pipelines
  -- (e.g. bounce_stems uses action 40892 = render selected tracks to stems).
  if p.command_id == nil then return nil, "Missing parameter: command_id" end
  local cmd_id = math.floor(tonumber(p.command_id) or 0)
  if cmd_id <= 0 then return nil, "command_id must be a positive integer" end
  reaper.Main_OnCommand(cmd_id, 0)
  return {success = true, command_id = cmd_id}
end


function project.project_set_grid(p)
  if p.grid_division == nil then return nil, "Missing parameter: grid_division" end
  local div = tonumber(p.grid_division)
  if not div or div <= 0 then return nil, "grid_division must be a positive number" end
  reaper.SetProjectGrid(0, div)
  -- Read back
  local _, actual_div = reaper.GetSetProjectGrid(0, false, 0, 0, 0)
  return {grid_division = actual_div}
end

-- ============================================================
-- FX handlers
-- ============================================================

local fx = {}

function fx.fx_add(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if not p.fx_name then return nil, "Missing parameter: fx_name" end
  local fx_idx = reaper.TrackFX_AddByName(tr, p.fx_name, false, -1)
  if fx_idx < 0 then return nil, "FX not found or could not be added: " .. p.fx_name end
  return build_fx_chain(tr)
end

function fx.fx_remove(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if not p.fx_index then return nil, "Missing parameter: fx_index" end
  reaper.TrackFX_Delete(tr, math.floor(p.fx_index))
  return build_fx_chain(tr)
end

function fx.fx_get_chain(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  return build_fx_chain(tr)
end

function fx.fx_get_params(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if not p.fx_index then return nil, "Missing parameter: fx_index" end
  return build_fx_params(tr, math.floor(p.fx_index))
end

function fx.fx_set_param(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local fi = require_int(p, "fx_index")
  local pi = require_int(p, "param_index")
  local val_in = require_num(p, "value")
  reaper.TrackFX_SetParam(tr, fi, pi, val_in)
  local val = reaper.TrackFX_GetParam(tr, fi, pi)
  local _, pname = reaper.TrackFX_GetParamName(tr, fi, pi, "")
  local _, fmt = reaper.TrackFX_FormatParamValue(tr, fi, pi, val, "")
  local _, fx_name = reaper.TrackFX_GetFXName(tr, fi, "")
  return {param_index = pi, name = pname, value = val, display = fmt, fx_name = fx_name}
end

function fx.fx_set_param_by_name(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local fi = require_int(p, "fx_index")
  if p.param_name == nil then return nil, "Missing parameter: param_name" end
  if p.value == nil then return nil, "Missing parameter: value" end
  local num = reaper.TrackFX_GetNumParams(tr, fi)
  local found = -1
  for i = 0, num - 1 do
    local _, pname = reaper.TrackFX_GetParamName(tr, fi, i, "")
    if pname:lower():find(p.param_name:lower(), 1, true) then
      found = i; break
    end
  end
  if found < 0 then return nil, "Parameter not found: " .. p.param_name end
  reaper.TrackFX_SetParam(tr, fi, found, p.value)
  local val = reaper.TrackFX_GetParam(tr, fi, found)
  local _, pname = reaper.TrackFX_GetParamName(tr, fi, found, "")
  local _, fmt = reaper.TrackFX_FormatParamValue(tr, fi, found, val, "")
  local _, fx_name = reaper.TrackFX_GetFXName(tr, fi, "")
  return {param_index = found, name = pname, value = val, display = fmt, fx_name = fx_name}
end

function fx.fx_enable(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local fi = require_int(p, "fx_index")
  reaper.TrackFX_SetEnabled(tr, fi, true)
  return build_fx_chain(tr)
end

function fx.fx_disable(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local fi = require_int(p, "fx_index")
  reaper.TrackFX_SetEnabled(tr, fi, false)
  return build_fx_chain(tr)
end

function fx.fx_show_ui(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local fi = require_int(p, "fx_index")
  reaper.TrackFX_Show(tr, fi, 1)
  return build_fx_info(tr, fi)
end

function fx.fx_get_preset(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local fi = require_int(p, "fx_index")
  local _, preset = reaper.TrackFX_GetPreset(tr, fi, "")
  local _, fx_name = reaper.TrackFX_GetFXName(tr, fi, "")
  local pi, total_presets = reaper.TrackFX_GetPresetIndex(tr, fi)
  return {fx_name = fx_name, preset = preset, preset_index = pi, total_presets = total_presets}
end

function fx.fx_set_preset(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if not p.preset_name then return nil, "Missing parameter: preset_name" end
  local fi = require_int(p, "fx_index")
  reaper.TrackFX_SetPreset(tr, fi, p.preset_name)
  return build_fx_params(tr, fi)
end

function fx.fx_navigate_preset(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local fi = require_int(p, "fx_index")
  local dir = require_int(p, "direction")
  reaper.TrackFX_NavigatePresets(tr, fi, dir)
  local _, preset = reaper.TrackFX_GetPreset(tr, fi, "")
  local _, fx_name = reaper.TrackFX_GetFXName(tr, fi, "")
  local pi, total_presets = reaper.TrackFX_GetPresetIndex(tr, fi)
  return {fx_name = fx_name, preset = preset, preset_index = pi, total_presets = total_presets}
end

function fx.fx_get_instrument(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local fi = reaper.TrackFX_GetInstrument(tr)
  if fi >= 0 then
    -- Lightweight version: only return non-default/non-zero params
    -- and skip bulk MIDI CC params (they bloat output to 300K+ chars)
    local _, fx_name = reaper.TrackFX_GetFXName(tr, fi, "")
    local _, preset = reaper.TrackFX_GetPreset(tr, fi, "")
    local num = reaper.TrackFX_GetNumParams(tr, fi)
    local params = {}
    for i = 0, num - 1 do
      local _, pname = reaper.TrackFX_GetParamName(tr, fi, i, "")
      local val = reaper.TrackFX_GetParam(tr, fi, i)
      -- Skip unnamed params ("-") and ALL MIDI CC params (not FX, they're MIDI routing)
      local is_midi_cc = pname:find("^MIDI CC")
      local skip = (pname == "-" and val == 0) or is_midi_cc
      if not skip then
        local _, fmt = reaper.TrackFX_FormatParamValue(tr, fi, i, val, "")
        params[#params+1] = {index = i, name = pname, value = val, display = fmt}
      end
    end
    return {
      fx_name = fx_name,
      preset = preset,
      enabled = reaper.TrackFX_GetEnabled(tr, fi),
      param_count = num,
      instrument_index = fi,
      params = params
    }
  else
    return {instrument_index = -1, message = "No instrument found on this track"}
  end
end

function fx.fx_move(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local fi = require_int(p, "fx_index")
  local ni = require_int(p, "new_index")
  reaper.TrackFX_CopyToTrack(tr, fi, tr, ni, true)
  return build_fx_chain(tr)
end

-- Rename an FX instance's display name (purely cosmetic — the underlying
-- plugin is unchanged). Used by the mix engine to tag its own FX with
-- "[MIX] " so cleanup can find them without affecting user-added FX.
function fx.fx_rename(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local fi = require_int(p, "fx_index")
  if p.new_name == nil then return nil, "Missing parameter: new_name" end
  local new_name = tostring(p.new_name)
  if #new_name > 1000 then return nil, "new_name exceeds 1000 characters" end
  if reaper.TrackFX_SetNamedConfigParm then
    local ok = reaper.TrackFX_SetNamedConfigParm(tr, fi, "renamed_name", new_name)
    if not ok then
      return nil, "TrackFX_SetNamedConfigParm failed (fx_index may be out of range or plugin doesn't support rename)"
    end
  else
    return nil, "REAPER is too old — TrackFX_SetNamedConfigParm requires REAPER 6.37+"
  end
  return {track_index = idx, fx_index = fi, new_name = new_name}
end

-- Enumerate every FX installed in REAPER's plugin list (VST2/VST3/JS/AU).
-- Used by the MCP's PluginInventory to see what the user actually has.
function fx.fx_list_installed(p)
  local plugins = {}
  if reaper.EnumInstalledFX then
    local i = 0
    while true do
      local retval, name, ident = reaper.EnumInstalledFX(i)
      if not retval or not name or name == "" then break end
      plugins[#plugins+1] = {name = name, ident = ident or ""}
      i = i + 1
      if i > 20000 then break end  -- safety cap; nobody has 20k plugins
    end
  end
  return {count = #plugins, plugins = plugins}
end

-- ============================================================
-- ITEM handlers
-- ============================================================

local item = {}

function item.item_get_all(p)
  local items = {}
  local track_idx = p.track_index or -1
  if track_idx >= 0 then
    local tr = reaper.GetTrack(0, math.floor(track_idx))
    if tr then
      local n = reaper.CountTrackMediaItems(tr)
      local total = reaper.CountMediaItems(0)
      for i = 0, n - 1 do
        local it = reaper.GetTrackMediaItem(tr, i)
        -- Find global item index (not per-track)
        local global_idx = -1
        for gi = 0, total - 1 do
          if reaper.GetMediaItem(0, gi) == it then global_idx = gi; break end
        end
        items[#items+1] = build_item_info(it, global_idx)
      end
    end
  else
    local n = reaper.CountMediaItems(0)
    for i = 0, n - 1 do
      items[#items+1] = build_item_info(reaper.GetMediaItem(0, i), i)
    end
  end
  return {items = items, total_items = reaper.CountMediaItems(0)}
end

function item.item_get_info(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))
  if not it then return nil, "Item not found" end
  return build_item_info(it, math.floor(p.item_index))
end

function item.item_select(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))
  if not it then return nil, "Item not found" end
  if p.exclusive then reaper.SelectAllMediaItems(0, false) end
  local sel = p.selected
  if sel == nil then sel = true end
  reaper.SetMediaItemSelected(it, sel)
  reaper.UpdateArrange()
  return build_item_info(it, math.floor(p.item_index))
end

function item.item_split(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))
  if not it then return nil, "Item not found" end
  if p.position == nil then return nil, "Missing parameter: position" end
  if p.position < 0 or p.position ~= p.position then return nil, "Invalid position" end
  local new_item = reaper.SplitMediaItem(it, p.position)
  if not new_item then return nil, "Split failed - position may be outside item bounds" end
  reaper.UpdateArrange()
  -- SplitMediaItem appends the new item at the end of REAPER's global item
  -- list, not at item_index+1 — resolve its real index by pointer lookup
  -- (same technique used by item_split_at_transients/item_split_at_positions).
  local new_index = -1
  local count_after = reaper.CountMediaItems(0)
  for g = 0, count_after - 1 do
    if reaper.GetMediaItem(0, g) == new_item then new_index = g; break end
  end
  return {left_item = build_item_info(it, math.floor(p.item_index)), right_item = build_item_info(new_item, new_index)}
end

function item.item_delete(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))
  if not it then return nil, "Item not found" end
  -- Capture info before deletion
  local pos = reaper.GetMediaItemInfo_Value(it, "D_POSITION")
  local len = reaper.GetMediaItemInfo_Value(it, "D_LENGTH")
  local tr = reaper.GetMediaItemTrack(it)
  local _, tr_name = reaper.GetTrackName(tr)
  local tr_idx = math.floor(reaper.GetMediaTrackInfo_Value(tr, "IP_TRACKNUMBER") - 1)
  reaper.DeleteTrackMediaItem(tr, it)
  reaper.UpdateArrange()
  return {
    deleted_index = math.floor(p.item_index), remaining_items = reaper.CountMediaItems(0),
    deleted = {position = pos, length = len, track_index = tr_idx, track_name = tr_name or ""}
  }
end

function item.item_move(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))
  if not it then return nil, "Item not found" end
  if p.new_position == nil then return nil, "Missing parameter: new_position" end
  reaper.SetMediaItemInfo_Value(it, "D_POSITION", p.new_position)
  reaper.UpdateArrange()
  return build_item_info(it, math.floor(p.item_index))
end

function item.item_set_length(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))
  if not it then return nil, "Item not found" end
  if not p.length or p.length <= 0 then return nil, "Length must be > 0" end
  reaper.SetMediaItemInfo_Value(it, "D_LENGTH", p.length)
  reaper.UpdateArrange()
  return build_item_info(it, math.floor(p.item_index))
end

function item.item_set_volume(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))
  if not it then return nil, "Item not found" end
  if p.volume_db == nil then return nil, "Missing parameter: volume_db" end
  reaper.SetMediaItemInfo_Value(it, "D_VOL", vol_from_db(p.volume_db))
  reaper.UpdateArrange()
  return build_item_info(it, math.floor(p.item_index))
end

function item.item_set_mute(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))
  if not it then return nil, "Item not found" end
  reaper.SetMediaItemInfo_Value(it, "B_MUTE", p.mute and 1 or 0)
  reaper.UpdateArrange()
  return build_item_info(it, math.floor(p.item_index))
end

function item.item_set_fade(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))
  if not it then return nil, "Item not found" end
  if p.fade_in and p.fade_in >= 0 then reaper.SetMediaItemInfo_Value(it, "D_FADEINLEN", p.fade_in) end
  if p.fade_out and p.fade_out >= 0 then reaper.SetMediaItemInfo_Value(it, "D_FADEOUTLEN", p.fade_out) end
  reaper.UpdateArrange()
  return build_item_info(it, math.floor(p.item_index))
end

function item.item_insert_media(p)
  local tr = reaper.GetTrack(0, math.floor(p.track_index))
  if not tr then return nil, "Track not found" end
  if not p.path then return nil, "Missing parameter: path" end
  local pos = p.position or 0
  if pos < 0 then pos = 0 end
  reaper.SetEditCurPos(pos, false, false)
  reaper.SetOnlyTrackSelected(tr)
  reaper.InsertMedia(p.path, 0)
  reaper.UpdateArrange()
  local n = reaper.CountTrackMediaItems(tr)
  if n > 0 then
    local it = reaper.GetTrackMediaItem(tr, n - 1)
    return build_item_info(it, reaper.CountMediaItems(0) - 1)
  end
  return nil, "Media insert failed"
end

function item.item_create_midi(p)
  local tr = reaper.GetTrack(0, math.floor(p.track_index))
  if not tr then return nil, "Track not found" end
  local pos = p.position or 0
  local len = p.length or 60.0  -- default 60s, compose_arrangement auto-calculates
  if pos < 0 then pos = 0 end
  if len <= 0 then len = 60.0 end
  reaper.Undo_BeginBlock()
  local it = reaper.CreateNewMIDIItemInProj(tr, pos, pos + len, false)
  if not it then
    reaper.Undo_EndBlock("MCP: item_create_midi (failed)", -1)
    return nil, "Failed to create MIDI item"
  end
  reaper.UpdateArrange()
  -- Find the item index
  local total = reaper.CountMediaItems(0)
  local item_idx = total - 1
  for i = 0, total - 1 do
    if reaper.GetMediaItem(0, i) == it then item_idx = i; break end
  end
  reaper.Undo_EndBlock("MCP: item_create_midi", -1)
  return build_item_info(it, item_idx)
end

function item.item_move_to_track(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))
  if not it then return nil, "Item not found" end
  local dest = reaper.GetTrack(0, math.floor(p.dest_track_index))
  if not dest then return nil, "Destination track not found" end
  reaper.MoveMediaItemToTrack(it, dest)
  reaper.UpdateArrange()
  return build_item_info(it, math.floor(p.item_index))
end

-- ============================================================
-- CHOP handlers (slicing, pitch, time-stretch, reverse, duplicate)
-- ============================================================

-- Slice an item at all detected transients using REAPER's native action.
-- Returns the new chop items found on the original track within the
-- original item's time range.
function item.item_split_at_transients(p)
  if p.item_index == nil then return nil, "Missing parameter: item_index" end
  local idx = math.floor(p.item_index)
  local it = reaper.GetMediaItem(0, idx)
  if not it then return nil, "Item not found at index " .. idx end

  local tr = reaper.GetMediaItem_Track(it)
  local orig_pos = reaper.GetMediaItemInfo_Value(it, "D_POSITION")
  local orig_len = reaper.GetMediaItemInfo_Value(it, "D_LENGTH")
  local orig_end = orig_pos + orig_len

  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)
  reaper.Main_OnCommand(40289, 0)  -- Item: Unselect all items
  reaper.SetMediaItemSelected(it, true)
  local count_before = reaper.CountMediaItems(0)
  reaper.Main_OnCommand(40310, 0)  -- Item: Split items at transients
  local count_after = reaper.CountMediaItems(0)
  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("MCP: item_split_at_transients", -1)

  -- Build a global-index lookup (one O(N) pass) so per-chop lookup is O(1).
  local index_by_item = {}
  for g = 0, count_after - 1 do
    index_by_item[reaper.GetMediaItem(0, g)] = g
  end

  -- Collect every item on the original track inside the original time range.
  -- Sort by position so the AI gets chops in playback order.
  local chops = {}
  local n_on_track = reaper.CountTrackMediaItems(tr)
  for i = 0, n_on_track - 1 do
    local chop = reaper.GetTrackMediaItem(tr, i)
    local p_pos = reaper.GetMediaItemInfo_Value(chop, "D_POSITION")
    local p_len = reaper.GetMediaItemInfo_Value(chop, "D_LENGTH")
    if p_pos >= orig_pos - 0.001 and p_pos < orig_end then
      chops[#chops+1] = {
        item_index = index_by_item[chop] or -1,
        position = p_pos,
        length = p_len,
        offset_in_original_sec = p_pos - orig_pos,
      }
    end
  end
  table.sort(chops, function(a, b) return a.position < b.position end)

  return {
    original_item_index = idx,
    chops_created = count_after - count_before,
    chops_total = #chops,
    chops = chops,
  }
end

-- Manually split an item at a list of absolute project-time positions.
-- Positions are sorted descending internally so earlier splits don't
-- shift later ones.
function item.item_split_at_positions(p)
  if p.item_index == nil then return nil, "Missing parameter: item_index" end
  if not p.positions then return nil, "Missing parameter: positions" end
  local idx = math.floor(p.item_index)
  local it = reaper.GetMediaItem(0, idx)
  if not it then return nil, "Item not found" end

  local positions = json_decode(p.positions)
  if type(positions) ~= "table" then return nil, "positions must be a JSON array" end

  -- Validate + sort descending
  local sorted = {}
  for _, v in ipairs(positions) do
    if type(v) == "number" then sorted[#sorted+1] = v end
  end
  table.sort(sorted, function(a, b) return a > b end)
  if #sorted == 0 then return nil, "positions array contains no numbers" end

  local tr = reaper.GetMediaItem_Track(it)
  local orig_pos = reaper.GetMediaItemInfo_Value(it, "D_POSITION")
  local orig_len = reaper.GetMediaItemInfo_Value(it, "D_LENGTH")
  local orig_end = orig_pos + orig_len

  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)

  local splits_made = 0
  for _, pos in ipairs(sorted) do
    if pos > orig_pos and pos < orig_end then
      local right = reaper.SplitMediaItem(it, pos)
      if right then splits_made = splits_made + 1 end
    end
  end

  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("MCP: item_split_at_positions", -1)

  -- Re-collect resulting items in playback order.
  local count_after = reaper.CountMediaItems(0)
  local index_by_item = {}
  for g = 0, count_after - 1 do
    index_by_item[reaper.GetMediaItem(0, g)] = g
  end
  local chops = {}
  local n_on_track = reaper.CountTrackMediaItems(tr)
  for i = 0, n_on_track - 1 do
    local chop = reaper.GetTrackMediaItem(tr, i)
    local p_pos = reaper.GetMediaItemInfo_Value(chop, "D_POSITION")
    local p_len = reaper.GetMediaItemInfo_Value(chop, "D_LENGTH")
    if p_pos >= orig_pos - 0.001 and p_pos < orig_end then
      chops[#chops+1] = {
        item_index = index_by_item[chop] or -1,
        position = p_pos,
        length = p_len,
        offset_in_original_sec = p_pos - orig_pos,
      }
    end
  end
  table.sort(chops, function(a, b) return a.position < b.position end)

  return {
    original_item_index = idx,
    splits_requested = #sorted,
    splits_made = splits_made,
    chops_total = #chops,
    chops = chops,
  }
end

-- Per-take pitch shift in semitones. Default operates on the active take;
-- pass take_index >= 0 for a specific take.
function item.take_set_pitch(p)
  if p.item_index == nil then return nil, "Missing parameter: item_index" end
  if p.semitones == nil then return nil, "Missing parameter: semitones" end
  local idx = math.floor(p.item_index)
  local it = reaper.GetMediaItem(0, idx)
  if not it then return nil, "Item not found" end

  local take
  local take_idx = p.take_index
  if take_idx == nil or take_idx < 0 then
    take = reaper.GetActiveTake(it)
    take_idx = -1
  else
    take = reaper.GetMediaItemTake(it, math.floor(take_idx))
  end
  if not take then return nil, "Take not found" end

  reaper.Undo_BeginBlock()
  reaper.SetMediaItemTakeInfo_Value(take, "D_PITCH", p.semitones)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("MCP: take_set_pitch", -1)

  return {
    item_index = idx,
    take_index = take_idx,
    pitch_semitones = p.semitones,
  }
end

-- Per-take playrate (time-stretch). With preserve_pitch=true the audio
-- is time-stretched without pitch change (default behaviour).
function item.take_set_playrate(p)
  if p.item_index == nil then return nil, "Missing parameter: item_index" end
  if p.rate == nil then return nil, "Missing parameter: rate" end
  if p.rate <= 0 then return nil, "rate must be > 0" end
  local idx = math.floor(p.item_index)
  local it = reaper.GetMediaItem(0, idx)
  if not it then return nil, "Item not found" end
  local take = reaper.GetActiveTake(it)
  if not take then return nil, "No active take on item" end

  reaper.Undo_BeginBlock()
  reaper.SetMediaItemTakeInfo_Value(take, "D_PLAYRATE", p.rate)
  if p.preserve_pitch ~= nil then
    reaper.SetMediaItemTakeInfo_Value(take, "B_PPITCH", p.preserve_pitch and 1 or 0)
  end
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("MCP: take_set_playrate", -1)

  return {
    item_index = idx,
    rate = p.rate,
    preserve_pitch = p.preserve_pitch,
  }
end

-- Reverse the active take's audio. Uses REAPER's "reverse items as new
-- take" action, which creates a reversed take and makes it active. The
-- original take is preserved (item now has 2 takes, reversed is active).
function item.take_set_reversed(p)
  if p.item_index == nil then return nil, "Missing parameter: item_index" end
  local idx = math.floor(p.item_index)
  local it = reaper.GetMediaItem(0, idx)
  if not it then return nil, "Item not found" end

  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)
  reaper.Main_OnCommand(40289, 0)  -- Unselect all items
  reaper.SetMediaItemSelected(it, true)
  reaper.Main_OnCommand(41051, 0)  -- Item: Reverse items as new take
  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("MCP: take_set_reversed", -1)

  return {item_index = idx, reversed = true}
end

-- Duplicate an item N times at fixed spacing. Each copy preserves the
-- source, take properties (pitch / playrate / fades / etc.) via
-- SetItemStateChunk. Default spacing = item length (back-to-back).
function item.item_duplicate(p)
  if p.item_index == nil then return nil, "Missing parameter: item_index" end
  if p.count == nil or p.count < 1 then return nil, "count must be >= 1" end
  local idx = math.floor(p.item_index)
  local count = math.floor(p.count)
  if count > 100 then return nil, "count must be <= 100" end

  local it = reaper.GetMediaItem(0, idx)
  if not it then return nil, "Item not found" end

  local tr = reaper.GetMediaItem_Track(it)
  local pos = reaper.GetMediaItemInfo_Value(it, "D_POSITION")
  local len = reaper.GetMediaItemInfo_Value(it, "D_LENGTH")

  local spacing = p.spacing_sec
  if spacing == nil or spacing <= 0 then spacing = len end

  local _, chunk = reaper.GetItemStateChunk(it, "", false)

  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)

  -- Capture base index so we can hand back the new items' indices.
  -- AddMediaItemToTrack appends to REAPER's global item list, so the
  -- new indices are count_before, count_before+1, ... (sequential).
  local count_before = reaper.CountMediaItems(0)

  local clones = {}
  for i = 1, count do
    local new_pos = pos + (i * spacing)
    local new_item = reaper.AddMediaItemToTrack(tr)
    if new_item then
      reaper.SetItemStateChunk(new_item, chunk, false)
      reaper.SetMediaItemInfo_Value(new_item, "D_POSITION", new_pos)
      clones[#clones+1] = {
        item_index = count_before + (#clones),
        position = new_pos,
        length = len,
      }
    end
  end

  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("MCP: item_duplicate x" .. count, -1)

  return {
    source_item_index = idx,
    copies_created = #clones,
    spacing_sec = spacing,
    clones = clones,
  }
end

-- Return the source file path, duration, and take offset for an item.
-- Used by chop_pipeline to know where to read source audio from.
function item.item_get_source_info(p)
  if p.item_index == nil then return nil, "Missing parameter: item_index" end
  local idx = math.floor(p.item_index)
  local it = reaper.GetMediaItem(0, idx)
  if not it then return nil, "Item not found" end

  local take = reaper.GetActiveTake(it)
  if not take then return nil, "Item has no active take" end

  local root, filename = resolve_source(take)
  if not root then return nil, "Take has no source" end

  local src_length, is_qn = reaper.GetMediaSourceLength(root)
  if is_qn then
    local bpm = reaper.Master_GetTempo()
    if bpm > 0 then src_length = src_length * (60.0 / bpm) end
  end

  return {
    item_index = idx,
    source_file = filename or "",
    source_length_sec = src_length,
    take_start_offset_sec = reaper.GetMediaItemTakeInfo_Value(take, "D_STARTOFFS"),
    take_pitch_semis = reaper.GetMediaItemTakeInfo_Value(take, "D_PITCH"),
    take_playrate = reaper.GetMediaItemTakeInfo_Value(take, "D_PLAYRATE"),
    item_position_sec = reaper.GetMediaItemInfo_Value(it, "D_POSITION"),
    item_length_sec = reaper.GetMediaItemInfo_Value(it, "D_LENGTH"),
    track_index = math.floor(reaper.GetMediaTrackInfo_Value(reaper.GetMediaItem_Track(it), "IP_TRACKNUMBER") - 1),
  }
end

-- Create a "virtual slice" item on a target track — a new item that
-- references the SAME source file as a given source item, but plays a
-- specific time range of the source at a given pitch with micro-fades.
-- This is the building block of chop_pipeline: one call places one chop
-- onto the target track, no bouncing / rendering required.
function item.chops_create_virtual_slice(p)
  if p.source_item_index == nil then return nil, "Missing: source_item_index" end
  if p.target_track_index == nil then return nil, "Missing: target_track_index" end
  if p.target_position_sec == nil then return nil, "Missing: target_position_sec" end
  if p.source_offset_sec == nil then return nil, "Missing: source_offset_sec" end
  if p.length_sec == nil or p.length_sec <= 0 then return nil, "length_sec must be > 0" end

  local src_idx = math.floor(p.source_item_index)
  local src_item = reaper.GetMediaItem(0, src_idx)
  if not src_item then return nil, "Source item not found" end
  local src_take = reaper.GetActiveTake(src_item)
  if not src_take then return nil, "Source item has no take" end
  local src_source = reaper.GetMediaItemTake_Source(src_take)
  if not src_source then return nil, "Source take has no PCM source" end
  local src_root = src_source
  for _ = 1, 8 do
    local parent = reaper.GetMediaSourceParent(src_root)
    if not parent then break end
    src_root = parent
  end
  local src_filename = reaper.GetMediaSourceFileName(src_root, "")
  if type(src_filename) ~= "string" or src_filename == "" then
    local _, fn2 = reaper.GetMediaSourceFileName(src_root, "")
    src_filename = fn2 or ""
  end
  if not src_filename or src_filename == "" then
    return nil, "Source is not a file-backed PCM source"
  end

  local tr_idx = math.floor(p.target_track_index)
  local target_track = reaper.GetTrack(0, tr_idx)
  if not target_track then return nil, "Target track not found" end

  local target_pos = p.target_position_sec
  if target_pos < 0 then target_pos = 0 end

  reaper.Undo_BeginBlock()

  local count_before = reaper.CountMediaItems(0)
  local new_item = reaper.AddMediaItemToTrack(target_track)
  if not new_item then
    reaper.Undo_EndBlock("MCP: chops_create_virtual_slice (fail)", -1)
    return nil, "Failed to create item"
  end
  local new_take = reaper.AddTakeToMediaItem(new_item)
  if not new_take then
    reaper.Undo_EndBlock("MCP: chops_create_virtual_slice (fail)", -1)
    return nil, "Failed to create take"
  end

  local fresh_source = reaper.PCM_Source_CreateFromFile(src_filename)
  if not fresh_source then
    reaper.Undo_EndBlock("MCP: chops_create_virtual_slice (fail)", -1)
    return nil, "Failed to create PCM source from: " .. src_filename
  end
  reaper.SetMediaItemTake_Source(new_take, fresh_source)

  reaper.SetMediaItemInfo_Value(new_item, "D_POSITION", target_pos)
  reaper.SetMediaItemInfo_Value(new_item, "D_LENGTH", p.length_sec)
  reaper.SetMediaItemTakeInfo_Value(new_take, "D_STARTOFFS", p.source_offset_sec)

  if p.pitch_semis and p.pitch_semis ~= 0 then
    reaper.SetMediaItemTakeInfo_Value(new_take, "D_PITCH", p.pitch_semis)
  end

  -- Playrate pass-through: when source is at a different BPM than the
  -- project, the pipeline passes the source item's existing playrate so
  -- derived chops stay in-tempo (e.g. 128 BPM vocal → 96 BPM project
  -- uses playrate 0.75). Default 1.0 = source plays at its native rate.
  if p.playrate and p.playrate > 0 and p.playrate ~= 1.0 then
    reaper.SetMediaItemTakeInfo_Value(new_take, "D_PLAYRATE", p.playrate)
  end

  -- Micro-fades to kill zero-crossing clicks on chop edges.
  local fade_len = p.fade_len_sec or 0.005
  if fade_len > 0 then
    reaper.SetMediaItemInfo_Value(new_item, "D_FADEINLEN", fade_len)
    reaper.SetMediaItemInfo_Value(new_item, "D_FADEOUTLEN", fade_len)
  end

  reaper.UpdateArrange()
  reaper.Undo_EndBlock("MCP: chops_create_virtual_slice", -1)

  return {
    source_item_index = src_idx,
    new_item_index = count_before,
    target_track_index = tr_idx,
    target_position_sec = target_pos,
    source_offset_sec = p.source_offset_sec,
    length_sec = p.length_sec,
    pitch_semis = p.pitch_semis or 0,
    playrate = p.playrate or 1.0,
  }
end

-- Clone an item to a specific position, optionally on a different track.
-- Used by stack_chop_layers to overlay copies at the same position with
-- different pitch shifts (root + 5th + octave harmonized stack).
function item.item_clone_to_position(p)
  if p.source_item_index == nil then return nil, "Missing parameter: source_item_index" end
  if p.target_position_sec == nil then return nil, "Missing parameter: target_position_sec" end

  local idx = math.floor(p.source_item_index)
  local source = reaper.GetMediaItem(0, idx)
  if not source then return nil, "Source item not found" end

  local target_track_idx = p.target_track_index
  local target_track
  if target_track_idx == nil or target_track_idx < 0 then
    target_track = reaper.GetMediaItem_Track(source)
  else
    target_track = reaper.GetTrack(0, math.floor(target_track_idx))
    if not target_track then return nil, "Target track not found" end
  end

  local target_pos = p.target_position_sec
  if target_pos < 0 then target_pos = 0 end

  local source_length = reaper.GetMediaItemInfo_Value(source, "D_LENGTH")
  local _, chunk = reaper.GetItemStateChunk(source, "", false)

  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)

  local count_before = reaper.CountMediaItems(0)
  local new_item = reaper.AddMediaItemToTrack(target_track)
  local new_idx = -1
  if new_item then
    reaper.SetItemStateChunk(new_item, chunk, false)
    reaper.SetMediaItemInfo_Value(new_item, "D_POSITION", target_pos)
    new_idx = count_before
  end

  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("MCP: item_clone_to_position", -1)

  if not new_item then return nil, "Failed to clone item" end

  return {
    source_item_index = idx,
    new_item_index = new_idx,
    position = target_pos,
    length = source_length,
  }
end

-- ============================================================
-- MARKER handlers
-- ============================================================

local marker = {}

function marker.marker_get_all(p)
  local count = reaper.CountProjectMarkers(0)
  local markers = {}
  for i = 0, count - 1 do
    local _, isrgn, pos, rgnend, name, num, color = reaper.EnumProjectMarkers3(0, i)
    markers[#markers+1] = {
      index = i, number = num, is_region = isrgn,
      position = pos, region_end = rgnend, name = name, color = color
    }
  end
  return {count = count, markers = markers}
end

function marker.marker_add(p)
  if p.position == nil then return nil, "Missing parameter: position" end
  local r, g, b = clamp_color(p.color_r), clamp_color(p.color_g), clamp_color(p.color_b)
  local color = native_color_or_none(r, g, b)
  local idx = reaper.AddProjectMarker2(0, false, p.position, 0, p.name or "", -1, color)
  return {marker_number = idx, position = p.position, name = p.name or "", color = {r = r, g = g, b = b}, total_markers = reaper.CountProjectMarkers(0)}
end

function marker.marker_add_region(p)
  if not p.start or not p["end"] then return nil, "Missing parameter: start/end" end
  local r, g, b = clamp_color(p.color_r), clamp_color(p.color_g), clamp_color(p.color_b)
  local color = native_color_or_none(r, g, b)
  local idx = reaper.AddProjectMarker2(0, true, p.start, p["end"], p.name or "", -1, color)
  return {region_number = idx, start = p.start, ["end"] = p["end"], name = p.name or "", color = {r = r, g = g, b = b}, total_markers = reaper.CountProjectMarkers(0)}
end

function marker.marker_delete(p)
  if p.marker_index == nil then return nil, "Missing parameter: marker_index" end
  reaper.DeleteProjectMarkerByIndex(0, math.floor(p.marker_index))
  return {deleted_index = math.floor(p.marker_index), remaining = reaper.CountProjectMarkers(0)}
end

function marker.marker_edit(p)
  if p.marker_index == nil then return nil, "Missing parameter: marker_index" end
  local idx = math.floor(p.marker_index)
  local count = reaper.CountProjectMarkers(0)
  if idx < 0 or idx >= count then return nil, "Marker index out of range (0-" .. (count - 1) .. ")" end
  local _, isrgn, pos, rgnend, name, num, color = reaper.EnumProjectMarkers3(0, idx)
  if p.position and p.position >= 0 then pos = p.position end
  if p.name then name = p.name end
  reaper.SetProjectMarkerByIndex2(0, idx, isrgn, pos, rgnend, num, name, color, 0)
  return {index = idx, position = pos, name = name}
end

function marker.marker_go_to(p)
  if p.marker_number == nil then return nil, "Missing parameter: marker_number" end
  reaper.GoToMarker(0, math.floor(p.marker_number), false)
  return {marker_number = math.floor(p.marker_number), cursor_position = reaper.GetCursorPosition()}
end

-- ============================================================
-- SELECTION handlers
-- ============================================================

local selection = {}

function selection.selection_set_time(p)
  if p.start == nil or p["end"] == nil then return nil, "Missing parameter: start/end" end
  reaper.GetSet_LoopTimeRange(true, false, p.start, p["end"], false)
  local s, e = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)
  return {start = s, ["end"] = e, length = e - s}
end

function selection.selection_get_time(p)
  local s, e = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)
  return {start = s, ["end"] = e, length = e - s}
end

function selection.selection_set_loop(p)
  if p.start == nil or p["end"] == nil then return nil, "Missing parameter: start/end" end
  reaper.GetSet_LoopTimeRange(true, true, p.start, p["end"], false)
  local s, e = reaper.GetSet_LoopTimeRange(false, true, 0, 0, false)
  return {loop_start = s, loop_end = e, length = e - s}
end

function selection.selection_select_all_items(p)
  reaper.SelectAllMediaItems(0, true)
  return {selected_count = reaper.CountMediaItems(0)}
end

function selection.selection_deselect_all_items(p)
  reaper.SelectAllMediaItems(0, false)
  return {selected_count = 0}
end

function selection.selection_select_all_tracks(p)
  reaper.Main_OnCommand(40296, 0)
  return {selected_count = reaper.CountTracks(0)}
end

function selection.selection_deselect_all_tracks(p)
  reaper.Main_OnCommand(40297, 0)
  return {selected_count = 0}
end

function selection.selection_get_selected_tracks(p)
  local n = reaper.CountSelectedTracks(0)
  local tracks = {}
  for i = 0, n - 1 do
    local tr = reaper.GetSelectedTrack(0, i)
    local ti = math.floor(reaper.GetMediaTrackInfo_Value(tr, "IP_TRACKNUMBER") - 1)
    tracks[#tracks+1] = build_track_info(tr, ti)
  end
  return {selected_count = n, tracks = tracks}
end

function selection.selection_get_selected_items(p)
  local n = reaper.CountSelectedMediaItems(0)
  local total = reaper.CountMediaItems(0)
  local items = {}
  for i = 0, n - 1 do
    local it = reaper.GetSelectedMediaItem(0, i)
    -- Find global item index
    local global_idx = -1
    for gi = 0, total - 1 do
      if reaper.GetMediaItem(0, gi) == it then global_idx = gi; break end
    end
    items[#items+1] = build_item_info(it, global_idx)
  end
  return {selected_count = n, items = items}
end

-- ============================================================
-- SEND handlers
-- ============================================================

local send = {}

function send.send_create(p)
  if p.source_track == nil or p.dest_track == nil then return nil, "Missing parameter: source_track/dest_track" end
  local src = reaper.GetTrack(0, math.floor(p.source_track))
  local dst = reaper.GetTrack(0, math.floor(p.dest_track))
  if not src then return nil, "Source track not found: " .. math.floor(p.source_track) end
  if not dst then return nil, "Dest track not found: " .. math.floor(p.dest_track) end
  local _, src_name = reaper.GetTrackName(src)
  local _, dst_name = reaper.GetTrackName(dst)
  local si = reaper.CreateTrackSend(src, dst)
  local send_info = build_send_info(src, si)
  send_info.source_track_index = math.floor(p.source_track)
  send_info.source_track_name = src_name
  send_info.total_sends = reaper.GetTrackNumSends(src, 0)
  return send_info
end

function send.send_remove(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  reaper.RemoveTrackSend(tr, 0, math.floor(p.send_index))
  return {removed_index = math.floor(p.send_index), remaining_sends = reaper.GetTrackNumSends(tr, 0)}
end

function send.send_get_all(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local sc = reaper.GetTrackNumSends(tr, 0)
  local rc = reaper.GetTrackNumSends(tr, -1)
  local sends = {}
  for i = 0, sc - 1 do sends[#sends+1] = build_send_info(tr, i) end
  local receives = {}
  for i = 0, rc - 1 do
    local vol = reaper.GetTrackSendInfo_Value(tr, -1, i, "D_VOL")
    receives[#receives+1] = {index = i, volume_db = db_from_vol(vol), pan = reaper.GetTrackSendInfo_Value(tr, -1, i, "D_PAN")}
  end
  return {send_count = sc, receive_count = rc, sends = sends, receives = receives}
end

function send.send_set_volume(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if p.volume_db == nil then return nil, "Missing parameter: volume_db" end
  reaper.SetTrackSendInfo_Value(tr, 0, math.floor(p.send_index), "D_VOL", vol_from_db(p.volume_db))
  return build_send_info(tr, math.floor(p.send_index))
end

function send.send_set_pan(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if p.pan == nil then return nil, "Missing parameter: pan" end
  local pan = clamp(p.pan, -1.0, 1.0)
  reaper.SetTrackSendInfo_Value(tr, 0, math.floor(p.send_index), "D_PAN", pan)
  return build_send_info(tr, math.floor(p.send_index))
end

function send.send_set_mute(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  reaper.SetTrackSendInfo_Value(tr, 0, math.floor(p.send_index), "B_MUTE", p.mute and 1 or 0)
  return build_send_info(tr, math.floor(p.send_index))
end

function send.send_get_routing_diagram(p)
  local tracks = {}
  for i = 0, reaper.CountTracks(0) - 1 do
    local tr = reaper.GetTrack(0, i)
    local _, name = reaper.GetTrackName(tr)
    local num_sends = reaper.GetTrackNumSends(tr, 0)
    local num_receives = reaper.GetTrackNumSends(tr, -1)
    local sends_list = {}
    for si = 0, num_sends - 1 do
      local dest_tr = reaper.GetTrackSendInfo_Value(tr, 0, si, "P_DESTTRACK")
      local dest_name = ""
      local dest_idx = -1
      if dest_tr then
        dest_idx = math.floor(reaper.GetMediaTrackInfo_Value(dest_tr, "IP_TRACKNUMBER") - 1)
        local _, dn = reaper.GetTrackName(dest_tr)
        dest_name = dn or ""
      end
      local vol = reaper.GetTrackSendInfo_Value(tr, 0, si, "D_VOL")
      sends_list[#sends_list+1] = {
        dest_track_index = dest_idx,
        dest_track_name = dest_name,
        volume_db = db_from_vol(vol),
        mute = reaper.GetTrackSendInfo_Value(tr, 0, si, "B_MUTE") == 1,
      }
    end
    local receives_list = {}
    for ri = 0, num_receives - 1 do
      local src_tr = reaper.GetTrackSendInfo_Value(tr, -1, ri, "P_SRCTRACK")
      local src_name = ""
      local src_idx = -1
      if src_tr then
        src_idx = math.floor(reaper.GetMediaTrackInfo_Value(src_tr, "IP_TRACKNUMBER") - 1)
        local _, sn = reaper.GetTrackName(src_tr)
        src_name = sn or ""
      end
      receives_list[#receives_list+1] = {
        source_track_index = src_idx,
        source_track_name = src_name,
      }
    end
    tracks[#tracks+1] = {
      index = i, name = name,
      send_count = num_sends, sends = sends_list,
      receive_count = num_receives, receives = receives_list,
    }
  end
  return {tracks = tracks}
end

-- ============================================================
-- MIDI handlers
-- ============================================================

local midi = {}

local function get_midi_take(p)
  if p.item_index == nil then return nil, nil, nil, "Missing parameter: item_index" end
  local it = reaper.GetMediaItem(0, math.floor(p.item_index))  -- always use global index
  if not it then return nil, nil, nil, "Item not found" end
  -- If track_index given, verify item is on that track
  if p.track_index ~= nil then
    local tr = reaper.GetTrack(0, math.floor(p.track_index))
    if not tr then return nil, nil, nil, "Track not found" end
    local item_track = reaper.GetMediaItemTrack(it)
    if item_track ~= tr then return nil, nil, nil, "Item is not on specified track" end
  end
  local take = reaper.GetActiveTake(it)
  if not take then return nil, nil, nil, "Item has no active take" end
  if not reaper.TakeIsMIDI(take) then return nil, nil, nil, "Item is not a MIDI item" end
  return it, take, math.floor(p.item_index), nil
end

function midi.midi_insert_note(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  if not p.start_position or not p.end_position then return nil, "Missing parameter: start_position/end_position" end
  if not p.channel or not p.pitch or not p.velocity then return nil, "Missing parameter: channel/pitch/velocity" end
  local startppq = reaper.MIDI_GetPPQPosFromProjTime(take, p.start_position)
  local endppq = reaper.MIDI_GetPPQPosFromProjTime(take, p.end_position)
  reaper.Undo_BeginBlock()
  reaper.MIDI_InsertNote(take, false, false, startppq, endppq, math.floor(p.channel), math.floor(p.pitch), math.floor(p.velocity), true)
  reaper.MIDI_Sort(take)
  reaper.Undo_EndBlock("MCP: midi_insert_note", -1)
  local _, notes, ccs, sysex = reaper.MIDI_CountEvts(take)
  return {
    inserted = {channel = p.channel, pitch = p.pitch, velocity = p.velocity, start = p.start_position, ["end"] = p.end_position},
    total_notes = notes, total_ccs = ccs
  }
end

function midi.midi_insert_notes_batch(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  if not p.notes then return nil, "Missing parameter: notes" end
  local notes_data = json_decode(p.notes)
  if not notes_data then return nil, "Invalid notes JSON" end
  reaper.Undo_BeginBlock()
  reaper.MIDI_DisableSort(take)
  local count = 0
  for _, n in ipairs(notes_data) do
    if n.pitch and n.velocity and n.start and n["end"] then
      local ch = math.floor(n.channel or 0)
      local startppq = reaper.MIDI_GetPPQPosFromProjTime(take, n.start)
      local endppq = reaper.MIDI_GetPPQPosFromProjTime(take, n["end"])
      reaper.MIDI_InsertNote(take, false, false, startppq, endppq, ch, math.floor(n.pitch), math.floor(n.velocity), false)
      count = count + 1
    end
  end
  reaper.MIDI_Sort(take)
  local _, notes, ccs, sysex = reaper.MIDI_CountEvts(take)
  reaper.Undo_EndBlock("MCP: midi_insert_notes_batch (" .. count .. " notes)", -1)
  return {inserted_count = count, total_notes = notes, total_ccs = ccs}
end

function midi.midi_get_notes(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  local _, note_count, cc_count, sysex_count = reaper.MIDI_CountEvts(take)
  local notes = {}
  local max_notes = p.max_results or 500
  local returned = math.min(note_count, max_notes)
  for i = 0, returned - 1 do
    local _, sel, muted, startppq, endppq, ch, pitch, vel = reaper.MIDI_GetNote(take, i)
    local s = reaper.MIDI_GetProjTimeFromPPQPos(take, startppq)
    local e = reaper.MIDI_GetProjTimeFromPPQPos(take, endppq)
    notes[#notes+1] = {
      index = i, channel = ch, pitch = pitch, velocity = vel,
      start = s, ["end"] = e, duration = e - s,
      selected = sel, muted = muted
    }
  end
  return {note_count = note_count, notes_returned = returned, truncated = note_count > max_notes, notes = notes}
end

function midi.midi_set_note(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  if p.note_index == nil then return nil, "Missing parameter: note_index" end
  local ni = math.floor(p.note_index)
  local _, sel, muted, startppq, endppq, ch, pitch, vel = reaper.MIDI_GetNote(take, ni)
  if p.pitch and p.pitch >= 0 then pitch = math.floor(p.pitch) end
  if p.velocity and p.velocity >= 0 then vel = math.floor(p.velocity) end
  if p.channel and p.channel >= 0 then ch = math.floor(p.channel) end
  if p.start_position and p.start_position >= 0 then startppq = reaper.MIDI_GetPPQPosFromProjTime(take, p.start_position) end
  if p.end_position and p.end_position >= 0 then endppq = reaper.MIDI_GetPPQPosFromProjTime(take, p.end_position) end
  reaper.Undo_BeginBlock()
  reaper.MIDI_SetNote(take, ni, sel, muted, startppq, endppq, ch, pitch, vel, true)
  reaper.MIDI_Sort(take)
  reaper.Undo_EndBlock("MCP: midi_set_note", -1)
  local s = reaper.MIDI_GetProjTimeFromPPQPos(take, startppq)
  local e = reaper.MIDI_GetProjTimeFromPPQPos(take, endppq)
  return {index = ni, channel = ch, pitch = pitch, velocity = vel, start = s, ["end"] = e}
end

function midi.midi_delete_note(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  if p.note_index == nil then return nil, "Missing parameter: note_index" end
  local ni = math.floor(p.note_index)
  -- Capture note info before deleting
  local _, _, _, startppq, endppq, ch, pitch, vel = reaper.MIDI_GetNote(take, ni)
  local del_start = reaper.MIDI_GetProjTimeFromPPQPos(take, startppq)
  local del_end = reaper.MIDI_GetProjTimeFromPPQPos(take, endppq)
  reaper.Undo_BeginBlock()
  reaper.MIDI_DeleteNote(take, ni)
  reaper.MIDI_Sort(take)
  reaper.Undo_EndBlock("MCP: midi_delete_note", -1)
  local _, notes = reaper.MIDI_CountEvts(take)
  return {
    deleted_index = ni, remaining_notes = notes,
    deleted = {pitch = pitch, velocity = vel, channel = ch, start = del_start, ["end"] = del_end}
  }
end

function midi.midi_select_notes(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  reaper.MIDI_SelectAll(take, p.select_all and true or false)
  local _, notes = reaper.MIDI_CountEvts(take)
  return {note_count = notes, selected_all = p.select_all and true or false}
end

function midi.midi_delete_all_notes(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  local _, count = reaper.MIDI_CountEvts(take)
  reaper.Undo_BeginBlock()
  for i = count - 1, 0, -1 do reaper.MIDI_DeleteNote(take, i) end
  reaper.MIDI_Sort(take)
  reaper.Undo_EndBlock("MCP: midi_delete_all_notes (" .. count .. " notes)", -1)
  return {cleared = true, deleted_count = count}
end

function midi.midi_insert_cc(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  if p.position == nil or p.channel == nil or p.cc_number == nil or p.cc_value == nil then
    return nil, "Missing parameter: position/channel/cc_number/cc_value"
  end
  local ch = clamp(math.floor(p.channel), 0, 15)
  local ccnum = clamp(math.floor(p.cc_number), 0, 127)
  local ccval = clamp(math.floor(p.cc_value), 0, 127)
  local ppq = reaper.MIDI_GetPPQPosFromProjTime(take, p.position)
  reaper.Undo_BeginBlock()
  reaper.MIDI_InsertCC(take, false, false, ppq, 0xB0, ch, ccnum, ccval)
  reaper.MIDI_Sort(take)
  reaper.Undo_EndBlock("MCP: midi_insert_cc", -1)
  local _, notes, ccs = reaper.MIDI_CountEvts(take)
  return {inserted = {channel = ch, cc_number = ccnum, cc_value = ccval, position = p.position}, total_ccs = ccs}
end

-- midi_get_ccs was intentionally removed — the AI doesn't need to read CC
-- data back (it would blow context for any realistic dynamics-heavy project).
-- Use midi_count_events to see how many CC events exist, and insert your own.

function midi.midi_delete_cc(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  if p.cc_index == nil then return nil, "Missing parameter: cc_index" end
  local ci = math.floor(p.cc_index)
  -- Capture CC info before deleting
  local _, _, _, ppq, _, ch, msg2, msg3 = reaper.MIDI_GetCC(take, ci)
  local del_pos = reaper.MIDI_GetProjTimeFromPPQPos(take, ppq)
  reaper.Undo_BeginBlock()
  reaper.MIDI_DeleteCC(take, ci)
  reaper.MIDI_Sort(take)
  reaper.Undo_EndBlock("MCP: midi_delete_cc", -1)
  local _, _, ccs = reaper.MIDI_CountEvts(take)
  return {
    deleted_index = ci, remaining_ccs = ccs,
    deleted = {cc_number = msg2, cc_value = msg3, channel = ch, position = del_pos}
  }
end

function midi.midi_get_note_names(p)
  return {
    reference = {
      C2=36,D2=38,E2=40,F2=41,G2=43,A2=45,B2=47,
      C3=48,D3=50,E3=52,F3=53,G3=55,A3=57,B3=59,
      C4=60,D4=62,E4=64,F4=65,G4=67,A4=69,B4=71,
      C5=72,D5=74,E5=76,F5=77,G5=79,A5=81,B5=83,
      C6=84,D6=86,E6=88,F6=89,G6=91,A6=93,B6=95
    },
    sharps = {
      ["C#3"]=49,["D#3"]=51,["F#3"]=54,["G#3"]=56,["A#3"]=58,
      ["C#4"]=61,["D#4"]=63,["F#4"]=66,["G#4"]=68,["A#4"]=70,
      ["C#5"]=73,["D#5"]=75,["F#5"]=78,["G#5"]=80,["A#5"]=82
    }
  }
end

function midi.midi_count_events(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  local _, notes, ccs, sysex = reaper.MIDI_CountEvts(take)
  return {notes = notes, ccs = ccs, text_sysex = sysex}
end

function midi.midi_sort(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  reaper.MIDI_Sort(take)
  local _, notes, ccs = reaper.MIDI_CountEvts(take)
  return {sorted = true, notes = notes, ccs = ccs}
end

function midi.midi_set_item_extents(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  if not p.start_qn or not p.end_qn then return nil, "Missing parameter: start_qn/end_qn" end
  reaper.MIDI_SetItemExtents(it, p.start_qn, p.end_qn)
  reaper.UpdateArrange()
  return build_item_info(it, idx)
end

-- ============================================================
-- Compose pipeline handlers
-- ============================================================

local compose = {}

function compose.wipe_all_midi(p)
  -- Deletes MIDI items from ALL tracks (or specified tracks) in one call.
  -- Audio items (and items with no active take) are left untouched.
  -- p.tracks: optional JSON array of track indices e.g. [0,1,2]. If omitted, wipes ALL tracks.
  reaper.Undo_BeginBlock()
  local track_count = reaper.CountTracks(0)
  local target_tracks = {}

  if p.tracks then
    local tracks_list = json_decode(p.tracks)
    if tracks_list then
      for _, ti in ipairs(tracks_list) do
        target_tracks[math.floor(ti)] = true
      end
    end
  end
  local wipe_all = (next(target_tracks) == nil)

  local total_deleted = 0
  local tracks_wiped = 0
  for i = 0, track_count - 1 do
    if wipe_all or target_tracks[i] then
      local tr = reaper.GetTrack(0, i)
      if tr then
        local item_count = reaper.CountTrackMediaItems(tr)
        if item_count > 0 then
          local deleted_on_track = 0
          for j = item_count - 1, 0, -1 do
            local item = reaper.GetTrackMediaItem(tr, j)
            if item then
              local take = reaper.GetActiveTake(item)
              if take and reaper.TakeIsMIDI(take) then
                reaper.DeleteTrackMediaItem(tr, item)
                total_deleted = total_deleted + 1
                deleted_on_track = deleted_on_track + 1
              end
            end
          end
          if deleted_on_track > 0 then
            tracks_wiped = tracks_wiped + 1
          end
        end
      end
    end
  end

  reaper.UpdateArrange()
  reaper.Undo_EndBlock("wipe_all_midi", -1)
  return {success = true, items_deleted = total_deleted, tracks_wiped = tracks_wiped}
end

function compose.get_track_instruments(p)
  local results = {}
  local track_count = reaper.CountTracks(0)
  for i = 0, track_count - 1 do
    local tr = reaper.GetTrack(0, i)
    local _, name = reaper.GetTrackName(tr)
    local fx_idx = reaper.TrackFX_GetInstrument(tr)
    local instrument = nil
    if fx_idx >= 0 then
      local _, fx_name = reaper.TrackFX_GetFXName(tr, fx_idx, "")
      instrument = fx_name
    end
    local item_count = reaper.CountTrackMediaItems(tr)
    results[#results+1] = {
      track_index = i,
      name = name,
      instrument = instrument,
      item_count = item_count,
    }
  end
  return {tracks = results, track_count = track_count}
end

function compose.compose_arrangement(p)
  if not p.tracks then return nil, "Missing parameter: tracks" end

  local t0 = os.clock()
  local tracks_data = json_decode(p.tracks)
  local t_parse = os.clock() - t0
  if not tracks_data then return nil, "Invalid tracks JSON" end

  local num_tracks = #tracks_data
  local total_notes_all, total_ccs_all = 0, 0
  for _, e in ipairs(tracks_data) do
    total_notes_all = total_notes_all + (e.notes and #e.notes or 0)
    total_ccs_all = total_ccs_all + (e.ccs and #e.ccs or 0)
  end
  -- silent

  local clear = true
  if p.clear_existing == false then clear = false end

  -- Check for duplicate track indices
  local seen_ti = {}
  for _, entry in ipairs(tracks_data) do
    local ti = math.floor(entry.track_index)
    if seen_ti[ti] then
      return nil, "Duplicate track_index " .. ti .. " — each track must appear only once"
    end
    seen_ti[ti] = true
  end

  reaper.Undo_BeginBlock()
  local summary = {}

  -- Ensure all referenced tracks exist (create if needed)
  local max_track = -1
  for _, entry in ipairs(tracks_data) do
    local ti = math.floor(entry.track_index)
    if ti > max_track then max_track = ti end
  end
  local existing = reaper.CountTracks(0)
  for i = existing, max_track do
    reaper.InsertTrackAtIndex(i, true)
  end

  for track_num, entry in ipairs(tracks_data) do
    local t_track = os.clock()
    local ti = math.floor(entry.track_index)
    local tr = reaper.GetTrack(0, ti)
    if not tr then
      reaper.Undo_EndBlock("compose_arrangement", -1)
      return nil, "Track not found: " .. ti
    end

    -- Set track name if provided
    if entry.track_name then
      reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", entry.track_name, true)
    end

    local _, track_name = reaper.GetTrackName(tr)

    -- Clear existing items on this track if requested
    if clear then
      for j = reaper.CountTrackMediaItems(tr) - 1, 0, -1 do
        local old_item = reaper.GetTrackMediaItem(tr, j)
        if old_item then reaper.DeleteTrackMediaItem(tr, old_item) end
      end
    end

    -- Create MIDI item — auto-size from notes if length not provided
    local pos = entry.position or 0
    local len = entry.length
    if not len then
      -- Auto-calculate: find the latest note/CC end time
      local max_end = 4.0
      if entry.notes then
        for _, n in ipairs(entry.notes) do
          local ne = n["end"] or (n.start + 1)
          if ne > max_end then max_end = ne end
        end
      end
      if entry.ccs then
        for _, c in ipairs(entry.ccs) do
          if c.position and c.position > max_end then max_end = c.position end
        end
      end
      len = max_end + 1.0  -- add 1s padding
    end
    if pos < 0 then pos = 0 end
    if len <= 0 then len = 4.0 end
    local it = reaper.CreateNewMIDIItemInProj(tr, pos, pos + len, false)
    if not it then
      reaper.Undo_EndBlock("compose_arrangement", -1)
      return nil, "Failed to create MIDI item on track " .. ti
    end

    local take = reaper.GetActiveTake(it)
    if not take then
      reaper.Undo_EndBlock("compose_arrangement", -1)
      return nil, "No active take on created item, track " .. ti
    end

    -- Insert notes
    local note_count = 0
    local earliest_note = math.huge
    local latest_note = -1
    local t_notes = os.clock()
    if entry.notes then
      local notes_dropped = 0
      reaper.MIDI_DisableSort(take)
      for _, n in ipairs(entry.notes) do
        if n.pitch and n.velocity and n.start and n["end"] then
          local ch = math.floor(n.channel or 0)
          local ns = n.start
          local ne = n["end"]
          -- Notes outside item bounds are inserted as-is (item auto-sized to fit)
          if ne > ns then
            local startppq = reaper.MIDI_GetPPQPosFromProjTime(take, ns)
            local endppq = reaper.MIDI_GetPPQPosFromProjTime(take, ne)
            reaper.MIDI_InsertNote(take, false, false, startppq, endppq, ch,
                                  math.floor(n.pitch), math.floor(n.velocity), true)
            note_count = note_count + 1
            if ns < earliest_note then earliest_note = ns end
            if ne > latest_note then latest_note = ne end
          else
            notes_dropped = notes_dropped + 1
          end
        end
      end
      reaper.MIDI_Sort(take)
    end
    local t_notes_done = os.clock() - t_notes
    if note_count == 0 then earliest_note = pos; latest_note = pos end

    -- Insert CCs
    local cc_count = 0
    local t_ccs = os.clock()
    if entry.ccs then
      reaper.MIDI_DisableSort(take)
      for _, cc in ipairs(entry.ccs) do
        if cc.pitch_bend ~= nil and cc.position then
          -- Pitch bend event: value 0-16383 (8192=center)
          local ch = math.floor(cc.channel or 0)
          local bend_val = clamp(math.floor(cc.pitch_bend), 0, 16383)
          local lsb = bend_val % 128
          local msb = math.floor(bend_val / 128)
          local ppq = reaper.MIDI_GetPPQPosFromProjTime(take, cc.position)
          -- chanmsg must include channel nibble for pitch bend
          local status = 0xE0 + ch
          reaper.MIDI_InsertCC(take, false, false, ppq, status, ch, lsb, msb)
          cc_count = cc_count + 1
        elseif cc.cc_number and cc.cc_value and cc.position then
          local ch = math.floor(cc.channel or 0)
          local ccnum = clamp(math.floor(cc.cc_number), 0, 127)
          local ccval = clamp(math.floor(cc.cc_value), 0, 127)
          local ppq = reaper.MIDI_GetPPQPosFromProjTime(take, cc.position)
          reaper.MIDI_InsertCC(take, false, false, ppq, 0xB0, ch, ccnum, ccval)
          cc_count = cc_count + 1
        end
      end
      reaper.MIDI_Sort(take)
    end
    local t_ccs_done = os.clock() - t_ccs

    -- Check coverage: warn if notes don't fill the item
    local coverage_pct = 0
    if note_count > 0 and len > 0 then
      coverage_pct = math.floor(((latest_note - earliest_note) / len) * 100)
    end
    local coverage_warning = nil
    if note_count > 0 and coverage_pct < 50 then
      coverage_warning = string.format(
        "notes span %.1f-%.1fs (%d%% of %.1fs item)",
        earliest_note, latest_note, coverage_pct, len)
    end

    local t_track_done = os.clock() - t_track

    summary[#summary+1] = {
      track_index = ti,
      track_name = track_name,
      position = pos,
      length = len,
      notes_inserted = note_count,
      ccs_inserted = cc_count,
      notes_earliest = earliest_note,
      notes_latest = latest_note,
      coverage_pct = coverage_pct,
      warning = coverage_warning,
    }

    -- Update arrange view after each track so user sees real-time progress
    reaper.UpdateArrange()
  end

  reaper.Undo_EndBlock("compose_arrangement", -1)

  local t_total = os.clock() - t0
  -- silent

  return {success = true, tracks_composed = #summary, summary = summary}
end

function compose.compose_ensure_tracks(p)
  local max_ti = math.floor(p.max_track_index or 0)
  local existing = reaper.CountTracks(0)
  for i = existing, max_ti do
    reaper.InsertTrackAtIndex(i, true)
  end
  reaper.UpdateArrange()
  return {success = true, tracks_ensured = max_ti + 1, tracks_existing = existing}
end

function compose.compose_single_track(p)
  if not p.track_data then return nil, "Missing parameter: track_data" end

  local entry = json_decode(p.track_data)
  if not entry then return nil, "Invalid track_data JSON" end

  local clear = true
  if p.clear_existing == false then clear = false end

  local ti = math.floor(entry.track_index)
  local tr = reaper.GetTrack(0, ti)
  if not tr then return nil, "Track not found: " .. ti end

  reaper.Undo_BeginBlock()

  -- Set track name if provided
  if entry.track_name then
    reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", entry.track_name, true)
  end

  local _, track_name = reaper.GetTrackName(tr)

  -- Clear existing items on this track if requested
  if clear then
    for j = reaper.CountTrackMediaItems(tr) - 1, 0, -1 do
      local old_item = reaper.GetTrackMediaItem(tr, j)
      if old_item then reaper.DeleteTrackMediaItem(tr, old_item) end
    end
  end

  -- Create MIDI item — auto-size from notes if length not provided
  local pos = entry.position or 0
  local len = entry.length
  if not len then
    local max_end = 4.0
    if entry.notes then
      for _, n in ipairs(entry.notes) do
        local ne = n["end"] or (n.start + 1)
        if ne > max_end then max_end = ne end
      end
    end
    if entry.ccs then
      for _, c in ipairs(entry.ccs) do
        if c.position and c.position > max_end then max_end = c.position end
      end
    end
    len = max_end + 1.0
  end
  if pos < 0 then pos = 0 end
  if len <= 0 then len = 4.0 end
  local it = reaper.CreateNewMIDIItemInProj(tr, pos, pos + len, false)
  if not it then
    reaper.Undo_EndBlock("compose_single_track", -1)
    return nil, "Failed to create MIDI item on track " .. ti
  end

  local take = reaper.GetActiveTake(it)
  if not take then
    reaper.Undo_EndBlock("compose_single_track", -1)
    return nil, "No active take on created item, track " .. ti
  end

  -- Insert notes
  local note_count = 0
  local earliest_note = math.huge
  local latest_note = -1
  if entry.notes then
    reaper.MIDI_DisableSort(take)
    for _, n in ipairs(entry.notes) do
      if n.pitch and n.velocity and n.start and n["end"] then
        local ch = math.floor(n.channel or 0)
        local ns = n.start
        local ne = n["end"]
        if ne > ns then
          local startppq = reaper.MIDI_GetPPQPosFromProjTime(take, ns)
          local endppq = reaper.MIDI_GetPPQPosFromProjTime(take, ne)
          reaper.MIDI_InsertNote(take, false, false, startppq, endppq, ch,
                                math.floor(n.pitch), math.floor(n.velocity), true)
          note_count = note_count + 1
          if ns < earliest_note then earliest_note = ns end
          if ne > latest_note then latest_note = ne end
        end
      end
    end
    reaper.MIDI_Sort(take)
  end
  if note_count == 0 then earliest_note = pos; latest_note = pos end

  -- Insert CCs
  local cc_count = 0
  if entry.ccs then
    reaper.MIDI_DisableSort(take)
    for _, cc in ipairs(entry.ccs) do
      if cc.pitch_bend ~= nil and cc.position then
        -- Pitch bend event: value 0-16383 (8192=center)
        local ch = math.floor(cc.channel or 0)
        local bend_val = clamp(math.floor(cc.pitch_bend), 0, 16383)
        local lsb = bend_val % 128
        local msb = math.floor(bend_val / 128)
        local ppq = reaper.MIDI_GetPPQPosFromProjTime(take, cc.position)
        local status = 0xE0 + ch
        reaper.MIDI_InsertCC(take, false, false, ppq, status, ch, lsb, msb)
        cc_count = cc_count + 1
      elseif cc.cc_number and cc.cc_value and cc.position then
        local ch = math.floor(cc.channel or 0)
        local ccnum = clamp(math.floor(cc.cc_number), 0, 127)
        local ccval = clamp(math.floor(cc.cc_value), 0, 127)
        local ppq = reaper.MIDI_GetPPQPosFromProjTime(take, cc.position)
        reaper.MIDI_InsertCC(take, false, false, ppq, 0xB0, ch, ccnum, ccval)
        cc_count = cc_count + 1
      end
    end
    reaper.MIDI_Sort(take)
  end

  -- Coverage check
  local coverage_pct = 0
  if note_count > 0 and len > 0 then
    coverage_pct = math.floor(((latest_note - earliest_note) / len) * 100)
  end
  local coverage_warning = nil
  if note_count > 0 and coverage_pct < 50 then
    coverage_warning = string.format(
      "notes span %.1f-%.1fs (%d%% of %.1fs item)",
      earliest_note, latest_note, coverage_pct, len)
  end

  reaper.Undo_EndBlock("compose track " .. ti, -1)
  reaper.UpdateArrange()

  return {
    success = true,
    track_index = ti,
    track_name = track_name,
    position = pos,
    length = len,
    notes_inserted = note_count,
    ccs_inserted = cc_count,
    notes_earliest = earliest_note,
    notes_latest = latest_note,
    coverage_pct = coverage_pct,
    warning = coverage_warning,
  }
end

function compose.edit_section(p)
  if not p.tracks then return nil, "Missing parameter: tracks" end
  if p.start_time == nil or p.end_time == nil then return nil, "Missing parameter: start_time/end_time" end

  local start_time = p.start_time
  local end_time = p.end_time
  local trim = p.trim_item or false
  -- mode: "all" = notes+CCs (default), "ccs_only" = only CCs, "notes_only" = only notes
  local mode = p.mode or "all"
  local edit_notes = (mode == "all" or mode == "notes_only")
  local edit_ccs = (mode == "all" or mode == "ccs_only")

  local t0 = os.clock()

  -- Determine which tracks to edit
  local track_edits = {}  -- {track_index => {notes=..., ccs=...}}
  local all_tracks = false

  if p.tracks == "all" then
    all_tracks = true
    -- reaper.ShowConsoleMsg(string.format("\nMCP: editing all tracks (%.1f-%.1fs, %s)...\n", start_time, end_time, mode))
  else
    local tracks_data = json_decode(p.tracks)
    if not tracks_data then return nil, "Invalid tracks JSON" end
    for _, entry in ipairs(tracks_data) do
      local ti = math.floor(entry.track_index)
      track_edits[ti] = {notes = entry.notes, ccs = entry.ccs}
    end
    -- reaper.ShowConsoleMsg(string.format("\nMCP: editing %d tracks (%.1f-%.1fs, %s)...\n", #tracks_data, start_time, end_time, mode))
  end

  reaper.Undo_BeginBlock()
  local summary = {}

  -- Build list of tracks to process
  local track_indices = {}
  if all_tracks then
    for i = 0, reaper.CountTracks(0) - 1 do
      track_indices[#track_indices+1] = i
      track_edits[i] = track_edits[i] or {}
    end
  else
    for ti, _ in pairs(track_edits) do
      track_indices[#track_indices+1] = ti
    end
    table.sort(track_indices)
  end

  for _, ti in ipairs(track_indices) do
    local tr = reaper.GetTrack(0, ti)
    if not tr then goto next_track end

    local _, track_name = reaper.GetTrackName(tr)
    local edit = track_edits[ti] or {}
    local notes_deleted, ccs_deleted = 0, 0
    local notes_inserted, ccs_inserted = 0, 0

    -- Find MIDI items on this track that overlap the edit range
    local inserted_replacement = false
    for item_j = 0, reaper.CountTrackMediaItems(tr) - 1 do
      local it = reaper.GetTrackMediaItem(tr, item_j)
      if not it then goto next_item end

      local take = reaper.GetActiveTake(it)
      if not take or not reaper.TakeIsMIDI(take) then goto next_item end

      local item_pos = reaper.GetMediaItemInfo_Value(it, "D_POSITION")
      local item_len = reaper.GetMediaItemInfo_Value(it, "D_LENGTH")
      local item_end = item_pos + item_len

      -- Skip items that don't overlap the edit range
      if item_end <= start_time or item_pos >= end_time then goto next_item end

      -- Trim the item BEFORE inserting (so we don't destroy new notes)
      if trim and start_time > item_pos then
        reaper.SetMediaItemInfo_Value(it, "D_LENGTH", start_time - item_pos)
      end

      -- Delete notes in range (iterate backwards to preserve indices)
      if edit_notes then
        local _, note_count = reaper.MIDI_CountEvts(take)
        for ni = note_count - 1, 0, -1 do
          local _, _, _, startppq = reaper.MIDI_GetNote(take, ni)
          local note_time = reaper.MIDI_GetProjTimeFromPPQPos(take, startppq)
          if note_time >= start_time and note_time < end_time then
            reaper.MIDI_DeleteNote(take, ni)
            notes_deleted = notes_deleted + 1
          end
        end
      end

      -- Delete CCs in range (iterate backwards)
      if edit_ccs then
        local _, _, cc_count = reaper.MIDI_CountEvts(take)
        for ci = cc_count - 1, 0, -1 do
          local _, _, _, ppq = reaper.MIDI_GetCC(take, ci)
          local cc_time = reaper.MIDI_GetProjTimeFromPPQPos(take, ppq)
          if cc_time >= start_time and cc_time < end_time then
            reaper.MIDI_DeleteCC(take, ci)
            ccs_deleted = ccs_deleted + 1
          end
        end
      end

      -- Insert replacement content into FIRST overlapping item only (avoid duplicates)
      if not inserted_replacement then
        if edit_notes and edit.notes then
          reaper.MIDI_DisableSort(take)
          for _, n in ipairs(edit.notes) do
            if n.pitch and n.velocity and n.start and n["end"] then
              local ch = math.floor(n.channel or 0)
              local startppq = reaper.MIDI_GetPPQPosFromProjTime(take, n.start)
              local endppq = reaper.MIDI_GetPPQPosFromProjTime(take, n["end"])
              reaper.MIDI_InsertNote(take, false, false, startppq, endppq, ch,
                                    math.floor(n.pitch), math.floor(n.velocity), true)
              notes_inserted = notes_inserted + 1
            end
          end
          reaper.MIDI_Sort(take)
        end

        if edit_ccs and edit.ccs then
          reaper.MIDI_DisableSort(take)
          for _, cc in ipairs(edit.ccs) do
            if cc.cc_number and cc.cc_value and cc.position then
              local ch = math.floor(cc.channel or 0)
              local ccnum = clamp(math.floor(cc.cc_number), 0, 127)
              local ccval = clamp(math.floor(cc.cc_value), 0, 127)
              local ppq = reaper.MIDI_GetPPQPosFromProjTime(take, cc.position)
              reaper.MIDI_InsertCC(take, false, false, ppq, 0xB0, ch, ccnum, ccval)
              ccs_inserted = ccs_inserted + 1
            end
          end
          reaper.MIDI_Sort(take)
        end

        inserted_replacement = true
      end

      ::next_item::
    end

    summary[#summary+1] = {
      track_index = ti,
      track_name = track_name,
      notes_deleted = notes_deleted,
      ccs_deleted = ccs_deleted,
      notes_inserted = notes_inserted,
      ccs_inserted = ccs_inserted,
    }

    ::next_track::
  end

  reaper.UpdateArrange()
  reaper.Undo_EndBlock("edit_section", -1)

  local t_total = os.clock() - t0
  -- reaper.ShowConsoleMsg(string.format("MCP: edit done (%.2fs)\n", t_total))

  return {success = true, tracks_edited = #summary, summary = summary}
end

function compose.configure_tracks(p)
  if not p.tracks then return nil, "Missing parameter: tracks" end
  local tracks_data = json_decode(p.tracks)
  if not tracks_data then return nil, "Invalid tracks JSON" end

  reaper.Undo_BeginBlock()

  -- Ensure all referenced tracks exist
  local max_track = -1
  for _, entry in ipairs(tracks_data) do
    local ti = math.floor(entry.track_index)
    if ti > max_track then max_track = ti end
  end
  local existing = reaper.CountTracks(0)
  for i = existing, max_track do
    reaper.InsertTrackAtIndex(i, true)
  end

  local results = {}

  for _, entry in ipairs(tracks_data) do
    local ti = math.floor(entry.track_index)
    local tr = reaper.GetTrack(0, ti)
    if not tr then
      reaper.Undo_EndBlock("configure_tracks", -1)
      return nil, "Track not found: " .. ti
    end

    if entry.name ~= nil then
      reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", entry.name, true)
    end
    if entry.volume_db ~= nil then
      reaper.SetMediaTrackInfo_Value(tr, "D_VOL", vol_from_db(entry.volume_db))
    end
    if entry.pan ~= nil then
      reaper.SetMediaTrackInfo_Value(tr, "D_PAN", clamp(entry.pan, -1.0, 1.0))
    end
    if entry.mute ~= nil then
      reaper.SetMediaTrackInfo_Value(tr, "B_MUTE", entry.mute and 1 or 0)
    end
    if entry.solo ~= nil then
      reaper.SetMediaTrackInfo_Value(tr, "I_SOLO", entry.solo and 1 or 0)
    end
    if entry.color ~= nil then
      local c, err = native_color_from_array(entry.color)
      if not c then
        reaper.Undo_EndBlock("configure_tracks", -1)
        return nil, "Track " .. ti .. ": " .. err
      end
      reaper.SetMediaTrackInfo_Value(tr, "I_CUSTOMCOLOR", c)
    end

    -- Return full readback so AI can verify
    results[#results+1] = build_track_info(tr, ti)
  end

  reaper.UpdateArrange()
  reaper.Undo_EndBlock("configure_tracks", -1)
  return {success = true, tracks_configured = #results, tracks = results}
end

function compose.setup_routing(p)
  if not p.sends then return nil, "Missing parameter: sends" end
  local sends_data = json_decode(p.sends)
  if not sends_data then return nil, "Invalid sends JSON" end

  reaper.Undo_BeginBlock()
  local results = {}

  for _, entry in ipairs(sends_data) do
    local src = reaper.GetTrack(0, math.floor(entry.source_track))
    local dst = reaper.GetTrack(0, math.floor(entry.dest_track))
    if not src or not dst then
      reaper.Undo_EndBlock("setup_routing", -1)
      return nil, "Track not found: source=" .. entry.source_track .. " dest=" .. entry.dest_track
    end
    local si = reaper.CreateTrackSend(src, dst)

    if entry.volume_db ~= nil then
      reaper.SetTrackSendInfo_Value(src, 0, si, "D_VOL", vol_from_db(entry.volume_db))
    end
    if entry.pan ~= nil then
      reaper.SetTrackSendInfo_Value(src, 0, si, "D_PAN", clamp(entry.pan, -1.0, 1.0))
    end

    results[#results+1] = {
      source_track = entry.source_track,
      dest_track = entry.dest_track,
      send_index = si,
    }
  end

  reaper.Undo_EndBlock("setup_routing", -1)
  return {success = true, sends_created = #results, sends = results}
end

function compose.add_markers_batch(p)
  if not p.markers then return nil, "Missing parameter: markers" end
  local markers_data = json_decode(p.markers)
  if not markers_data then return nil, "Invalid markers JSON" end

  reaper.Undo_BeginBlock()
  local results = {}

  for _, entry in ipairs(markers_data) do
    local is_region = entry.is_region or false
    local name = entry.name or ""
    local color = 0
    if entry.color then
      local c, err = native_color_from_array(entry.color)
      if not c then
        reaper.Undo_EndBlock("add_markers_batch", -1)
        return nil, err
      end
      color = c
    end

    if is_region then
      local s = entry.start or entry.position or 0
      local e = entry["end"] or (s + 1)
      local idx = reaper.AddProjectMarker2(0, true, s, e, name, -1, color)
      results[#results+1] = {type = "region", index = idx, name = name, start = s, ["end"] = e}
    else
      local pos = entry.position or 0
      local idx = reaper.AddProjectMarker2(0, false, pos, 0, name, -1, color)
      results[#results+1] = {type = "marker", index = idx, name = name, position = pos}
    end
  end

  reaper.UpdateArrange()
  reaper.Undo_EndBlock("add_markers_batch", -1)
  return {success = true, items_added = #results, items = results}
end

function compose.setup_fx_chain(p)
  if not p.tracks then return nil, "Missing parameter: tracks" end
  local data
  if type(p.tracks) == "table" then
    data = p.tracks
  else
    data = json_decode(p.tracks)
  end
  if not data then return nil, "Invalid tracks JSON" end

  -- reaper.ShowConsoleMsg(string.format("\n=== setup_fx_chain: %d track entries ===\n", #data))

  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)
  local summary = {}

  for _, entry in ipairs(data) do
    local ti = math.floor(entry.track_index)
    local tr = reaper.GetTrack(0, ti)
    if not tr then
      reaper.PreventUIRefresh(-1)
      reaper.Undo_EndBlock("setup_fx_chain", -1)
      return nil, "Track not found: " .. ti
    end
    local _, track_name = reaper.GetTrackName(tr)
    local track_result = {track_index = ti, track_name = track_name, fx_added = {}}

    local fx_chain = entry.fx_chain
    if type(fx_chain) == "string" then fx_chain = json_decode(fx_chain) end
    if fx_chain then
      for _, fx_entry in ipairs(fx_chain) do
        local fx_idx = -1

        if fx_entry.fx_index ~= nil then
          -- Use existing FX by index
          fx_idx = math.floor(fx_entry.fx_index)
          if fx_idx < 0 or fx_idx >= reaper.TrackFX_GetCount(tr) then
            track_result.fx_added[#track_result.fx_added+1] = {
              name = fx_entry.name or ("fx_index " .. fx_idx), error = "FX index out of range"
            }
            goto next_fx
          end
        elseif fx_entry.name then
          if fx_entry.add_mode == "find_or_add" then
            -- Find existing by name, add only if not found
            fx_idx = reaper.TrackFX_AddByName(tr, fx_entry.name, false, 0)
            if fx_idx < 0 then
              fx_idx = reaper.TrackFX_AddByName(tr, fx_entry.name, false, -1)
            end
          elseif fx_entry.add_mode == "find_only" then
            -- Find existing only, don't add
            fx_idx = reaper.TrackFX_AddByName(tr, fx_entry.name, false, 0)
          else
            -- Default: always add new
            fx_idx = reaper.TrackFX_AddByName(tr, fx_entry.name, false, -1)
          end
          if fx_idx < 0 then
            track_result.fx_added[#track_result.fx_added+1] = {
              name = fx_entry.name, error = "FX not found"
            }
            goto next_fx
          end
        else
          goto next_fx
        end

        local params_set = {}

        -- Set params by name (fuzzy match)
        if fx_entry.params then
          local num_params = reaper.TrackFX_GetNumParams(tr, fx_idx)
          for param_name, param_val in pairs(fx_entry.params) do
            local found = -1
            local pname_lower = tostring(param_name):lower()
            for pi = 0, num_params - 1 do
              local _, pn = reaper.TrackFX_GetParamName(tr, fx_idx, pi, "")
              if pn:lower():find(pname_lower, 1, true) then
                found = pi; break
              end
            end
            if found >= 0 then
              reaper.TrackFX_SetParam(tr, fx_idx, found, param_val)
              local val = reaper.TrackFX_GetParam(tr, fx_idx, found)
              local _, fmt = reaper.TrackFX_FormatParamValue(tr, fx_idx, found, val, "")
              params_set[#params_set+1] = {name = param_name, index = found, value = val, display = fmt}
            end
          end
        end

        -- Set params by index
        if fx_entry.params_by_index then
          for pi_str, param_val in pairs(fx_entry.params_by_index) do
            local pi = math.floor(tonumber(pi_str) or -1)
            if pi >= 0 then
              reaper.TrackFX_SetParam(tr, fx_idx, pi, param_val)
              local val = reaper.TrackFX_GetParam(tr, fx_idx, pi)
              local _, pn = reaper.TrackFX_GetParamName(tr, fx_idx, pi, "")
              local _, fmt = reaper.TrackFX_FormatParamValue(tr, fx_idx, pi, val, "")
              params_set[#params_set+1] = {name = pn, index = pi, value = val, display = fmt}
            end
          end
        end

        -- Load preset if specified
        if fx_entry.preset then
          reaper.TrackFX_SetPreset(tr, fx_idx, fx_entry.preset)
        end

        -- Enable/disable
        if fx_entry.enabled == false then
          reaper.TrackFX_SetEnabled(tr, fx_idx, false)
        end

        -- Optional rename — cosmetic label used by mix engine to tag
        -- its own FX with "[MIX] " so cleanup can find them without
        -- touching user-added FX of the same plugin type.
        if fx_entry.renamed_name and reaper.TrackFX_SetNamedConfigParm then
          reaper.TrackFX_SetNamedConfigParm(tr, fx_idx, "renamed_name", tostring(fx_entry.renamed_name))
        end

        reaper.ShowConsoleMsg(string.format(
          "  Track %d: FX %d (%s) — %d params set\n",
          ti, fx_idx, fx_entry.name or "existing", #params_set))

        track_result.fx_added[#track_result.fx_added+1] = {
          name = fx_entry.name,
          fx_index = fx_idx,
          params_set = params_set,
          preset = fx_entry.preset,
        }

        ::next_fx::
      end
    end

    summary[#summary+1] = track_result
  end

  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("setup_fx_chain", -1)
  -- reaper.ShowConsoleMsg(string.format("  DONE: %d tracks processed\n", #summary))
  return {success = true, tracks_processed = #summary, summary = summary}
end

function compose.setup_effect_bus(p)
  if not p.bus_name then return nil, "Missing parameter: bus_name" end

  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)

  -- Create the bus track
  local bus_pos = p.bus_position or reaper.CountTracks(0)
  reaper.InsertTrackAtIndex(math.floor(bus_pos), true)
  local bus_tr = reaper.GetTrack(0, math.floor(bus_pos))
  if not bus_tr then
    reaper.PreventUIRefresh(-1)
    reaper.Undo_EndBlock("setup_effect_bus", -1)
    return nil, "Failed to create bus track"
  end
  reaper.GetSetMediaTrackInfo_String(bus_tr, "P_NAME", p.bus_name, true)

  -- Set bus color if provided
  if p.bus_color then
    local c, err = native_color_from_array(p.bus_color)
    if not c then
      reaper.Undo_EndBlock("setup_effect_bus", -1)
      return nil, "bus_color: " .. err
    end
    reaper.SetMediaTrackInfo_Value(bus_tr, "I_CUSTOMCOLOR", c)
  end

  -- Add FX plugins to the bus
  local fx_results = {}
  if p.fx_chain then
    local fx_data = p.fx_chain
    if type(fx_data) == "string" then fx_data = json_decode(fx_data) end
    if fx_data then
      for _, fx_entry in ipairs(fx_data) do
        if not fx_entry.name then goto next_bus_fx end
        local fx_idx = reaper.TrackFX_AddByName(bus_tr, fx_entry.name, false, -1)
        if fx_idx < 0 then
          fx_results[#fx_results+1] = {name = fx_entry.name, error = "FX not found"}
          goto next_bus_fx
        end

        -- Set params by name
        if fx_entry.params then
          local num_params = reaper.TrackFX_GetNumParams(bus_tr, fx_idx)
          for param_name, param_val in pairs(fx_entry.params) do
            local pname_lower = tostring(param_name):lower()
            for pi = 0, num_params - 1 do
              local _, pn = reaper.TrackFX_GetParamName(bus_tr, fx_idx, pi, "")
              if pn:lower():find(pname_lower, 1, true) then
                reaper.TrackFX_SetParam(bus_tr, fx_idx, pi, param_val)
                break
              end
            end
          end
        end

        -- Set params by index
        if fx_entry.params_by_index then
          for pi_str, param_val in pairs(fx_entry.params_by_index) do
            local pi = math.floor(tonumber(pi_str) or -1)
            if pi >= 0 then
              reaper.TrackFX_SetParam(bus_tr, fx_idx, pi, param_val)
            end
          end
        end

        -- Load preset
        if fx_entry.preset then
          reaper.TrackFX_SetPreset(bus_tr, fx_idx, fx_entry.preset)
        end

        fx_results[#fx_results+1] = {name = fx_entry.name, fx_index = fx_idx}
        ::next_bus_fx::
      end
    end
  end

  -- Create sends from source tracks to the bus
  local send_results = {}
  if p.sends_from then
    local sends_data = p.sends_from
    if type(sends_data) == "string" then sends_data = json_decode(sends_data) end
    if sends_data then
      for _, s in ipairs(sends_data) do
        local src_ti = math.floor(s.source_track)
        -- Adjust index if source is at or after bus position (bus insertion shifted indices)
        local adjusted_ti = src_ti
        if src_ti >= bus_pos then adjusted_ti = src_ti + 1 end
        local src_tr = reaper.GetTrack(0, adjusted_ti)
        if src_tr then
          local si = reaper.CreateTrackSend(src_tr, bus_tr)
          if s.volume_db ~= nil then
            reaper.SetTrackSendInfo_Value(src_tr, 0, si, "D_VOL", vol_from_db(s.volume_db))
          end
          if s.pan ~= nil then
            reaper.SetTrackSendInfo_Value(src_tr, 0, si, "D_PAN", clamp(s.pan, -1.0, 1.0))
          end
          send_results[#send_results+1] = {
            source_track = src_ti, send_index = si
          }
        end
      end
    end
  end

  -- Set bus volume if provided
  if p.bus_volume_db ~= nil then
    reaper.SetMediaTrackInfo_Value(bus_tr, "D_VOL", vol_from_db(p.bus_volume_db))
  end

  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("setup_effect_bus", -1)

  return {
    success = true,
    bus_track_index = math.floor(bus_pos),
    bus_name = p.bus_name,
    fx_added = fx_results,
    sends_created = send_results,
  }
end

-- ============================================================
-- setup_master_chain — apply FX chain to the master bus.
-- Used by engine_master for professional mastering.
-- ============================================================

function compose.setup_master_chain(p)
  local master = reaper.GetMasterTrack(0)
  if not master then return nil, "Could not access master track" end

  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)

  -- Body wrapped in pcall so PreventUIRefresh(-1) is GUARANTEED to run
  -- even if the master FX chain throws. Otherwise REAPER UI stays frozen
  -- until the user restarts.
  local ok, cleared_or_err, fx_results = pcall(function()
    local cleared = 0
    if p.clean then
      local clear_names = p.clean_names
      if type(clear_names) == "string" then clear_names = json_decode(clear_names) end
      clear_names = clear_names or {"ReaEQ", "ReaComp", "ReaLimit",
                                     "FabFilter Pro-Q 3", "FabFilter Pro-C 2",
                                     "FabFilter Pro-L", "FabFilter Pro-L 2"}
      -- First pass: remove any FX tagged by the mix engine with the
      -- "[MIX] " prefix. Safe — we know we added these.
      local num_fx = reaper.TrackFX_GetCount(master)
      local any_tagged = false
      for fi = num_fx - 1, 0, -1 do
        local _, fn = reaper.TrackFX_GetFXName(master, fi, "")
        if fn:sub(1, 6) == "[MIX] " then
          reaper.TrackFX_Delete(master, fi)
          cleared = cleared + 1
          any_tagged = true
        end
      end
      -- Fallback — only if we found NO tagged FX, fall back to name-substring
      -- matching for backward compat with projects from before the prefix
      -- system. New projects rely on the tagged pass above exclusively.
      if not any_tagged then
        num_fx = reaper.TrackFX_GetCount(master)
        for fi = num_fx - 1, 0, -1 do
          local _, fn = reaper.TrackFX_GetFXName(master, fi, "")
          for _, cname in ipairs(clear_names) do
            if fn:find(cname, 1, true) then
              reaper.TrackFX_Delete(master, fi)
              cleared = cleared + 1
              break
            end
          end
        end
      end
    end

    local results = {}
    if p.fx_chain then
      local fx_data = p.fx_chain
      if type(fx_data) == "string" then fx_data = json_decode(fx_data) end
      if fx_data then
        for _, fx_entry in ipairs(fx_data) do
          if not fx_entry.name then goto next_master_fx end
          local fx_idx = reaper.TrackFX_AddByName(master, fx_entry.name, false, -1)
          if fx_idx < 0 then
            results[#results+1] = {name = fx_entry.name, error = "Plugin not installed or name mismatch — check spelling / install plugin"}
            goto next_master_fx
          end

          -- Set params by name (fuzzy)
          if fx_entry.params then
            local num_params = reaper.TrackFX_GetNumParams(master, fx_idx)
            for param_name, param_val in pairs(fx_entry.params) do
              local pname_lower = tostring(param_name):lower()
              for pi = 0, num_params - 1 do
                local _, pn = reaper.TrackFX_GetParamName(master, fx_idx, pi, "")
                if pn:lower():find(pname_lower, 1, true) then
                  reaper.TrackFX_SetParam(master, fx_idx, pi, param_val)
                  break
                end
              end
            end
          end

          -- Set params by index
          if fx_entry.params_by_index then
            for pi_str, param_val in pairs(fx_entry.params_by_index) do
              local pi = math.floor(tonumber(pi_str) or -1)
              if pi >= 0 then
                reaper.TrackFX_SetParam(master, fx_idx, pi, param_val)
              end
            end
          end

          if fx_entry.preset then
            reaper.TrackFX_SetPreset(master, fx_idx, fx_entry.preset)
          end

          -- Tag with caller-supplied display name so cleanup can identify
          -- mix-engine-added FX. The mix engine passes "[MIX] <plugin>"
          -- so a later clean=true pass won't destroy user-added FX.
          if fx_entry.renamed_name and reaper.TrackFX_SetNamedConfigParm then
            reaper.TrackFX_SetNamedConfigParm(master, fx_idx, "renamed_name", tostring(fx_entry.renamed_name))
          end

          results[#results+1] = {name = fx_entry.name, fx_index = fx_idx}
          ::next_master_fx::
        end
      end
    end

    return cleared, results
  end)

  -- Cleanup ALWAYS runs — even if pcall caught an error
  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("setup_master_chain", -1)

  if not ok then
    return nil, "setup_master_chain failed: " .. tostring(cleared_or_err)
  end

  local cleared = cleared_or_err

  return {
    success = true,
    cleared = cleared,
    fx_added = fx_results,
  }
end


-- ============================================================
-- setup_sidechain — route source track audio to target track's
-- compressor sidechain (channels 3/4) for pumping / ducking.
-- Sets target I_NCHAN=4, creates send on ch 3/4, pin-maps the
-- compressor's sidechain inputs, and tunes comp params.
-- ============================================================

function compose.setup_sidechain(p)
  local src_ti = p.source_track
  local dst_ti = p.target_track
  if src_ti == nil or dst_ti == nil then
    return nil, "Missing parameter: source_track/target_track"
  end
  src_ti = math.floor(src_ti)
  dst_ti = math.floor(dst_ti)
  if src_ti == dst_ti then
    return nil, "Source and target must differ"
  end

  local src = reaper.GetTrack(0, src_ti)
  local dst = reaper.GetTrack(0, dst_ti)
  if not src then return nil, "Source track not found: " .. src_ti end
  if not dst then return nil, "Target track not found: " .. dst_ti end

  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)

  -- 1. Ensure target track has 4 channels for aux routing
  local ncha = reaper.GetMediaTrackInfo_Value(dst, "I_NCHAN")
  if ncha < 4 then
    reaper.SetMediaTrackInfo_Value(dst, "I_NCHAN", 4)
  end

  -- 2. Find existing sidechain send (ch 3/4) or create one
  local num_sends = reaper.GetTrackNumSends(src, 0)
  local send_idx = -1
  for si = 0, num_sends - 1 do
    local dtr = reaper.GetTrackSendInfo_Value(src, 0, si, "P_DESTTRACK")
    if dtr == dst then
      local dstch = reaper.GetTrackSendInfo_Value(src, 0, si, "I_DSTCHAN")
      if dstch == 2 then
        send_idx = si
        break
      end
    end
  end
  if send_idx < 0 then
    send_idx = reaper.CreateTrackSend(src, dst)
    reaper.SetTrackSendInfo_Value(src, 0, send_idx, "I_DSTCHAN", 2)   -- channels 3/4
    reaper.SetTrackSendInfo_Value(src, 0, send_idx, "I_SRCCHAN", 0)   -- from ch 1/2
  end
  -- Set send volume (post-fader by default; amount controls drive into SC)
  local send_db = p.send_db or 0.0
  reaper.SetTrackSendInfo_Value(src, 0, send_idx, "D_VOL", vol_from_db(send_db))

  -- 3. Locate the compressor FX on target
  local fx_index = p.fx_index
  local compressor_name = p.compressor_name or "ReaComp"
  if fx_index == nil then
    -- Search existing FX by name (case-insensitive substring)
    local num_fx = reaper.TrackFX_GetCount(dst)
    local want = tostring(compressor_name):lower()
    for fi = 0, num_fx - 1 do
      local _, fn = reaper.TrackFX_GetFXName(dst, fi, "")
      if fn and fn:lower():find(want, 1, true) then
        fx_index = fi
        break
      end
    end
    if fx_index == nil then
      -- Add one
      fx_index = reaper.TrackFX_AddByName(dst, compressor_name, false, -1)
      if fx_index < 0 then
        reaper.PreventUIRefresh(-1)
        reaper.Undo_EndBlock("setup_sidechain", -1)
        return nil, "Could not add compressor '" .. compressor_name ..
                    "' — plugin not installed, or name mismatch. Install it or pass a different compressor_name."
      end
    end
  else
    fx_index = math.floor(fx_index)
  end

  -- 4. Pin-map channels 3/4 → sidechain input pins 2/3
  -- Most compressors with sidechain use pin 2=SC L, pin 3=SC R
  -- Masks: bit 0 = track ch 1, bit 1 = ch 2, bit 2 = ch 3, bit 3 = ch 4
  -- If SetPinMappings is unavailable (very old REAPER), abort cleanly — the
  -- sidechain won't actually work without it, and silent success is worse.
  if not reaper.TrackFX_SetPinMappings then
    reaper.PreventUIRefresh(-1)
    reaper.Undo_EndBlock("setup_sidechain", -1)
    return nil, "REAPER version too old: TrackFX_SetPinMappings unavailable. " ..
                "Update REAPER to >= 6.0 for sidechain support."
  end
  reaper.TrackFX_SetPinMappings(dst, fx_index, 0, 0, 1, 0)   -- L ← ch1
  reaper.TrackFX_SetPinMappings(dst, fx_index, 0, 1, 2, 0)   -- R ← ch2
  reaper.TrackFX_SetPinMappings(dst, fx_index, 0, 2, 4, 0)   -- SC L ← ch3
  reaper.TrackFX_SetPinMappings(dst, fx_index, 0, 3, 8, 0)   -- SC R ← ch4
  local pin_ok = true

  -- 5. Try to toggle "external sidechain" / "detector = aux" params for plugins that need it
  local num_params = reaper.TrackFX_GetNumParams(dst, fx_index)
  local sc_keywords = {"external sc", "ext. sc", "ext sc", "side-chain", "sidechain",
                        "aux input", "external input"}
  for pi = 0, num_params - 1 do
    local _, pn = reaper.TrackFX_GetParamName(dst, fx_index, pi, "")
    local pn_low = pn:lower()
    for _, kw in ipairs(sc_keywords) do
      if pn_low:find(kw, 1, true) then
        reaper.TrackFX_SetParam(dst, fx_index, pi, 1.0)
        break
      end
    end
  end

  -- 6. Set comp params for the pump
  -- Translate amount (0..1) into threshold + ratio if those params are not explicitly provided
  local amount = tonumber(p.amount or 0.7) or 0.7
  if amount < 0 then amount = 0 end
  if amount > 1 then amount = 1 end
  local thresh_db = tonumber(p.threshold_db) or (-10.0 - amount * 20.0)
  local ratio = tonumber(p.ratio) or (2.0 + amount * 10.0)
  local attack_ms = tonumber(p.attack_ms) or 5.0
  local release_ms = tonumber(p.release_ms) or 180.0

  local comp_params = {
    {names = {"thresh", "threshold"},   kind = "thresh_db",  value = thresh_db},
    {names = {"ratio"},                 kind = "ratio",      value = ratio},
    {names = {"attack"},                kind = "attack_ms",  value = attack_ms},
    {names = {"release"},               kind = "release_ms", value = release_ms},
  }

  local function norm_thresh(db)
    local v = (db + 60.0) / 60.0
    if v < 0 then v = 0 end
    if v > 1 then v = 1 end
    return v
  end
  local function norm_ratio(r)
    local v = (r - 1.0) / 19.0
    if v < 0 then v = 0 end
    if v > 1 then v = 1 end
    return v
  end
  local function norm_attack(ms)
    local ln = math.log(math.max(0.1, ms) / 0.1) / math.log(10)
    local v = ln / 4.0
    if v < 0 then v = 0 end
    if v > 1 then v = 1 end
    return v
  end
  local function norm_release(ms)
    local ln = math.log(math.max(1.0, ms)) / math.log(3000)
    if ln < 0 then ln = 0 end
    if ln > 1 then ln = 1 end
    return ln
  end

  local unmatched_params = {}
  for _, cp in ipairs(comp_params) do
    local found = false
    for pi = 0, num_params - 1 do
      local _, pn = reaper.TrackFX_GetParamName(dst, fx_index, pi, "")
      local pn_low = pn:lower()
      local matched = false
      for _, kw in ipairs(cp.names) do
        if pn_low:find(kw, 1, true) then matched = true; break end
      end
      if matched then
        local nv
        if cp.kind == "thresh_db" then nv = norm_thresh(cp.value)
        elseif cp.kind == "ratio" then nv = norm_ratio(cp.value)
        elseif cp.kind == "attack_ms" then nv = norm_attack(cp.value)
        elseif cp.kind == "release_ms" then nv = norm_release(cp.value)
        end
        if nv then
          reaper.TrackFX_SetParam(dst, fx_index, pi, nv)
        end
        found = true
        break
      end
    end
    if not found then
      unmatched_params[#unmatched_params+1] = cp.names[1]
    end
  end

  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("setup_sidechain", -1)

  local warnings = {}
  if #unmatched_params > 0 then
    warnings[#warnings+1] = "Compressor '" .. compressor_name ..
      "' has no parameter matching: " .. table.concat(unmatched_params, ", ") ..
      ". Routing is set but pump/duck character may need manual tuning."
  end

  return {
    success = true,
    source_track = src_ti,
    target_track = dst_ti,
    send_index = send_idx,
    fx_index = fx_index,
    compressor_name = compressor_name,
    target_channels = math.max(4, math.floor(ncha)),
    pin_mappings_set = pin_ok,
    unmatched_params = unmatched_params,
    warnings = warnings,
    threshold_db = thresh_db,
    ratio = ratio,
    attack_ms = attack_ms,
    release_ms = release_ms,
  }
end


-- ============================================================
-- analyze_score — raw MIDI data dump from REAPER. No scores, no
-- percentages, no judgments. Just facts: what notes, what CCs,
-- what gaps. The human listens and decides if it sounds good.
-- ============================================================

function compose.analyze_score(p)
  local start_time = p.start_time or 0.0
  local end_time = p.end_time or -1

  -- Determine which tracks to analyze
  local track_indices = {}
  local tracks_str = tostring(p.tracks or "all"):gsub('"', ''):gsub("'", '')
  if tracks_str == "all" then
    for i = 0, reaper.CountTracks(0) - 1 do
      track_indices[#track_indices+1] = i
    end
  else
    local td = json_decode(p.tracks)
    if not td then return nil, "Invalid tracks JSON" end
    for _, ti in ipairs(td) do
      track_indices[#track_indices+1] = math.floor(ti)
    end
  end

  -- If end_time == -1, find project end
  if end_time < 0 then
    end_time = 0
    for i = 0, reaper.CountTracks(0) - 1 do
      local tr = reaper.GetTrack(0, i)
      for j = 0, reaper.CountTrackMediaItems(tr) - 1 do
        local it = reaper.GetTrackMediaItem(tr, j)
        local pos = reaper.GetMediaItemInfo_Value(it, "D_POSITION")
        local len = reaper.GetMediaItemInfo_Value(it, "D_LENGTH")
        if pos + len > end_time then end_time = pos + len end
      end
    end
  end

  local results = {}

  for _, ti in ipairs(track_indices) do
    local tr = reaper.GetTrack(0, ti)
    if not tr then goto next_analyze_track end

    local _, track_name = reaper.GetTrackName(tr)
    local track_result = {
      track_index = ti,
      track_name = track_name,
    }

    local all_notes = {}
    local has_midi = false

    for item_j = 0, reaper.CountTrackMediaItems(tr) - 1 do
      local it = reaper.GetTrackMediaItem(tr, item_j)
      if not it then goto next_analyze_item end

      local take = reaper.GetActiveTake(it)
      if not take or not reaper.TakeIsMIDI(take) then goto next_analyze_item end

      has_midi = true

      -- Read ALL notes
      local _, note_count = reaper.MIDI_CountEvts(take)
      for ni = 0, note_count - 1 do
        local _, _, _, startppq, endppq, chan, pitch, vel = reaper.MIDI_GetNote(take, ni)
        local note_start = reaper.MIDI_GetProjTimeFromPPQPos(take, startppq)
        local note_end = reaper.MIDI_GetProjTimeFromPPQPos(take, endppq)

        if note_start >= start_time and note_start < end_time then
          all_notes[#all_notes+1] = {
            p = pitch, v = vel,
            s = math.floor(note_start * 1000 + 0.5) / 1000,
            e = math.floor(note_end * 1000 + 0.5) / 1000,
          }
        end
      end

      -- CC event reading intentionally removed — analyze_score reports notes
      -- only. AI writes CCs but does not read them back.

      ::next_analyze_item::
    end

    if not has_midi then goto next_analyze_track end

    -- Sort notes by start time
    table.sort(all_notes, function(a, b) return a.s < b.s end)

    -- Compute compact stats instead of sending raw data
    local note_count = #all_notes
    local pitch_sum, vel_sum = 0, 0
    local pitch_min, pitch_max = 127, 0
    local vel_min, vel_max = 127, 0
    local dur_sum = 0

    for _, n in ipairs(all_notes) do
      pitch_sum = pitch_sum + n.p
      vel_sum = vel_sum + n.v
      if n.p < pitch_min then pitch_min = n.p end
      if n.p > pitch_max then pitch_max = n.p end
      if n.v < vel_min then vel_min = n.v end
      if n.v > vel_max then vel_max = n.v end
      dur_sum = dur_sum + (n.e - n.s)
    end

    local time_span = 0
    if note_count > 0 then
      time_span = all_notes[note_count].e - all_notes[1].s
    end

    -- Detect gaps > 2s (potential issues)
    local gaps = {}
    for i = 2, note_count do
      local gap = all_notes[i].s - all_notes[i-1].e
      if gap > 2.0 then
        gaps[#gaps+1] = {s = math.floor(all_notes[i-1].e * 10 + 0.5) / 10, dur = math.floor(gap * 10 + 0.5) / 10}
      end
      if #gaps >= 5 then break end
    end

    track_result.note_count = note_count
    if note_count > 0 then
      track_result.pitch_range = {pitch_min, pitch_max}
      track_result.avg_pitch = math.floor(pitch_sum / note_count + 0.5)
      track_result.vel_range = {vel_min, vel_max}
      track_result.avg_vel = math.floor(vel_sum / note_count + 0.5)
      track_result.avg_dur = math.floor(dur_sum / note_count * 100 + 0.5) / 100
      track_result.time_span = math.floor(time_span * 10 + 0.5) / 10
    end
    if #gaps > 0 then track_result.gaps = gaps end

    results[#results+1] = track_result
    ::next_analyze_track::
  end

  return {
    success = true,
    tracks_analyzed = #results,
    analysis_range = {start = start_time, ["end"] = end_time},
    tracks = results,
  }
end

-- ============================================================
-- ENVELOPE handlers (track vol/pan/mute + FX param automation)
-- ============================================================

local envelope = {}

local function _resolve_envelope(p)
  local tr = reaper.GetTrack(0, math.floor(p.track_index or -1))
  if not tr then return nil, "Track not found" end
  local fx_index = p.fx_index
  local param_index = p.param_index
  if fx_index ~= nil and param_index ~= nil then
    -- FX parameter envelope
    local env = reaper.GetFXEnvelope(tr, math.floor(fx_index), math.floor(param_index), false)
    if not env and p.create then
      env = reaper.GetFXEnvelope(tr, math.floor(fx_index), math.floor(param_index), true)
    end
    if not env then
      return nil, ("FX param envelope not found (fx=%d, param=%d). "
                   .. "Pass create=true to create it."):format(
        math.floor(fx_index), math.floor(param_index))
    end
    return env, nil
  end
  -- Track envelope by name: Volume / Pan / Mute / Width / "Volume (Pre-FX)" / etc.
  local name = p.envelope_name or "Volume"
  local env = reaper.GetTrackEnvelopeByName(tr, name)
  if not env and p.create then
    -- REAPER creates volume/pan envelopes via Main_OnCommand on selected track
    reaper.SetOnlyTrackSelected(tr)
    if name == "Volume" then reaper.Main_OnCommand(40406, 0)  -- Track: Toggle volume envelope
    elseif name == "Pan" then reaper.Main_OnCommand(40407, 0)
    elseif name == "Mute" then reaper.Main_OnCommand(40867, 0)
    end
    env = reaper.GetTrackEnvelopeByName(tr, name)
  end
  if not env then
    return nil, "Track envelope '" .. name .. "' not found. Pass create=true to create it."
  end
  return env, nil
end

function envelope.envelope_get_points(p)
  local env, err = _resolve_envelope(p)
  if not env then return nil, err end
  local count = reaper.CountEnvelopePoints(env)
  local points = {}
  local max_pts = p.max_results or 2000
  local returned = math.min(count, math.floor(max_pts))
  for i = 0, returned - 1 do
    local _, time, value, shape, tension, selected = reaper.GetEnvelopePoint(env, i)
    points[#points+1] = {
      index = i, time = time, value = value,
      shape = shape, tension = tension, selected = selected,
    }
  end
  return {
    total_points = count,
    returned = returned,
    truncated = count > returned,
    points = points,
  }
end

function envelope.envelope_add_points(p)
  local env, err = _resolve_envelope(p)
  if not env then return nil, err end
  local pts = p.points
  if type(pts) == "string" then pts = json_decode(pts) end
  if type(pts) ~= "table" then return nil, "points must be a JSON array" end
  local added = 0
  for _, pt in ipairs(pts) do
    if type(pt.time) == "number" and type(pt.value) == "number" then
      reaper.InsertEnvelopePoint(
        env, pt.time, pt.value,
        math.floor(pt.shape or 0),
        pt.tension or 0,
        pt.selected and true or false,
        true  -- no sort (we sort at end)
      )
      added = added + 1
    end
  end
  reaper.Envelope_SortPoints(env)
  reaper.UpdateArrange()
  return {success = true, points_added = added}
end

function envelope.envelope_clear_range(p)
  local env, err = _resolve_envelope(p)
  if not env then return nil, err end
  local t0 = tonumber(p.start_time or 0) or 0
  local t1 = tonumber(p.end_time or -1) or -1
  if t1 < 0 or t1 <= t0 then return nil, "end_time must be > start_time" end
  reaper.DeleteEnvelopePointRange(env, t0, t1)
  reaper.UpdateArrange()
  return {success = true, cleared_range = {start = t0, ["end"] = t1}}
end

-- ============================================================
-- TEMPO + time-signature marker handlers
-- ============================================================

local tempo = {}

function tempo.tempo_list_markers(p)
  local count = reaper.CountTempoTimeSigMarkers(0)
  local markers = {}
  for i = 0, count - 1 do
    local retval, timepos, measurepos, beatpos, bpm, tsnum, tsden, linear =
      reaper.GetTempoTimeSigMarker(0, i)
    if retval then
      markers[#markers+1] = {
        index = i, time = timepos, measure = measurepos, beat = beatpos,
        bpm = bpm, time_sig_num = tsnum, time_sig_denom = tsden,
        linear = linear,
      }
    end
  end
  return {count = count, markers = markers}
end

function tempo.tempo_add_marker(p)
  local pos = tonumber(p.position)
  if pos == nil or pos < 0 then return nil, "position must be >= 0" end
  local bpm = tonumber(p.bpm) or 0
  local tsnum = math.floor(tonumber(p.time_sig_num) or 0)
  local tsden = math.floor(tonumber(p.time_sig_denom) or 0)
  local linear = p.linear and true or false
  local ok = reaper.SetTempoTimeSigMarker(0, -1, pos, -1, -1, bpm, tsnum, tsden, linear)
  if not ok then return nil, "SetTempoTimeSigMarker failed" end
  reaper.UpdateTimeline()
  return {success = true, position = pos, bpm = bpm, time_sig = tsnum .. "/" .. tsden}
end

function tempo.tempo_delete_marker(p)
  local idx = math.floor(tonumber(p.index or -1) or -1)
  if idx < 0 then return nil, "index must be >= 0" end
  local ok = reaper.DeleteTempoTimeSigMarker(0, idx)
  if not ok then return nil, "DeleteTempoTimeSigMarker failed" end
  reaper.UpdateTimeline()
  return {success = true, deleted_index = idx}
end

function tempo.tempo_clear_all(p)
  local count = reaper.CountTempoTimeSigMarkers(0)
  for i = count - 1, 0, -1 do
    reaper.DeleteTempoTimeSigMarker(0, i)
  end
  reaper.UpdateTimeline()
  return {success = true, deleted = count}
end

-- ============================================================
-- Track peak/RMS (for AI to see levels during mixing)
-- ============================================================

function track.track_get_peak(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  -- Channel 0 = left, 1 = right. Track_GetPeakInfo returns 0 if not playing.
  -- For meaningful readings, project must be playing. REAPER doesn't expose
  -- instantaneous LUFS, so we return instantaneous peak in dB + linear.
  local peak_l = reaper.Track_GetPeakInfo(tr, 0) or 0
  local peak_r = reaper.Track_GetPeakInfo(tr, 1) or 0
  local function to_db(lin)
    if lin <= 0 then return -144.0 end
    return 20 * math.log(lin, 10)
  end
  return {
    track_index = idx,
    peak_l_linear = peak_l,
    peak_r_linear = peak_r,
    peak_l_db = to_db(peak_l),
    peak_r_db = to_db(peak_r),
    peak_max_db = to_db(math.max(peak_l, peak_r)),
  }
end

function track.track_freeze(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  reaper.SetOnlyTrackSelected(tr)
  -- 41223 = Track: Freeze to stereo (render pre-fader) — the common choice
  reaper.Main_OnCommand(41223, 0)
  return {success = true, track_index = idx, action = "freeze_stereo"}
end

function track.track_unfreeze(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  reaper.SetOnlyTrackSelected(tr)
  -- 41644 = Track: Unfreeze tracks
  reaper.Main_OnCommand(41644, 0)
  return {success = true, track_index = idx, action = "unfreeze"}
end


-- ============================================================
-- TAKE handlers (multiple takes per item for comping)
-- ============================================================

function item.item_take_list(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index or -1))
  if not it then return nil, "Item not found" end
  local count = reaper.CountTakes(it)
  local active = reaper.GetActiveTake(it)
  local takes = {}
  for i = 0, count - 1 do
    local tk = reaper.GetTake(it, i)
    if tk then
      local _, tname = reaper.GetSetMediaItemTakeInfo_String(tk, "P_NAME", "", false)
      takes[#takes+1] = {
        index = i, name = tname or "",
        is_active = (tk == active),
        is_midi = reaper.TakeIsMIDI(tk),
      }
    end
  end
  return {count = count, takes = takes}
end

function item.item_take_set_active(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index or -1))
  if not it then return nil, "Item not found" end
  local ti = math.floor(p.take_index or -1)
  if ti < 0 or ti >= reaper.CountTakes(it) then
    return nil, "take_index out of range"
  end
  local tk = reaper.GetTake(it, ti)
  if not tk then return nil, "Take not found" end
  reaper.SetActiveTake(tk)
  reaper.UpdateArrange()
  return {success = true, item_index = math.floor(p.item_index), active_take = ti}
end

function item.item_take_add(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index or -1))
  if not it then return nil, "Item not found" end
  local tk = reaper.AddTakeToMediaItem(it)
  if not tk then return nil, "Failed to add take" end
  local new_idx = reaper.CountTakes(it) - 1
  reaper.UpdateArrange()
  return {success = true, item_index = math.floor(p.item_index), new_take_index = new_idx}
end

function item.item_take_delete_active(p)
  local it = reaper.GetMediaItem(0, math.floor(p.item_index or -1))
  if not it then return nil, "Item not found" end
  -- Select only this item, then delete active take via action
  reaper.SelectAllMediaItems(0, false)
  reaper.SetMediaItemSelected(it, true)
  reaper.Main_OnCommand(40129, 0)  -- Item: Delete active take from items
  reaper.UpdateArrange()
  return {success = true, item_index = math.floor(p.item_index)}
end

-- ============================================================
-- MIDI quantize + humanize (work on a single item's active take)
-- ============================================================

function midi.midi_quantize(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  local grid_sec = tonumber(p.grid_seconds)
  if not grid_sec or grid_sec <= 0 then
    return nil, "grid_seconds must be > 0 (e.g. 0.125 for 16th at 120bpm)"
  end
  local strength = tonumber(p.strength or 1.0) or 1.0
  if strength < 0 then strength = 0 end
  if strength > 1 then strength = 1 end

  local _, note_count = reaper.MIDI_CountEvts(take)
  for ni = 0, note_count - 1 do
    local _, sel, muted, sppq, eppq, chan, pitch, vel = reaper.MIDI_GetNote(take, ni)
    local s_sec = reaper.MIDI_GetProjTimeFromPPQPos(take, sppq)
    local dur = reaper.MIDI_GetProjTimeFromPPQPos(take, eppq) - s_sec
    local grid_pos = math.floor(s_sec / grid_sec + 0.5) * grid_sec
    local new_s = s_sec + (grid_pos - s_sec) * strength
    local new_sppq = reaper.MIDI_GetPPQPosFromProjTime(take, new_s)
    local new_eppq = reaper.MIDI_GetPPQPosFromProjTime(take, new_s + dur)
    reaper.MIDI_SetNote(take, ni, sel, muted, new_sppq, new_eppq, chan, pitch, vel, true)
  end
  reaper.MIDI_Sort(take)
  return {success = true, notes_quantized = note_count,
          grid_seconds = grid_sec, strength = strength}
end

function midi.midi_humanize(p)
  local it, take, idx, err = get_midi_take(p)
  if not take then return nil, err end
  local timing_ms = tonumber(p.timing_ms or 15) or 15
  local vel_amount = math.floor(tonumber(p.velocity_amount or 8) or 8)
  if timing_ms < 0 then timing_ms = 0 end
  if vel_amount < 0 then vel_amount = 0 end

  local _, note_count = reaper.MIDI_CountEvts(take)
  for ni = 0, note_count - 1 do
    local _, sel, muted, sppq, eppq, chan, pitch, vel = reaper.MIDI_GetNote(take, ni)
    if timing_ms > 0 then
      local jitter = (math.random() * 2 - 1) * (timing_ms / 1000)
      local s_sec = reaper.MIDI_GetProjTimeFromPPQPos(take, sppq)
      local e_sec = reaper.MIDI_GetProjTimeFromPPQPos(take, eppq)
      sppq = reaper.MIDI_GetPPQPosFromProjTime(take, s_sec + jitter)
      eppq = reaper.MIDI_GetPPQPosFromProjTime(take, e_sec + jitter)
    end
    if vel_amount > 0 then
      local v = vel + math.random(-vel_amount, vel_amount)
      if v < 1 then v = 1 end
      if v > 127 then v = 127 end
      vel = v
    end
    reaper.MIDI_SetNote(take, ni, sel, muted, sppq, eppq, chan, pitch, vel, true)
  end
  reaper.MIDI_Sort(take)
  return {success = true, notes_humanized = note_count,
          timing_ms = timing_ms, velocity_amount = vel_amount}
end

-- ============================================================
-- Ripple edit mode toggle
-- ============================================================

function project.project_set_ripple_mode(p)
  local mode = math.floor(tonumber(p.mode or 0) or 0)
  -- 0 = off, 1 = per-track, 2 = all tracks
  reaper.GetSetRepeatEx(0, 0)  -- (unrelated, but we'll use Main_OnCommand)
  if mode == 0 then
    reaper.Main_OnCommand(40310, 0)  -- Options: Set ripple editing off (ensures we start from known state)
  elseif mode == 1 then
    reaper.Main_OnCommand(40311, 0)  -- Options: Set ripple editing per-track
  elseif mode == 2 then
    reaper.Main_OnCommand(40312, 0)  -- Options: Set ripple editing all tracks
  else
    return nil, "mode must be 0 (off), 1 (per-track), or 2 (all tracks)"
  end
  return {success = true, mode = mode}
end

-- ============================================================
-- Track template save/load (JSON-based — our own format, not .RTrackTemplate)
-- ============================================================

function track.track_get_state_chunk(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  local ok, chunk = reaper.GetTrackStateChunk(tr, "", false)
  if not ok then return nil, "GetTrackStateChunk failed" end
  return {track_index = idx, chunk = chunk}
end

function track.track_set_state_chunk(p)
  local tr, idx, err = get_track(p)
  if not tr then return nil, err end
  if type(p.chunk) ~= "string" or p.chunk == "" then
    return nil, "chunk must be a non-empty string"
  end
  local ok = reaper.SetTrackStateChunk(tr, p.chunk, false)
  if not ok then return nil, "SetTrackStateChunk failed" end
  reaper.UpdateArrange()
  return {success = true, track_index = idx}
end


-- ============================================================
-- Command dispatch table
-- ============================================================

local handlers = {}
for k, v in pairs(transport) do handlers[k] = v end
for k, v in pairs(track) do handlers[k] = v end
for k, v in pairs(project) do handlers[k] = v end
for k, v in pairs(fx) do handlers[k] = v end
for k, v in pairs(item) do handlers[k] = v end
for k, v in pairs(marker) do handlers[k] = v end
for k, v in pairs(selection) do handlers[k] = v end
for k, v in pairs(send) do handlers[k] = v end
for k, v in pairs(midi) do handlers[k] = v end
for k, v in pairs(compose) do handlers[k] = v end
for k, v in pairs(envelope) do handlers[k] = v end
for k, v in pairs(tempo) do handlers[k] = v end

-- ============================================================
-- Main loop
-- ============================================================

local function process_command()
  local f = io.open(command_file, "r")
  if not f then return end

  local raw = f:read("*a")
  f:close()
  os.remove(command_file)

  if not raw or raw == "" then
    send_error("Empty command")
    return
  end

  local cmd = json_decode(raw)
  if not cmd or not cmd.command then
    send_error("Invalid command JSON")
    return
  end

  local handler = handlers[cmd.command]
  if not handler then
    send_error("Unknown command: " .. tostring(cmd.command))
    return
  end

  local ok, result, err = pcall(handler, cmd.params or {})
  if not ok then
    -- pcall failed — result contains the error message
    local errmsg = "Internal error: " .. tostring(result)
    reaper.ShowConsoleMsg("ReaperMCP: " .. errmsg .. "\n")
    local sok, serr = pcall(send_error, errmsg)
    if not sok then
      reaper.ShowConsoleMsg("ReaperMCP: Failed to send error response: " .. tostring(serr) .. "\n")
    end
  elseif err then
    send_error(err)
  elseif result then
    send_success(result)
  else
    send_error("Command returned no data")
  end
end

local function main_loop()
  if not running then return end
  update_heartbeat()
  process_command()
  reaper.defer(main_loop)
end

-- ============================================================
-- Start
-- ============================================================

setup_ipc()
main_loop()
