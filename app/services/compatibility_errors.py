class CompatibilityProviderError(Exception):
    pass


class CompatibilityProviderConfigurationError(CompatibilityProviderError):
    pass


class CompatibilityProviderRequestError(CompatibilityProviderError):
    pass


class CompatibilityProviderTimeoutError(CompatibilityProviderRequestError):
    pass


class CompatibilityProviderResponseError(CompatibilityProviderError):
    pass
