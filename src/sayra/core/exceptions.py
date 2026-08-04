class SayraError(Exception):
    status_code = 500
    code = "sayra_error"


class NotFoundError(SayraError):
    status_code = 404
    code = "not_found"


class ConflictError(SayraError):
    status_code = 409
    code = "conflict"


class BadRequestError(SayraError):
    status_code = 400
    code = "bad_request"


class PayloadTooLargeError(SayraError):
    status_code = 413
    code = "payload_too_large"


class InvalidStateError(ConflictError):
    code = "invalid_state"


class ProviderError(SayraError):
    status_code = 502
    code = "provider_error"


class StorageError(SayraError):
    status_code = 502
    code = "storage_error"
