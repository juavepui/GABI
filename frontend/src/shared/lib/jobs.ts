/** Spanish names of the local job kinds and states, shared by Administración and the header indicator. */
export const JOB_NAMES: Record<string, string> = {
  refresh: 'Actualizar datos del mercado',
  symbols: 'Descargar símbolos indicados',
  quality: 'Auditar cobertura local',
  backtest: 'Backtest exploratorio',
  maintenance: 'Mantenimiento prospectivo',
  tiingo: 'Descarga histórica Tiingo',
  sim_result: 'Resultado de cartera simulada',
  sim_compare: 'Comparar carteras simuladas',
  sim_prices: 'Precios de cartera simulada',
  decision_plan: 'Generar decisiones de cartera',
  filing_check: 'Comprobar filings SEC',
  historical_ranking: 'Ranking histórico',
  factor_analysis: 'Factor Lab',
  estimate_analysis: 'Análisis de estimaciones',
  backtest_v1: 'Backtest V1',
  backtest_v2: 'Backtest V2',
  backtest_register: 'Registrar backtest en Research Lab',
  backtest_factors: 'Contraste Fama-French',
  prepare_history: 'Preparar datos históricos',
  historical_outcomes: 'Resultado posterior del ranking',
  experiment_pbo: 'PBO de experimentos',
  experiment_bootstrap: 'Bootstrap por bloques',
  live_forward_report: 'Informe del registro prospectivo',
  blind_rebalance: 'Rebalanceo de validación ciega',
  blind_performance: 'Rendimiento de validación ciega',
  blind_export: 'Exportar validación ciega',
  portfolio_lab: 'Portfolio Lab',
  company_sync: 'Sincronizar datos de una empresa',
  data_update: 'Actualizar datos (Yahoo y SEC)',
  data_health: 'Comprobar calidad de los datos',
};

export const JOB_STATES: Record<string, string> = {
  queued: 'En espera',
  running: 'En curso',
  succeeded: 'Completado',
  failed: 'Fallido',
  cancelled: 'Cancelado',
};

export const ACTIVE_JOB_STATES = ['queued', 'running'];

export const jobName = (kind: string) => JOB_NAMES[kind] ?? kind;
