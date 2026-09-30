import type {
  CompanyResponse,
  RankingResponse,
  RankingApiV1RankingGetData,
  CreateJobRequest,
  JobListResponse,
  JobResponse,
  LocalSettingsResponse,
  ModelResponse,
  WeightsRequest,
  PlanRequest,
  PlanResponse,
  JournalCreate,
  JournalEntry,
  JournalList,
  JournalReview,
  ComparisonResponse,
  MacroResponse,
  SaveSnapshot,
  Snapshot,
  SnapshotList,
  CompareSignals,
  SignalEventList,
  EarningsList,
  FilingCheckSaved,
  SimulationCreate,
  SimulationPortfolio,
  SimulationList,
  SimulationTrade,
  SimulationTradeCreate,
  SimulationTrades,
  SimulationResult,
  UndoResult,
  DecisionList,
  DecisionJobSave,
  DecisionRename,
  SavedDecision,
  DecisionProgress,
  ResearchOverview,
  SearchTrials,
  HistoricalPreview,
  BlindStatuses,
  FactorPreview,
  ModeRequest,
  PublishedFactors,
  EstimateCaptureStatus,
  EstimateAnalysisPreview,
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
  return request<T>(url, { signal, headers: { Accept: 'application/json' } });
}
async function request<T>(url: string, options: RequestInit): Promise<T> {
  const response = await fetch(url, options);
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
export function getJobs(signal?: AbortSignal): Promise<JobListResponse> {
  return get('/api/v1/jobs', signal);
}
export function getResearchOverview(signal?: AbortSignal): Promise<ResearchOverview> {
  return get('/api/v1/research/overview', signal);
}
export function getResearchTrials(
  offset: number,
  family: string,
  signal?: AbortSignal,
): Promise<SearchTrials> {
  const params = new URLSearchParams({ offset: String(offset), limit: '25' });
  if (family) params.set('family', family);
  return get('/api/v1/research/trials?' + params.toString(), signal);
}
export function getHistoricalPreview(id: string, signal?: AbortSignal): Promise<HistoricalPreview> {
  return get('/api/v1/research/historical/' + encodeURIComponent(id), signal);
}
export function getBlindValidations(signal?: AbortSignal): Promise<BlindStatuses> {
  return get('/api/v1/research/blind-validations', signal);
}
export function getFactorPreview(id: string, signal?: AbortSignal): Promise<FactorPreview> {
  return get('/api/v1/research/factors/' + encodeURIComponent(id), signal);
}
export function getPublishedFactors(signal?: AbortSignal): Promise<PublishedFactors> {
  return get('/api/v1/research/published-factors', signal);
}
export function getEstimateCaptures(signal?: AbortSignal): Promise<EstimateCaptureStatus> {
  return get('/api/v1/research/estimate-captures', signal);
}
export function getEstimateAnalysisPreview(
  id: string,
  signal?: AbortSignal,
): Promise<EstimateAnalysisPreview> {
  return get('/api/v1/research/estimate-analysis/' + encodeURIComponent(id), signal);
}
export function getJob(id: string, signal?: AbortSignal): Promise<JobResponse> {
  return get('/api/v1/jobs/' + encodeURIComponent(id), signal);
}
export function getLocalSettings(signal?: AbortSignal): Promise<LocalSettingsResponse> {
  return get('/api/v1/administration/settings', signal);
}
export function getModel(signal?: AbortSignal): Promise<ModelResponse> {
  return get('/api/v1/model', signal);
}
export function setMode(mode: ModeRequest['mode']): Promise<ModelResponse> {
  return request('/api/v1/administration/mode', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
}
export function saveWeights(body: WeightsRequest): Promise<ModelResponse> {
  return request('/api/v1/administration/weights', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
export function createJob(body: CreateJobRequest): Promise<JobResponse> {
  return request('/api/v1/jobs', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
export function cancelJob(id: string): Promise<JobResponse> {
  return request('/api/v1/jobs/' + encodeURIComponent(id) + '/cancel', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: '{}',
  });
}
export function getJobResult(id: string, signal?: AbortSignal): Promise<unknown> {
  return get('/api/v1/jobs/' + encodeURIComponent(id) + '/result', signal);
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

export function getPortfolioPlan(body: PlanRequest, signal?: AbortSignal): Promise<PlanResponse> {
  return request('/api/v1/portfolio/plan', {
    method: 'POST',
    signal,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function getJournal(offset = 0, signal?: AbortSignal): Promise<JournalList> {
  return get('/api/v1/portfolio/journal?limit=50&offset=' + offset, signal);
}
export function createJournal(body: JournalCreate): Promise<JournalEntry> {
  return request('/api/v1/portfolio/journal', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
export function reviewJournal(id: number, body: JournalReview): Promise<JournalEntry> {
  return request('/api/v1/portfolio/journal/' + id + '/review', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
export async function deleteJournal(id: number): Promise<void> {
  const response = await fetch('/api/v1/portfolio/journal/' + id + '/delete', { method: 'POST' });
  if (!response.ok)
    throw new ApiError(response.status, 'journal_delete_failed', 'No se pudo eliminar la entrada.');
}

export function getComparison(
  symbols: string[],
  signal?: AbortSignal,
): Promise<ComparisonResponse> {
  const params = new URLSearchParams();
  symbols.forEach((symbol) => params.append('symbols', symbol));
  return get('/api/v1/comparison?' + params.toString(), signal);
}

export function getMacro(signal?: AbortSignal): Promise<MacroResponse> {
  return get('/api/v1/market/macro', signal);
}

export function getSnapshots(signal?: AbortSignal): Promise<SnapshotList> {
  return get('/api/v1/market/snapshots', signal);
}
export function saveSnapshot(body: SaveSnapshot): Promise<Snapshot> {
  return request('/api/v1/market/snapshots', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
export function getSignals(signal?: AbortSignal): Promise<SignalEventList> {
  return get('/api/v1/market/signals', signal);
}
export function compareSignals(body: CompareSignals): Promise<SignalEventList> {
  return request('/api/v1/market/signals/compare', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
export function getSnapshotEarnings(id: number, signal?: AbortSignal): Promise<EarningsList> {
  return get('/api/v1/market/snapshots/' + id + '/earnings', signal);
}
export function recordFilingCheck(jobId: string): Promise<FilingCheckSaved> {
  return request('/api/v1/market/signals/filings/record', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId }),
  });
}

export function getSimulations(signal?: AbortSignal): Promise<SimulationList> {
  return get('/api/v1/portfolio/simulations', signal);
}
export function createSimulation(body: SimulationCreate): Promise<SimulationPortfolio> {
  return request('/api/v1/portfolio/simulations', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
export function getSimulationTrades(id: number, signal?: AbortSignal): Promise<SimulationTrades> {
  return get('/api/v1/portfolio/simulations/' + id + '/trades', signal);
}
export function createSimulationTrade(
  id: number,
  body: SimulationTradeCreate,
): Promise<SimulationTrade> {
  return request('/api/v1/portfolio/simulations/' + id + '/trades', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
export function undoSimulationTrade(id: number): Promise<UndoResult> {
  return request('/api/v1/portfolio/simulations/' + id + '/undo', { method: 'POST' });
}
export function getSimulationResult(id: number, signal?: AbortSignal): Promise<SimulationResult> {
  return get('/api/v1/portfolio/simulations/' + id + '/result', signal);
}

export function getDecisions(signal?: AbortSignal): Promise<DecisionList> {
  return get('/api/v1/portfolio/decisions', signal);
}
export function getDecision(id: number, signal?: AbortSignal): Promise<SavedDecision> {
  return get('/api/v1/portfolio/decisions/' + id, signal);
}
export function getDecisionProgress(id: number, signal?: AbortSignal): Promise<DecisionProgress> {
  return get('/api/v1/portfolio/decisions/' + id + '/progress', signal);
}
export function saveDecision(body: DecisionJobSave): Promise<SavedDecision> {
  return request('/api/v1/portfolio/decisions', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
export function renameDecision(id: number, body: DecisionRename): Promise<SavedDecision> {
  return request('/api/v1/portfolio/decisions/' + id + '/rename', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
export function deleteDecision(id: number): Promise<{ deleted: boolean }> {
  return request('/api/v1/portfolio/decisions/' + id + '/delete', { method: 'POST' });
}
