"""Conservative SEC thread pool; the source retry port owns shared pacing."""

from concurrent.futures import ThreadPoolExecutor, as_completed


def run(tasks, operation, *, max_workers: int = 4):
    if not 1 <= max_workers <= 4:
        raise ValueError("SEC batch workers must be between 1 and 4")
    if not tasks:
        return
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(operation, symbol, cik): symbol for symbol, cik in tasks}
        for future in as_completed(futures):
            error = None
            try:
                future.result()
            except Exception as exc:
                error = exc
            yield futures[future], error
