-- Sliding Window Counter, executed atomically on the Redis server.
--
-- KEYS[1] = current fixed-window key
-- KEYS[2] = previous fixed-window key
-- ARGV[1] = now_ms
-- ARGV[2] = window_ms
-- ARGV[3] = limit
--
-- Returns: { allowed (0/1), remaining, retry_after_ms }

local current_key = KEYS[1]
local previous_key = KEYS[2]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Which fixed window "slot" are we in right now, and how far into it are we?
local current_slot = math.floor(now_ms / window_ms)
local elapsed_in_current = now_ms - (current_slot * window_ms)
local overlap_ratio = (window_ms - elapsed_in_current) / window_ms

-- Read stored slot markers so we know if 'current_key' actually corresponds
-- to this slot, or is stale (i.e. we've rolled into a new window).
local stored_slot = redis.call("GET", current_key .. ":slot")

local current_count = 0
local previous_count = 0

if stored_slot == false then
    -- No data yet at all: fresh key set, nothing to weight.
    current_count = 0
    previous_count = 0
elseif tonumber(stored_slot) == current_slot then
    -- Still in the same fixed window as last write.
    current_count = tonumber(redis.call("GET", current_key)) or 0
    previous_count = tonumber(redis.call("GET", previous_key)) or 0
elseif tonumber(stored_slot) == current_slot - 1 then
    -- We've rolled exactly one window forward: previous becomes what was current.
    previous_count = tonumber(redis.call("GET", current_key)) or 0
    current_count = 0
else
    -- More than one window has elapsed since last write (idle client): both stale.
    current_count = 0
    previous_count = 0
end

local weighted_count = current_count + (previous_count * overlap_ratio)

if weighted_count >= limit then
    local retry_after_ms = window_ms - elapsed_in_current
    return { 0, math.max(0, math.floor(limit - weighted_count)), retry_after_ms }
end

-- Allowed: consume one unit. Roll the window state if needed, then increment.
if stored_slot == false or tonumber(stored_slot) ~= current_slot then
    if stored_slot ~= false and tonumber(stored_slot) == current_slot - 1 then
        redis.call("SET", previous_key, redis.call("GET", current_key) or 0)
    else
        redis.call("SET", previous_key, 0)
    end
    redis.call("SET", current_key, 0)
    redis.call("SET", current_key .. ":slot", current_slot)
end

local new_count = redis.call("INCR", current_key)

redis.call("PEXPIRE", current_key, window_ms * 2)
redis.call("PEXPIRE", previous_key, window_ms * 2)
redis.call("PEXPIRE", current_key .. ":slot", window_ms * 2)

-- FIXED: use new_count (post-increment), not the stale pre-increment current_count
local remaining = math.max(0, limit - math.floor(new_count + previous_count * overlap_ratio))
return { 1, remaining, 0 }