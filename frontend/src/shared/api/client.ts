import type {
  CompanyResponse,
  RankingResponse,
  RankingApiV1RankingGetData,
} from './generated/types.gen';

export type RankingQuery = NonNullable<RankingApiV1RankingGetData['query']>;
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}
async function get<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = body && typeof body === 'object' && 'error' in body ? body.error : null;
    const code =
      detail && typeof detail === 'object' && 'code' in detail && typeof detail.code === 'string'
        ? detail.code
        : 'HTTP_ERROR';
    // The API sanitizes its errors. Do not display unexpected proxy/HTML bodies.
    const message =
      detail &&
      typeof detail === 'object' &&
      'message' in detail &&
      typeof detail.message === 'string'
        ? detail.message
        : 'No se ha podido consultar la API local.';
    throw new ApiError(response.status, code, message);
  }
  return response.json() as Promise<T>;
}
export function getRanking(query: RankingQuery, signal?: AbortSignal): Promise<RankingResponse> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach((item) => params.append(key, item));
    else if (value != null) params.set(key, String(value));
  });
  return get('/api/v1/ranking?' + params.toString(), signal);
}
export function getCompany(
  symbol: string,
  bars: number,
  signal?: AbortSignal,
): Promise<CompanyResponse> {
  return get('/api/v1/companies/' + encodeURIComponent(symbol) + '?bars=' + bars, signal);
}
