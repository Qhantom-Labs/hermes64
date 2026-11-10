"""STORY 1.2 data contracts. Nothing in authored data loads executable code."""


def enabled(value):
    return isinstance(value, dict) and value.get('contract_version') == '1.2.0'
