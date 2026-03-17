from .calendar import (
    calendar_check_calendar_with_at_least_3_events,
    calendar_check_weekly_event,
    calendar_check_weekly_event_advanced,
    calendar_check_calendar_contains_events,
)
from .clock import (
    clock_get_world_clock_order,
    clock_list_alarms,
    clock_reset_window_status,
    clock_check_korea_alarm,
    clock_check_clock_timer_value,
    clock_get_world_clock_top_item,
)
from .finder import (
    finder_check_file_exists,
    finder_check_file_tag,
    finder_check_tagged_files_strict,
    finder_read_file_contents,
    finder_check_folder_exists,
    finder_check_smart_folder_filters_pdf_in_seven_days,
)
from .notes import (
    notes_count_notes_in_folder,
    notes_find_note_by_title,
    notes_get_note_plaintext_by_name,
    notes_list_locked_note_titles,
    notes_list_attachment_names_by_note_name,
)
from .new_apple_notes import (
    new_apple_notes_check_export_contains_note_title,
    new_apple_notes_check_file_contains_all_note_titles,
    new_apple_notes_check_file_contains_all_search_result_titles,
    new_apple_notes_check_file_contains_all_titles_in_folder,
    new_apple_notes_check_note_absent,
    new_apple_notes_check_note_exists_in_folder,
    new_apple_notes_check_note_exists_with_content,
)
from .new_obsidian import (
    new_obsidian_check_file_contains_all_note_paths_in_folder,
    new_obsidian_check_file_contains_all_search_matches,
    new_obsidian_check_file_equals_note_content,
    new_obsidian_check_links_updated_after_move,
    new_obsidian_check_note_contains_all_texts,
    new_obsidian_check_note_exists_with_exact_content,
    new_obsidian_check_note_contains_text,
    new_obsidian_check_note_moved,
    new_obsidian_check_note_absent,
    new_obsidian_check_frontmatter_value,
)
from .new_peekaboo import (
    new_peekaboo_check_app_running,
    new_peekaboo_check_clipboard_empty,
    new_peekaboo_check_clipboard_text_equals,
    new_peekaboo_check_file_equals,
    new_peekaboo_check_frontmost_app,
    new_peekaboo_check_image_exists_nonempty,
    new_peekaboo_check_safari_front_url,
    new_peekaboo_check_textedit_document_count_at_least,
    new_peekaboo_check_textedit_document_equals,
    new_peekaboo_check_window_count_at_least,
    new_peekaboo_check_window_bounds,
)
from .new_blogwatcher import (
    new_blogwatcher_check_article_marked_read,
    new_blogwatcher_check_article_title_is_read,
    new_blogwatcher_check_blog_absent,
    new_blogwatcher_check_blog_has_read_article,
    new_blogwatcher_check_blog_has_no_unread_articles,
    new_blogwatcher_check_file_contains_all_article_titles,
    new_blogwatcher_check_scan_success_for_blog,
    new_blogwatcher_check_no_unread_articles,
    new_blogwatcher_check_articles_not_empty,
    new_blogwatcher_check_blog_exists,
    new_blogwatcher_check_file_contains_all_blog_names,
)
from .new_clawhub import (
    new_clawhub_check_list_output_contains_all_skills,
    new_clawhub_check_list_output_contains_skill,
    new_clawhub_check_skill_installed,
)
from .new_gifgrep import (
    new_gifgrep_check_download_matches_first_result,
    new_gifgrep_check_file_exists_nonempty,
    new_gifgrep_check_png_exists_nonempty,
    new_gifgrep_check_sheet_matches_expected_hash,
    new_gifgrep_check_sheet_exists_nonempty,
    new_gifgrep_check_still_matches_expected_hash,
    new_gifgrep_check_url_file_has_min_lines,
)
from .new_github import (
    new_github_check_file_contains_live_lines,
    new_github_check_repo_info_matches,
    new_github_check_top_issue_values_present,
)
from .new_himalaya import (
    new_himalaya_check_keyword_moved_after,
    new_himalaya_check_file_contains_live_lines,
    new_himalaya_check_file_equals_live_output,
    new_himalaya_check_json_equals_live,
    new_himalaya_check_keyword_moved,
    new_himalaya_check_keyword_moved_with_baseline,
    new_himalaya_check_single_kv_equals,
)
from .new_weather import (
    new_weather_check_contains_live_current_values,
    new_weather_check_file_contains_live_lines,
    new_weather_check_rain_dates_exact,
    new_weather_check_temp_range_with_tolerance,
    new_weather_check_yes_no_matches_live,
)
from .new_video_frames import (
    new_video_frames_check_first_frame_matches_expected,
    new_video_frames_check_scaled_frame_matches_expected,
    new_video_frames_check_timestamp_frame_matches_expected,
)
from .new_reminders import (
    new_reminders_check_file_contains_all_titles_in_list,
    new_reminders_check_file_contains_overdue_titles,
    new_reminders_check_file_contains_today_titles,
    new_reminders_check_list_absent,
    new_reminders_check_list_exists,
    new_reminders_check_reminder_absent,
    new_reminders_check_reminder_completed,
    new_reminders_check_reminder_due_date_in_list,
    new_reminders_check_reminder_due_datetime,
    new_reminders_check_reminder_exists,
    new_reminders_check_reminder_exists_in_list,
)
from .new_songsee import (
    new_songsee_check_render_matches_expected,
)
from .new_sherpa_onnx_tts import (
    new_sherpa_onnx_tts_check_wav_properties,
)
from .new_whisper import (
    new_whisper_check_file_matches_live_output,
)
from .new_tmux import (
    new_tmux_check_file_contains_text,
    new_tmux_check_json_key_contains_text,
    new_tmux_check_json_key_value,
    new_tmux_check_json_list_exact,
    new_tmux_check_pane_contains_text,
)
from .reminders import (
    reminders_check_all_completed_with_expected_items,
    reminders_check_due_time,
    reminders_check_work_due_next_week,
    reminders_get_due_year,
    reminders_check_on_date,
    reminders_get_body_by_name,
)
from .safari import (
    safari_check_steam_cart_contains_all_top3_items,
    safari_get_all_bookmark_folders,
    safari_get_bookmarks_in_folder,
    safari_get_default_property,
    safari_get_url,
    safari_get_window_count,
)
from .mac_system_settings import (
    setting_dump_siri_panel,
    setting_get_siri_status_and_voice,
    settings_reset_window_status,
    settings_check_purple_and_tinting_off,
    settings_set_desktop_wallpaper,
    settings_check_dnd_repeated_calls_enabled,
)
from .terminal import (
    terminal_check_archive_validity_count_name_mod,
    terminal_check_echo_macos_script,
    terminal_check_package_in_conda_env,
    terminal_check_command_in_history,
    terminal_reset_window_status,
    terminal_check_files_in_directory,
)
from .vscode import (
    vscode_check_extension_installed,
    vscode_check_tab_to_4space_replacement,
    vscode_check_workspace_folders,
    vscode_check_python_extension_and_conda_path,
)

from .common import (
    check_file_exists
)

from .numbers import(
    numbers_test_create_and_save_table,
    numbers_test_cell_operation,
    numbers_test_cell_format,
    numbers_test_value_replacement,
    numbers_test_cell_merge,
    numbers_test_filter,
    numbers_test_change_bgcolor,
    numbers_init_table
)

from .pages import (
    pages_test_create_and_enter_content,
    pages_test_change_font_color,
    pages_test_change_text_alignment,
    pages_test_change_text_font,
    pages_test_insert_table,
    pages_test_find_and_replace,
    pages_create_new_doc,
    pages_test_shape_pos_and_size,
    pages_check_body_text
)

from .keynote import (
    keynote_test_doc_creation,
    keynote_test_item_delection,
    keynote_test_image_insertion,
    keynote_test_table_insertion,
    keynote_test_text_box_insertion,
    keynote_test_shape_insertion,
    keynote_test_slide_insertion,
    keynote_test_shape_insertion_multi
)
