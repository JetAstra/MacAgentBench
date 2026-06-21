from typing import List, Union


def find_str(value: str, keyword: str) -> bool:
    """
    Checks if the keyword is a substring of the given value.

    :param value: The full string to search within.
    :param keyword: The substring to look for.
    :return: True if keyword exists in value, else False.
    """
    return keyword in value


def find_str_in_list(
    value: Union[str, List[str]], keyword: Union[str, List[str]]
) -> bool:
    """
    Checks if any item in `value` contains the keyword(s).

    - If `value` is a str, treat it as a single-item list.
    - If `keyword` is str: return True if any item in `value` contains it.
    - If `keyword` is list[str]: return True if any item in `value` contains ALL strings in `keyword`.

    :param value: A string or list of strings to search within.
    :param keyword: A string or list of strings to search for.
    :return: True if matching condition is met, False otherwise.
    """
    if isinstance(value, str):
        value = [value]

    if isinstance(keyword, str):
        return any(keyword in v for v in value)
    elif isinstance(keyword, list):
        return any(all(k in v for k in keyword) for v in value)
    else:
        raise TypeError("Keyword must be a string or a list of strings")


def find_str_in_list_ci(value: List[str], keyword: Union[str, List[str]]) -> bool:
    """
    Case-insensitive version of find_str_in_list:
    Checks if any item in `value` contains the keyword(s), ignoring case.

    - If keyword is str: return True if any item in value contains it (case-insensitive).
    - If keyword is list[str]: return True if any item in value contains ALL strings in keyword (case-insensitive).

    :param value: List of strings to search within.
    :param keyword: A string or list of strings to search for.
    :return: True if matching condition is met, False otherwise.
    """
    lowered_value = [v.lower() for v in value]

    if isinstance(keyword, str):
        keyword_lower = keyword.lower()
        return any(keyword_lower in v for v in lowered_value)
    elif isinstance(keyword, list):
        keyword_lower_list = [k.lower() for k in keyword]
        return any(all(k in v for k in keyword_lower_list) for v in lowered_value)
    else:
        raise TypeError("Keyword must be a string or a list of strings")


def find_dict(dict_list: list[dict], target: dict) -> bool:
    """
    Checks if the target dictionary is a subset of any dictionary in the list.

    :param target: The key-value pairs to match.
    :param dict_list: The list of dictionaries to search within.
    :return: True if any dictionary in the list contains all items in target, else False.
    """
    for d in dict_list:
        if all(item in d.items() for item in target.items()):
            return True
    return False


def exact_match(value: str, expected: str) -> bool:
    """
    Checks if the value exactly matches the expected string.

    :param value: Actual value.
    :param expected: Expected value to match against.
    :return: True if exactly equal, else False.
    """
    return value == expected


def dict_equal(value: dict, expected: dict) -> bool:
    """
    Check if two dictionaries are exactly equal.

    :param value: The actual dictionary.
    :param expected: The expected dictionary.
    :return: True if both dictionaries are equal, False otherwise.
    """
    if not isinstance(value, dict) or not isinstance(expected, dict):
        return False
    return value == expected


def is_true(value) -> bool:
    """
    Checks if the value is explicitly True (boolean type).

    :param value: Value to evaluate.
    :return: True if value is True, else False.
    """
    return value is True


def is_false(value) -> bool:
    """
    Checks if the value is explicitly False (boolean type).

    :param value: Value to evaluate.
    :return: True if value is False, else False.
    """
    return value is False


def check_list_length(lst: list, op: str, number: int) -> bool:
    """
    Compares the length of a list against a given number using an operator.

    :param lst: The list to evaluate.
    :param op: A comparison operator string: ">", "<", "==", ">=", "<=", "!=".
    :param number: The number to compare against.
    :return: True if the comparison holds, False otherwise.
    """
    length = len(lst)
    if op == ">":
        return length > number
    elif op == "<":
        return length < number
    elif op == "==":
        return length == number
    elif op == ">=":
        return length >= number
    elif op == "<=":
        return length <= number
    elif op == "!=":
        return length != number
    else:
        raise ValueError(f"Unsupported operator: {op}")


def compare_numbers(a: float, op: str, b: float) -> bool:
    """
    Compares two numbers using a specified operator.

    :param a: The first number.
    :param op: A comparison operator string: ">", "<", "==", ">=", "<=", "!=".
    :param b: The second number.
    :return: True if the comparison is valid, False otherwise.
    """
    if op == ">":
        return a > b
    elif op == "<":
        return a < b
    elif op == "==":
        return a == b
    elif op == ">=":
        return a >= b
    elif op == "<=":
        return a <= b
    elif op == "!=":
        return a != b
    else:
        raise ValueError(f"Unsupported operator: {op}")


def contains_element(lst: list, element: str) -> bool:
    """
    Checks if a specific element exists in the list.

    :param lst: The list to search in.
    :param element: The element to look for.
    :return: True if element exists in the list, False otherwise.
    """
    return element in lst


def contains_all_elements(lst: list, elements: list) -> bool:
    """
    Checks if all elements in `elements` exist in the list.

    :param lst: The list to search in.
    :param elements: The list of elements to look for.
    :return: True if all elements exist in the list, False otherwise.
    """
    return all(e in lst for e in elements)


def check_list_length_and_contains_element(
    lst: list, op: str, number: int, element: str
):
    return check_list_length(lst, op, number) and contains_element(lst, element)

def check_element_at_index(
    lst: list, idx: int, element: str
) -> bool:
    if len(lst) > idx:
        return exact_match(lst[idx], element)
    else:
        raise ValueError(f"Invalid idx: {idx}")


# ====================================================================== #
# Fine-grained metrics: return float in [0, 1] instead of bool
# ====================================================================== #


def is_non_empty(value) -> bool:
    """
    Returns True if value has any content, False if empty.

    Handles strings, lists, tuples, dicts, and None:
    - ``""`` → False
    - ``[]`` → False
    - ``None`` → False
    - ``"hello"`` → True
    - ``["item"]`` → True

    Use this instead of ``ratio_match([""])`` for "has any content" checks,
    because ``ratio_match([""])`` incorrectly matches empty strings.
    """
    if value is None:
        return False
    if isinstance(value, (str, list, tuple, dict)):
        return len(value) > 0
    return bool(value)


def ratio_match(value, expected) -> float:
    """
    Fraction of items in ``expected`` that appear in ``value``.

    Behaviour:
    - ``expected`` is treated as a list (a single non-list value is wrapped).
    - If ``value`` is a string, each expected item is matched as a substring.
    - If ``value`` is a list/tuple/set, each expected item is matched as
      either an exact element or a substring of any element.

    Returns 0.0 for unsupported value types, 1.0 if ``expected`` is empty.

    This is the float-valued counterpart to ``find_str_in_list`` /
    ``contains_all_elements`` and is the primary tool for assigning
    partial credit to "did the agent collect N of the expected items"
    style checkpoints.
    """
    if expected is None:
        return 1.0
    if not isinstance(expected, (list, tuple)):
        expected = [expected]
    if not expected:
        return 1.0

    if isinstance(value, str):
        hits = sum(1 for e in expected if str(e) in value)
    elif isinstance(value, (list, tuple, set)):
        def _present(e) -> bool:
            es = str(e)
            for v in value:
                vs = str(v)
                if es == vs or es in vs:
                    return True
            return False

        hits = sum(1 for e in expected if _present(e))
    else:
        return 0.0

    return hits / len(expected)


def strip_accents(s: str) -> str:
    """
    Strip Unicode combining marks (accents) from a string.

    ``"Bogotá"`` → ``"Bogota"``, ``"Schröder"`` → ``"Schroder"``,
    ``"naïve"`` → ``"naive"``.  Case is preserved.

    This is a shared utility used by :func:`exact_match_normalized`
    and ``finder_check_file_exists_normalized``.
    """
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s))
        if unicodedata.category(c) != "Mn"
    )


def exact_match_normalized(value: str, expected: str) -> bool:
    """
    Accent-insensitive exact match.

    Strips Unicode combining marks (accents) from both sides before
    comparing, so ``"Bogotá"`` matches ``"Bogota"``. Case-sensitive
    (use :func:`find_str_in_list_ci` when case-insensitivity is also
    needed).

    Added to fix clock_multi_3_1 where macOS returns ``"Bogotá"``
    (with accent) but the task expected ``"Bogota"`` (without).
    """
    return strip_accents(value) == strip_accents(expected)


def dict_match_ratio(value, expected) -> float:
    """
    Fraction of (key, value) pairs in ``expected`` that match in ``value``.

    Both arguments must be dicts. For each key ``k`` in ``expected``,
    a "hit" is counted iff ``k in value`` and ``value[k] == expected[k]``.

    Returns 1.0 if ``expected`` is empty, 0.0 if either argument is not a dict.

    This is the float-valued counterpart to ``dict_equal`` and is used
    for "did the agent set N of the expected attributes" style checks
    (e.g. Siri ``{"enabled": True, "voice": "American (Voice 4)"}``).
    """
    if not isinstance(value, dict) or not isinstance(expected, dict):
        return 0.0
    if not expected:
        return 1.0
    hits = sum(1 for k, v in expected.items() if k in value and value[k] == v)
    return hits / len(expected)