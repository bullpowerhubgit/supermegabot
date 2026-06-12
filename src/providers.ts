import type { ApiError } from './errors.js';
import { normalizeError } from './normalize.js';

type HttpLikeError = {
  status?: number;
  message?: string;
  headers?: Record<string, string | number | undefined> | undefined;
  data?: any;
};

function asHttpLikeError(error: unknown): HttpLikeError {
  if (typeof error === 'object' && error !== null) {
    return error as HttpLikeError;
  }

  return {
    status: 500,
    message: typeof error === 'string' ? error : 'Unknown error',
    data: undefined,
    headers: undefined,
  } satisfies HttpLikeError;
}

export function normalizeShopifyError(error: unknown): ApiError {
  const e = asHttpLikeError(error);
  const status = e.status ?? 500;
  const message =
    e.data?.errors
      ? JSON.stringify(e.data.errors)
      : e.message ?? 'Shopify API error';

  const requestId =
    typeof e.headers?.['x-request-id'] === 'string'
      ? e.headers['x-request-id']
      : undefined;

  return normalizeError({
    provider: 'shopify',
    status,
    message,
    requestId,
    raw: e,
  });
}

export function normalizeMetaError(error: unknown): ApiError {
  const e = asHttpLikeError(error);
  const status = e.status ?? 500;
  const metaError = e.data?.error;

  const isRateLimit = metaError?.code === 613 || status === 429;

  if (isRateLimit) {
    return {
      provider: 'meta',
      status: 429,
      code: 'RATE_LIMIT',
      message: metaError?.message ?? e.message ?? 'Meta API rate limit',
      retryable: true,
      category: 'rate_limit',
      raw: e,
    };
  }

  const codeParts = [
    metaError?.code != null ? String(metaError.code) : null,
    metaError?.error_subcode != null ? String(metaError.error_subcode) : null,
  ].filter(Boolean);

  const code = codeParts.length ? `META_${codeParts.join('_')}` : `HTTP_${status}`;

  return normalizeError({
    provider: 'meta',
    status,
    code,
    message: metaError?.message ?? e.message ?? 'Meta API error',
    raw: e,
  });
}

export function normalizeTwilioError(error: unknown): ApiError {
  const e = asHttpLikeError(error);
  const status = e.status ?? 500;
  const twilioCode = e.data?.code != null ? String(e.data.code) : undefined;
  const message =
    e.data?.message ??
    e.message ??
    'Twilio API error';

  return normalizeError({
    provider: 'twilio',
    status,
    code: twilioCode ? `TWILIO_${twilioCode}` : undefined,
    message,
    raw: e,
  });
}
