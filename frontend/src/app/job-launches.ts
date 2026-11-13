/** Route where this tab queued each job: a job that finishes on that same page needs no toast. */
export const jobLaunches = new Map<string, string>();

export function rememberLaunch(job: unknown) {
  if (typeof job === 'object' && job !== null && 'id' in job && 'kind' in job && 'status' in job) {
    const id = String((job as { id: unknown }).id);
    if (!jobLaunches.has(id)) jobLaunches.set(id, window.location.pathname);
  }
}
