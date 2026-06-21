import paramiko
from controllers.env import MacOSEnv
from utils.logger import ProjectLogger
from pathlib import Path
import json
import time
from bs4 import BeautifulSoup

script_dir = Path(__file__).resolve().parent.parent

logger = ProjectLogger(log_dir=script_dir / "logs")


def safari_get_window_count(env: MacOSEnv) -> int:
    """
    Get the number of open Safari windows via AppleScript.
    Returns the count as an integer, or -1 if an error occurred.
    """
    apple_script = """
    tell application "Safari"
        return count of windows
    end tell
    """
    env.connect_ssh()
    try:
        stdout, stderr = env.run_command(f"osascript -e '{apple_script}'")
        output = stdout.read().decode().strip()
        return int(output)
    except Exception as e:
        logger.error(f"Failed to get Safari window count: {e}")
        return -1


def safari_get_url(env: MacOSEnv) -> str:
    """
    Get the URL of the front-most Safari tab.

    This function uses AppleScript executed remotely via SSH to check
    if Safari has at least one open window, and if so, returns the URL
    of the front document (active tab). If no window exists, it returns
    a specific error string.

    :param env: MacOSEnv instance containing SSH connection to macOS
    :return: The current URL string or "SafariWindowsNotFindError" if no window is open
    """
    apple_script = """
    tell application "Safari"
        if (count of windows) > 0 then
            set currentURL to URL of front document
            return currentURL
        else
            return "SafariWindowsNotFindError"
        end if
    end tell
    """
    env.connect_ssh()
    try:
        stdout, stderr = env.run_command(f"osascript -e '{apple_script}'")
        if isinstance(stdout, str):
            return stdout.strip()
        return stdout.read().decode().strip()
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        return "SafariScriptExecutionError"


def safari_get_default_property(env: MacOSEnv, property_name: str) -> str:
    """
    Get the value of a specific Safari default property from com.apple.Safari.

    :param env: MacOSEnv instance for SSH access
    :param property_name: Property key to retrieve from Safari's preferences
    :return: The value of the property as a string, or None if not found
    """
    env.connect_ssh()
    try:
        command = f"defaults read com.apple.Safari {property_name}"
        stdout, stderr = env.run_command(command)
        if isinstance(stdout, str):
            return stdout.strip()
        return stdout.read().decode().strip()
    except Exception as e:
        logger.error(f"Failed to read '{property_name}': {e}")
        return None


def safari_get_startpage_section_enabled(env: MacOSEnv, section_id: str) -> str:
    """
    Check whether a specific Start Page section is enabled in Safari.
    Reads the StartPageSections binary plist from com.apple.Safari and
    returns "1" if enabled, "0" if disabled.

    :param env: MacOSEnv instance for SSH access
    :param section_id: Section identifier, e.g. "favoritesItemIdentifier"
    :return: "1" if enabled, "0" if disabled, or None on error
    """
    env.connect_ssh()
    try:
        script = f'''python3 -c "
import plistlib, subprocess
result = subprocess.run(['defaults', 'export', 'com.apple.Safari', '-'], capture_output=True)
plist = plistlib.loads(result.stdout)
sections = plist.get('StartPageSections')
if sections and isinstance(sections, bytes):
    inner = plistlib.loads(sections)
    objects = inner.get('\\$objects', [])
    for i, obj in enumerate(objects):
        if obj == '{section_id}' and i > 0:
            prev = objects[i-1]
            if isinstance(prev, dict):
                print('1' if prev.get('IsEnabled', False) else '0')
                exit()
print('0')
"'''
        stdout, stderr = env.run_command(script)
        if isinstance(stdout, str):
            return stdout.strip()
        return stdout.read().decode().strip()
    except Exception as e:
        logger.error(f"Failed to read StartPageSections for '{section_id}': {e}")
        return None


def safari_get_all_bookmark_folders(env: MacOSEnv) -> list[str]:
    """
    Get all Safari bookmark folder names from Bookmarks.plist.
    Uses plistlib to parse the binary plist directly, avoiding plutil JSON
    conversion issues with date fields in newer macOS versions.
    """
    env.connect_ssh()
    try:
        command = '''python3 -c "
import plistlib, os
path = os.path.expanduser('~/Library/Safari/Bookmarks.plist')
with open(path, 'rb') as f:
    plist = plistlib.load(f)
for child in plist.get('Children', []):
    if child.get('Children') is not None and child.get('Title'):
        print(child['Title'])
"'''
        stdout, _ = env.run_command(command)
        if isinstance(stdout, str):
            output = stdout.strip()
        else:
            output = stdout.read().decode().strip()
        return output.splitlines() if output else []
    except Exception as e:
        logger.error(f"Failed to get bookmark folders: {e}")
        return []


def safari_get_bookmarks_in_folder(env: MacOSEnv, folder_name: str) -> list[str]:
    """
    Get all bookmark URLs inside a specific Safari bookmark folder.
    Uses plistlib to parse the binary plist directly, avoiding plutil JSON
    conversion issues with date fields in newer macOS versions.
    """
    env.connect_ssh()
    try:
        command = f'''python3 -c "
import plistlib, os
path = os.path.expanduser('~/Library/Safari/Bookmarks.plist')
with open(path, 'rb') as f:
    plist = plistlib.load(f)
for child in plist.get('Children', []):
    if child.get('Title') == '{folder_name}' and child.get('WebBookmarkType') == 'WebBookmarkTypeList':
        for item in child.get('Children', []):
            url = item.get('URLString', '')
            if url:
                print(url)
        break
"'''
        stdout, _ = env.run_command(command)
        if isinstance(stdout, str):
            output = stdout.strip()
        else:
            output = stdout.read().decode().strip()
        return output.splitlines() if output else []
    except Exception as e:
        logger.error(f"Failed to get bookmarks in folder '{folder_name}': {e}")
        return []


# def safari_get_steam_cart_summary(env: MacOSEnv) -> dict:
#     """
#     Get number of items in Steam cart and whether any item exceeds $50.

#     :param env: MacOSEnv instance
#     :return: dict with keys 'count' (int) and 'has_expensive' (bool)
#     """
#     js = """const items = Array.from(document.querySelectorAll('div[class*="Panel Focusable"]'));
#     const prices = items.map(item => {
#         const priceText = item.innerText.match(/\\$\\d+(\\.\\d{2})?/);
#         return priceText ? parseFloat(priceText[0].replace('$', '')) : 0;
#     });
#     JSON.stringify({
#         count: prices.length,
#         has_expensive: prices.some(p => p > 10)
#     });
#     """


#     env.connect_ssh()
#     try:
#         stdout, stderr = env.run_command(script)
#         logger.info(stderr)
#         logger.info(stdout)
#         if isinstance(stdout, str):
#             output = stdout.strip()
#         else:
#             output = stdout.read().decode().strip()
#         logger.info(output)
#         return json.loads(output)
#     except Exception as e:
#         logger.error(f"Failed to get Steam cart summary: {e}")
#         return {"count": 0, "has_expensive": False}


# def get_steam_topseller_items(env) -> list[dict]:
#     """
#     Get the Steam top-sellers list from the current Safari page by parsing HTML.

#     Safari must have navigated to: https://store.steampowered.com/search/?filter=topsellers

#     :param env: MacOSEnv instance
#     :return: List of dictionaries with 'title', 'price', and 'release_date'
#     """
#     env.connect_ssh()
#     try:
#         js = "document.documentElement.outerHTML"
#         apple_script = f'tell application "Safari" to do JavaScript "{js}" in document 1'
#         stdout, stderr = env.run_command(f"osascript -e '{apple_script}'")
#         if isinstance(stdout, str):
#             html = stdout.strip()
#         else:
#             html = stdout.read().decode().strip()

#         soup = BeautifulSoup(html, 'html.parser')
#         games = soup.select('a.search_result_row')

#         game_list = []
#         for game in games:
#             try:
#                 title = game.find('span', class_='title').text.strip()
#                 price_elem = game.find('div', class_='discount_final_price')
#                 price = price_elem.text.strip() if price_elem else "N/A"
#                 release_elem = game.find('div', class_='col search_released responsive_secondrow')
#                 release_date = release_elem.text.strip() if release_elem else "N/A"

#                 game_list.append({
#                     'title': title,
#                     'price': price,
#                     'release_date': release_date
#                 })
#             except Exception as e:
#                 continue

#         return game_list

#     except Exception as e:
#         logger.error(f"Failed to get Steam top-seller items: {e}")
#         return []


def safari_check_steam_cart_contains_top_items(env, count: int = 3) -> bool:
    """
    Check whether the top N purchasable (non-free) Steam top-seller games
    appear in the Safari cart.

    :param env: MacOSEnv instance
    :param count: Number of top purchasable games to check (default 3)
    :return: True if all top N purchasable games are in the cart
    """
    env.connect_ssh()

    def get_page_html():
        js = "document.documentElement.outerHTML"
        apple_script = (
            f'tell application "Safari" to do JavaScript "{js}" in document 1'
        )
        stdout, stderr = env.run_command(f"osascript -e '{apple_script}'")
        return (
            stdout.read().decode().strip()
            if not isinstance(stdout, str)
            else stdout.strip()
        )

    # Step 1: Navigate to top sellers
    env.run_command(
        'osascript -e \'tell application "Safari" to open location "https://store.steampowered.com/search/?filter=topsellers"\''
    )
    time.sleep(4)

    # Step 2: Parse top seller titles, skipping free games
    html_top = get_page_html()
    soup_top = BeautifulSoup(html_top, "html.parser")
    games = soup_top.select("a.search_result_row")
    top_titles = []
    for game in games:
        if len(top_titles) >= count:
            break
        try:
            title = game.find("span", class_="title").text.strip()
            price_elem = game.find("div", class_="discount_final_price")
            price_text = price_elem.text.strip() if price_elem else ""
            if not title:
                continue
            if price_text.lower() in ("free", "free to play", ""):
                continue
            top_titles.append(title)
        except:
            continue

    logger.info(f"Top {count} purchasable titles: {top_titles}")
    if len(top_titles) < count:
        logger.warning(f"Could not extract {count} valid purchasable top seller titles.")
        return False

    # Step 3: Navigate to cart
    env.run_command(
        'osascript -e \'tell application "Safari" to open location "https://store.steampowered.com/cart"\''
    )
    time.sleep(4)

    # Step 4: Parse cart page and extract Panel Focusable content
    html_cart = get_page_html()
    soup_cart = BeautifulSoup(html_cart, "html.parser")
    cart_blocks = soup_cart.find_all("div", class_="Panel Focusable")

    # Step 5: Match all titles
    cart_text = " ".join(
        [block.get_text(separator=" ", strip=True) for block in cart_blocks]
    )
    found_all = all(title in cart_text for title in top_titles)
    logger.info(f"Cart contains all top {count} titles: {found_all}")
    return found_all


if __name__ == "__main__":
    # Initialize the environment with default config
    macos_env = MacOSEnv()

    # Connect to Docker container
    macos_env.connect_ssh()

    prop = "ShowFavorites"
    value = safari_check_steam_cart_contains_all_top3_items(macos_env)
    logger.info(value)

    import time

    time.sleep(3)
    macos_env.close_connection()
