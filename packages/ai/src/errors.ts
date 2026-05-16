// Errors thrown by the LiteLLM client. Consumers handle these explicitly so
// retries, fallbacks, and 5xx surfacing don't get swallowed.

export class LiteLLMError extends Error {
  override readonly name = "LiteLLMError";
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
  ) {
    super(message);
  }
}

export class LiteLLMNetworkError extends Error {
  override readonly name = "LiteLLMNetworkError";
  constructor(message: string, readonly cause: unknown) {
    super(message);
  }
}

/** JSON-mode response failed to parse against the caller-supplied schema. */
export class LiteLLMSchemaError extends Error {
  override readonly name = "LiteLLMSchemaError";
  constructor(
    message: string,
    readonly raw: string,
    readonly cause: unknown,
  ) {
    super(message);
  }
}
