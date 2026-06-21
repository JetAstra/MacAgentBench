import json
from typing import List
from controllers.env import MacOSEnv
from utils.logger import ProjectLogger
import time
import datetime
import pytz

logger = ProjectLogger().get()


def force_close_clock(env: MacOSEnv):
    env.connect_ssh()
    cmds = [
        "sudo pkill -9 'Clock'",
        "sudo pkill -9 securityagent" "sudo pkill -9 'Clock.app'",
        "sudo pkill -9 'Clock Widgets'",
        "sudo pkill -9 'com.apple.clock'",
        "sudo pkill -9 'application.com.apple.clock.*'",
    ]
    for cmd in cmds:
        env.run_command(f"{cmd}")
    time.sleep(3)


def clock_reset_window_status(env: MacOSEnv):
    send_esc_script = """
    tell application "System Events"
        key code 53 -- Esc key
    end tell
    """
    env.run_command(f"osascript -e '{send_esc_script.strip()}'")
    time.sleep(0.5)
    env.connect_ssh()

    force_close_clock(env)
    env.run_command(f"open -a 'Clock'")
    stdout, _ = env.run_command(f"osascript -e '{send_esc_script.strip()}'")
    time.sleep(5)


# click radio button 2 of radio group 1 of group 1 of toolbar 1 of window 1 -- ALARMS


def clock_debug(env: MacOSEnv) -> str:
    """
    Debug UI structure of Clock.app: get class, name, description, and value of each top-level UI element.

    Returns:
        str: Formatted information for each UI element in Clock's main window.
    """
    env.connect_ssh()
    # force_close_clock(env)
    clock_reset_window_status(env)

    apple_script = """
    tell application "System Events"
        tell application process "Clock"
            if (count of windows) = 0 then
                return "No window found"
            end if
            
            click menu item "World Clock" of menu "View" of menu bar 1
            delay 5

            set output to ""
            set elems to every UI element of group 1 of group 1 of group 1 of group 1 of group 1 of group 1 of group 1 of group 1 of group 1 of group 1 of group 1 of group 1 of group 1 of window 1
            repeat with elem in elems
                set elem_class to (class of elem as string)

                -- name
                try
                    set elem_name to name of elem
                    if (class of elem_name is not text) then set elem_name to "<non-text name>"
                on error
                    set elem_name to "<no name>"
                end try

                -- description
                try
                    set elem_desc to description of elem
                    if (class of elem_desc is not text) then set elem_desc to "<non-text description>"
                on error
                    set elem_desc to "<no description>"
                end try

                -- value
                try
                    set elem_value to value of elem
                    if (class of elem_value is not text) then set elem_value to "<non-text value>"
                on error
                    set elem_value to "<no value>"
                end try

                set output to output & "[class: " & elem_class & "] "
                set output to output & "[name: " & elem_name & "] "
                set output to output & "[description: " & elem_desc & "] "
                set output to output & "[value: " & elem_value & "]\\n"
            end repeat

            return output
        end tell
    end tell
    """

    #     apple_script = '''
    #     tell application "System Events"
    #         tell application process "Clock"
    #             if (count of windows) = 0 then
    #                 return "No window found"
    #             end if

    #             set output to ""
    #             set current_group to window 1
    #             set path_desc to "window 1"
    #             set max_depth to 20
    #             repeat with depth from 1 to max_depth
    #                 try
    #                     set current_group to group 1 of current_group
    #                     set path_desc to path_desc & " -> group 1"
    #                 on error
    #                     set output to output & "Reached max or no group 1 at depth " & depth & "\\n"
    #                     exit repeat
    #                 end try

    #                 set elems to every UI element of current_group
    #                 set class_list to {}

    #                 repeat with elem in elems
    #                     set elem_class to (class of elem as string)
    #                     copy elem_class to the end of class_list
    #                 end repeat

    #                 -- group search
    #                 if class_list contains "static text" or class_list contains "button" or class_list contains "checkbox" or class_list contains "text field" or class_list contains "image" then
    #                     set output to output & "⤵ Found mixed content at: " & path_desc & "\\n"

    #                     repeat with elem in elems
    #                         set elem_class to (class of elem as string)
    #                         try
    #                             set elem_name to name of elem
    #                             if (class of elem_name is not text) then set elem_name to "<non-text name>"
    #                         on error
    #                             set elem_name to "<no name>"
    #                         end try

    #                         try
    #                             set elem_desc to description of elem
    #                             if (class of elem_desc is not text) then set elem_desc to "<non-text description>"
    #                         on error
    #                             set elem_desc to "<no description>"
    #                         end try

    #                         try
    #                             set elem_value to value of elem
    #                             if (class of elem_value is not text) then set elem_value to "<non-text value>"
    #                         on error
    #                             set elem_value to "<no value>"
    #                         end try

    #                         set output to output & "[class: " & elem_class & "] "
    #                         set output to output & "[name: " & elem_name & "] "
    #                         set output to output & "[description: " & elem_desc & "] "
    #                         set output to output & "[value: " & elem_value & "]\\n"
    #                     end repeat

    #                     exit repeat
    #                 end if
    #             end repeat

    #             return output
    #         end tell
    #     end tell
    # '''

    try:
        stdout, stderr = env.run_command(f"osascript -e '{apple_script.strip()}'")
        logger.info(stderr)
        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        # logger.info(f"[clock_debug] Clock UI detailed structure:\n{output}")
        return output
    except Exception as e:
        logger.error(f"[clock_debug] Failed to extract Clock UI structure: {e}")
        return "Error: Unable to retrieve UI elements"


def clock_list_alarms(env) -> list[dict]:
    """
    Launch Clock.app, switch to Alarm tab, and extract structured alarm data including 'enabled' status.

    Returns:
        list of dicts: [
            {
                "time": "6:30AM",
                "label": "Morning run",
                "repeat": "Weekdays",
                "sound": "Ripples",
                "enabled": True
            },
            ...
        ]
    """
    env.connect_ssh()
    env.run_command("open -a 'Clock'")
    time.sleep(2)

    apple_script = """
    tell application "Clock"
        activate
    end tell

    delay 1

    tell application "System Events"
        tell process "Clock"

            click menu item "Alarms" of menu "View" of menu bar 1 
            delay 3

            if (count of windows) = 0 then
                return "[]"
            end if

            set w to window 1
            set all_elements to entire contents of w

            set output to "["

            repeat with el in all_elements
                try
                    -- 只处理 button
                    if role of el is "AXButton" then

                        set sub_elements to entire contents of el

                        set text_items to {}
                        set checkbox_items to {}

                        -- 🔍 收集子元素
                        repeat with sub in sub_elements
                            try
                                set r to role of sub

                                if r is "AXStaticText" then
                                    set end of text_items to sub
                                else if r is "AXCheckBox" then
                                    set end of checkbox_items to sub
                                end if
                            end try
                        end repeat

                        -- 🎯 判断是不是 alarm（关键过滤）
                        if (count of text_items) ≥ 2 and (count of checkbox_items) = 1 then

                            set alarm_time to ""
                            set alarm_label to ""
                            set alarm_repeat to ""
                            set alarm_sound to ""
                            set alarm_enabled to "false"

                            try
                                set checkbox_value to value of item 1 of checkbox_items
                                
                                if checkbox_value is 1 or checkbox_value is "1" or checkbox_value is true or checkbox_value is "true" then
                                    set alarm_enabled to "true"
                                end if
                            end try

                            -- 🔍 解析文本
                            repeat with t in text_items
                                try
                                    set d to missing value

                                    try
                                        set d to value of t
                                    end try

                                    if d is missing value then
                                        try
                                            set d to name of t
                                        end try
                                    end if

                                    if d is missing value then
                                        try
                                            set d to description of t
                                        end try
                                    end if

                                    if d is not missing value then
                                        if d contains "AM" or d contains "PM" then
                                            set alarm_time to d
                                        else if d starts with "Repeat" then
                                            set alarm_repeat to d
                                        else if d starts with "Sound" then
                                            set alarm_sound to d
                                        else
                                            -- 避免把 Repeat/Sound 覆盖 label
                                            if alarm_label is "" then
                                                set alarm_label to d
                                            end if
                                        end if
                                    end if
                                end try
                            end repeat

                            -- 拼 JSON
                            set output to output & "{"
                            set output to output & "\\"time\\":\\"" & alarm_time & "\\","
                            set output to output & "\\"label\\":\\"" & alarm_label & "\\","
                            set output to output & "\\"repeat\\":\\"" & alarm_repeat & "\\","
                            set output to output & "\\"sound\\":\\"" & alarm_sound & "\\","
                            set output to output & "\\"enabled\\":" & alarm_enabled
                            set output to output & "},"

                        end if

                    end if
                end try
            end repeat

            -- 去掉最后一个逗号
            if output ends with "," then
                set output to text 1 thru -2 of output
            end if

            set output to output & "]"

            return output

        end tell
    end tell
    """

    try:
        stdout, _ = env.run_command(f"osascript -e '{apple_script.strip()}'")
        logger.info(_)
        raw_output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        logger.info(f"[clock_list_alarms] Raw AppleScript output:\n{raw_output}")

        # Convert to JSON
        alarms = json.loads(raw_output)
        for alarm in alarms:
            alarm["sound"] = alarm["sound"].replace("Sound: ", "", 1) if alarm["sound"].startswith("Sound: ") else alarm["sound"]
            alarm["repeat"] = alarm["repeat"].replace("Repeat: ", "", 1) if alarm["repeat"].startswith("Repeat: ") else alarm["repeat"]
        return alarms

    except Exception as e:
        logger.error(f"[clock_list_alarms] Failed to extract alarms: {e}")
        return []


def clock_get_world_clock_order(env) -> list[str]:
    """
    Switch to World Clock tab and extract the current order of world clocks shown.

    Returns:
        list of city names in order of appearance (top to bottom).
    """
    env.connect_ssh()

    # open_script = """
    # tell application "System Events"
    #     tell application process "Clock"
    #         if (count of windows) = 0 then
    #             return "No window found"
    #         end if
    #         click menu item "World Clock" of menu "View" of menu bar 1
    #     end tell
    # end tell
    # """
    # env.run_command(f"osascript -e '{open_script.strip()}'")
    # time.sleep(3)

    apple_script = """
    set cityList to {}
        tell application "System Events"
            tell application process "Clock"
                if not (exists window 1) then return "[]"
                
                -- 获取所有深层嵌套的静态文本的描述
                set allTexts to description of every UI element of every UI element of every UI element of every UI element of every UI element of every UI element of every UI element of every UI element of every UI element of every UI element of every UI element of every UI element of every UI element of every UI element of window 1
                
                -- 这里的嵌套非常深，我们直接用刚才跑通的递归逻辑来提取
                set rawData to my getCityNames(window 1)
                return rawData
            end tell
        end tell

        on getCityNames(currentElem)
            set names to ""
            tell application "System Events"
                try
                    if role of currentElem is "AXStaticText" then
                        set d to description of currentElem
                        if d is not missing value and d contains "," then
                            -- 提取逗号前的城市名
                            set cityName to text 1 thru ((offset of "," in d) - 1) of d
                            return cityName & "|"
                        end if
                    end if
                    
                    set children to UI elements of currentElem
                    repeat with child in children
                        set names to names & my getCityNames(child)
                    end repeat
                end try
            end tell
            return names
        end getCityNames
    """

    try:
        stdout, _ = env.run_command(f"osascript -e '{apple_script.strip()}'")
        raw_output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        # logger.info(f"[clock_get_world_clock_order] Raw output: {raw_output}")

        if raw_output == "No window found":
            return []

        # Split by custom delimiter
        cities = [c.strip() for c in raw_output.split("|") if c.strip()]
        print(cities)
        import traceback; print("[DEBUG] clock_get_world_clock_order called from:"); traceback.print_stack()
        return cities

    except Exception as e:
        logger.error(f"Failed to get world clock order: {e}")
        return []


def clock_get_world_clock_top_item(env):
    clock_list = clock_get_world_clock_order(env)
    if clock_list != []:
        return clock_list[0]


def clock_check_timezone_alarm(env, timezone: str = "Asia/Seoul", alarm_name: str = "Korea") -> bool:
    """
    Check whether the first alarm in Clock app matches the given name and
    its time matches the current time in the specified timezone (±3 minutes).

    :param env: MacOSEnv instance
    :param timezone: Timezone string (e.g., "Asia/Seoul", "Europe/London")
    :param alarm_name: Expected alarm label
    :return: True if matched, False otherwise
    """
    env.connect_ssh()

    # Step 1: Get current time in target timezone
    try:
        target_tz = pytz.timezone(timezone)
        target_time = datetime.datetime.now(target_tz)
        target_hour = target_time.hour
        target_minute = target_time.minute
        logger.info(f"current {timezone} time: {target_time}")
    except Exception as e:
        logger.error(f"[clock_check_timezone_alarm] Failed to get time for {timezone}: {e}")
        return False

    # Step 2: Get alarm list from Clock.app
    try:
        alarms = clock_list_alarms(env)
        if not alarms:
            logger.warning("[clock_check_timezone_alarm] No alarms found.")
            return False

        alarm = alarms[0]  # First alarm
        alarm_label = alarm.get("label", "")
        alarm_time_str = alarm.get("time", "")

        # Validate label
        if alarm_label.lower() != alarm_name.lower():
            logger.warning(
                f"[clock_check_timezone_alarm] First alarm label is not '{alarm_name}': {alarm_label}"
            )
            return False

        # Parse alarm time string (e.g., '3:00PM')
        try:
            alarm_dt = datetime.datetime.strptime(alarm_time_str.strip(), "%I:%M%p")
        except ValueError:
            logger.error(
                f"[clock_check_timezone_alarm] Invalid alarm time format: {alarm_time_str}"
            )
            return False

        # Convert alarm time to 24-hour
        alarm_hour = alarm_dt.hour
        alarm_minute = alarm_dt.minute

        # Step 3: Compare time (±3 min)
        delta = abs((alarm_hour * 60 + alarm_minute) - (target_hour * 60 + target_minute))
        # Handle midnight wrap-around
        if delta > 720:
            delta = 1440 - delta
        logger.info(
            f"[clock_check_timezone_alarm] {timezone} time: {target_hour}:{target_minute:02d}, "
            f"Alarm: {alarm_hour}:{alarm_minute:02d}, Δ={delta}min"
        )

        return delta <= 3
    except Exception as e:
        logger.error(f"[clock_check_korea_alarm] Failed to evaluate alarm: {e}")
        return False


def clock_check_clock_timer_value(env: MacOSEnv, hours=0, minutes=0, seconds=0) -> bool:
    """
    Check whether the Clock app's Timer matches the given (hours, minutes, seconds).

    Args:
        env (MacOSEnv): Remote macOS environment
        hours (int): Expected hour value (default: 0)
        minutes (int): Expected minute value (default: 0)
        seconds (int): Expected second value (default: 0)

    Returns:
        bool: True if matches, False otherwise
    """
    env.connect_ssh()

    open_timer_script = """
    tell application "Clock" to activate
    delay 1
    tell application "System Events"
        tell process "Clock"
            click menu item "Timers" of menu "View" of menu bar 1
        end tell
    end tell
    """
    env.run_command(f"osascript -e '{open_timer_script.strip()}'")
    time.sleep(2)

    read_timer_script = """
    tell application "System Events"
        tell process "Clock"
            set window1 to window 1
            set commonPath to group 1 of group 1 of group 4 of group 1 of group 1 of group 1 of group 1 of group 1 of group 1 of group 2 of group 1 of group 1 of group 1 of group 1 of group 1 of window1
            
            try
                set hoursValue to value of slider 1 of commonPath -- 例如 "0 hours"
                set minsValue to value of slider 2 of commonPath  -- 例如 "0 minutes"
                set secsValue to value of slider 3 of commonPath  -- 例如 "0 seconds"
                
                return {hoursValue, minsValue, secsValue}
            on error
                return "Error"
            end try
        end tell
    end tell
    """

    stdout, stderr = env.run_command(f"osascript -e '{read_timer_script.strip()}'")
    output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )
    logger.info(f"[settings_check_clock_timer_value] Raw output: {output}")

    try:
        if "Error" in output:
            return False

        timer_parts = output.strip().split(", ")
        timer_parts = [timer_parts[i].split(" ")[0] for i in range(len(timer_parts))]
        if len(timer_parts) != 3:
            return False

        actual_h, actual_m, actual_s = map(int, timer_parts)
        return actual_h == hours and actual_m == minutes and actual_s == seconds

    except Exception as e:
        logger.error(f"Failed to parse timer output: {e}")
        return False


# ====================================================================== #
# World Clock fine-grained helper (added 2026-04-12).
# ====================================================================== #


def clock_check_city_in_world_clocks(env, city: str) -> bool:
    """
    Check whether a city appears anywhere in the World Clock list.

    Uses accent-insensitive matching (via ``strip_accents``) so that
    e.g. ``"Bogota"`` matches ``"Bogotá"`` as returned by macOS.

    Args:
        env (MacOSEnv): macOS automation environment
        city (str): City name to look for (accent-insensitive)

    Returns:
        bool: True if the city is in the world clock list.
    """
    from evaluators.metrics.common import strip_accents

    cities = clock_get_world_clock_order(env)
    target = strip_accents(city)
    for c in cities:
        if strip_accents(c) == target:
            logger.info(f"[clock_check_city_in_world_clocks] Found {city!r} (as {c!r})")
            return True
    logger.info(f"[clock_check_city_in_world_clocks] {city!r} not in {cities}")
    return False


# ====================================================================== #
# Alarm fine-grained helper (added 2026-04-12).
#
# `clock_get_alarm_by_label` reuses `clock_list_alarms` internally and
# returns the full alarm dict for a given label, enabling per-property
# checks via `dict_match_ratio` or `is_true`.
#
# `clock_list_alarms` is left untouched per the "only-add-never-modify"
# rule (FINE_GRAINED_EVAL_DESIGN.md §6.1).
# ====================================================================== #


def clock_count_alarms(env) -> int:
    """
    Return the number of alarms currently in the Clock app.

    Internally calls ``clock_list_alarms`` and returns ``len()``.
    Use with ``exact_match(1)`` to check that only one alarm remains
    (e.g. after deleting all others).

    Returns:
        int: Number of alarms, or 0 on error.
    """
    alarms = clock_list_alarms(env)
    count = len(alarms)
    logger.info(f"[clock_count_alarms] {count} alarms")
    return count


def clock_get_alarm_by_label(env, label: str) -> dict:
    """
    Find an alarm by its label and return the full alarm dict.

    Internally calls :func:`clock_list_alarms` to retrieve all alarms,
    then returns the first one whose ``label`` field exactly matches
    *label*.  Returns an empty dict ``{}`` if no match is found.

    An empty dict is falsy in Python, so using ``is_true`` as the metric
    on this getter naturally checks "does an alarm with this label exist?".
    Using ``dict_match_ratio`` with a single-key dict (e.g.
    ``{"time": "9:20AM"}``) checks a specific property of that alarm.

    Args:
        env (MacOSEnv): macOS automation environment
        label (str): Exact alarm label to look for

    Returns:
        dict: The alarm dict (with keys time/label/repeat/sound/enabled),
              or ``{}`` if no alarm with this label exists.
    """
    alarms = clock_list_alarms(env)
    for alarm in alarms:
        if alarm.get("label") == label:
            logger.info(f"[clock_get_alarm_by_label] Found alarm: {alarm}")
            return alarm
    logger.info(f"[clock_get_alarm_by_label] No alarm with label={label!r}")
    return {}


# ====================================================================== #
# Timer fine-grained helpers (added 2026-04-12).
#
# `clock_get_timer_value` returns the timer's current slider values as a
# dict so individual fields can be checked via `dict_match_ratio`.
# `clock_check_timer_recents_empty` checks whether the Recents section
# in Timers view is empty.
#
# `clock_check_clock_timer_value` is left untouched per the
# "only-add-never-modify" rule.
# ====================================================================== #


def clock_get_timer_value(env) -> dict:
    """
    Read the Clock app's Timer slider values and return them as a dict.

    Reuses the same AppleScript logic as ``clock_check_clock_timer_value``
    but returns the raw values instead of a bool comparison.

    Returns:
        dict: ``{"hours": int, "minutes": int, "seconds": int}``
              or ``{}`` on any error.
    """
    env.connect_ssh()

    open_timer_script = """
    tell application "Clock" to activate
    delay 1
    tell application "System Events"
        tell process "Clock"
            click menu item "Timers" of menu "View" of menu bar 1
        end tell
    end tell
    """
    env.run_command(f"osascript -e '{open_timer_script.strip()}'")
    time.sleep(2)

    read_timer_script = """
    tell application "System Events"
        tell process "Clock"
            set window1 to window 1
            set commonPath to group 1 of group 1 of group 4 of group 1 of group 1 of group 1 of group 1 of group 1 of group 1 of group 2 of group 1 of group 1 of group 1 of group 1 of group 1 of window1

            try
                set hoursValue to value of slider 1 of commonPath
                set minsValue to value of slider 2 of commonPath
                set secsValue to value of slider 3 of commonPath
                return {hoursValue, minsValue, secsValue}
            on error
                return "Error"
            end try
        end tell
    end tell
    """

    stdout, _ = env.run_command(f"osascript -e '{read_timer_script.strip()}'")
    output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )
    logger.info(f"[clock_get_timer_value] Raw output: {output}")

    try:
        if "Error" in output:
            return {}

        timer_parts = output.strip().split(", ")
        timer_parts = [p.split(" ")[0] for p in timer_parts]
        if len(timer_parts) != 3:
            return {}

        h, m, s = map(int, timer_parts)
        result = {"hours": h, "minutes": m, "seconds": s}
        logger.info(f"[clock_get_timer_value] Parsed: {result}")
        return result

    except Exception as e:
        logger.error(f"[clock_get_timer_value] Failed to parse: {e}")
        return {}


def clock_check_timer_recents_empty(env) -> bool:
    """
    Check whether the Recents section in the Clock Timers view is empty.

    Switches to the Timers view and looks for any UI elements that
    represent recent timer entries. Returns True if Recents is empty
    (i.e. the agent successfully cleared it).

    Returns:
        bool: True if Recents section is empty or not present.
    """
    env.connect_ssh()

    open_timer_script = """
    tell application "Clock" to activate
    delay 1
    tell application "System Events"
        tell process "Clock"
            click menu item "Timers" of menu "View" of menu bar 1
        end tell
    end tell
    """
    env.run_command(f"osascript -e '{open_timer_script.strip()}'")
    time.sleep(2)

    # Look for "Recent" / "Recents" static text header, then count
    # static text elements after it that look like timer entries
    # (e.g. "01:53", "1 min, 53 sec").  The actual UI shows recent
    # timer values as static text, not buttons.
    check_script = """
    tell application "System Events"
        tell process "Clock"
            set ec to entire contents of window 1
            set foundRecent to false
            set recentCount to 0
            repeat with e in ec
                try
                    -- The header is "Recent" (no trailing s) on current macOS
                    -- Note: the visible text is in `description`, not `value`
                    if class of e is static text then
                        set val to description of e as text
                        if val is "Recent" or val is "Recents" then
                            set foundRecent to true
                        else if foundRecent then
                            -- After the header, static texts with time patterns are recent entries
                            if val contains ":" or val contains "min" or val contains "sec" or val contains "hr" then
                                set recentCount to recentCount + 1
                            end if
                        end if
                    end if
                end try
            end repeat
            return recentCount as text
        end tell
    end tell
    """

    try:
        stdout, _ = env.run_command(f"osascript -e '{check_script.strip()}'")
        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        logger.info(f"[clock_check_timer_recents_empty] Recent count: {output}")
        return output == "0"
    except Exception as e:
        logger.error(f"[clock_check_timer_recents_empty] Failed: {e}")
        return False


if __name__ == "__main__":
    # Initialize the environment with default config
    macos_env = MacOSEnv()

    # Connect to Docker container
    macos_env.connect_ssh()

    # prop = "ShowFavorites"
    value = clock_check_clock_timer_value(macos_env, minutes=1, seconds=20)
    logger.info(value)

    import time

    time.sleep(3)
    macos_env.close_connection()
