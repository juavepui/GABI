import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { cancelJob, createJob, getJob } from '@/shared/api/client';
import type { CreateJobRequest } from '@/shared/api/generated/types.gen';

export function useJob(prefix: string) {
  const [jobId, setJobId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: (body: Omit<CreateJobRequest, 'idempotency_key'>) =>
      createJob({ ...body, idempotency_key: prefix + ':' + crypto.randomUUID() }),
    onSuccess: (job) => setJobId(job.id),
  });
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: ({ signal }) => getJob(jobId!, signal),
    enabled: jobId != null,
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
  const cancel = useMutation({ mutationFn: () => cancelJob(jobId!) });
  return { jobId, setJobId, start, job, cancel };
}
