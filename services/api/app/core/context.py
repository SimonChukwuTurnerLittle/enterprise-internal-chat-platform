from contextvars import ContextVar

# Correlation id of the current HTTP request; set by RequestContextMiddleware.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
