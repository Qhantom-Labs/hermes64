"""Contract errors are domain failures, not arbitrary execution failures."""


class SpecError(ValueError):
    pass


class StateError(ValueError):
    pass
