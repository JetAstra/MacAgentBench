import shlex
import re

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger


logger = ProjectLogger().get()


def _run_blogwatcher(env: MacOSEnv, args: str) -> str:
    command = f"blogwatcher {args} 2>&1"
    stdout, _ = env.run_command(command)
    text = stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    logger.info("[new_blogwatcher] command=%s output=%r", command, text)
    return text


def _read_remote_file(env: MacOSEnv, output_file: str) -> str | None:
    remote_py = f"""
from pathlib import Path
import os

path = os.path.expandvars(os.path.expanduser({output_file!r}))
p = Path(path)
if not p.exists():
    print("__MISSING__")
else:
    print(p.read_text(encoding="utf-8", errors="replace"))
"""
    safe_code = shlex.quote(remote_py.strip())
    stdout, _ = env.run_command(f"python3 -c {safe_code}")
    text = stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    if text == "__MISSING__":
        return None
    return text


def _parse_blog_names_from_blogs_output(output: str) -> list[str]:
    names: list[str] = []
    for line in output.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("Tracked blogs"):
            continue
        if s.startswith("URL:"):
            continue
        if "://" in s:
            continue
        # Name lines are typically plain tokens (e.g. "xkcd")
        if ":" not in s:
            names.append(s)
    return names


def _has_article_like_lines(output: str) -> bool:
    for line in output.splitlines():
        s = line.strip()
        if not s:
            continue
        lowered = s.lower()
        if lowered.startswith("articles"):
            continue
        if lowered.startswith("tracked blogs"):
            continue
        if lowered.startswith("no articles"):
            continue
        if lowered.startswith("found 0"):
            continue
        return True
    return False


def _parse_article_titles_from_articles_output(output: str) -> list[str]:
    titles: list[str] = []
    for line in output.splitlines():
        # Example: "  [21] [new] Some article title"
        match = re.match(r"^\s*\[\d+\]\s*(?:\[[^\]]+\]\s*)?(.*\S)\s*$", line)
        if match:
            titles.append(match.group(1).strip())
    return titles


def _parse_article_status_by_id(output: str) -> dict[int, str]:
    status_by_id: dict[int, str] = {}
    for line in output.splitlines():
        match = re.match(r"^\s*\[(\d+)\]\s*\[([^\]]+)\]\s+", line)
        if match:
            status_by_id[int(match.group(1))] = match.group(2).strip().lower()
    return status_by_id


def _parse_articles_all_entries(output: str) -> list[dict[str, str | int]]:
    entries: list[dict[str, str | int]] = []
    current: dict[str, str | int] | None = None
    for line in output.splitlines():
        item_match = re.match(r"^\s*\[(\d+)\]\s*\[([^\]]+)\]\s*(.*\S)?\s*$", line)
        if item_match:
            current = {
                "id": int(item_match.group(1)),
                "status": item_match.group(2).strip().lower(),
                "title": (item_match.group(3) or "").strip(),
                "blog": "",
            }
            entries.append(current)
            continue

        if current is None:
            continue

        blog_match = re.match(r"^\s*Blog:\s*(.*\S)\s*$", line)
        if blog_match:
            current["blog"] = blog_match.group(1).strip()
    return entries


def new_blogwatcher_check_blog_exists(env: MacOSEnv, blog_name: str) -> bool:
    """
    Check whether a tracked blog with exact name exists in `blogwatcher blogs` output.
    """
    output = _run_blogwatcher(env, "blogs")
    for line in output.splitlines():
        if line.strip() == blog_name:
            return True
    return False


def new_blogwatcher_check_blog_absent(env: MacOSEnv, blog_name: str) -> bool:
    """
    Check whether a tracked blog with exact name is absent.
    """
    return not new_blogwatcher_check_blog_exists(env, blog_name)


def new_blogwatcher_check_file_contains_all_blog_names(
    env: MacOSEnv, output_file: str
) -> bool:
    """
    Check whether output file contains all tracked blog names.
    """
    blogs_output = _run_blogwatcher(env, "blogs")
    names = _parse_blog_names_from_blogs_output(blogs_output)
    if not names:
        return False

    file_content = _read_remote_file(env, output_file)
    if file_content is None:
        return False

    return all(name in file_content for name in names)


def new_blogwatcher_check_articles_not_empty(env: MacOSEnv) -> bool:
    """
    Check whether `blogwatcher articles` shows at least one article-like line.
    """
    output = _run_blogwatcher(env, "articles")
    return _has_article_like_lines(output)


def new_blogwatcher_check_scan_success_for_blog(
    env: MacOSEnv, blog_name: str
) -> bool:
    """
    Check whether a specific tracked blog has been scanned successfully.
    This evaluator is read-only: it does not execute `scan` itself.
    """
    output = _run_blogwatcher(env, "blogs")

    lines = output.splitlines()
    start_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == blog_name:
            start_idx = i
            break
    if start_idx == -1:
        return False

    block: list[str] = []
    for line in lines[start_idx + 1 :]:
        if line.startswith("  ") and not line.startswith("    "):
            break
        block.append(line.strip())

    has_last_scanned = False
    for line in block:
        lowered = line.lower()
        if lowered.startswith("last scanned:"):
            has_last_scanned = True
            # Some tools show "never" before first scan.
            if "never" in lowered:
                return False
            return True

    return has_last_scanned


def new_blogwatcher_check_file_contains_all_article_titles(
    env: MacOSEnv, output_file: str
) -> bool:
    """
    Check whether output file contains all current unread article titles.
    """
    articles_output = _run_blogwatcher(env, "articles")
    file_content = _read_remote_file(env, output_file)
    if file_content is None:
        return False

    titles = _parse_article_titles_from_articles_output(articles_output)
    if not titles:
        return "No unread articles" in file_content

    return all(title in file_content for title in titles)


def new_blogwatcher_check_article_marked_read(
    env: MacOSEnv, article_id: int
) -> bool:
    """
    Check whether the specified article ID is marked as read in all articles.
    """
    output = _run_blogwatcher(env, "articles --all")
    status_by_id = _parse_article_status_by_id(output)
    status = status_by_id.get(int(article_id))
    return status == "read"


def new_blogwatcher_check_no_unread_articles(env: MacOSEnv) -> bool:
    """
    Check whether there are no unread articles.
    """
    output = _run_blogwatcher(env, "articles")
    if "No unread articles" in output:
        return True
    return len(_parse_article_titles_from_articles_output(output)) == 0


def new_blogwatcher_check_blog_has_read_article(
    env: MacOSEnv, blog_name: str
) -> bool:
    """
    Check whether there is at least one read article for the specified blog.
    """
    output = _run_blogwatcher(env, "articles --all")
    entries = _parse_articles_all_entries(output)
    blog_entries = [e for e in entries if e.get("blog") == blog_name]
    if not blog_entries:
        return False
    return any(e.get("status") == "read" for e in blog_entries)


def new_blogwatcher_check_blog_has_no_unread_articles(
    env: MacOSEnv, blog_name: str
) -> bool:
    """
    Check whether the specified blog has at least one article and none unread.
    """
    output = _run_blogwatcher(env, "articles --all")
    entries = _parse_articles_all_entries(output)
    blog_entries = [e for e in entries if e.get("blog") == blog_name]
    if not blog_entries:
        return False
    return all(e.get("status") == "read" for e in blog_entries)


def new_blogwatcher_check_article_title_is_read(
    env: MacOSEnv, blog_name: str, article_title: str
) -> bool:
    """
    Check whether the specified article title under the blog is marked read.
    """
    output = _run_blogwatcher(env, "articles --all")
    entries = _parse_articles_all_entries(output)
    for entry in entries:
        if entry.get("blog") == blog_name and entry.get("title") == article_title:
            return entry.get("status") == "read"
    return False
